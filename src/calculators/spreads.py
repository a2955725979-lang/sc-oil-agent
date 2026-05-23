"""Calculate SC USD reference, calendar spread, and simplified external spreads.

This module only uses local daily_input JSON data. It does not fetch market
data, write databases, or modify the original input file.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


CALCULATION_METHOD = "simple_fx_adjusted_v1"
CALCULATED_FIELDS = {
    "SC_USD",
    "SC_calendar_spread",
    "SC_Brent_spread_simple",
    "SC_WTI_spread_simple",
}


class SpreadCalculationError(RuntimeError):
    """Raised when spread calculation cannot run because input shape is invalid."""


def load_daily_input(path: str | Path) -> dict[str, Any]:
    input_path = Path(path)
    with input_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise SpreadCalculationError(f"daily input JSON must be an object: {input_path}")
    return data


def build_default_output_path(report_date: str) -> Path:
    return PROJECT_ROOT / "data" / "processed" / f"calculated_input_{report_date}.json"


def calculate_spreads_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
    preserve_existing: bool = False,
) -> dict[str, Any]:
    daily_input = load_daily_input(input_path)
    calculated = calculate_spreads(daily_input, preserve_existing=preserve_existing)
    report_date = str(calculated.get("report_date") or "UNKNOWN_DATE")
    final_output_path = Path(output_path) if output_path else build_default_output_path(report_date)
    write_daily_input(calculated, final_output_path)
    return calculated


def calculate_spreads(daily_input: dict[str, Any], preserve_existing: bool = False) -> dict[str, Any]:
    """Return a copy of daily_input with calculated spread fields added."""

    result = copy.deepcopy(daily_input)
    fields = result.get("fields")
    if not isinstance(fields, dict):
        raise SpreadCalculationError("daily input must include a fields object")

    context = result.get("context")
    if context is None:
        context = {}
    if not isinstance(context, dict):
        context = {}
    result["context"] = context
    warnings = context.get("calculation_warnings")
    if not isinstance(warnings, list):
        warnings = []
    context["calculation_warnings"] = warnings

    _calculate_sc_usd(fields, warnings, preserve_existing)
    _calculate_calendar_spread(fields, warnings, preserve_existing)
    _calculate_external_spread(
        fields=fields,
        warnings=warnings,
        target_field="SC_Brent_spread_simple",
        external_field="Brent_close",
        preserve_existing=preserve_existing,
    )
    _calculate_external_spread(
        fields=fields,
        warnings=warnings,
        target_field="SC_WTI_spread_simple",
        external_field="WTI_close",
        preserve_existing=preserve_existing,
    )
    return result


def write_daily_input(daily_input: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(daily_input, file, ensure_ascii=False, indent=2)
        file.write("\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calculate SC spreads from local daily input JSON.")
    parser.add_argument("--input", required=True, help="Daily input JSON path.")
    parser.add_argument("--output", help="Processed daily input JSON output path.")
    parser.add_argument(
        "--preserve-existing",
        action="store_true",
        help="Keep existing calculated fields instead of recalculating them.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        calculated = calculate_spreads_file(
            input_path=args.input,
            output_path=args.output,
            preserve_existing=args.preserve_existing,
        )
    except (SpreadCalculationError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1

    warnings = calculated.get("context", {}).get("calculation_warnings", [])
    print(f"report_date: {calculated.get('report_date', '')}")
    print(f"calculation_method: {CALCULATION_METHOD}")
    print(f"calculation_warnings: {len(warnings) if isinstance(warnings, list) else 0}")
    return 0


def _calculate_sc_usd(fields: dict[str, Any], warnings: list[str], preserve_existing: bool) -> None:
    target = "SC_USD"
    if _skip_existing(fields, target, warnings, preserve_existing):
        return

    sc_close = _field_number(fields, "SC_close", warnings)
    usd_cny = _field_number(fields, "USD_CNY", warnings)
    if sc_close is None or usd_cny is None:
        warnings.append(f"{target}: skipped because SC_close or USD_CNY is missing/non-numeric")
        return
    if usd_cny == 0:
        warnings.append(f"{target}: skipped because USD_CNY is zero")
        return

    if not _require_unit(fields, "SC_close", "CNY/barrel", warnings):
        warnings.append(f"{target}: skipped because SC_close unit is not CNY/barrel")
        return
    if not _require_unit(fields, "USD_CNY", "CNY/USD", warnings):
        warnings.append(f"{target}: skipped because USD_CNY unit is not CNY/USD")
        return

    sc_date = _field_date(fields, "SC_close")
    fx_date = _field_date(fields, "USD_CNY")
    fields[target] = {
        "value": round(sc_close / usd_cny, 4),
        "metadata": {
            "unit": "USD/barrel",
            "sc_date": sc_date,
            "external_date": fx_date,
            "fx_date": fx_date,
            "timezone": _field_timezone(fields, "SC_close"),
            "calculation_method": CALCULATION_METHOD,
            "calculation_inputs": ["SC_close", "USD_CNY"],
        },
    }


def _calculate_calendar_spread(fields: dict[str, Any], warnings: list[str], preserve_existing: bool) -> None:
    target = "SC_calendar_spread"
    if _skip_existing(fields, target, warnings, preserve_existing):
        return

    near_price = _field_number(fields, "SC_near_price", warnings)
    next_price = _field_number(fields, "SC_next_price", warnings)
    if near_price is None or next_price is None:
        warnings.append(f"{target}: skipped because SC_near_price or SC_next_price is missing/non-numeric")
        return

    if not _require_unit(fields, "SC_near_price", "CNY/barrel", warnings):
        warnings.append(f"{target}: skipped because SC_near_price unit is not CNY/barrel")
        return
    if not _require_unit(fields, "SC_next_price", "CNY/barrel", warnings):
        warnings.append(f"{target}: skipped because SC_next_price unit is not CNY/barrel")
        return

    value = round(near_price - next_price, 4)
    sc_date = _field_date(fields, "SC_near_price") or _field_date(fields, "SC_next_price")
    timezone = _field_timezone(fields, "SC_near_price") or _field_timezone(fields, "SC_next_price")
    fields[target] = {
        "value": value,
        "metadata": {
            "unit": "CNY/barrel",
            "sc_date": sc_date,
            "external_date": sc_date,
            "fx_date": sc_date,
            "timezone": timezone,
            "calculation_method": CALCULATION_METHOD,
            "calculation_inputs": ["SC_near_price", "SC_next_price"],
            "near_field": "SC_near_price",
            "next_field": "SC_next_price",
        },
    }


def _calculate_external_spread(
    fields: dict[str, Any],
    warnings: list[str],
    target_field: str,
    external_field: str,
    preserve_existing: bool,
) -> None:
    if _skip_existing(fields, target_field, warnings, preserve_existing):
        return

    sc_usd = _field_number(fields, "SC_USD", warnings)
    external_close = _field_number(fields, external_field, warnings)
    if sc_usd is None or external_close is None:
        warnings.append(f"{target_field}: skipped because required input is missing/non-numeric")
        return

    if not _require_unit(fields, "SC_USD", "USD/barrel", warnings):
        warnings.append(f"{target_field}: skipped because SC_USD unit is not USD/barrel")
        return
    if not _require_unit(fields, external_field, "USD/barrel", warnings):
        warnings.append(f"{target_field}: skipped because {external_field} unit is not USD/barrel")
        return

    value = round(sc_usd - external_close, 4)
    fields[target_field] = {
        "value": value,
        "metadata": {
            "unit": "USD/barrel",
            "sc_date": _field_metadata(fields, "SC_USD").get("sc_date"),
            "external_date": _field_date(fields, external_field),
            "fx_date": _field_metadata(fields, "SC_USD").get("fx_date"),
            "timezone": _field_timezone(fields, "SC_USD"),
            "calculation_method": CALCULATION_METHOD,
            "calculation_inputs": ["SC_USD", external_field],
        },
    }


def _skip_existing(
    fields: dict[str, Any],
    target_field: str,
    warnings: list[str],
    preserve_existing: bool,
) -> bool:
    if not preserve_existing or target_field not in fields:
        return False
    warnings.append(f"{target_field}: preserved existing field because --preserve-existing was used")
    return True


def _field_number(fields: dict[str, Any], field_name: str, warnings: list[str]) -> float | None:
    payload = fields.get(field_name)
    if not isinstance(payload, dict):
        warnings.append(f"{field_name}: missing field")
        return None
    value = payload.get("value")
    try:
        return float(value)
    except (TypeError, ValueError):
        warnings.append(f"{field_name}: non-numeric value")
        return None


def _require_unit(
    fields: dict[str, Any],
    field_name: str,
    expected_unit: str,
    warnings: list[str],
) -> bool:
    observed = _field_metadata(fields, field_name).get("unit")
    if observed == expected_unit:
        return True
    warnings.append(f"{field_name}: unit mismatch, expected {expected_unit}, got {observed}")
    return False


def _field_metadata(fields: dict[str, Any], field_name: str) -> dict[str, Any]:
    payload = fields.get(field_name)
    if not isinstance(payload, dict):
        return {}
    metadata = payload.get("metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _field_date(fields: dict[str, Any], field_name: str) -> Any:
    metadata = _field_metadata(fields, field_name)
    return metadata.get("date") or metadata.get("data_date")


def _field_timezone(fields: dict[str, Any], field_name: str) -> Any:
    metadata = _field_metadata(fields, field_name)
    return metadata.get("timezone") or metadata.get("time_zone")


if __name__ == "__main__":
    raise SystemExit(main())
