"""Smoke tests for src/pipeline/run_auto_daily.py.

Run from the project root:
    python tests/test_run_auto_daily.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.akshare_sc import build_fetch_result_from_rows as build_akshare_fetch_result  # noqa: E402
from src.fetchers.base import DAILY_INPUT_SCHEMA_VERSION  # noqa: E402
from src.fetchers.market_fx import build_fetch_result_from_rows as build_market_fx_fetch_result  # noqa: E402
from src.pipeline import run_auto_daily as workflow  # noqa: E402


FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "akshare_sc" / "ine_sc_rows.json"
PROJECT_DICTIONARY = PROJECT_ROOT / "config" / "data_dictionary.yaml"
REPORT_DATE = "2026-01-15"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_akshare_raw_data(report_date: str = REPORT_DATE) -> dict:
    rows = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return build_akshare_fetch_result(
        rows=rows,
        report_date=report_date,
        fetched_at=f"{report_date}T16:00:00+08:00",
    )


def build_akshare_raw_fail(report_date: str = REPORT_DATE) -> dict:
    return build_akshare_fetch_result(
        rows=[],
        report_date=report_date,
        fetched_at=f"{report_date}T16:00:00+08:00",
    )


def build_market_fx_raw_data(report_date: str = REPORT_DATE) -> dict:
    return build_market_fx_fetch_result(
        rows={
            "date": report_date,
            "USD_CNY": 7.18,
            "Brent_close": 82.4,
            "WTI_close": 78.6,
            "source_name": "fixture_market_fx",
            "url_or_reference": "fixture://market_fx",
        },
        report_date=report_date,
        fetched_at=f"{report_date}T16:30:00+08:00",
    )


def manual_supplement(report_date: str = REPORT_DATE) -> dict:
    return {
        "schema_version": DAILY_INPUT_SCHEMA_VERSION,
        "report_date": report_date,
        "context": {
            "required_for_topic": [],
            "manual_context": "test-only manual supplement",
        },
        "fields": {
            "manual_notes": {
                "value": "Human reviewed note for auto daily smoke.",
                "metadata": {
                    "unit": "text",
                    "date": report_date,
                    "timezone": "Asia/Shanghai",
                    "source_level": "manual",
                },
            },
            "EIA_crude_inventory": {
                "value": 443.2,
                "metadata": {
                    "unit": "million_barrels",
                    "date": report_date,
                    "publish_time": f"{report_date} 22:30:00",
                    "timezone": "America/New_York",
                    "source_level": "manual",
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


def workflow_args(
    root: Path,
    akshare_raw_path: Path,
    market_fx_raw_path: Path,
    report_date: str = REPORT_DATE,
    extra_args: list[str] | None = None,
) -> list[str]:
    args = [
        "--report-date",
        report_date,
        "--raw-input",
        str(akshare_raw_path),
        "--market-fx-raw-input",
        str(market_fx_raw_path),
        "--akshare-raw-output",
        str(root / "raw" / "should_not_fetch_akshare.json"),
        "--market-fx-raw-output",
        str(root / "raw" / "should_not_fetch_market_fx.json"),
        "--akshare-daily-input-output",
        str(root / "processed" / "akshare_daily_input.json"),
        "--market-fx-daily-input-output",
        str(root / "processed" / "market_fx_daily_input.json"),
        "--default-fields-output",
        str(root / "processed" / "default_fields.json"),
        "--akshare-conversion-result-output",
        str(root / "processed" / "akshare_conversion_result.json"),
        "--market-fx-conversion-result-output",
        str(root / "processed" / "market_fx_conversion_result.json"),
        "--auto-daily-input-output",
        str(root / "manual" / "daily_input.json"),
        "--calculated-input-output",
        str(root / "processed" / "calculated_input.json"),
        "--quality-report-output",
        str(root / "processed" / "quality_report.json"),
        "--evidence-list-output",
        str(root / "processed" / "evidence_list.json"),
        "--daily-report-output",
        str(root / "reports" / "SC_daily.md"),
        "--db",
        str(root / "sc_oil.sqlite"),
        "--config",
        str(root / "config.yaml"),
        "--dictionary",
        str(PROJECT_DICTIONARY),
        "--init-db",
        "--report-id",
        "RPT-AUTO-TEST",
    ]
    if extra_args:
        args.extend(extra_args)
    return args


def research_report_rows(db_path: Path) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT report_id, data_snapshot_id, report_status, report_path
                FROM research_reports
                ORDER BY report_id;
                """
            ).fetchall()
        ]


