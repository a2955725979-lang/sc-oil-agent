"""Smoke tests for raw_data to daily_input CLI conversion.

Run from the project root:
    python tests/test_fetcher_transform_cli.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.akshare_sc import build_fetch_result_from_rows  # noqa: E402
from src.fetchers.transform import main  # noqa: E402
from src.validators.run_quality_validation import run_validation  # noqa: E402


FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "akshare_sc" / "ine_sc_rows.json"
SAMPLE_DIR = PROJECT_ROOT / "data" / "samples" / "fetchers"


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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_akshare_raw_data() -> dict:
    rows = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return build_fetch_result_from_rows(
        rows=rows,
        report_date="2026-01-15",
        fetched_at="2026-01-15T16:00:00+08:00",
    )


def write_sc_dictionary(path: Path) -> None:
    write_text(
        path,
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
    )


def test_akshare_raw_data_cli_writes_daily_input_and_validates() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw_path = root / "raw" / "akshare_sc.json"
        daily_input_path = root / "manual" / "daily_input.json"
        result_path = root / "processed" / "conversion_result.json"
        dictionary_path = root / "dictionary.yaml"
        quality_report_path = root / "quality_report.json"
        write_json(raw_path, build_akshare_raw_data())
        write_sc_dictionary(dictionary_path)

        exit_code = main(
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
        conversion_result = load_json(result_path)
        quality_report = run_validation(
            input_path=daily_input_path,
            data_dictionary_path=dictionary_path,
            output_path=quality_report_path,
        )

    assert_equal(exit_code, 0, "AKShare fixture conversion should return 0")
    assert_equal(daily_input["report_date"], "2026-01-15", "daily input report date")
    assert_equal(conversion_result["usable_for_pipeline"], True, "conversion should be usable")
    assert_equal(conversion_result["conversion_errors"], [], "conversion errors")
    assert_equal(quality_report["overall_status"], "pass", "converted daily input should validate")


def test_duplicate_field_returns_zero_and_preserves_warning() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw_path = SAMPLE_DIR / "raw_warning_duplicate_field.json"
        daily_input_path = root / "daily_input.json"
        result_path = root / "conversion_result.json"

        exit_code = main(
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
        conversion_result = load_json(result_path)
        daily_input_exists = daily_input_path.exists()

    assert_equal(exit_code, 0, "duplicate warning should still return 0")
    assert_equal(daily_input_exists, True, "daily input should be written")
    assert_equal(daily_input["fields"]["SC_close"]["value"], 620.5, "duplicate keeps first value")
    assert_contains(conversion_result["conversion_warnings"], "duplicate field", "duplicate warning")


def test_raw_fail_returns_two_and_does_not_write_daily_input() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw_path = SAMPLE_DIR / "raw_fail.json"
        daily_input_path = root / "daily_input_should_not_exist.json"
        result_path = root / "conversion_result.json"

        exit_code = main(
            [
                "--input",
                str(raw_path),
                "--output",
                str(daily_input_path),
                "--result-output",
                str(result_path),
            ]
        )
        conversion_result = load_json(result_path)
        daily_input_exists = daily_input_path.exists()

    assert_equal(exit_code, 2, "raw fail should return 2")
    assert_equal(daily_input_exists, False, "fail conversion should not write daily input")
    assert_equal(conversion_result["usable_for_pipeline"], False, "raw fail should not be usable")
    assert_equal(conversion_result["daily_input"]["fields"], {}, "raw fail should not carry fields")


def test_missing_input_or_invalid_json_returns_one() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        missing_result = root / "missing_result.json"
        invalid_path = root / "invalid.json"
        invalid_result = root / "invalid_result.json"
        write_text(invalid_path, "{not-json")

        missing_exit = main(
            [
                "--input",
                str(root / "missing.json"),
                "--result-output",
                str(missing_result),
            ]
        )
        invalid_exit = main(
            [
                "--input",
                str(invalid_path),
                "--result-output",
                str(invalid_result),
            ]
        )
        missing_result_exists = missing_result.exists()
        invalid_result_exists = invalid_result.exists()

    assert_equal(missing_exit, 1, "missing input should return 1")
    assert_equal(invalid_exit, 1, "invalid JSON should return 1")
    assert_equal(missing_result_exists, False, "missing input should not write result")
    assert_equal(invalid_result_exists, False, "invalid JSON should not write result")


def test_report_date_override_updates_daily_input() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw_path = root / "raw.json"
        daily_input_path = root / "daily_input.json"
        result_path = root / "conversion_result.json"
        write_json(raw_path, build_akshare_raw_data())

        exit_code = main(
            [
                "--input",
                str(raw_path),
                "--output",
                str(daily_input_path),
                "--result-output",
                str(result_path),
                "--report-date",
                "2026-01-16",
            ]
        )
        daily_input = load_json(daily_input_path)
        conversion_result = load_json(result_path)

    assert_equal(exit_code, 0, "override conversion should return 0")
    assert_equal(daily_input["report_date"], "2026-01-16", "daily input report date override")
    assert_equal(conversion_result["daily_input"]["report_date"], "2026-01-16", "result report date override")


def run() -> None:
    tests = [
        test_akshare_raw_data_cli_writes_daily_input_and_validates,
        test_duplicate_field_returns_zero_and_preserves_warning,
        test_raw_fail_returns_two_and_does_not_write_daily_input,
        test_missing_input_or_invalid_json_returns_one,
        test_report_date_override_updates_daily_input,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
