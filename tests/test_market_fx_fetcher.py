"""Smoke tests for src/fetchers/market_fx.py.

Run from the project root:
    python tests/test_market_fx_fetcher.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.base import DAILY_INPUT_SCHEMA_VERSION, RAW_DATA_CONTRACT_VERSION, validate_raw_data_contract  # noqa: E402
from src.fetchers.market_fx import build_fetch_result_from_rows, fetch_market_fx_daily  # noqa: E402
from src.fetchers.transform import convert_raw_data_to_daily_input  # noqa: E402


REPORT_DATE = "2026-05-22"
FETCHED_AT = "2026-05-22T16:30:00+08:00"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(items: list[str], expected_fragment: str, message: str) -> None:
    if not any(expected_fragment in item for item in items):
        raise AssertionError(f"{message}: {expected_fragment!r} not found in {items!r}")


def fixture_row(report_date: str = REPORT_DATE) -> dict:
    return {
        "date": report_date,
        "USD_CNY": 7.18,
        "Brent_close": 82.4,
        "WTI_close": 78.6,
        "source_name": "fixture_market_fx",
        "url_or_reference": "fixture://market_fx",
    }


def test_fixture_rows_emit_frozen_raw_data_contract() -> None:
    raw_data = build_fetch_result_from_rows(fixture_row(), REPORT_DATE, FETCHED_AT)
    fields = [record["field"] for record in raw_data["records"]]
    first_metadata = raw_data["records"][0]["metadata"]

    assert_equal(raw_data["contract_version"], RAW_DATA_CONTRACT_VERSION, "raw_data contract version")
    assert_equal(raw_data["fetch_status"], "pass", "fixture raw_data status")
    assert_equal(fields, ["USD_CNY", "Brent_close", "WTI_close"], "market/fx fields")
    assert_equal(validate_raw_data_contract(raw_data), [], "raw_data contract errors")
    assert_equal(first_metadata["source_name"], "fixture_market_fx", "source name metadata")
    assert_equal(first_metadata["source_field"], "usd_cny", "source field metadata")
    assert_equal(first_metadata["source_level"], "third_party", "source level metadata")
    assert_equal(first_metadata["fetched_at"], FETCHED_AT, "fetched_at metadata")
    assert_equal(first_metadata["url_or_reference"], "fixture://market_fx", "reference metadata")


def test_latest_available_date_marks_warning_and_fallback_metadata() -> None:
    raw_data = build_fetch_result_from_rows(fixture_row("2026-05-21"), REPORT_DATE, FETCHED_AT)
    usd_metadata = raw_data["records"][0]["metadata"]

    assert_equal(raw_data["fetch_status"], "warning", "stale row should mark warning")
    assert_equal(usd_metadata["fallback_used"], True, "fallback marker")
    assert_contains(raw_data["warnings"], "using latest available date", "stale date warning")


def test_missing_field_returns_structured_fail() -> None:
    row = fixture_row()
    row.pop("WTI_close")
    raw_data = build_fetch_result_from_rows(row, REPORT_DATE, FETCHED_AT)

    assert_equal(raw_data["fetch_status"], "fail", "missing required field should fail")
    assert_equal([record["field"] for record in raw_data["records"]], ["USD_CNY", "Brent_close"], "valid records remain")
    assert_contains(raw_data["errors"], "WTI_close", "missing WTI error")


def test_provider_exception_returns_structured_fail() -> None:
    def broken_provider(_report_date: str) -> list[dict]:
        raise RuntimeError("provider unavailable")

    raw_data = fetch_market_fx_daily(REPORT_DATE, rows_provider=broken_provider, fetched_at=FETCHED_AT)

    assert_equal(raw_data["fetch_status"], "fail", "provider exception should be structured fail")
    assert_equal(raw_data["records"], [], "provider exception should not emit records")
    assert_contains(raw_data["errors"], "provider unavailable", "provider error message")


def test_output_can_transform_to_daily_input_schema_v1() -> None:
    raw_data = build_fetch_result_from_rows(fixture_row(), REPORT_DATE, FETCHED_AT)
    conversion = convert_raw_data_to_daily_input(raw_data)
    daily_input = conversion["daily_input"]

    assert_equal(conversion["usable_for_pipeline"], True, "market/fx conversion should be usable")
    assert_equal(conversion["conversion_errors"], [], "market/fx conversion errors")
    assert_equal(daily_input["schema_version"], DAILY_INPUT_SCHEMA_VERSION, "daily_input schema version")
    assert_equal(sorted(daily_input["fields"].keys()), ["Brent_close", "USD_CNY", "WTI_close"], "converted fields")


def run() -> None:
    tests = [
        test_fixture_rows_emit_frozen_raw_data_contract,
        test_latest_available_date_marks_warning_and_fallback_metadata,
        test_missing_field_returns_structured_fail,
        test_provider_exception_returns_structured_fail,
        test_output_can_transform_to_daily_input_schema_v1,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
