"""Base data contracts for future market data fetchers.

This module defines the raw_data contract used before real AKShare, EIA,
FRED, or yfinance integrations exist. It is intentionally dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


RAW_DATA_CONTRACT_VERSION = "raw_data_contract_v1"
FETCH_STATUSES = {"pass", "warning", "fail"}
SOURCE_LEVELS = {"test", "manual", "official", "third_party", "derived"}


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
