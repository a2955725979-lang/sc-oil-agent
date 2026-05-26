"""Market and FX fetcher for auto daily preflight.

The first version keeps tests deterministic by accepting injected rows. The
live path intentionally returns a structured failure until real providers are
enabled for USD/CNY, Brent, and WTI.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.base import FetchResult, RawDataRecord  # noqa: E402


SOURCE_NAME = "market_fx_preflight"
SOURCE_LEVEL = "third_party"
FETCHER_NAME = "market_fx_fetcher"
FETCHER_VERSION = "market_fx_v1"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw"
URL_OR_REFERENCE = "fixture_or_future_market_fx_provider"

FIELD_CONFIG = {
    "USD_CNY": {
        "unit": "CNY/USD",
        "timezone": "Asia/Shanghai",
        "source_field": "usd_cny",
        "required": True,
    },
    "Brent_close": {
        "unit": "USD/barrel",
        "timezone": "Europe/London",
        "source_field": "brent_close",
        "required": True,
    },
    "WTI_close": {
        "unit": "USD/barrel",
        "timezone": "America/New_York",
        "source_field": "wti_close",
        "required": True,
    },
}

RowsProvider = Callable[[str], Any]


def fetch_market_fx_daily(
    report_date: str,
    rows_provider: RowsProvider | None = None,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    """Fetch or receive market/fx rows and emit raw_data_contract_v1."""

    final_fetched_at = fetched_at or _now_shanghai()
    try:
        rows = rows_provider(report_date) if rows_provider else _fetch_rows_live(report_date)
    except Exception as exc:  # noqa: BLE001 - fetcher failures are structured.
        return _failure_result(report_date, final_fetched_at, f"market_fx fetch failed: {exc}")

    return build_fetch_result_from_rows(rows, report_date, final_fetched_at)


def build_fetch_result_from_rows(
    rows: Any,
    report_date: str,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    final_fetched_at = fetched_at or _now_shanghai()
    row = _row_to_dict(rows)
    warnings: list[str] = []
    errors: list[str] = []
    records: list[RawDataRecord] = []

    if not row:
        return _failure_result(report_date, final_fetched_at, "market_fx provider returned no usable row")

    for field_name, config in FIELD_CONFIG.items():
        value = _to_float(_get_value(row, field_name))
        if value is None:
            message = f"{field_name}: missing or non-numeric value"
            if config["required"]:
                errors.append(message)
            else:
                warnings.append(message)
            continue

        field_date = _clean_date(_get_value(row, f"{field_name}_date") or row.get("date")) or report_date
        metadata = {
            "unit": config["unit"],
            "date": field_date,
            "timezone": config["timezone"],
            "source_name": str(row.get("source_name") or SOURCE_NAME),
            "source_field": config["source_field"],
            "source_level": SOURCE_LEVEL,
            "fetcher_name": FETCHER_NAME,
            "fetched_at": final_fetched_at,
            "url_or_reference": str(row.get("url_or_reference") or URL_OR_REFERENCE),
        }
        if field_date != report_date:
            metadata["fallback_used"] = True
            metadata["fallback_reason"] = "latest_available_date differs from report_date"
            warnings.append(f"{field_name}: using latest available date {field_date} for report_date {report_date}")

        records.append(
            RawDataRecord(
                field=field_name,
                value=value,
                metadata=metadata,
                raw_payload=_json_safe_dict(row),
            )
        )

    status = "fail" if errors else "warning" if warnings else "pass"
    return FetchResult(
        report_date=report_date,
        source_name=str(row.get("source_name") or SOURCE_NAME),
        fetcher_name=FETCHER_NAME,
        fetcher_version=FETCHER_VERSION,
        fetched_at=final_fetched_at,
        fetch_status=status,
        records=tuple(records),
        warnings=tuple(warnings),
        errors=tuple(errors),
    ).to_dict()


def write_raw_data(raw_data: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(raw_data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def build_default_output_path(report_date: str) -> Path:
    return DEFAULT_OUTPUT_DIR / f"market_fx_{report_date}.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch market/fx daily data.")
    parser.add_argument("--report-date", required=True, help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--output", help="Raw data output JSON path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_path = Path(args.output) if args.output else build_default_output_path(args.report_date)
    raw_data = fetch_market_fx_daily(args.report_date)
    write_raw_data(raw_data, output_path)
    print(f"report_date: {raw_data['report_date']}")
    print(f"fetch_status: {raw_data['fetch_status']}")
    print(f"records: {len(raw_data['records'])}")
    print(f"warnings: {len(raw_data['warnings'])}")
    print(f"errors: {len(raw_data['errors'])}")
    print(f"output_path: {output_path}")
    return 2 if raw_data["fetch_status"] == "fail" else 0


def _fetch_rows_live(_report_date: str) -> dict[str, Any]:
    raise RuntimeError("live market_fx providers are not enabled in v0.6 preflight")


def _row_to_dict(rows: Any) -> dict[str, Any]:
    if isinstance(rows, dict):
        return dict(rows)
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return dict(rows[0])
    if isinstance(rows, tuple) and rows and isinstance(rows[0], dict):
        return dict(rows[0])
    if hasattr(rows, "empty") and bool(getattr(rows, "empty")):
        return {}
    if hasattr(rows, "to_dict"):
        records = rows.to_dict(orient="records")
        if records:
            return dict(records[0])
    return {}


def _get_value(row: dict[str, Any], field_name: str) -> Any:
    aliases = {
        "USD_CNY": ("USD_CNY", "usd_cny", "USDCNY", "usd_cny_close"),
        "Brent_close": ("Brent_close", "brent_close", "BRENT", "brent"),
        "WTI_close": ("WTI_close", "wti_close", "WTI", "wti"),
    }
    for key in aliases.get(field_name, (field_name,)):
        if key in row:
            return row[key]
    return None


def _clean_date(value: Any) -> str | None:
    if value is None:
        return None
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
        text = str(value).replace(",", "").strip()
        if text in {"", "-", "--", "nan", "NaN", "None"}:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


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


def _now_shanghai() -> str:
    shanghai = timezone(timedelta(hours=8))
    return datetime.now(tz=shanghai).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
