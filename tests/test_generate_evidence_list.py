"""Smoke tests for field-level Evidence List v1.

Run from the project root:
    python tests/test_generate_evidence_list.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evidence.generate_evidence_list import generate_evidence_list, main  # noqa: E402
from src.validators.run_quality_validation import run_validation  # noqa: E402


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_not_equal(actual, unexpected, message: str) -> None:
    if actual == unexpected:
        raise AssertionError(f"{message}: unexpected {unexpected!r}")


def assert_contains(items: list[str], expected_fragment: str, message: str) -> None:
    if not any(expected_fragment in item for item in items):
        raise AssertionError(f"{message}: {expected_fragment!r} not found in {items!r}")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def by_field(evidence_items: list[dict]) -> dict[str, dict]:
    return {item["field"]: item for item in evidence_items}


def test_example_generates_typed_field_level_evidence() -> None:
    input_path = PROJECT_ROOT / "data" / "manual" / "daily_input_example.json"
    dictionary_path = PROJECT_ROOT / "config" / "data_dictionary.yaml"

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        quality_report_path = root / "quality_report_example.json"
        evidence_output_path = root / "evidence_list_example.json"

        run_validation(
            input_path=input_path,
            data_dictionary_path=dictionary_path,
            output_path=quality_report_path,
        )
        report = generate_evidence_list(
            daily_input_path=input_path,
            quality_report_path=quality_report_path,
            output_path=evidence_output_path,
            data_snapshot_id="SNAP-EXAMPLE-001",
        )
        saved_report = json.loads(evidence_output_path.read_text(encoding="utf-8"))

    items = saved_report["evidence_list"]
    fields = by_field(items)

    assert_equal(report, saved_report, "saved evidence report should match returned report")
    assert_equal(saved_report["evidence_scope"], "field_level_only", "scope should be field-level only")
    assert_contains(
        saved_report["limitations"],
        "not conclusion-level",
        "limitations should reject conclusion-level use",
    )
    assert_equal(fields["SC_close"]["source_status"], "pass", "pass field should be kept")
    assert_equal(fields["SC_close"]["evidence_type"], "validated_field", "ordinary field type")
    assert_equal(fields["SC_calendar_spread"]["evidence_type"], "calculated_indicator", "spread type")
    assert_equal(
        fields["OPEC_monthly_summary"]["evidence_type"],
        "monthly_report_summary",
        "monthly report type",
    )
    assert_equal(fields["exchange_notice"]["evidence_type"], "exchange_notice", "notice type")
    assert_equal(fields["important_oil_news"]["evidence_type"], "important_news", "news type")
    assert_equal(fields["manual_notes"]["evidence_type"], "manual_note", "manual note type")
    assert_equal(fields["OPEC_monthly_summary"]["source_status"], "warning", "warning field kept")
    assert_not_equal(fields["OPEC_monthly_summary"]["confidence"], "high", "warning confidence not high")
    assert_contains(
        saved_report["skipped_fields"],
        "Oman_price_experimental",
        "extra field should be skipped",
    )
    assert_equal(
        items[0]["evidence_id"],
        "EVID-20260522-001",
        "evidence id should be stable for the same input field order",
    )


def test_fail_fields_do_not_generate_evidence() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "daily_input.json"
        quality_report_path = root / "quality_report.json"
        output_path = root / "evidence_list.json"

        write_json(
            input_path,
            {
                "report_date": "2026-05-22",
                "fields": {
                    "SC_close": {"value": 620.5, "metadata": {"unit": "CNY/barrel"}},
                    "Brent_close": {"value": 82.0, "metadata": {"unit": "USD/barrel"}},
                },
            },
        )
        write_json(
            quality_report_path,
            {
                "report_date": "2026-05-22",
                "overall_status": "fail",
                "field_results": [
                    {
                        "field": "SC_close",
                        "source_status": "fail",
                        "warnings": [],
                        "errors": ["unit mismatch"],
                    },
                    {
                        "field": "Brent_close",
                        "source_status": "pass",
                        "warnings": [],
                        "errors": [],
                    },
                ],
                "warnings": [],
                "errors": ["SC_close: unit mismatch"],
            },
        )

        report = generate_evidence_list(input_path, quality_report_path, output_path=output_path)

    fields = by_field(report["evidence_list"])
    assert_equal("SC_close" in fields, False, "fail field should be skipped")
    assert_equal(fields["Brent_close"]["evidence_id"], "EVID-20260522-001", "ids should skip fail fields")
    assert_contains(report["skipped_fields"], "SC_close: source_status=fail", "fail skip should be recorded")


def test_cli_generates_evidence_list_with_custom_paths() -> None:
    input_path = PROJECT_ROOT / "data" / "manual" / "daily_input_example.json"
    dictionary_path = PROJECT_ROOT / "config" / "data_dictionary.yaml"

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        quality_report_path = root / "quality_report_example.json"
        evidence_output_path = root / "nested" / "evidence_list_example.json"

        run_validation(
            input_path=input_path,
            data_dictionary_path=dictionary_path,
            output_path=quality_report_path,
        )
        exit_code = main(
            [
                "--daily-input",
                str(input_path),
                "--quality-report",
                str(quality_report_path),
                "--output",
                str(evidence_output_path),
                "--data-snapshot-id",
                "SNAP-EXAMPLE-CLI",
            ]
        )
        saved_report = json.loads(evidence_output_path.read_text(encoding="utf-8"))

    assert_equal(exit_code, 0, "CLI should return success")
    assert_equal(saved_report["data_snapshot_id"], "SNAP-EXAMPLE-CLI", "snapshot id should be saved")


def run() -> None:
    tests = [
        test_example_generates_typed_field_level_evidence,
        test_fail_fields_do_not_generate_evidence,
        test_cli_generates_evidence_list_with_custom_paths,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
