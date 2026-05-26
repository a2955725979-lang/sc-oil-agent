"""Live market/fx provider adapter for yfinance/Yahoo data.

This module returns normalized rows for ``src.fetchers.market_fx``. It does
not emit raw_data_contract_v1 directly; the contract builder remains in
``market_fx.py`` so fixture rows and live rows share the same output path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote


SOURCE_NAME = "Yahoo Finance via yfinance"
SOURCE_LEVEL = "third_party"
URL_ROOT = "https://finance.yahoo.com/quote"
LOOKBACK_DAYS = 10

FIELD_SYMBOLS = {
    "USD_CNY": ("CNY=X", "USDCNY=X"),
    "Brent_close": ("BZ=F",),
    "WTI_close": ("CL=F",),
}


class MarketFxProviderError(RuntimeError):
    """Raised when live market/fx data cannot be fetched without fabrication."""


@dataclass(frozen=True)
class ProviderQuote:
    field_name: str
    value: float
    symbol: str
    actual_data_date: str
    raw_payload: dict[str, Any]
    attempted_symbols: tuple[str, ...]


class YFinanceMarketFxClient:
    """Small yfinance wrapper kept injectable for tests."""

    def history(self, symbol: str, start: str, end: str) -> Any:
        try:
            import yfinance as yf  # type: ignore[import-not-found]
        except ImportError as exc:
            raise MarketFxProviderError("yfinance is not installed; run `pip install -r requirements.txt`") from exc

        ticker = yf.Ticker(symbol)
        return ticker.history(start=start, end=end, interval="1d", auto_adjust=False)


def fetch_market_fx_live_rows(
    report_date: str,
    client: Any | None = None,
) -> dict[str, Any]:
    """Fetch normalized market/fx rows from yfinance-compatible client."""

    final_client = client or YFinanceMarketFxClient()
    errors: list[str] = []
    quotes: dict[str, ProviderQuote] = {}

    for field_name, symbols in FIELD_SYMBOLS.items():
        try:
            quotes[field_name] = _fetch_first_available_symbol(
                field_name=field_name,
                symbols=symbols,
                report_date=report_date,
                client=final_client,
            )
        except MarketFxProviderError as exc:
            errors.append(str(exc))

    if errors:
        raise MarketFxProviderError("; ".join(errors))

    row: dict[str, Any] = {
        "date": report_date,
        "source_name": SOURCE_NAME,
        "source_level": SOURCE_LEVEL,
        "url_or_reference": "https://finance.yahoo.com",
        "is_real_provider": True,
        "field_metadata": {},
    }
    field_metadata = row["field_metadata"]
    for field_name, quote_data in quotes.items():
        row[field_name] = quote_data.value
        row[f"{field_name}_date"] = quote_data.actual_data_date
        fallback_used = quote_data.actual_data_date != report_date
        field_metadata[field_name] = _build_field_metadata(
            field_name=field_name,
            quote_data=quote_data,
            report_date=report_date,
            fallback_used=fallback_used,
        )

    return row


def _fetch_first_available_symbol(
    field_name: str,
    symbols: tuple[str, ...],
    report_date: str,
    client: Any,
) -> ProviderQuote:
    symbol_errors: list[str] = []
    for symbol in symbols:
        try:
            return _fetch_symbol(field_name, symbol, symbols, report_date, client)
        except MarketFxProviderError as exc:
            symbol_errors.append(f"{symbol}: {exc}")

    raise MarketFxProviderError(
        f"{field_name}: no usable yfinance data from {', '.join(symbols)}; "
        + "; ".join(symbol_errors)
    )


def _fetch_symbol(
    field_name: str,
    symbol: str,
    attempted_symbols: tuple[str, ...],
    report_date: str,
    client: Any,
) -> ProviderQuote:
    report_day = _parse_date(report_date)
    start = (report_day - timedelta(days=LOOKBACK_DAYS)).isoformat()
    end = (report_day + timedelta(days=1)).isoformat()
    try:
        history = client.history(symbol=symbol, start=start, end=end)
    except TypeError:
        history = client.history(symbol, start, end)
    except Exception as exc:  # noqa: BLE001 - live provider errors are converted upstream.
        raise MarketFxProviderError(str(exc)) from exc

    rows = _history_rows(history)
    selected = _select_latest_row(rows, report_date)
    if selected is None:
        raise MarketFxProviderError(f"no rows on or before {report_date}")

    value = _to_float(_get_close(selected))
    if value is None:
        raise MarketFxProviderError(f"latest row has no numeric close on {_row_date(selected)}")

    actual_data_date = _row_date(selected)
    if actual_data_date is None:
        raise MarketFxProviderError("latest row has no data date")

    return ProviderQuote(
        field_name=field_name,
        value=value,
        symbol=symbol,
        actual_data_date=actual_data_date,
        raw_payload=_json_safe_dict(selected),
        attempted_symbols=attempted_symbols,
    )


def _build_field_metadata(
    field_name: str,
    quote_data: ProviderQuote,
    report_date: str,
    fallback_used: bool,
) -> dict[str, Any]:
    source_status = "warning" if fallback_used else "pass"
    confidence = "low" if fallback_used else "medium"
    metadata = {
        "date": quote_data.actual_data_date,
        "data_time": quote_data.actual_data_date,
        "source_name": SOURCE_NAME,
        "source_field": quote_data.symbol,
        "source_level": SOURCE_LEVEL,
        "source_status": source_status,
        "confidence": confidence,
        "url_or_reference": f"{URL_ROOT}/{quote(quote_data.symbol, safe='')}",
        "is_real_provider": True,
        "fallback_used": fallback_used,
        "provider_metadata": {
            "provider": "yfinance",
            "provider_family": "Yahoo Finance",
            "symbol": quote_data.symbol,
            "attempted_symbols": list(quote_data.attempted_symbols),
            "raw_field": "Close",
            "provider_limit_note": "free public convenience provider; not official exchange data",
        },
    }
    if fallback_used:
        metadata["original_report_date"] = report_date
        metadata["actual_data_date"] = quote_data.actual_data_date
        metadata["data_alignment_note"] = (
            "Yahoo/yfinance returned the latest available previous trading date "
            "for the requested futures/FX report date."
        )
    return metadata


def _history_rows(history: Any) -> list[dict[str, Any]]:
    if history is None:
        return []
    if isinstance(history, list):
        return [dict(item) for item in history if isinstance(item, dict)]
    if isinstance(history, tuple):
        return [dict(item) for item in history if isinstance(item, dict)]
    if hasattr(history, "empty") and bool(getattr(history, "empty")):
        return []
    if hasattr(history, "to_dict"):
        records = history.to_dict(orient="records")
        index = list(getattr(history, "index", []))
        rows: list[dict[str, Any]] = []
        for position, record in enumerate(records):
            row = dict(record)
            if "Date" not in row and position < len(index):
                row["Date"] = index[position]
            rows.append(row)
        return rows
    return []


def _select_latest_row(rows: list[dict[str, Any]], report_date: str) -> dict[str, Any] | None:
    dated_rows: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        row_date = _row_date(row)
        if row_date is None or row_date > report_date:
            continue
        dated_rows.append((row_date, row))
    if not dated_rows:
        return None
    dated_rows.sort(key=lambda item: item[0])
    return dated_rows[-1][1]


def _row_date(row: dict[str, Any]) -> str | None:
    for key in ("Date", "date", "Datetime", "data_time"):
        cleaned = _clean_date(row.get(key))
        if cleaned:
            return cleaned
    return None


def _get_close(row: dict[str, Any]) -> Any:
    for key in ("Close", "close", "Adj Close", "adj_close"):
        if key in row:
            return row[key]
    return None


def _parse_date(value: str) -> datetime.date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _clean_date(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "date"):
        try:
            return value.date().isoformat()
        except (AttributeError, TypeError, ValueError):
            pass
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _json_safe_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _json_safe_value(value) for key, value in payload.items()}


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if hasattr(value, "item"):
        try:
            return _json_safe_value(value.item())
        except (TypeError, ValueError):
            pass
    return str(value)
