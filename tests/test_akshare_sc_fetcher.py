"""Smoke tests for AKShare SC daily fetcher v1.

Run from the project root:
    python tests/test_akshare_sc_fetcher.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.akshare_sc import (  # noqa: E402
    FETCHER_NAME,
    FETCHER_VERSION,
    SOURCE_NAME,
    build_fetch_result_from_rows,
    fetch_akshare_sc_daily,
)
from src.fetchers.base import RAW_DATA_CONTRACT_VERSION  # noqa: E402
from src.fetchers.transform import convert_raw_data_to_daily_input  # noqa: E402
from src.validators.run_quality_validation import run_validation  # noqa: E402


FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "akshare_sc" / "ine_sc_rows.json"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(items: list[str], expected_fragment: str, message: str) -> None:
    if not any(expected_fragment in item for item in items):
        raise AssertionError(f"{message}: {expected_fragment!r} not found in {items!r}")


def load_rows() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def find_record(raw_data: dict, field_name: str) -> dict:
    for record in raw_data["records"]:
        if record["field"] == field_name:
            return record
    raise AssertionError(f"record not found: {field_name}")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_sc_dictionary(path: Path) -> None:
    path.write_text(
        """
SC_close:
  required: true
  unit: CNY/barrel
  quality_checks: [missing_check, unit_check]
  fail_action: report_as_missing
SC_settlement:
  required: true
  unit: CNY/barrel
  quality_checks: [missing_check, unit_check]
  fail_action: report_as_missing
SC_volume:
  required: true
  unit: contracts
  quality_checks: [missing_check, unit_check]
  fail_action: report_as_missing
SC_open_interest:
  required: true
  unit: contracts
  quality_checks: [missing_check, unit_check]
  fail_action: report_as_missing
SC_near_price:
  required: true
  unit: CNY/barrel
  quality_checks: [missing_check, unit_check]
  fail_action: report_as_missing
SC_next_price:
  required: true
  unit: CNY/barrel
  quality_checks: [missing_check, unit_check]
  fail_action: report_as_missing
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_fixture_builds_raw_data_contract_v1() -> None:
    raw_data = build_fetch_result_from_rows(
        rows=load_rows(),
        report_date="2026-01-15",
        fetched_at="2026-01-15T16:00:00+08:00",
    )

    assert_equal(raw_data["contract_version"], RAW_DATA_CONTRACT_VERSION, "contract version")
    assert_equal(raw_data["source_name"], SOURCE_NAME, "source name")
    assert_equal(raw_data["fetcher_name"], FETCHER_NAME, "fetcher name")
    assert_equal(raw_data["fetcher_version"], FETCHER_VERSION, "fetcher version")
    assert_equal(raw_data["fetch_status"], "warning", "fixture should warn on main contract mismatch")
    assert_equal(len(raw_data["records"]), 6, "six SC fields should be emitted")


def test_lowercase_symbol_is_normalized_and_raw_symbol_preserved() -> None:
    raw_data = build_fetch_result_from_rows(load_rows(), "2026-01-15", "2026-01-15T16:00:00+08:00")
    close_record = find_record(raw_data, "SC_close")

    assert_equal(close_record["metadata"]["contract"], "SC2602", "contract should be uppercase")
    assert_equal(close_record["metadata"]["raw_symbol"], "sc2602", "raw symbol should be preserved")
    assert_equal(close_record["metadata"]["source_level"], "third_party", "source level")
    assert_equal(close_record["metadata"]["source_name"], "AKShare", "source name metadata")


def test_settlement_maps_from_settle_source_field() -> None:
    raw_data = build_fetch_result_from_rows(load_rows(), "2026-01-15", "2026-01-15T16:00:00+08:00")
    settlement_record = find_record(raw_data, "SC_settlement")

    assert_equal(settlement_record["value"], 619.8, "SC_settlement value")
    assert_equal(settlement_record["metadata"]["source_field"], "settle", "settlement source field")


