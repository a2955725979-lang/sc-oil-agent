"""Smoke tests for src/fetchers/eia_inventory.py.

Run from the project root:
    python tests/test_eia_inventory_fetcher.py
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.base import DAILY_INPUT_SCHEMA_VERSION, RAW_DATA_CONTRACT_VERSION, validate_raw_data_contract  # noqa: E402
from src.fetchers.eia_inventory import build_fetch_result_from_rows, fetch_eia_inventory_daily  # noqa: E402
from src.fetchers.transform import convert_raw_data_to_daily_input  # noqa: E402


REPORT_DATE = "2026-05-22"
FETCHED_AT = "2026-05-22T16:40:00+08:00"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(items: list[str], expected_fragment: str, message: str) -> None:
    if not any(expected_fragment in item for item in items):
        raise AssertionError(f"{message}: {expected_fragment!r} not found in {items!r}")


def test_default_stub_emits_warning_raw_data_contract() -> None:
    raw_data = fetch_eia_inventory_daily(REPORT_DATE, fetched_at=FETCHED_AT)
    record = raw_data["records"][0]
    metadata = record["metadata"]

    assert_equal(raw_data["contract_version"], RAW_DATA_CONTRACT_VERSION, "raw_data contract version")
    assert_equal(raw_data["fetch_status"], "warning", "default EIA stub status")
    assert_equal(validate_raw_data_contract(raw_data), [], "raw_data contract errors")
    assert_equal(record["field"], "EIA_crude_inventory", "field name")
    assert_equal(record["value"], None, "stub value")
    assert_equal(metadata["source_status"], "warning", "source status")
    assert_equal(metadata["confidence"], "low", "confidence")
    assert_equal(metadata["eia_warning_stub"], True, "EIA warning stub marker")
    assert_equal(metadata["fallback_used"], True, "fallback marker")
    assert_equal(metadata["pending_manual_review"], True, "manual review marker")
    assert_contains(raw_data["warnings"], "pending provider/manual review", "stub warning")


def test_provider_row_can_emit_real_eia_value() -> None:
    raw_data = build_fetch_result_from_rows(
        rows={
            "date": REPORT_DATE,
            "EIA_crude_inventory": 443.2,
            "source_name": "fixture_eia",
            "source_level": "official",
            "url_or_reference": "fixture://eia",
        },
        report_date=REPORT_DATE,
        fetched_at=FETCHED_AT,
    )
    record = raw_data["records"][0]

    assert_equal(raw_data["fetch_status"], "pass", "provider row status")
    assert_equal(record["value"], 443.2, "provider value")
    assert_equal(record["metadata"]["source_level"], "official", "source level")
    assert_equal(record["metadata"]["url_or_reference"], "fixture://eia", "reference")


def test_output_can_transform_to_daily_input_schema_v1() -> None:
    raw_data = fetch_eia_inventory_daily(REPORT_DATE, fetched_at=FETCHED_AT)
    conversion = convert_raw_data_to_daily_input(raw_data)
    daily_input = conversion["daily_input"]

    assert_equal(conversion["usable_for_pipeline"], True, "warning EIA stub should be usable")
    assert_equal(conversion["conversion_errors"], [], "EIA conversion errors")
    assert_equal(daily_input["schema_version"], DAILY_INPUT_SCHEMA_VERSION, "daily_input schema version")
    assert_equal("EIA_crude_inventory" in daily_input["fields"], True, "converted EIA field")


def run() -> None:
    tests = [
        test_default_stub_emits_warning_raw_data_contract,
        test_provider_row_can_emit_real_eia_value,
        test_output_can_transform_to_daily_input_schema_v1,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
