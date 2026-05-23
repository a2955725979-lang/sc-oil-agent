"""Convert fetcher raw_data contract objects into daily_input structures."""

from __future__ import annotations

from typing import Any

from src.fetchers.base import FETCH_STATUSES, RAW_DATA_CONTRACT_VERSION, is_valid_source_level


def convert_raw_data_to_daily_input(raw_data: dict[str, Any]) -> dict[str, Any]:
    """Convert raw_data JSON into a daily_input plus conversion diagnostics."""

    warnings: list[str] = []
    errors: list[str] = []
    daily_input = {
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


def _validate_top_level(raw_data: dict[str, Any], errors: list[str]) -> None:
    if raw_data.get("contract_version") != RAW_DATA_CONTRACT_VERSION:
        errors.append(f"contract_version must be {RAW_DATA_CONTRACT_VERSION}")

    fetch_status = raw_data.get("fetch_status")
    if fetch_status not in FETCH_STATUSES:
        errors.append("fetch_status must be one of pass/warning/fail")

    for required_name in (
        "report_date",
        "source_name",
        "fetcher_name",
        "fetcher_version",
        "fetched_at",
    ):
        if not raw_data.get(required_name):
            errors.append(f"{required_name} is required")

    records = raw_data.get("records")
    if not isinstance(records, list):
        errors.append("records must be a list")

    warnings = raw_data.get("warnings")
    if warnings is not None and not isinstance(warnings, list):
        errors.append("warnings must be a list")

    raw_errors = raw_data.get("errors")
    if raw_errors is not None and not isinstance(raw_errors, list):
        errors.append("errors must be a list")
