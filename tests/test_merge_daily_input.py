"""Smoke tests for daily_input merge CLI.

Run from the project root:
    python tests/test_merge_daily_input.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.base import DAILY_INPUT_SCHEMA_VERSION, validate_daily_input_schema  # noqa: E402
from src.fetchers.merge_daily_input import main, merge_daily_inputs  # noqa: E402
from src.pipeline.run_daily_pipeline import main as pipeline_main  # noqa: E402


PROJECT_DICTIONARY = PROJECT_ROOT / "config" / "data_dictionary.yaml"


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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def base_input(include_schema: bool = True) -> dict:
    data = {
        "report_date": "2026-05-22",
        "context": {
            "required_for_topic": [],
            "manual_notes": "base analyst context must survive",
            "source_name": "manual_base",
        },
        "fields": {
            "SC_close": {
                "value": 620.0,
                "metadata": {
                    "unit": "CNY/barrel",
                    "date": "2026-05-22",
                    "timezone": "Asia/Shanghai",
                    "source_level": "manual",
                },
            },
            "Brent_close": {
                "value": 82.4,
                "metadata": {
                    "unit": "USD/barrel",
                    "date": "2026-05-22",
                    "timezone": "Europe/London",
                    "source_level": "manual",
                },
            },
            "WTI_close": {
                "value": 78.6,
                "metadata": {
                    "unit": "USD/barrel",
                    "date": "2026-05-22",
                    "timezone": "America/New_York",
                    "source_level": "manual",
                },
            },
            "USD_CNY": {
                "value": 7.18,
                "metadata": {
                    "unit": "CNY/USD",
                    "date": "2026-05-22",
                    "timezone": "Asia/Shanghai",
                    "source_level": "manual",
                },
            },
            "EIA_crude_inventory": {
                "value": 443.2,
                "metadata": {
                    "unit": "million_barrels",
                    "date": "2026-05-17",
                    "publish_time": "2026-05-20 22:30:00",
                    "timezone": "America/New_York",
                    "source_level": "manual",
                },
            },
            "important_oil_news": {
                "value": "Manual supplement news item.",
                "metadata": {
                    "unit": "text",
                    "date": "2026-05-22",
                    "publish_time": "2026-05-22 16:30:00",
                    "timezone": "Asia/Shanghai",
                    "source_level": "manual",
                },
            },
            "manual_notes": {
                "value": "Manual supplement note.",
                "metadata": {
                    "unit": "text",
                    "date": "2026-05-22",
                    "timezone": "Asia/Shanghai",
                    "source_level": "manual",
                },
            },
        },
    }
    if include_schema:
        data["schema_version"] = DAILY_INPUT_SCHEMA_VERSION
    return data


def overlay_input(report_date: str = "2026-05-22") -> dict:
    return {
        "schema_version": DAILY_INPUT_SCHEMA_VERSION,
        "report_date": report_date,
        "context": {
            "raw_data_contract_version": "raw_data_contract_v1",
            "source_name": "AKShare",
            "fetcher_name": "akshare_sc_daily_fetcher",
            "fetcher_version": "akshare_sc_daily_v1",
            "fetched_at": "2026-05-22T16:00:00+08:00",
            "fetch_status": "pass",
            "manual_notes": "overlay context must not replace base",
        },
        "fields": {
            "SC_close": {
                "value": 641.1,
                "metadata": {
                    "unit": "CNY/barrel",
                    "date": "2026-05-22",
                    "timezone": "Asia/Shanghai",
                    "source_level": "third_party",
                    "source_name": "AKShare",
                    "fetcher_name": "akshare_sc_daily_fetcher",
                    "fetched_at": "2026-05-22T16:00:00+08:00",
                },
            },
            "SC_settlement": {
                "value": 650.6,
                "metadata": {
                    "unit": "CNY/barrel",
                    "date": "2026-05-22",
                    "timezone": "Asia/Shanghai",
                    "source_level": "third_party",
                    "source_name": "AKShare",
                    "fetcher_name": "akshare_sc_daily_fetcher",
                },
            },
            "SC_volume": {
                "value": 52412,
                "metadata": {
                    "unit": "contracts",
                    "date": "2026-05-22",
                    "timezone": "Asia/Shanghai",
                    "source_level": "third_party",
                },
            },
            "SC_open_interest": {
                "value": 37808,
                "metadata": {
                    "unit": "contracts",
                    "date": "2026-05-22",
                    "timezone": "Asia/Shanghai",
                    "source_level": "third_party",
                },
            },
            "SC_near_price": {
                "value": 644.5,
                "metadata": {
                    "unit": "CNY/barrel",
                    "date": "2026-05-22",
                    "timezone": "Asia/Shanghai",
                    "source_level": "third_party",
                },
            },
            "SC_next_price": {
                "value": 641.1,
                "metadata": {
                    "unit": "CNY/barrel",
                    "date": "2026-05-22",
                    "timezone": "Asia/Shanghai",
                    "source_level": "third_party",
                },
            },
        },
    }


def write_config(path: Path) -> None:
    write_text(
        path,
        """
report:
  prompt_version: test_prompt_v1
  calculation_version: test_calc_v1
