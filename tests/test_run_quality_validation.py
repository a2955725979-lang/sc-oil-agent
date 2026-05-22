"""Smoke tests for the daily batch quality validation entrypoint.

Run from the project root:
    python tests/test_run_quality_validation.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.validators.run_quality_validation import (  # noqa: E402
    build_default_input_path,
    main,
    run_validation,
    validate_daily_input,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(items: list[str], expected_fragment: str, message: str) -> None:
    if not any(expected_fragment in item for item in items):
        raise AssertionError(f"{message}: {expected_fragment!r} not found in {items!r}")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def minimal_dictionary_yaml() -> str:
    return """
SC_close:
  required: true
  unit: CNY/barrel
  frequency: daily
  quality_checks: [missing_check, range_check, unit_check]
  fail_action: report_as_missing
Brent_close:
  required: true
  unit: USD/barrel
  frequency: daily
  quality_checks: [missing_check]
  fail_action: use_latest_with_warning
SC_Brent_spread_simple:
  required: true
  unit: USD/barrel
  frequency: daily
  quality_checks: [missing_check, spread_check, unit_check]
  fail_action: skip_calculation
"""


def test_missing_fields_object_fails_without_field_results() -> None:
    report = validate_daily_input(
        daily_input={"report_date": "2026-05-22"},
        data_dictionary={"SC_close": {"required": True}},
        report_date="2026-05-22",
        input_path="input.json",
        data_dictionary_path="dictionary.yaml",
    )
    assert_equal(report["overall_status"], "fail", "missing fields should fail")
    assert_equal(report["field_results"], [], "structure errors should not expand fields")
    assert_contains(report["errors"], "fields object", "structure error should be explicit")


def test_fields_wrong_type_fails_without_field_results() -> None:
    report = validate_daily_input(
        daily_input={"report_date": "2026-05-22", "fields": []},
        data_dictionary={"SC_close": {"required": True}},
        report_date="2026-05-22",
        input_path="input.json",
        data_dictionary_path="dictionary.yaml",
    )
    assert_equal(report["overall_status"], "fail", "non-object fields should fail")
    assert_equal(report["field_results"], [], "structure errors should not expand fields")


def test_output_directory_is_created_and_report_is_readable() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "input.json"
        dictionary_path = root / "dictionary.yaml"
        output_path = root / "nested" / "quality" / "report.json"

        write_text(dictionary_path, minimal_dictionary_yaml())
        write_json(
            input_path,
            {
                "report_date": "2026-05-22",
                "fields": {
                    "SC_close": {
                        "value": 620.5,
                        "metadata": {"unit": "CNY/barrel", "date": "2026-05-22"},
                    },
                    "Brent_close": {
                        "value": 82.0,
                        "metadata": {"unit": "USD/barrel", "date": "2026-05-22"},
                    },
                    "SC_Brent_spread_simple": {
                        "value": 4.2,
                        "metadata": {
                            "unit": "USD/barrel",
                            "sc_date": "2026-05-22",
                            "external_date": "2026-05-22",
                            "fx_date": "2026-05-22",
                        },
                    },
                },
            },
        )

        report = run_validation(input_path, dictionary_path, output_path=output_path)
        saved_report = json.loads(output_path.read_text(encoding="utf-8"))

    assert_equal(report["overall_status"], "pass", "all valid fields should pass")
    assert_equal(saved_report["overall_status"], "pass", "saved report should be readable")
    assert_equal(
        saved_report["input_path"],
        str(input_path.resolve()),
        "report should keep input path",
    )
    assert_equal(
        saved_report["data_dictionary_path"],
        str(dictionary_path.resolve()),
        "report should keep dictionary path",
    )


def test_dictionary_driven_missing_required_field_fails() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "input.json"
        dictionary_path = root / "dictionary.yaml"
        output_path = root / "report.json"

        write_text(dictionary_path, minimal_dictionary_yaml())
        write_json(input_path, {"report_date": "2026-05-22", "fields": {}})

        report = run_validation(input_path, dictionary_path, output_path=output_path)

    assert_equal(report["overall_status"], "fail", "missing required fields should fail")
    assert_contains(report["errors"], "SC_close", "missing SC_close should be reported")


def test_downgradable_missing_field_warns() -> None:
    report = validate_daily_input(
        daily_input={
            "report_date": "2026-05-22",
            "fields": {
                "SC_close": {
                    "value": 620.5,
                    "metadata": {"unit": "CNY/barrel"},
                },
                "SC_Brent_spread_simple": {
                    "value": 4.2,
                    "metadata": {"unit": "USD/barrel"},
                },
            },
        },
        data_dictionary={
            "SC_close": {
                "required": True,
                "unit": "CNY/barrel",
                "quality_checks": ["missing_check", "unit_check"],
                "fail_action": "report_as_missing",
            },
            "Brent_close": {
                "required": True,
                "quality_checks": ["missing_check"],
                "fail_action": "use_latest_with_warning",
            },
            "SC_Brent_spread_simple": {
                "required": True,
                "unit": "USD/barrel",
                "quality_checks": ["missing_check", "unit_check"],
                "fail_action": "skip_calculation",
            },
        },
        report_date="2026-05-22",
        input_path="input.json",
        data_dictionary_path="dictionary.yaml",
    )
    assert_equal(report["overall_status"], "warning", "downgradable missing field should warn")
    assert_contains(report["warnings"], "Brent_close", "Brent warning should be reported")


def test_unit_mismatch_fails() -> None:
    report = validate_daily_input(
        daily_input={
            "report_date": "2026-05-22",
            "fields": {
                "SC_close": {
                    "value": 620.5,
                    "metadata": {"unit": "USD/barrel"},
                }
            },
        },
        data_dictionary={
            "SC_close": {
                "required": True,
                "unit": "CNY/barrel",
                "quality_checks": ["missing_check", "unit_check"],
                "fail_action": "report_as_missing",
            }
        },
        report_date="2026-05-22",
        input_path="input.json",
        data_dictionary_path="dictionary.yaml",
    )
    assert_equal(report["overall_status"], "fail", "unit mismatch should fail")
    assert_contains(report["errors"], "unit mismatch", "unit mismatch should be reported")


def test_spread_date_mismatch_warns() -> None:
    report = validate_daily_input(
        daily_input={
            "report_date": "2026-05-22",
            "fields": {
                "SC_Brent_spread_simple": {
                    "value": 4.2,
                    "metadata": {
                        "unit": "USD/barrel",
                        "sc_date": "2026-05-22",
                        "external_date": "2026-05-21",
                        "fx_date": "2026-05-22",
                    },
                }
            },
        },
        data_dictionary={
            "SC_Brent_spread_simple": {
                "required": True,
                "unit": "USD/barrel",
                "quality_checks": ["missing_check", "spread_check", "unit_check"],
                "fail_action": "skip_calculation",
            }
        },
        report_date="2026-05-22",
        input_path="input.json",
        data_dictionary_path="dictionary.yaml",
    )
    assert_equal(report["overall_status"], "warning", "spread date mismatch should warn")
    assert_contains(report["warnings"], "date inputs", "spread date warning should be reported")


def test_extra_field_warns_without_failing() -> None:
    report = validate_daily_input(
        daily_input={
            "report_date": "2026-05-22",
            "fields": {
                "SC_close": {
                    "value": 620.5,
                    "metadata": {"unit": "CNY/barrel"},
                },
                "Oman_price_experimental": {
                    "value": 81.2,
                    "metadata": {"unit": "USD/barrel"},
                },
            },
        },
        data_dictionary={
            "SC_close": {
                "required": True,
                "unit": "CNY/barrel",
                "quality_checks": ["missing_check", "unit_check"],
                "fail_action": "report_as_missing",
            }
        },
        report_date="2026-05-22",
        input_path="input.json",
        data_dictionary_path="dictionary.yaml",
    )
    assert_equal(report["overall_status"], "warning", "extra field should warn")
    assert_contains(report["warnings"], "Oman_price_experimental", "extra field should be named")
    assert_equal(report["errors"], [], "extra field should not fail")


def test_context_required_for_topic_is_passed_through() -> None:
    report = validate_daily_input(
        daily_input={
            "report_date": "2026-05-22",
            "context": {"required_for_topic": ["OPEC_monthly_summary"]},
            "fields": {},
        },
        data_dictionary={
            "OPEC_monthly_summary": {
                "required": False,
                "quality_checks": ["missing_check"],
                "fail_action": "mark_missing",
            }
        },
        report_date="2026-05-22",
        input_path="input.json",
        data_dictionary_path="dictionary.yaml",
    )
    assert_equal(report["overall_status"], "fail", "topic-required missing field should fail")
    assert_contains(report["errors"], "required for current topic", "context should affect checks")


def test_default_input_path_uses_report_date() -> None:
    path = build_default_input_path("2026-05-22")
    assert_equal(
        path.as_posix().endswith("data/manual/daily_input_2026-05-22.json"),
        True,
        "default input path should include report date",
    )


def test_cli_runs_with_custom_paths() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "input.json"
        dictionary_path = root / "dictionary.yaml"
        output_path = root / "output" / "quality.json"

        write_text(
            dictionary_path,
            """
