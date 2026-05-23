"""AKShare SC daily market fetcher.

This module fetches INE SC daily futures rows through AKShare and emits the
project's raw_data_contract_v1 structure. Tests inject local rows and never
import or call AKShare.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.base import FetchResult, RawDataRecord  # noqa: E402


SOURCE_NAME = "AKShare"
SOURCE_LEVEL = "third_party"
FETCHER_NAME = "akshare_sc_daily_fetcher"
FETCHER_VERSION = "akshare_sc_daily_v1"
URL_OR_REFERENCE = "https://akshare.akfamily.xyz/data/futures/futures.html#get-futures-daily"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw"
LOW_LIQUIDITY_THRESHOLD = 100

FIELD_ALIASES = {
    "symbol": ("symbol", "合约", "合约代码"),
    "date": ("date", "交易日", "日期"),
    "close": ("close", "收盘价"),
    "volume": ("volume", "成交量"),
    "open_interest": ("open_interest", "持仓量"),
    "settle": ("settle", "结算价"),
    "variety": ("variety", "品种"),
}


@dataclass(frozen=True)
class NormalizedScRow:
    raw: dict[str, Any]
    raw_symbol: str
    contract: str
    contract_month: tuple[int, int] | None
    date: str
    close: float | None
    settle: float | None
    volume: float
    open_interest: float


RowsProvider = Callable[[str], Any]


def fetch_akshare_sc_daily(
    report_date: str,
    rows_provider: RowsProvider | None = None,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    """Fetch AKShare rows and return raw_data_contract_v1 as a dict."""

    final_fetched_at = fetched_at or _now_shanghai()
    try:
        rows = rows_provider(report_date) if rows_provider else _fetch_rows_from_akshare(report_date)
    except Exception as exc:  # noqa: BLE001 - fetcher errors are structured in raw_data.
        return _failure_result(
            report_date=report_date,
            fetched_at=final_fetched_at,
            error=f"AKShare fetch failed: {exc}",
        )

    return build_fetch_result_from_rows(
        rows=rows,
        report_date=report_date,
        fetched_at=final_fetched_at,
    )


def build_fetch_result_from_rows(
    rows: Any,
    report_date: str,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    """Build raw_data_contract_v1 from local AKShare-like rows."""

    final_fetched_at = fetched_at or _now_shanghai()
    row_dicts = _rows_to_dicts(rows)
    if not row_dicts:
        return _failure_result(
            report_date=report_date,
            fetched_at=final_fetched_at,
            error="AKShare returned no rows for INE SC daily data",
        )

    warnings: list[str] = []
    normalized_rows = _normalize_rows(row_dicts, report_date, warnings)
    if not normalized_rows:
        return _failure_result(
            report_date=report_date,
            fetched_at=final_fetched_at,
            error="AKShare rows did not contain recognizable SC contracts",
        )

    main_row = _select_main_contract(normalized_rows)
    if main_row is None:
        return _failure_result(
            report_date=report_date,
            fetched_at=final_fetched_at,
            error="Unable to select SC main contract because all volumes are missing or zero",
        )

    if main_row.close is None:
        return _failure_result(
            report_date=report_date,
            fetched_at=final_fetched_at,
            error=f"Main contract {main_row.contract} is missing close price",
        )

    open_interest_row = max(normalized_rows, key=lambda item: item.open_interest)
    if open_interest_row.contract != main_row.contract:
        warnings.append(
            "main contract by volume differs from max open_interest contract: "
            f"volume_main={main_row.contract}, open_interest_main={open_interest_row.contract}"
        )

    records: list[RawDataRecord] = [
        _make_record("SC_close", main_row.close, "close", "CNY/barrel", main_row, final_fetched_at),
        _make_record("SC_volume", _format_contract_count(main_row.volume), "volume", "contracts", main_row, final_fetched_at),
        _make_record(
            "SC_open_interest",
            _format_contract_count(main_row.open_interest),
            "open_interest",
            "contracts",
            main_row,
            final_fetched_at,
        ),
    ]

    if main_row.settle is None:
        warnings.append(f"{main_row.contract}: missing settle; SC_settlement not emitted")
    else:
        records.append(_make_record("SC_settlement", main_row.settle, "settle", "CNY/barrel", main_row, final_fetched_at))

    near_rows = _select_near_next_rows(normalized_rows, report_date, warnings)
    if len(near_rows) >= 1 and near_rows[0].close is not None:
        records.append(_make_record("SC_near_price", near_rows[0].close, "close", "CNY/barrel", near_rows[0], final_fetched_at))
    else:
        warnings.append("SC_near_price was not emitted because no usable near contract close was found")

    if len(near_rows) >= 2 and near_rows[1].close is not None:
        records.append(_make_record("SC_next_price", near_rows[1].close, "close", "CNY/barrel", near_rows[1], final_fetched_at))
    else:
        warnings.append("SC_next_price was not emitted because no usable next contract close was found")

    status = "warning" if warnings else "pass"
    return FetchResult(
        report_date=report_date,
        source_name=SOURCE_NAME,
        fetcher_name=FETCHER_NAME,
        fetcher_version=FETCHER_VERSION,
        fetched_at=final_fetched_at,
        fetch_status=status,
        records=tuple(records),
        warnings=tuple(warnings),
        errors=(),
    ).to_dict()


def write_raw_data(raw_data: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(raw_data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def build_default_output_path(report_date: str) -> Path:
    return DEFAULT_OUTPUT_DIR / f"akshare_sc_{report_date}.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch AKShare INE SC daily market data.")
    parser.add_argument("--report-date", required=True, help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--output", help="Raw data output JSON path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_path = Path(args.output) if args.output else build_default_output_path(args.report_date)
    raw_data = fetch_akshare_sc_daily(args.report_date)
    write_raw_data(raw_data, output_path)
    print(f"report_date: {raw_data['report_date']}")
    print(f"fetch_status: {raw_data['fetch_status']}")
    print(f"records: {len(raw_data['records'])}")
    print(f"warnings: {len(raw_data['warnings'])}")
    print(f"errors: {len(raw_data['errors'])}")
    print(f"output_path: {output_path}")
    return 2 if raw_data["fetch_status"] == "fail" else 0


def _fetch_rows_from_akshare(report_date: str) -> Any:
    try:
        import akshare as ak  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("akshare is not installed; run `pip install -r requirements.txt`") from exc

    get_futures_daily = getattr(ak, "get_futures_daily", None)
    if not callable(get_futures_daily):
        raise RuntimeError("akshare.get_futures_daily is not available in the installed akshare version")

    query_date = _to_akshare_date(report_date)
    return get_futures_daily(start_date=query_date, end_date=query_date, market="INE")


def _normalize_rows(
    rows: Iterable[dict[str, Any]],
    report_date: str,
    warnings: list[str],
) -> list[NormalizedScRow]:
    normalized: list[NormalizedScRow] = []
    for index, row in enumerate(rows):
        raw_symbol = _get_value(row, "symbol")
        parsed_contract = _parse_sc_contract(raw_symbol)
        if not parsed_contract:
            continue

        contract, contract_month = parsed_contract
        if contract_month is None:
            warnings.append(f"rows[{index}] {raw_symbol}: SC contract month is not parseable")

        row_date = _clean_date(_get_value(row, "date")) or report_date
        if row_date != report_date:
            warnings.append(f"{contract}: row date {row_date} differs from report_date {report_date}")

        normalized.append(
            NormalizedScRow(
                raw=dict(row),
                raw_symbol=str(raw_symbol),
                contract=contract,
                contract_month=contract_month,
                date=row_date,
                close=_to_float(_get_value(row, "close")),
                settle=_to_float(_get_value(row, "settle")),
                volume=_to_float(_get_value(row, "volume")) or 0.0,
                open_interest=_to_float(_get_value(row, "open_interest")) or 0.0,
            )
        )
    return normalized


def _select_main_contract(rows: list[NormalizedScRow]) -> NormalizedScRow | None:
    candidates = [row for row in rows if row.volume > 0]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.volume)


def _select_near_next_rows(
    rows: list[NormalizedScRow],
    report_date: str,
    warnings: list[str],
) -> list[NormalizedScRow]:
    report_month = _report_month_key(report_date)
    active_rows = [
        row
        for row in rows
        if row.contract_month is not None
        and row.contract_month >= report_month
        and (row.volume > 0 or row.open_interest > 0)
    ]
    active_rows.sort(key=lambda item: item.contract_month or (9999, 12))
    selected = active_rows[:2]

    if len(selected) < 2:
        warnings.append("Fewer than two active SC contracts were available for near/next selection")

    for row in selected:
        if row.volume < LOW_LIQUIDITY_THRESHOLD or row.open_interest < LOW_LIQUIDITY_THRESHOLD:
            warnings.append(
                f"{row.contract}: near/next candidate has low liquidity "
                f"(volume={_format_contract_count(row.volume)}, open_interest={_format_contract_count(row.open_interest)})"
            )

    return selected


def _make_record(
    field_name: str,
    value: Any,
    source_field: str,
    unit: str,
    row: NormalizedScRow,
    fetched_at: str,
) -> RawDataRecord:
    return RawDataRecord(
        field=field_name,
        value=value,
        metadata={
            "unit": unit,
            "date": row.date,
            "timezone": "Asia/Shanghai",
            "source_name": SOURCE_NAME,
            "source_field": source_field,
            "source_level": SOURCE_LEVEL,
            "fetcher_name": FETCHER_NAME,
            "fetched_at": fetched_at,
            "contract": row.contract,
            "raw_symbol": row.raw_symbol,
            "url_or_reference": URL_OR_REFERENCE,
        },
        raw_payload=_json_safe_dict(row.raw),
    )


def _failure_result(report_date: str, fetched_at: str, error: str) -> dict[str, Any]:
    return FetchResult(
        report_date=report_date,
        source_name=SOURCE_NAME,
        fetcher_name=FETCHER_NAME,
        fetcher_version=FETCHER_VERSION,
        fetched_at=fetched_at,
        fetch_status="fail",
        records=(),
        warnings=(),
        errors=(error,),
    ).to_dict()


def _rows_to_dicts(rows: Any) -> list[dict[str, Any]]:
    if rows is None:
        return []
    if hasattr(rows, "empty") and bool(getattr(rows, "empty")):
        return []
    if hasattr(rows, "to_dict"):
        records = rows.to_dict(orient="records")
        return [dict(record) for record in records]
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, dict)]
    if isinstance(rows, tuple):
        return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _get_value(row: dict[str, Any], field_name: str) -> Any:
    for key in FIELD_ALIASES[field_name]:
        if key in row:
            return row[key]
    return None


def _parse_sc_contract(raw_symbol: Any) -> tuple[str, tuple[int, int] | None] | None:
    if raw_symbol is None:
        return None
    match = re.search(r"(?i)\bSC\s*([0-9]{4})\b", str(raw_symbol).strip())
    if not match:
        return None

    digits = match.group(1)
    year = 2000 + int(digits[:2])
    month = int(digits[2:])
    contract = f"SC{digits}"
    if not 1 <= month <= 12:
        return contract, None
    return contract, (year, month)


def _report_month_key(report_date: str) -> tuple[int, int]:
    parsed = datetime.strptime(report_date, "%Y-%m-%d")
    return parsed.year, parsed.month


def _to_akshare_date(report_date: str) -> str:
    return datetime.strptime(report_date, "%Y-%m-%d").strftime("%Y%m%d")


def _clean_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:10]


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        text = str(value).replace(",", "").strip()
        if text in {"", "-", "--", "nan", "NaN", "None"}:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _format_contract_count(value: float) -> int | float:
    if float(value).is_integer():
        return int(value)
    return value


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
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    return str(value)


def _now_shanghai() -> str:
    shanghai_tz = timezone(timedelta(hours=8))
    return datetime.now(shanghai_tz).isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