""",
    )


def test_merge_overlay_wins_and_preserves_manual_before_merge() -> None:
    merged = merge_daily_inputs(base_input(), overlay_input())
    close = merged["fields"]["SC_close"]

    assert_equal(merged["schema_version"], DAILY_INPUT_SCHEMA_VERSION, "schema version")
    assert_equal(validate_daily_input_schema(merged, require_version=True), [], "merged schema errors")
    assert_equal(close["value"], 641.1, "overlay should replace base value")
    assert_equal(close["metadata"]["manual_value_before_merge"], 620.0, "manual value should be preserved")
    assert_equal(close["metadata"]["manual_source_before_merge"], "base", "manual source marker")
    assert_equal(close["metadata"]["merge_source"], "overlay", "overlay merge source")
    assert_contains(merged["context"]["merge_warnings"], "SC_close", "field overwrite warning")


def test_context_base_wins_and_overlay_source_fields_only_fill_missing() -> None:
    merged = merge_daily_inputs(base_input(), overlay_input())
    context = merged["context"]

    assert_equal(context["manual_notes"], "base analyst context must survive", "base manual context should survive")
    assert_equal(context["source_name"], "manual_base", "base source_name should win")
    assert_equal(context["fetcher_name"], "akshare_sc_daily_fetcher", "missing fetcher_name should be filled")
    assert_contains(context["merge_warnings"], "context.source_name", "context conflict warning")
    assert_equal("manual_notes: overlay" in " ".join(context["merge_warnings"]), False, "non-source context should be ignored")


def test_manual_only_and_overlay_only_fields_are_kept_with_merge_source() -> None:
    merged = merge_daily_inputs(base_input(), overlay_input())

    assert_equal(merged["fields"]["Brent_close"]["value"], 82.4, "manual-only field should remain")
    assert_equal(merged["fields"]["Brent_close"]["metadata"]["merge_source"], "manual", "manual merge source")
    assert_equal(merged["fields"]["SC_settlement"]["value"], 650.6, "overlay-only field should be added")
    assert_equal(merged["fields"]["SC_settlement"]["metadata"]["merge_source"], "overlay", "overlay merge source")
    assert_equal(merged["fields"]["SC_settlement"]["metadata"]["source_name"], "AKShare", "overlay metadata should remain")


def test_legacy_base_without_schema_version_is_accepted_and_output_is_versioned() -> None:
    merged = merge_daily_inputs(base_input(include_schema=False), overlay_input())

    assert_equal(merged["schema_version"], DAILY_INPUT_SCHEMA_VERSION, "legacy base output version")
    assert_equal(validate_daily_input_schema(merged, require_version=True), [], "legacy base merged schema")


def test_report_date_mismatch_returns_one_and_does_not_write_output() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        base_path = root / "base.json"
        overlay_path = root / "overlay.json"
        output_path = root / "merged.json"
        write_json(base_path, base_input())
        write_json(overlay_path, overlay_input(report_date="2026-05-23"))

        exit_code = main(["--base", str(base_path), "--overlay", str(overlay_path), "--output", str(output_path)])

    assert_equal(exit_code, 1, "date mismatch should return 1")
    assert_equal(output_path.exists(), False, "date mismatch should not write output")


def test_cli_writes_merged_daily_input() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        base_path = root / "manual_supplement.json"
        overlay_path = root / "akshare_daily_input.json"
        output_path = root / "daily_input.json"
        write_json(base_path, base_input())
        write_json(overlay_path, overlay_input())

        exit_code = main(["--base", str(base_path), "--overlay", str(overlay_path), "--output", str(output_path)])
        merged = load_json(output_path)

    assert_equal(exit_code, 0, "CLI should return 0")
    assert_equal(merged["fields"]["SC_close"]["value"], 641.1, "CLI should write merged field")
    assert_equal(validate_daily_input_schema(merged, require_version=True), [], "CLI output schema")


def test_merged_daily_input_runs_pipeline_smoke() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "daily_input.json"
        db_path = root / "sc_oil.sqlite"
        config_path = root / "config.yaml"
        calculated_input_path = root / "processed" / "calculated_input.json"
        quality_report_path = root / "processed" / "quality_report.json"
        evidence_list_path = root / "processed" / "evidence_list.json"
        daily_report_path = root / "reports" / "SC_daily.md"
        write_json(input_path, merge_daily_inputs(base_input(), overlay_input()))
        write_config(config_path)

        exit_code = pipeline_main(
            [
                "--input",
                str(input_path),
                "--dictionary",
                str(PROJECT_DICTIONARY),
                "--db",
                str(db_path),
                "--config",
                str(config_path),
                "--calculated-input-output",
                str(calculated_input_path),
                "--quality-report-output",
                str(quality_report_path),
                "--evidence-list-output",
                str(evidence_list_path),
                "--daily-report-output",
                str(daily_report_path),
                "--init-db",
            ]
        )
        quality_report = load_json(quality_report_path)
        calculated = load_json(calculated_input_path)
        with sqlite3.connect(db_path) as conn:
            report_count = conn.execute("SELECT COUNT(*) FROM research_reports;").fetchone()[0]

    assert_equal(exit_code, 0, "merged daily input should run pipeline")
    assert_equal(quality_report["overall_status"], "warning", "merged smoke should be warning not fail")
    assert_equal("SC_USD" in calculated["fields"], True, "pipeline should calculate SC_USD")
    assert_equal(report_count, 1, "pipeline should write research report")


def run() -> None:
    tests = [
        test_merge_overlay_wins_and_preserves_manual_before_merge,
        test_context_base_wins_and_overlay_source_fields_only_fill_missing,
        test_manual_only_and_overlay_only_fields_are_kept_with_merge_source,
        test_legacy_base_without_schema_version_is_accepted_and_output_is_versioned,
        test_report_date_mismatch_returns_one_and_does_not_write_output,
        test_cli_writes_merged_daily_input,
        test_merged_daily_input_runs_pipeline_smoke,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
