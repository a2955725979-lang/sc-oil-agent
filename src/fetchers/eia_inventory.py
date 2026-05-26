"""EIA inventory preflight stub.

This module deliberately does not claim live EIA automation. Until a real EIA
provider is wired in, it emits a warning raw_data_contract_v1 record for
EIA_crude_inventory with a null value and explicit pending/manual-review
metadata. The existing quality rules then downgrade the report without
blocking the auto preflight.
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


SOURCE_NAME = "eia_inventory_preflight"
SOURCE_LEVEL = "derived"
FETCHER_NAME = "eia_inventory_stub"
FETCHER_VERSION = "eia_inventory_stub_v1"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw"
URL_OR_REFERENCE = "not_configured:eia_provider_pending"

RowsProvider = Callable[[str], Any]


def fetch_eia_inventory_daily(
    report_date: str,
    rows_provider: RowsProvider | None = None,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    """Fetch or stub EIA inventory and emit raw_data_contract_v1."""

    final_fetched_at = fetched_at or _now_shanghai()
    try:
        rows = rows_provider(report_date) if rows_provider else _fetch_rows_live(report_date)
    except Exception as exc:  # noqa: BLE001 - fetch failures are structured.
        return build_fetch_result_from_rows(
            rows={},
            report_date=report_date,
            fetched_at=final_fetched_at,
            unavailable_reason=f"EIA inventory fetch failed: {exc}",
        )

    return build_fetch_result_from_rows(rows, report_date, final_fetched_at)


def build_fetch_result_from_rows(
    rows: Any,
    report_date: str,
    fetched_at: str | None = None,
    unavailable_reason: str | None = None,
) -> dict[str, Any]:
    """Build raw_data_contract_v1 from an EIA-like row or warning stub."""

    final_fetched_at = fetched_at or _now_shanghai()
    row = _row_to_dict(rows)
    value = _to_float(_get_value(row, "EIA_crude_inventory"))
    field_date = _clean_date(_get_value(row, "EIA_crude_inventory_date") or row.get("date")) or report_date

    warnings: list[str] = []
    if value is None:
        reason = unavailable_reason or "EIA crude inventory not fetched; pending provider/manual review"
        warnings.append(reason)
    elif field_date != report_date:
        warnings.append(f"EIA_crude_inventory: using latest available date {field_date} for report_date {report_date}")

    metadata = {
        "unit": "million_barrels",
        "date": field_date,
        "publish_time": str(row.get("publish_time") or ""),
        "timezone": "America/New_York",
        "source_name": str(row.get("source_name") or SOURCE_NAME),
        "source_field": "weekly_crude_inventory",
        "source_level": SOURCE_LEVEL if value is None else str(row.get("source_level") or "official"),
        "fetcher_name": FETCHER_NAME,
        "fetched_at": final_fetched_at,
        "url_or_reference": str(row.get("url_or_reference") or URL_OR_REFERENCE),
    }
    if value is None:
        metadata.update(
            {
                "source_status": "warning",
                "confidence": "low",
                "eia_warning_stub": True,
                "fallback_used": True,
                "fallback_reason": "no_eia_provider_configured",
                "pending_manual_review": True,
            }
        )
    elif field_date != report_date:
        metadata["fallback_used"] = True
        metadata["fallback_reason"] = "latest_available_date differs from report_date"

    return FetchResult(
        report_date=report_date,
        source_name=str(row.get("source_name") or SOURCE_NAME),
        fetcher_name=FETCHER_NAME,
        fetcher_version=FETCHER_VERSION,
        fetched_at=final_fetched_at,
        fetch_status="warning" if warnings else "pass",
        records=(
            RawDataRecord(
                field="EIA_crude_inventory",
                value=value,
                metadata=metadata,
                raw_payload=_json_safe_dict(row),
            ),
        ),
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
    return DEFAULT_OUTPUT_DIR / f"eia_inventory_{report_date}.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch or stub EIA inventory daily data.")
    parser.add_argument("--report-date", required=True, help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--output", help="Raw data output JSON path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_path = Path(args.output) if args.output else build_default_output_path(args.report_date)
    raw_data = fetch_eia_inventory_daily(args.report_date)
    write_raw_data(raw_data, output_path)
    print(f"report_date: {raw_data['report_date']}")
    print(f"fetch_status: {raw_data['fetch_status']}")
    print(f"records: {len(raw_data['records'])}")
    print(f"warnings: {len(raw_data['warnings'])}")
    print(f"errors: {len(raw_data['errors'])}")
    print(f"output_path: {output_path}")
    return 0


def _fetch_rows_live(_report_date: str) -> dict[str, Any]:
    return {}


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
        "EIA_crude_inventory": ("EIA_crude_inventory", "eia_crude_inventory", "crude_inventory", "value"),
        "EIA_crude_inventory_date": ("EIA_crude_inventory_date", "eia_crude_inventory_date", "period", "date"),
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
