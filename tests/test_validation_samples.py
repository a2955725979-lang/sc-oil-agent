"""Regression tests for test-only validation samples.

Run from the project root:
    python tests/test_validation_samples.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.validators.run_quality_validation import run_validation  # noqa: E402


SAMPLE_DIR = PROJECT_ROOT / "data" / "samples" / "validation"
PASS_FIELDS = {
    "SC_close",
    "SC_near_price",
    "SC_next_price",
    "USD_CNY",
    "Brent_close",
    "WTI_close",
    "SC_USD",
    "SC_calendar_spread",
    "SC_Brent_spread_simple",
    "SC_WTI_spread_simple",
}


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(items: list[str], expected_fragment: str, message: str) -> None:
    if not any(expected_fragment in item for item in items):
        raise AssertionError(f"{message}: {expected_fragment!r} not found in {items!r}")


def sample_report(name: str) -> dict:
    with TemporaryDirectory() as tmp:
        output_path = Path(tmp) / f"{name}_quality_report.json"
        return run_validation(
            input_path=SAMPLE_DIR / f"{name}_input.json",
            data_dictionary_path=SAMPLE_DIR / f"{name}_dictionary.yaml",
            output_path=output_path,
        )


def fields_by_name(report: dict) -> dict[str, dict]:
    return {field_result["field"]: field_result for field_result in report["field_results"]}


def test_pass_sample_is_stable_pass() -> None:
    report = sample_report("pass")
    statuses = [field_result["source_status"] for field_result in report["field_results"]]
    fields = fields_by_name(report)

    assert_equal(report["overall_status"], "pass", "pass sample should pass")
    assert_equal(report["warnings"], [], "pass sample should not warn")
    assert_equal(report["errors"], [], "pass sample should not error")
    assert_equal(set(fields), PASS_FIELDS, "pass sample should cover the full local calculation chain")
    assert_equal(set(statuses), {"pass"}, "all pass sample fields should pass")


def test_warning_sample_is_stable_warning_without_errors() -> None:
    report = sample_report("warning")
    fields = fields_by_name(report)

    assert_equal(report["overall_status"], "warning", "warning sample should warn")
    assert_equal(report["errors"], [], "warning sample should not error")
    assert_equal(fields["SC_close"]["source_status"], "pass", "control field should pass")
    assert_equal(fields["important_oil_news"]["source_status"], "warning", "news field should warn")
    assert_contains(report["warnings"], "timezone", "warning should be a controlled timezone warning")


def test_fail_sample_is_stable_fail() -> None:
    report = sample_report("fail")
    fields = fields_by_name(report)

    assert_equal(report["overall_status"], "fail", "fail sample should fail")
    assert_equal(report["warnings"], [], "fail sample should not warn")
    assert_equal(fields["SC_close"]["source_status"], "fail", "missing required SC_close should fail")
    assert_contains(report["errors"], "SC_close", "fail sample should report SC_close error")


def test_sample_readme_rejects_market_use() -> None:
    readme = (SAMPLE_DIR / "README.md").read_text(encoding="utf-8")
    assert_equal("not real market data" in readme, True, "sample README should reject market data use")
    assert_equal("must not be used for research, trading, or market judgment" in readme, True, "sample README should reject research/trading use")


def run() -> None:
    tests = [
        test_pass_sample_is_stable_pass,
        test_warning_sample_is_stable_warning_without_errors,
        test_fail_sample_is_stable_fail,
        test_sample_readme_rejects_market_use,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