def test_without_manual_supplement_runs_warning_daily_report_without_fetching() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        akshare_raw_path = root / "raw" / "akshare_sc.json"
        market_fx_raw_path = root / "raw" / "market_fx.json"
        write_json(akshare_raw_path, build_akshare_raw_data())
        write_json(market_fx_raw_path, build_market_fx_raw_data())
        write_config(root / "config.yaml")

        original_akshare_fetch = workflow.fetch_akshare_sc_daily
        original_market_fx_fetch = workflow.fetch_market_fx_daily

        def forbidden_fetch(_report_date: str) -> dict:
            raise AssertionError("fetch must not be called when raw input is provided")

        workflow.fetch_akshare_sc_daily = forbidden_fetch
        workflow.fetch_market_fx_daily = forbidden_fetch
        try:
            exit_code = workflow.main(workflow_args(root, akshare_raw_path, market_fx_raw_path))
        finally:
            workflow.fetch_akshare_sc_daily = original_akshare_fetch
            workflow.fetch_market_fx_daily = original_market_fx_fetch

        auto_daily_input_path = root / "manual" / "daily_input.json"
        quality_report_path = root / "processed" / "quality_report.json"
        evidence_list_path = root / "processed" / "evidence_list.json"
        daily_report_path = root / "reports" / "SC_daily.md"
        output_exists = {
            "auto_daily_input": auto_daily_input_path.exists(),
            "quality_report": quality_report_path.exists(),
            "evidence_list": evidence_list_path.exists(),
            "daily_report": daily_report_path.exists(),
        }
        auto_daily_input = load_json(auto_daily_input_path)
        quality_report = load_json(quality_report_path)
        reports = research_report_rows(root / "sc_oil.sqlite")

    assert_equal(exit_code, 0, "auto daily workflow should succeed with warning quality")
    assert_equal(output_exists["auto_daily_input"], True, "auto daily input should be written")
    assert_equal(output_exists["quality_report"], True, "quality report should be written")
    assert_equal(output_exists["evidence_list"], True, "evidence list should be written")
    assert_equal(output_exists["daily_report"], True, "daily report should be written")
    assert_equal(auto_daily_input["schema_version"], DAILY_INPUT_SCHEMA_VERSION, "auto daily schema version")
    for field_name in ["SC_close", "USD_CNY", "Brent_close", "WTI_close", "important_oil_news"]:
        assert_equal(field_name in auto_daily_input["fields"], True, f"{field_name} should be present")
    assert_equal(auto_daily_input["fields"]["important_oil_news"]["metadata"]["source_status"], "warning", "news warning")
    assert_equal(quality_report["overall_status"], "warning", "auto preflight should produce warning report")
    assert_equal(len(reports), 1, "research report row should be written")
    assert_equal(reports[0]["report_status"], "warning", "research report status")


def test_optional_manual_supplement_can_override_default_text_and_add_eia() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        akshare_raw_path = root / "raw" / "akshare_sc.json"
        market_fx_raw_path = root / "raw" / "market_fx.json"
        manual_path = root / "manual" / "manual_supplement.json"
        write_json(akshare_raw_path, build_akshare_raw_data())
        write_json(market_fx_raw_path, build_market_fx_raw_data())
        write_json(manual_path, manual_supplement())
        write_config(root / "config.yaml")

        exit_code = workflow.main(
            workflow_args(root, akshare_raw_path, market_fx_raw_path, extra_args=["--manual-supplement", str(manual_path)])
        )
        auto_daily_input = load_json(root / "manual" / "daily_input.json")

    assert_equal(exit_code, 0, "auto daily workflow with manual supplement")
    assert_equal(auto_daily_input["fields"]["manual_notes"]["value"], "Human reviewed note for auto daily smoke.", "manual override")
    assert_equal(auto_daily_input["fields"]["manual_notes"]["metadata"]["merge_source"], "overlay", "manual overlay source")
    assert_equal(auto_daily_input["fields"]["EIA_crude_inventory"]["value"], 443.2, "manual EIA supplement")


def test_akshare_fail_returns_controlled_data_failure_without_pipeline_outputs() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        akshare_raw_path = root / "raw" / "akshare_sc_fail.json"
        market_fx_raw_path = root / "raw" / "market_fx.json"
        write_json(akshare_raw_path, build_akshare_raw_fail())
        write_json(market_fx_raw_path, build_market_fx_raw_data())
        write_config(root / "config.yaml")

        exit_code = workflow.main(workflow_args(root, akshare_raw_path, market_fx_raw_path))
        akshare_conversion_result_exists = (root / "processed" / "akshare_conversion_result.json").exists()
        auto_daily_input_exists = (root / "manual" / "daily_input.json").exists()
        quality_report_exists = (root / "processed" / "quality_report.json").exists()
        evidence_list_exists = (root / "processed" / "evidence_list.json").exists()
        db_exists = (root / "sc_oil.sqlite").exists()

    assert_equal(exit_code, 2, "AKShare fail should be controlled data failure")
    assert_equal(akshare_conversion_result_exists, True, "AKShare conversion result should be written")
    assert_equal(auto_daily_input_exists, False, "final daily input should not be written")
    assert_equal(quality_report_exists, False, "pipeline should not run")
    assert_equal(evidence_list_exists, False, "evidence should not be written")
    assert_equal(db_exists, False, "DB should not be initialized")


def run() -> None:
    tests = [
        test_without_manual_supplement_runs_warning_daily_report_without_fetching,
        test_optional_manual_supplement_can_override_default_text_and_add_eia,
        test_akshare_fail_returns_controlled_data_failure_without_pipeline_outputs,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
