"""Smoke tests for src/fetchers/default_fields.py.

Run from the project root:
    python tests/test_default_fields.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.base import DAILY_INPUT_SCHEMA_VERSION, validate_daily_input_schema  # noqa: E402
from src.fetchers.default_fields import DEFAULT_TEXTS, build_default_daily_input, main  # noqa: E402


REPORT_DATE = "2026-05-22"
FETCHED_AT = "2026-05-22T16:40:00+08:00"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_default_text_fields_are_complete_and_warning_low_confidence() -> None:
    daily_input = build_default_daily_input(REPORT_DATE, FETCHED_AT)

    assert_equal(daily_input["schema_version"], DAILY_INPUT_SCHEMA_VERSION, "schema version")
    assert_equal(validate_daily_input_schema(daily_input, require_version=True), [], "schema validation errors")
    assert_equal(sorted(daily_input["fields"].keys()), sorted(DEFAULT_TEXTS.keys()), "default fields")

    for field_name, field_data in daily_input["fields"].items():
        metadata = field_data["metadata"]
        assert_equal("不得用于强结论" in field_data["value"], True, f"{field_name} conservative text")
        assert_equal(metadata["source_level"], "derived", f"{field_name} source_level")
        assert_equal(metadata["source_status"], "warning", f"{field_name} source_status")
        assert_equal(metadata["confidence"], "low", f"{field_name} confidence")
        assert_equal(metadata["fetched_at"], FETCHED_AT, f"{field_name} fetched_at")


def test_cli_writes_daily_input() -> None:
    with TemporaryDirectory() as tmp:
        output_path = Path(tmp) / "default_fields.json"
        exit_code = main(["--report-date", REPORT_DATE, "--output", str(output_path)])
        daily_input = load_json(output_path)

    assert_equal(exit_code, 0, "CLI exit code")
    assert_equal(daily_input["report_date"], REPORT_DATE, "CLI report date")
    assert_equal(daily_input["schema_version"], DAILY_INPUT_SCHEMA_VERSION, "CLI schema version")


def run() -> None:
    tests = [
        test_default_text_fields_are_complete_and_warning_low_confidence,
        test_cli_writes_daily_input,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
