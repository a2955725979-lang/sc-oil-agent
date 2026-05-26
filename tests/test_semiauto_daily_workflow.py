"""Smoke tests for src/workflows/run_semiauto_daily.py.

Run from the project root:
    python tests/test_semiauto_daily_workflow.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.akshare_sc import build_fetch_result_from_rows  # noqa: E402
from src.fetchers.base import DAILY_INPUT_SCHEMA_VERSION  # noqa: E402
from src.workflows import run_semiauto_daily as workflow  # noqa: E402


FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "akshare_sc" / "ine_sc_rows.json"
PROJECT_DICTIONARY = PROJECT_ROOT / "config" / "data_dictionary.yaml"


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


def build_akshare_raw_data(report_date: str = "2026-01-15") -> dict:
    rows = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return build_fetch_result_from_rows(
        rows=rows,
        report_date=report_date,
        fetched_at=f"{report_date}T16:00:00+08:00",
    )


def build_raw_fail(report_date: str = "2026-01-15") -> dict:
    return build_fetch_result_from_rows(
        rows=[],
        report_date=report_date,
        fetched_at=f"{report_date}T16:00:00+08:00",
    )


def manual_supplement(report_date: str = "2026-01-15") -> dict:
    return {
        "schema_version": DAILY_INPUT_SCHEMA_VERSION,
        "report_date": report_date,
        "context": {
            "required_for_topic": [],
            "manual_notes": "test-only manual supplement",
        },
        "fields": {
            "Brent_close": {
                "value": 82.4,
                "metadata": {
                    "unit": "USD/barrel",
                    "date": report_date,
                    "timezone": "Europe/London",
                    "source_level": "manual",
                },
            },
            "WTI_close": {
                "value": 78.6,
                "metadata": {
                    "unit": "USD/barrel",
                    "date": report_date,
                    "timezone": "America/New_York",
                    "source_level": "manual",
                },
            },
            "USD_CNY": {
                "value": 7.18,
                "metadata": {
                    "unit": "CNY/USD",
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
            "EIA_gasoline_inventory": {
                "value": 225.1,
                "metadata": {
                    "unit": "million_barrels",
                    "date": report_date,
                    "publish_time": f"{report_date} 22:30:00",
                    "timezone": "America/New_York",
                    "source_level": "manual",
                },
            },
            "EIA_distillate_inventory": {
                "value": 116.4,
                "metadata": {
                    "unit": "million_barrels",
                    "date": report_date,
                    "publish_time": f"{report_date} 22:30:00",
                    "timezone": "America/New_York",
                    "source_level": "manual",
                },
            },
            "OPEC_monthly_summary": {
                "value": "Test-only OPEC summary.",
                "metadata": {
                    "unit": "text",
                    "date": report_date,
                    "publish_time": f"{report_date} 18:00:00",
                    "timezone": "Europe/Vienna",
                    "source_level": "manual",
                },
            },
            "IEA_monthly_summary": {
                "value": "Test-only IEA summary.",
                "metadata": {
                    "unit": "text",
                    "date": report_date,
                    "publish_time": f"{report_date} 17:00:00",
                    "timezone": "Europe/Paris",
                    "source_level": "manual",
                },
            },
            "important_oil_news": {
                "value": "Test-only oil news.",
                "metadata": {
                    "unit": "text",
                    "date": report_date,
                    "publish_time": f"{report_date} 16:30:00",
                    "timezone": "Asia/Shanghai",
                    "source_level": "manual",
                },
            },
            "manual_notes": {
                "value": "Test-only analyst note.",
                "metadata": {
                    "unit": "text",
                    "date": report_date,
                    "timezone": "Asia/Shanghai",
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
    raw_path: Path,
    manual_path: Path,
    report_date: str = "2026-01-15",
    extra_args: list[str] | None = None,
) -> list[str]:
    args = [
        "--report-date",
        report_date,
        "--manual-supplement",
        str(manual_path),
        "--raw-input",
        str(raw_path),
        "--raw-output",
        str(root / "raw" / "should_not_fetch.json"),
        "--akshare-daily-input-output",
        str(root / "processed" / "akshare_daily_input.json"),
        "--conversion-result-output",
        str(root / "processed" / "conversion_result.json"),
        "--merged-daily-input-output",
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
        "RPT-SEMIAUTO-TEST",
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


def test_success_with_raw_input_runs_complete_workflow_without_fetching() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw_path = root / "raw" / "akshare_sc.json"
        manual_path = root / "manual" / "manual_supplement.json"
        config_path = root / "config.yaml"
        write_json(raw_path, build_akshare_raw_data())
        write_json(manual_path, manual_supplement())
        write_config(config_path)

        original_fetch = workflow.fetch_akshare_sc_daily

        def forbidden_fetch(_report_date: str) -> dict:
            raise AssertionError("AKShare fetch must not be called when --raw-input is provided")

        workflow.fetch_akshare_sc_daily = forbidden_fetch
        try:
            exit_code = workflow.main(workflow_args(root, raw_path, manual_path))
        finally:
            workflow.fetch_akshare_sc_daily = original_fetch

        akshare_daily_input = root / "processed" / "akshare_daily_input.json"
        conversion_result = root / "processed" / "conversion_result.json"
        merged_daily_input = root / "manual" / "daily_input.json"
        calculated_input = root / "processed" / "calculated_input.json"
        quality_report_path = root / "processed" / "quality_report.json"
        evidence_list = root / "processed" / "evidence_list.json"
        daily_report = root / "reports" / "SC_daily.md"
        db_path = root / "sc_oil.sqlite"
        raw_output = root / "raw" / "should_not_fetch.json"
        output_exists = {
            path.name: path.exists()
            for path in [
                akshare_daily_input,
                conversion_result,
                merged_daily_input,
                calculated_input,
                quality_report_path,
                evidence_list,
                daily_report,
            ]
        }
        raw_output_exists = raw_output.exists()
        quality_report = load_json(quality_report_path)
        reports = research_report_rows(db_path)

    assert_equal(exit_code, 0, "semi-auto workflow should succeed on fixture raw data")
    assert_equal(raw_output_exists, False, "--raw-input should not write --raw-output")
    for name, exists in output_exists.items():
        assert_equal(exists, True, f"{name} should be created")
    assert_equal(quality_report["overall_status"], "warning", "fixture workflow should complete with warning quality")
    assert_equal(len(reports), 1, "research_reports row should be written")
    assert_equal(reports[0]["report_id"], "RPT-SEMIAUTO-TEST", "explicit report id should be used")
    assert_equal(reports[0]["report_status"], "warning", "research report status should match quality")


def test_raw_fetch_status_fail_returns_two_and_does_not_run_pipeline() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw_path = root / "raw" / "akshare_sc_fail.json"
        manual_path = root / "manual" / "manual_supplement.json"
        write_json(raw_path, build_raw_fail())
        write_json(manual_path, manual_supplement())
        write_config(root / "config.yaml")

        exit_code = workflow.main(workflow_args(root, raw_path, manual_path))
        conversion_result_exists = (root / "processed" / "conversion_result.json").exists()
        akshare_daily_input_exists = (root / "processed" / "akshare_daily_input.json").exists()
        merged_daily_input_exists = (root / "manual" / "daily_input.json").exists()
        quality_report_exists = (root / "processed" / "quality_report.json").exists()
        db_exists = (root / "sc_oil.sqlite").exists()

    assert_equal(exit_code, 2, "raw fetch_status=fail should be a controlled data failure")
    assert_equal(conversion_result_exists, True, "conversion result should be written")
    assert_equal(akshare_daily_input_exists, False, "unusable conversion should not write daily input")
    assert_equal(merged_daily_input_exists, False, "merge should not run")
    assert_equal(quality_report_exists, False, "pipeline should not run")
    assert_equal(db_exists, False, "pipeline should not initialize db")


def test_missing_manual_supplement_returns_one() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw_path = root / "raw" / "akshare_sc.json"
        manual_path = root / "manual" / "missing_manual_supplement.json"
        write_json(raw_path, build_akshare_raw_data())
        write_config(root / "config.yaml")

        exit_code = workflow.main(workflow_args(root, raw_path, manual_path))
        conversion_result_exists = (root / "processed" / "conversion_result.json").exists()
        quality_report_exists = (root / "processed" / "quality_report.json").exists()

    assert_equal(exit_code, 1, "missing manual supplement should be a program error")
    assert_equal(conversion_result_exists, False, "conversion should not run")
    assert_equal(quality_report_exists, False, "pipeline should not run")


def test_report_date_mismatch_returns_one() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw_path = root / "raw" / "akshare_sc.json"
        manual_path = root / "manual" / "manual_supplement.json"
        write_json(raw_path, build_akshare_raw_data())
        write_json(manual_path, manual_supplement(report_date="2026-01-16"))
        write_config(root / "config.yaml")

        exit_code = workflow.main(workflow_args(root, raw_path, manual_path))
        merged_daily_input_exists = (root / "manual" / "daily_input.json").exists()
        quality_report_exists = (root / "processed" / "quality_report.json").exists()

    assert_equal(exit_code, 1, "manual/AKShare report_date mismatch should return 1")
    assert_equal(merged_daily_input_exists, False, "mismatch should not write merged input")
    assert_equal(quality_report_exists, False, "pipeline should not run")


def run() -> None:
    tests = [
        test_success_with_raw_input_runs_complete_workflow_without_fetching,
        test_raw_fetch_status_fail_returns_two_and_does_not_run_pipeline,
        test_missing_manual_supplement_returns_one,
        test_report_date_mismatch_returns_one,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
