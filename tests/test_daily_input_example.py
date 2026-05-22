"""Regression test for the teaching daily input example.

Run from the project root:
    python tests/test_daily_input_example.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.validators.run_quality_validation import run_validation  # noqa: E402


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(items: list[str], expected_fragment: str, message: str) -> None:
    if not any(expected_fragment in item for item in items):
        raise AssertionError(f"{message}: {expected_fragment!r} not found in {items!r}")


def test_daily_input_example_stays_warning_without_failures() -> None:
    input_path = PROJECT_ROOT / "data" / "manual" / "daily_input_example.json"
    dictionary_path = PROJECT_ROOT / "config" / "data_dictionary.yaml"

    with TemporaryDirectory() as tmp:
        output_path = Path(tmp) / "quality_report_example.json"
        report = run_validation(
            input_path=input_path,
            data_dictionary_path=dictionary_path,
            output_path=output_path,
        )

    statuses = [field_result["source_status"] for field_result in report["field_results"]]

    assert_equal(report["overall_status"], "warning", "example should demonstrate warnings")
    assert_equal(report["errors"], [], "example should not produce field or structure errors")
    assert_equal(statuses.count("fail"), 0, "example should not contain failing fields")
    assert_equal("pass" in statuses, True, "example should contain passing fields")
    assert_equal("warning" in statuses, True, "example should contain warning fields")
    assert_contains(
        report["warnings"],
        "Oman_price_experimental",
        "extra undefined field warning should be preserved",
    )
    assert_contains(
        report["warnings"],
        "source_conflict_check",
        "OPEC/IEA placeholder warning should be preserved",
    )


def run() -> None:
    tests = [test_daily_input_example_stays_warning_without_failures]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
