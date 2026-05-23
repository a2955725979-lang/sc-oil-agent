"""Smoke tests for fetcher raw_data contract v1.

Run from the project root:
    python tests/test_fetcher_contract.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.base import (  # noqa: E402
    RAW_DATA_CONTRACT_VERSION,
    FetchResult,
    RawDataRecord,
)
from src.fetchers.transform import convert_raw_data_to_daily_input  # noqa: E402
from src.validators.run_quality_validation import run_validation  # noqa: E402


SAMPLE_DIR = PROJECT_ROOT / "data" / "samples" / "fetchers"
VALIDATION_SAMPLE_DIR = PROJECT_ROOT / "data" / "samples" / "validation"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(items: list[str], expected_fragment: str, message: str) -> None:
    if not any(expected_fragment in item for item in items):
        raise AssertionError(f"{message}: {expected_fragment!r} not found in {items!r}")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_fetch_result_serializes_contract_v1() -> None:
    result = FetchResult(
        report_date="2026-05-22",
        source_name="sample_source",
        fetcher_name="sample_fetcher",
        fetcher_version="fetcher_contract_v1",
        fetched_at="2026-05-22T16:00:00+08:00",
        fetch_status="pass",
        records=(
            RawDataRecord(
                field="SC_close",
                value=620.5,
                metadata={
                    "unit": "CNY/barrel",
                    "date": "2026-05-22",
                    "timezone": "Asia/Shanghai",
                    "source_level": "test",
                },
                raw_payload={"close": 620.5},
            ),
        ),
    )

    payload = result.to_dict()

    assert_equal(payload["contract_version"], RAW_DATA_CONTRACT_VERSION, "contract version")
    assert_equal(payload["fetch_status"], "pass", "fetch status")
    assert_equal(payload["records"][0]["field"], "SC_close", "record field")
    assert_equal(payload["warnings"], [], "warnings list")
    assert_equal(payload["errors"], [], "errors list")


def test_raw_pass_converts_to_daily_input_and_validates() -> None:
    raw_data = load_json(SAMPLE_DIR / "raw_pass.json")
    conversion = convert_raw_data_to_daily_input(raw_data)

    assert_equal(conversion["usable_for_pipeline"], True, "pass raw data should be usable")
    assert_equal(conversion["conversion_warnings"], [], "pass raw data should not warn")
    assert_equal(conversion["conversion_errors"], [], "pass raw data should not error")
    assert_equal(
        conversion["daily_input"]["fields"]["SC_close"]["metadata"]["fetcher_name"],
        "sample_fetcher",
        "metadata should be enriched with fetcher_name",
    )

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "daily_input_from_raw.json"
        output_path = root / "quality_report.json"
        write_json(input_path, conversion["daily_input"])
        report = run_validation(
            input_path=input_path,
            data_dictionary_path=VALIDATION_SAMPLE_DIR / "pass_dictionary.yaml",
            output_path=output_path,
        )

    assert_equal(report["overall_status"], "pass", "converted pass raw data should validate")


def test_duplicate_field_warns_and_keeps_first_record() -> None:
    raw_data = load_json(SAMPLE_DIR / "raw_warning_duplicate_field.json")
    conversion = convert_raw_data_to_daily_input(raw_data)

    assert_equal(conversion["usable_for_pipeline"], True, "duplicate warning should still be usable")
    assert_contains(conversion["conversion_warnings"], "duplicate field", "duplicate should warn")
    assert_equal(
        conversion["daily_input"]["fields"]["SC_close"]["value"],
        620.5,
        "duplicate field should keep first value",
    )


def test_raw_fail_is_not_usable_for_pipeline() -> None:
    raw_data = load_json(SAMPLE_DIR / "raw_fail.json")
    conversion = convert_raw_data_to_daily_input(raw_data)

    assert_equal(conversion["usable_for_pipeline"], False, "fetch_status=fail should not be usable")
    assert_equal(conversion["daily_input"]["fields"], {}, "raw fail sample should not provide fields")


def test_invalid_source_level_becomes_conversion_error() -> None:
    raw_data = load_json(SAMPLE_DIR / "raw_warning_duplicate_field.json")
    raw_data["records"] = [
        {
            "field": "SC_close",
            "value": 620.5,
            "metadata": {
                "unit": "CNY/barrel",
                "date": "2026-05-22",
                "source_level": "unknown_source_level",
            },
            "raw_payload": {},
        }
    ]
    conversion = convert_raw_data_to_daily_input(raw_data)

    assert_equal(conversion["usable_for_pipeline"], False, "invalid source_level should block pipeline use")
    assert_contains(conversion["conversion_errors"], "invalid source_level", "source_level error should be explicit")


def test_missing_records_or_record_fields_become_conversion_errors() -> None:
    missing_records = {
        "contract_version": RAW_DATA_CONTRACT_VERSION,
        "report_date": "2026-05-22",
        "source_name": "sample_source",
        "fetcher_name": "sample_fetcher",
        "fetcher_version": "fetcher_contract_v1",
        "fetched_at": "2026-05-22T16:00:00+08:00",
        "fetch_status": "pass",
        "warnings": [],
        "errors": [],
    }
    bad_record = dict(missing_records)
    bad_record["records"] = [{"field": "SC_close", "metadata": {"source_level": "test"}}]

    missing_records_result = convert_raw_data_to_daily_input(missing_records)
    bad_record_result = convert_raw_data_to_daily_input(bad_record)

    assert_equal(missing_records_result["usable_for_pipeline"], False, "missing records should block pipeline use")
    assert_contains(missing_records_result["conversion_errors"], "records must be a list", "records error")
    assert_equal(bad_record_result["usable_for_pipeline"], False, "missing value should block pipeline use")
    assert_contains(bad_record_result["conversion_errors"], "missing value", "missing value error")


def test_sample_readme_rejects_market_use() -> None:
    readme = (SAMPLE_DIR / "README.md").read_text(encoding="utf-8")
    assert_equal("not real market data" in readme, True, "sample README should reject market data use")
    assert_equal("must not be used for research, trading, or market judgment" in readme, True, "sample README should reject research/trading use")


def run() -> None:
    tests = [
        test_fetch_result_serializes_contract_v1,
        test_raw_pass_converts_to_daily_input_and_validates,
        test_duplicate_field_warns_and_keeps_first_record,
        test_raw_fail_is_not_usable_for_pipeline,
        test_invalid_source_level_becomes_conversion_error,
        test_missing_records_or_record_fields_become_conversion_errors,
        test_sample_readme_rejects_market_use,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
