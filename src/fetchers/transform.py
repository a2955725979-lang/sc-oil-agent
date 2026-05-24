"""Convert fetcher raw_data contract objects into daily_input structures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.base import (
    DAILY_INPUT_SCHEMA_VERSION,
    is_valid_source_level,
    validate_raw_data_contract,
)


DEFAULT_DAILY_INPUT_DIR = PROJECT_ROOT / "data" / "manual"
DEFAULT_RESULT_DIR = PROJECT_ROOT / "data" / "processed"


class RawDataTransformError(RuntimeError):
    """Raised when raw_data cannot be loaded or written by the CLI."""


def convert_raw_data_to_daily_input(raw_data: dict[str, Any]) -> dict[str, Any]:
    """Convert raw_data JSON into a daily_input plus conversion diagnostics."""

    warnings: list[str] = []
    errors: list[str] = []
    daily_input = {
        "schema_version": DAILY_INPUT_SCHEMA_VERSION,
        "report_date": str(raw_data.get("report_date", "")),
        "context": {
            "raw_data_contract_version": raw_data.get("contract_version"),
            "source_name": raw_data.get("source_name"),
            "fetcher_name": raw_data.get("fetcher_name"),
            "fetcher_version": raw_data.get("fetcher_version"),
            "fetched_at": raw_data.get("fetched_at"),
            "fetch_status": raw_data.get("fetch_status"),
        },
        "fields": {},
    }

    _validate_top_level(raw_data, errors)
    records = raw_data.get("records")
    if not isinstance(records, list):
        records = []

    seen_fields: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"records[{index}] must be an object")
            continue

        field_name = record.get("field")
        if not isinstance(field_name, str) or not field_name.strip():
            errors.append(f"records[{index}] missing field")
            continue
        if "value" not in record:
            errors.append(f"records[{index}] missing value for field {field_name}")
            continue
        if field_name in seen_fields:
            warnings.append(f"{field_name}: duplicate field in raw_data; kept first record")
            continue

        metadata = record.get("metadata", {})
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            errors.append(f"{field_name}: metadata must be an object")
            continue

        source_level = metadata.get("source_level")
        if not is_valid_source_level(source_level):
            errors.append(
                f"{field_name}: invalid source_level={source_level}; "
                "expected one of test/manual/official/third_party/derived"
            )
            continue

        enriched_metadata = dict(metadata)
        enriched_metadata.setdefault("source_name", raw_data.get("source_name"))
        enriched_metadata.setdefault("fetcher_name", raw_data.get("fetcher_name"))
        enriched_metadata.setdefault("fetched_at", raw_data.get("fetched_at"))

        daily_input["fields"][field_name] = {
            "value": record["value"],
            "metadata": enriched_metadata,
        }
        seen_fields.add(field_name)

    usable_for_pipeline = raw_data.get("fetch_status") != "fail" and not errors
    return {
        "daily_input": daily_input,
        "conversion_warnings": warnings,
        "conversion_errors": errors,
        "usable_for_pipeline": usable_for_pipeline,
    }


def convert_raw_data_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
    result_output_path: str | Path | None = None,
    report_date: str | None = None,
) -> dict[str, Any]:
    """Convert a raw_data JSON file, write diagnostics, and maybe write daily_input."""

    raw_data = load_raw_data(input_path)
    if report_date:
        raw_data = dict(raw_data)
        raw_data["report_date"] = report_date

    conversion = convert_raw_data_to_daily_input(raw_data)
    final_report_date = str(conversion["daily_input"].get("report_date") or report_date or "UNKNOWN_DATE")
    final_result_output_path = (
        Path(result_output_path)
        if result_output_path
        else build_default_result_output_path(final_report_date)
    )
    final_daily_input_output_path = (
        Path(output_path)
        if output_path
        else build_default_daily_input_output_path(final_report_date)
    )

    write_json(conversion, final_result_output_path)
    conversion["conversion_result_path"] = str(final_result_output_path)
    conversion["daily_input_path"] = ""

    if conversion["usable_for_pipeline"]:
        write_json(conversion["daily_input"], final_daily_input_output_path)
        conversion["daily_input_path"] = str(final_daily_input_output_path)

    return conversion


def load_raw_data(path: str | Path) -> dict[str, Any]:
    input_path = Path(path)
    with input_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise RawDataTransformError(f"raw_data JSON must be an object: {input_path}")
    return data


def write_json(data: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def build_default_daily_input_output_path(report_date: str) -> Path:
    return DEFAULT_DAILY_INPUT_DIR / f"daily_input_{report_date}.json"


def build_default_result_output_path(report_date: str) -> Path:
    return DEFAULT_RESULT_DIR / f"conversion_result_{report_date}.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert fetcher raw_data JSON into daily_input JSON.")
    parser.add_argument("--input", required=True, help="Fetcher raw_data JSON path.")
    parser.add_argument("--output", help="Daily input output JSON path.")
    parser.add_argument("--result-output", help="Conversion result output JSON path.")
    parser.add_argument("--report-date", help="Override raw_data report_date in YYYY-MM-DD format.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        conversion = convert_raw_data_file(
            input_path=args.input,
            output_path=args.output,
            result_output_path=args.result_output,
            report_date=args.report_date,
        )
    except (OSError, json.JSONDecodeError, RawDataTransformError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print_summary(conversion)
    return 0 if conversion["usable_for_pipeline"] else 2


def print_summary(conversion: dict[str, Any]) -> None:
    daily_input = conversion.get("daily_input", {})
    context = daily_input.get("context", {}) if isinstance(daily_input, dict) else {}
    if not isinstance(context, dict):
        context = {}

    print(f"report_date: {daily_input.get('report_date', '') if isinstance(daily_input, dict) else ''}")
    print(f"source_name: {context.get('source_name', '')}")
    print(f"fetch_status: {context.get('fetch_status', '')}")
    print(f"usable_for_pipeline: {conversion.get('usable_for_pipeline')}")
    print(f"conversion_warnings: {len(conversion.get('conversion_warnings', []))}")
    print(f"conversion_errors: {len(conversion.get('conversion_errors', []))}")
    print(f"conversion_result_path: {conversion.get('conversion_result_path', '')}")
    print(f"daily_input_path: {conversion.get('daily_input_path', '')}")


def _validate_top_level(raw_data: dict[str, Any], errors: list[str]) -> None:
    errors.extend(validate_raw_data_contract(raw_data))


if __name__ == "__main__":
    raise SystemExit(main())
