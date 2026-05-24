"""Freeze tests for raw_data_contract_v1 and daily_input_schema_v1.

Run from the project root:
    python tests/test_contract_freeze.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.akshare_sc import build_fetch_result_from_rows  # noqa: E402
from src.fetchers.base import (  # noqa: E402
    DAILY_INPUT_SCHEMA_VERSION,
    DAILY_INPUT_TOP_LEVEL_KEYS,
    RAW_DATA_CONTRACT_VERSION,
    RAW_DATA_TOP_LEVEL_KEYS,
    FetchResult,
    RawDataRecord,
    validate_daily_input_schema,
    validate_raw_data_contract,
)
from src.fetchers.transform import main as transform_main  # noqa: E402


FETCHER_SAMPLE_DIR = PROJECT_ROOT / "data" / "samples" / "fetchers"
VALIDATION_SAMPLE_DIR = PROJECT_ROOT / "data" / "samples" / "validation"
AKSHARE_FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "akshare_sc" / "ine_sc_rows.json"


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


def test_contract_version_constants_are_frozen() -> None:
    assert_equal(RAW_DATA_CONTRACT_VERSION, "raw_data_contract_v1", "raw_data contract version")
    assert_equal(DAILY_INPUT_SCHEMA_VERSION, "daily_input_schema_v1", "daily_input schema version")


def test_fetch_result_top_level_keys_are_frozen() -> None:
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

    assert_equal(tuple(payload.keys()), RAW_DATA_TOP_LEVEL_KEYS, "raw_data top-level keys")
    assert_equal(validate_raw_data_contract(payload), [], "serialized raw_data should validate")


def test_raw_data_samples_validate_against_frozen_contract() -> None:
    for sample_name in ("raw_pass.json", "raw_warning_duplicate_field.json", "raw_fail.json"):
        raw_data = load_json(FETCHER_SAMPLE_DIR / sample_name)
        assert_equal(validate_raw_data_contract(raw_data), [], f"{sample_name} contract errors")


def test_akshare_fixture_output_validates_against_frozen_contract() -> None:
    rows = load_json(AKSHARE_FIXTURE_PATH)
    raw_data = build_fetch_result_from_rows(
        rows=rows,
        report_date="2026-01-15",
        fetched_at="2026-01-15T16:00:00+08:00",
    )

    assert_equal(validate_raw_data_contract(raw_data), [], "AKShare fixture raw_data contract errors")


def test_transform_cli_writes_versioned_daily_input_schema() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw_path = root / "raw.json"
        daily_input_path = root / "daily_input.json"
        result_path = root / "conversion_result.json"
        write_json(raw_path, load_json(FETCHER_SAMPLE_DIR / "raw_pass.json"))

        exit_code = transform_main(
            [
                "--input",
                str(raw_path),
                "--output",
                str(daily_input_path),
                "--result-output",
                str(result_path),
            ]
        )
        daily_input = load_json(daily_input_path)

    assert_equal(exit_code, 0, "transform CLI exit code")
    assert_equal(tuple(daily_input.keys()), DAILY_INPUT_TOP_LEVEL_KEYS, "daily_input top-level keys")
    assert_equal(daily_input["schema_version"], DAILY_INPUT_SCHEMA_VERSION, "daily_input schema_version")
    assert_equal(validate_daily_input_schema(daily_input, require_version=True), [], "daily_input schema errors")


def test_validation_samples_validate_against_frozen_daily_input_schema() -> None:
    for sample_name in ("pass_input.json", "warning_input.json", "fail_input.json"):
        daily_input = load_json(VALIDATION_SAMPLE_DIR / sample_name)
        assert_equal(
            validate_daily_input_schema(daily_input, require_version=True),
            [],
            f"{sample_name} schema errors",
        )


def test_legacy_daily_input_without_schema_version_remains_compatible() -> None:
    daily_input = {
        "report_date": "2026-05-22",
        "context": {},
        "fields": {
            "SC_close": {
                "value": 620.5,
                "metadata": {"unit": "CNY/barrel"},
            }
        },
    }

    assert_equal(validate_daily_input_schema(daily_input), [], "legacy daily_input should remain compatible")
    assert_contains(
        validate_daily_input_schema(daily_input, require_version=True),
        "schema_version",
        "strict schema should require version",
    )


def test_contract_validator_rejects_missing_required_raw_data_key() -> None:
    raw_data = load_json(FETCHER_SAMPLE_DIR / "raw_pass.json")
    raw_data.pop("fetcher_name")

    errors = validate_raw_data_contract(raw_data)

    assert_contains(errors, "fetcher_name", "missing fetcher_name should be rejected")


def test_contract_validator_rejects_invalid_fetch_status() -> None:
    raw_data = load_json(FETCHER_SAMPLE_DIR / "raw_pass.json")
    raw_data["fetch_status"] = "partial"

    errors = validate_raw_data_contract(raw_data)

    assert_contains(errors, "fetch_status", "invalid fetch_status should be rejected")


def test_contract_validator_rejects_invalid_source_level() -> None:
    raw_data = load_json(FETCHER_SAMPLE_DIR / "raw_pass.json")
    raw_data["records"][0]["metadata"]["source_level"] = "unknown_source"

    errors = validate_raw_data_contract(raw_data)

    assert_contains(errors, "invalid source_level", "invalid source_level should be rejected")


def run() -> None:
    tests = [
        test_contract_version_constants_are_frozen,
        test_fetch_result_top_level_keys_are_frozen,
        test_raw_data_samples_validate_against_frozen_contract,
        test_akshare_fixture_output_validates_against_frozen_contract,
        test_transform_cli_writes_versioned_daily_input_schema,
        test_validation_samples_validate_against_frozen_daily_input_schema,
        test_legacy_daily_input_without_schema_version_remains_compatible,
        test_contract_validator_rejects_missing_required_raw_data_key,
        test_contract_validator_rejects_invalid_fetch_status,
        test_contract_validator_rejects_invalid_source_level,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
