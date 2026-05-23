"""Smoke tests for src/calculators/spreads.py.

Run from the project root:
    python tests/test_spreads.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.calculators.spreads import calculate_spreads, calculate_spreads_file, main  # noqa: E402


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(items: list[str], expected_fragment: str, message: str) -> None:
    if not any(expected_fragment in item for item in items):
        raise AssertionError(f"{message}: {expected_fragment!r} not found in {items!r}")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def base_input(include_existing_spreads: bool = False) -> dict:
    fields = {
        "SC_close": {
            "value": 620.5,
            "metadata": {"unit": "CNY/barrel", "date": "2026-05-22", "timezone": "Asia/Shanghai"},
        },
        "SC_near_price": {
            "value": 621.0,
            "metadata": {"unit": "CNY/barrel", "date": "2026-05-22", "timezone": "Asia/Shanghai"},
        },
        "SC_next_price": {
            "value": 617.2,
            "metadata": {"unit": "CNY/barrel", "date": "2026-05-22", "timezone": "Asia/Shanghai"},
        },
        "USD_CNY": {
            "value": 7.18,
            "metadata": {"unit": "CNY/USD", "date": "2026-05-22", "timezone": "Asia/Shanghai"},
        },
        "Brent_close": {
            "value": 82.4,
            "metadata": {"unit": "USD/barrel", "date": "2026-05-22", "timezone": "Europe/London"},
        },
        "WTI_close": {
            "value": 78.6,
            "metadata": {"unit": "USD/barrel", "date": "2026-05-22", "timezone": "America/New_York"},
        },
    }
    if include_existing_spreads:
        fields["SC_calendar_spread"] = {
            "value": 99.0,
            "metadata": {"unit": "CNY/barrel", "date": "2026-05-22"},
        }
        fields["SC_Brent_spread_simple"] = {
            "value": 99.0,
            "metadata": {"unit": "USD/barrel", "date": "2026-05-22"},
        }
        fields["SC_WTI_spread_simple"] = {
            "value": 99.0,
            "metadata": {"unit": "USD/barrel", "date": "2026-05-22"},
        }
    return {
        "report_date": "2026-05-22",
        "context": {"required_for_topic": []},
        "fields": fields,
    }


def warnings_from(data: dict) -> list[str]:
    warnings = data["context"].get("calculation_warnings", [])
    return warnings if isinstance(warnings, list) else []


def test_calculates_calendar_and_external_spreads() -> None:
    data = calculate_spreads(base_input())
    fields = data["fields"]

    assert_equal(fields["SC_calendar_spread"]["value"], 3.8, "calendar spread")
    assert_equal(fields["SC_Brent_spread_simple"]["value"], 4.0206, "SC-Brent spread")
    assert_equal(fields["SC_WTI_spread_simple"]["value"], 7.8206, "SC-WTI spread")
    assert_equal(
        fields["SC_Brent_spread_simple"]["metadata"]["calculation_method"],
        "simple_fx_adjusted_v1",
        "calculation method",
    )
    assert_equal(
        fields["SC_Brent_spread_simple"]["metadata"]["calculation_inputs"],
        ["SC_close", "USD_CNY", "Brent_close"],
        "calculation inputs",
    )
    assert_equal(
        fields["SC_calendar_spread"]["metadata"]["near_field"],
        "SC_near_price",
        "near field metadata",
    )


def test_default_does_not_overwrite_existing_fields() -> None:
    data = calculate_spreads(base_input(include_existing_spreads=True))
    fields = data["fields"]

    assert_equal(fields["SC_calendar_spread"]["value"], 99.0, "existing calendar spread preserved")
    assert_equal(fields["SC_Brent_spread_simple"]["value"], 99.0, "existing Brent spread preserved")
    assert_equal(fields["SC_WTI_spread_simple"]["value"], 99.0, "existing WTI spread preserved")
    assert_contains(warnings_from(data), "SC_calendar_spread: skipped existing field", "skip warning")


def test_overwrite_recalculates_existing_fields() -> None:
    data = calculate_spreads(base_input(include_existing_spreads=True), overwrite=True)
    fields = data["fields"]

    assert_equal(fields["SC_calendar_spread"]["value"], 3.8, "calendar spread overwritten")
    assert_equal(fields["SC_Brent_spread_simple"]["value"], 4.0206, "Brent spread overwritten")
    assert_equal(fields["SC_WTI_spread_simple"]["value"], 7.8206, "WTI spread overwritten")


def test_missing_usd_cny_skips_external_spreads() -> None:
    source = base_input()
    del source["fields"]["USD_CNY"]

    data = calculate_spreads(source)
    fields = data["fields"]

    assert_equal("SC_calendar_spread" in fields, True, "calendar spread should still calculate")
    assert_equal("SC_Brent_spread_simple" in fields, False, "Brent spread should skip")
    assert_equal("SC_WTI_spread_simple" in fields, False, "WTI spread should skip")
    assert_contains(warnings_from(data), "USD_CNY: missing field", "missing USD warning")


def test_unit_mismatch_skips_calculation() -> None:
    source = base_input()
    source["fields"]["SC_close"]["metadata"]["unit"] = "USD/barrel"

    data = calculate_spreads(source)
    fields = data["fields"]

    assert_equal("SC_Brent_spread_simple" in fields, False, "Brent spread should skip on unit mismatch")
    assert_equal("SC_WTI_spread_simple" in fields, False, "WTI spread should skip on unit mismatch")
    assert_contains(warnings_from(data), "SC_close: unit mismatch", "unit warning")


def test_output_directory_is_created_and_json_is_readable() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "daily_input.json"
        output_path = root / "nested" / "processed" / "daily_input_with_spreads.json"
        write_json(input_path, base_input())

        result = calculate_spreads_file(input_path, output_path=output_path)
        saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert_equal(saved, result, "saved JSON should match returned result")
    assert_equal(saved["fields"]["SC_calendar_spread"]["value"], 3.8, "saved calendar spread")


def test_cli_runs_with_custom_paths() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "daily_input.json"
        output_path = root / "processed" / "daily_input_with_spreads.json"
        write_json(input_path, base_input())

        exit_code = main(["--input", str(input_path), "--output", str(output_path)])
        saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert_equal(exit_code, 0, "CLI should return success")
    assert_equal(saved["fields"]["SC_Brent_spread_simple"]["value"], 4.0206, "CLI Brent spread")


def run() -> None:
    tests = [
        test_calculates_calendar_and_external_spreads,
        test_default_does_not_overwrite_existing_fields,
        test_overwrite_recalculates_existing_fields,
        test_missing_usd_cny_skips_external_spreads,
        test_unit_mismatch_skips_calculation,
        test_output_directory_is_created_and_json_is_readable,
        test_cli_runs_with_custom_paths,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