SC_close:
  required: true
  unit: CNY/barrel
  quality_checks: [missing_check, unit_check]
  fail_action: report_as_missing
""",
        )
        write_json(
            input_path,
            {
                "report_date": "2026-05-21",
                "fields": {
                    "SC_close": {
                        "value": 620.5,
                        "metadata": {"unit": "CNY/barrel"},
                    }
                },
            },
        )

        exit_code = main(
            [
                "--report-date",
                "2026-05-22",
                "--input",
                str(input_path),
                "--dictionary",
                str(dictionary_path),
                "--output",
                str(output_path),
            ]
        )
        saved_report = json.loads(output_path.read_text(encoding="utf-8"))

    assert_equal(exit_code, 0, "CLI should return success")
    assert_equal(saved_report["report_date"], "2026-05-22", "CLI report date should win")
    assert_equal(saved_report["overall_status"], "pass", "CLI validation should pass")


def run() -> None:
    tests = [
        test_missing_fields_object_fails_without_field_results,
        test_fields_wrong_type_fails_without_field_results,
        test_output_directory_is_created_and_report_is_readable,
        test_dictionary_driven_missing_required_field_fails,
        test_downgradable_missing_field_warns,
        test_unit_mismatch_fails,
        test_spread_date_mismatch_warns,
        test_extra_field_warns_without_failing,
        test_context_required_for_topic_is_passed_through,
        test_default_input_path_uses_report_date,
        test_cli_runs_with_custom_paths,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