def test_main_contract_uses_max_volume_and_warns_on_open_interest_mismatch() -> None:
    raw_data = build_fetch_result_from_rows(load_rows(), "2026-01-15", "2026-01-15T16:00:00+08:00")
    volume_record = find_record(raw_data, "SC_volume")
    open_interest_record = find_record(raw_data, "SC_open_interest")

    assert_equal(volume_record["metadata"]["contract"], "SC2602", "volume main contract")
    assert_equal(volume_record["value"], 15000, "main volume")
    assert_equal(open_interest_record["metadata"]["contract"], "SC2602", "open interest follows volume main")
    assert_contains(raw_data["warnings"], "differs from max open_interest", "main mismatch warning")


def test_near_next_select_recent_active_contracts_by_month() -> None:
    raw_data = build_fetch_result_from_rows(load_rows(), "2026-01-15", "2026-01-15T16:00:00+08:00")
    near_record = find_record(raw_data, "SC_near_price")
    next_record = find_record(raw_data, "SC_next_price")

    assert_equal(near_record["metadata"]["contract"], "SC2602", "near contract")
    assert_equal(next_record["metadata"]["contract"], "SC2603", "next contract")
    assert_equal(near_record["value"], 620.5, "near close")
    assert_equal(next_record["value"], 622.1, "next close")


def test_empty_rows_return_structured_fail() -> None:
    raw_data = build_fetch_result_from_rows([], "2026-01-15", "2026-01-15T16:00:00+08:00")

    assert_equal(raw_data["fetch_status"], "fail", "empty rows should fail")
    assert_equal(raw_data["records"], [], "empty rows should not emit records")
    assert_contains(raw_data["errors"], "returned no rows", "empty rows error")


def test_provider_errors_return_structured_fail_without_importing_akshare() -> None:
    def broken_provider(_report_date: str) -> list[dict]:
        raise ImportError("No module named akshare")

    raw_data = fetch_akshare_sc_daily(
        report_date="2026-01-15",
        rows_provider=broken_provider,
        fetched_at="2026-01-15T16:00:00+08:00",
    )

    assert_equal(raw_data["fetch_status"], "fail", "provider import failure should fail")
    assert_equal(raw_data["records"], [], "provider failure should not emit records")
    assert_contains(raw_data["errors"], "AKShare fetch failed", "provider failure error")


def test_raw_data_converts_to_daily_input_and_validates_with_test_dictionary() -> None:
    raw_data = build_fetch_result_from_rows(load_rows(), "2026-01-15", "2026-01-15T16:00:00+08:00")
    conversion = convert_raw_data_to_daily_input(raw_data)

    assert_equal(conversion["usable_for_pipeline"], True, "warning raw data should still be usable")
    assert_equal(conversion["conversion_errors"], [], "conversion should not error")
    assert_equal(
        conversion["daily_input"]["fields"]["SC_settlement"]["metadata"]["source_field"],
        "settle",
        "converted settlement metadata",
    )

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "daily_input.json"
        dictionary_path = root / "dictionary.yaml"
        output_path = root / "quality_report.json"
        write_json(input_path, conversion["daily_input"])
        write_sc_dictionary(dictionary_path)

        report = run_validation(
            input_path=input_path,
            data_dictionary_path=dictionary_path,
            output_path=output_path,
        )

    assert_equal(report["overall_status"], "pass", "converted AKShare SC fields should pass local dictionary")


def run() -> None:
    tests = [
        test_fixture_builds_raw_data_contract_v1,
        test_lowercase_symbol_is_normalized_and_raw_symbol_preserved,
        test_settlement_maps_from_settle_source_field,
        test_main_contract_uses_max_volume_and_warns_on_open_interest_mismatch,
        test_near_next_select_recent_active_contracts_by_month,
        test_empty_rows_return_structured_fail,
        test_provider_errors_return_structured_fail_without_importing_akshare,
        test_raw_data_converts_to_daily_input_and_validates_with_test_dictionary,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
