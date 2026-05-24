"""Base data contracts for future market data fetchers.

This module defines the raw_data contract used before real AKShare, EIA,
FRED, or yfinance integrations exist. It is intentionally dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


RAW_DATA_CONTRACT_VERSION = "raw_data_contract_v1"
DAILY_INPUT_SCHEMA_VERSION = "daily_input_schema_v1"
FETCH_STATUSES = {"pass", "warning", "fail"}
SOURCE_LEVELS = {"test", "manual", "official", "third_party", "derived"}
RAW_DATA_TOP_LEVEL_KEYS = (
    "contract_version",
    "report_date",
    "source_name",
    "fetcher_name",
    "fetcher_version",
    "fetched_at",
    "fetch_status",
    "records",
    "warnings",
    "errors",
)
DAILY_INPUT_TOP_LEVEL_KEYS = (
    "schema_version",
    "report_date",
    "context",
    "fields",
)


class FetcherContractError(ValueError):
    """Raised when code constructs an invalid fetcher contract object."""


@dataclass(frozen=True)
class FetchRequest:
    """A normalized request object for future fetchers."""

    report_date: str
    fields: tuple[str, ...] = ()
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_date": self.report_date,
            "fields": list(self.fields),
            "params": dict(self.params),
        }


@dataclass(frozen=True)
class RawDataRecord:
    """One field-level raw data record emitted by a fetcher."""

    field: str
    value: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        if not self.field:
            raise FetcherContractError("RawDataRecord.field is required")
        return {
            "field": self.field,
            "value": self.value,
            "metadata": dict(self.metadata),
            "raw_payload": dict(self.raw_payload),
        }


@dataclass(frozen=True)
class FetchResult:
    """Structured fetcher output before conversion to daily_input."""

    report_date: str
    source_name: str
    fetcher_name: str
    fetcher_version: str
    fetched_at: str
    fetch_status: str
    records: tuple[RawDataRecord, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    contract_version: str = RAW_DATA_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        if self.contract_version != RAW_DATA_CONTRACT_VERSION:
            raise FetcherContractError(f"Unsupported contract_version: {self.contract_version}")
        if self.fetch_status not in FETCH_STATUSES:
            raise FetcherContractError(f"Invalid fetch_status: {self.fetch_status}")
        for required_name, value in {
            "report_date": self.report_date,
            "source_name": self.source_name,
            "fetcher_name": self.fetcher_name,
            "fetcher_version": self.fetcher_version,
            "fetched_at": self.fetched_at,
        }.items():
            if not value:
                raise FetcherContractError(f"FetchResult.{required_name} is required")

        return {
            "contract_version": self.contract_version,
            "report_date": self.report_date,
            "source_name": self.source_name,
            "fetcher_name": self.fetcher_name,
            "fetcher_version": self.fetcher_version,
            "fetched_at": self.fetched_at,
            "fetch_status": self.fetch_status,
            "records": [record.to_dict() for record in self.records],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def is_valid_source_level(source_level: Any) -> bool:
    return str(source_level) in SOURCE_LEVELS


def validate_raw_data_contract(raw_data: Any) -> list[str]:
    """Return raw_data_contract_v1 validation errors without external deps."""

    errors: list[str] = []
    if not isinstance(raw_data, dict):
        return ["raw_data must be an object"]

    _validate_top_level_keys(raw_data, RAW_DATA_TOP_LEVEL_KEYS, "raw_data", errors)

    if raw_data.get("contract_version") != RAW_DATA_CONTRACT_VERSION:
        errors.append(f"contract_version must be {RAW_DATA_CONTRACT_VERSION}")

    for required_name in (
        "report_date",
        "source_name",
        "fetcher_name",
        "fetcher_version",
        "fetched_at",
    ):
        if not raw_data.get(required_name):
            errors.append(f"{required_name} is required")

    fetch_status = raw_data.get("fetch_status")
    if fetch_status not in FETCH_STATUSES:
        errors.append("fetch_status must be one of pass/warning/fail")

    records = raw_data.get("records")
    if not isinstance(records, list):
        errors.append("records must be a list")
    else:
        for index, record in enumerate(records):
            _validate_raw_data_record(index, record, errors)

    warnings = raw_data.get("warnings")
    if not isinstance(warnings, list):
        errors.append("warnings must be a list")

    raw_errors = raw_data.get("errors")
    if not isinstance(raw_errors, list):
        errors.append("errors must be a list")

    return errors


def validate_daily_input_schema(daily_input: Any, require_version: bool = False) -> list[str]:
    """Return daily_input_schema_v1 validation errors.

    By default, missing schema_version is tolerated for legacy v0.4/v0.5 inputs.
    Set require_version=True for newly generated files and frozen samples.
    """

    errors: list[str] = []
    if not isinstance(daily_input, dict):
        return ["daily_input must be an object"]

    allowed_keys = (
        DAILY_INPUT_TOP_LEVEL_KEYS
        if require_version or "schema_version" in daily_input
        else tuple(key for key in DAILY_INPUT_TOP_LEVEL_KEYS if key != "schema_version")
    )
    _validate_top_level_keys(daily_input, allowed_keys, "daily_input", errors)

    schema_version = daily_input.get("schema_version")
    if require_version and schema_version != DAILY_INPUT_SCHEMA_VERSION:
        errors.append(f"schema_version must be {DAILY_INPUT_SCHEMA_VERSION}")
    elif schema_version is not None and schema_version != DAILY_INPUT_SCHEMA_VERSION:
        errors.append(f"schema_version must be {DAILY_INPUT_SCHEMA_VERSION}")

    if not daily_input.get("report_date"):
        errors.append("report_date is required")

    context = daily_input.get("context")
    if not isinstance(context, dict):
        errors.append("context must be an object")

    fields = daily_input.get("fields")
    if not isinstance(fields, dict):
        errors.append("fields must be an object")
    else:
        for field_name, payload in fields.items():
            _validate_daily_input_field(field_name, payload, errors)

    return errors


def _validate_top_level_keys(
    payload: dict[str, Any],
    expected_keys: tuple[str, ...],
    label: str,
    errors: list[str],
) -> None:
    expected = set(expected_keys)
    actual = set(payload)
    for missing_key in expected - actual:
        errors.append(f"{label} missing top-level key: {missing_key}")
    for unexpected_key in actual - expected:
        errors.append(f"{label} unexpected top-level key: {unexpected_key}")


def _validate_raw_data_record(index: int, record: Any, errors: list[str]) -> None:
    if not isinstance(record, dict):
        errors.append(f"records[{index}] must be an object")
        return

    expected_keys = {"field", "value", "metadata", "raw_payload"}
    actual_keys = set(record)
    for missing_key in expected_keys - actual_keys:
        errors.append(f"records[{index}] missing {missing_key}")
    for unexpected_key in actual_keys - expected_keys:
        errors.append(f"records[{index}] unexpected key: {unexpected_key}")

    field_name = record.get("field")
    if not isinstance(field_name, str) or not field_name.strip():
        errors.append(f"records[{index}] missing field")
    if "value" not in record:
        errors.append(f"records[{index}] missing value")

    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        errors.append(f"records[{index}] metadata must be an object")
    else:
        source_level = metadata.get("source_level")
        if not is_valid_source_level(source_level):
            errors.append(
                f"records[{index}] invalid source_level={source_level}; "
                "expected one of test/manual/official/third_party/derived"
            )

    raw_payload = record.get("raw_payload")
    if not isinstance(raw_payload, dict):
        errors.append(f"records[{index}] raw_payload must be an object")


def _validate_daily_input_field(field_name: Any, payload: Any, errors: list[str]) -> None:
    if not isinstance(field_name, str) or not field_name.strip():
        errors.append("fields contains an empty field name")
    if not isinstance(payload, dict):
        errors.append(f"{field_name} payload must be an object")
        return

    expected_keys = {"value", "metadata"}
    actual_keys = set(payload)
    for missing_key in expected_keys - actual_keys:
        errors.append(f"{field_name} payload missing {missing_key}")
    for unexpected_key in actual_keys - expected_keys:
        errors.append(f"{field_name} payload unexpected key: {unexpected_key}")

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        errors.append(f"{field_name} metadata must be an object")
