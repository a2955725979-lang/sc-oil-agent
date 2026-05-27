"""Smoke tests for src/pipeline/run_daily_pipeline.py.

Run from the project root:
    python tests/test_run_daily_pipeline.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.database.init_db import create_database  # noqa: E402
from src.pipeline.run_daily_pipeline import main  # noqa: E402


EXAMPLE_INPUT = PROJECT_ROOT / "data" / "manual" / "daily_input_example.json"
PROJECT_DICTIONARY = PROJECT_ROOT / "config" / "data_dictionary.yaml"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(text: str, expected_fragment: str, message: str) -> None:
    if expected_fragment not in text:
        raise AssertionError(f"{message}: {expected_fragment!r} not found")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def dictionary_yaml(required: bool = True, fail_action: str = "report_as_missing") -> str:
    return f"""
SC_close:
  required: {str(required).lower()}
  unit: CNY/barrel
  frequency: daily
  quality_checks: [missing_check, unit_check]
  fail_action: {fail_action}
"""


def failing_daily_input(report_date: str = "2026-05-22") -> dict:
    return {"report_date": report_date, "fields": {}}


def write_config(path: Path) -> None:
    write_text(
        path,
        """
report:
  prompt_version: test_prompt_v1
  calculation_version: test_calc_v1
""",
    )


def snapshot_count(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM data_snapshot;").fetchone()[0]


def snapshot_ids(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        return [
            row[0]
            for row in conn.execute(
                "SELECT data_snapshot_id FROM data_snapshot ORDER BY data_snapshot_id;"
            ).fetchall()
        ]


def research_report_rows(db_path: Path) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT report_id, data_snapshot_id, evidence_ids, report_status,
                       conclusion, report_path, report_markdown
                FROM research_reports
                ORDER BY report_id;
                """
            ).fetchall()
        ]


def table_count(db_path: Path, table_name: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table_name};").fetchone()[0]


def evidence_rows(db_path: Path) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT evidence_id, report_id, data_snapshot_id
                FROM evidence_database
                ORDER BY evidence_id;
                """
            ).fetchall()
        ]


def pipeline_args(
    input_path: Path,
    dictionary_path: Path,
    db_path: Path,
    config_path: Path,
    calculated_input_path: Path,
    quality_report_path: Path,
    evidence_list_path: Path,
    daily_report_path: Path,
    extra_args: list[str] | None = None,
) -> list[str]:
    args = [
        "--input",
        str(input_path),
        "--dictionary",
        str(dictionary_path),
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
    ]
    if extra_args:
        args.extend(extra_args)
    return args


def test_warning_status_runs_complete_pipeline() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "sc_oil.sqlite"
        config_path = root / "config.yaml"
        calculated_input_path = root / "processed" / "calculated_input.json"
        quality_report_path = root / "processed" / "quality_report.json"
        evidence_list_path = root / "processed" / "evidence_list.json"
        daily_report_path = root / "reports" / "SC_daily.md"

        write_config(config_path)
        exit_code = main(
            pipeline_args(
                EXAMPLE_INPUT,
                PROJECT_DICTIONARY,
                db_path,
                config_path,
                calculated_input_path,
                quality_report_path,
                evidence_list_path,
                daily_report_path,
                extra_args=["--init-db", "--snapshot-id", "SNAP-CUSTOM-PIPELINE"],
            )
        )

        calculated = json.loads(calculated_input_path.read_text(encoding="utf-8"))
        quality_report = json.loads(quality_report_path.read_text(encoding="utf-8"))
        evidence_report = json.loads(evidence_list_path.read_text(encoding="utf-8"))
        markdown = daily_report_path.read_text(encoding="utf-8")
        ids = snapshot_ids(db_path)
        reports = research_report_rows(db_path)
        business_counts = {
            "market": table_count(db_path, "market_prices"),
            "fx": table_count(db_path, "fx_rates"),
            "spread": table_count(db_path, "spread_table"),
            "evidence": table_count(db_path, "evidence_database"),
        }

    assert_equal(exit_code, 0, "warning quality should be a successful pipeline run")
    assert_equal(quality_report["overall_status"], "warning", "example should remain warning")
    assert_equal("SC_USD" in calculated["fields"], True, "calculated input should contain SC_USD")
    assert_equal(
        calculated["fields"]["SC_Brent_spread_simple"]["value"],
        4.0206,
        "calculated input should overwrite stale spread values by default",
    )
    assert_contains(quality_report["input_path"], "calculated_input.json", "quality should use calculated input")
    assert_equal(evidence_report["data_snapshot_id"], "SNAP-CUSTOM-PIPELINE", "snapshot id should reach evidence")
    assert_equal("SC_USD" in markdown, True, "daily report should be rendered from calculated input evidence")
    assert_equal(ids, ["SNAP-CUSTOM-PIPELINE"], "snapshot should be written")
    assert_equal(len(reports), 1, "research report should be written")
    assert_equal(reports[0]["data_snapshot_id"], "SNAP-CUSTOM-PIPELINE", "report should link snapshot")
    assert_equal(reports[0]["report_status"], "warning", "report status should be warning")
    assert_equal(json.loads(reports[0]["evidence_ids"])[0], "EVID-20260522-001", "evidence ids should be stored")
    assert_equal(
        business_counts,
        {"market": 0, "fx": 0, "spread": 0, "evidence": 0},
        "business tables should remain untouched by default",
    )


def test_warning_status_writes_business_tables_after_research_report() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "sc_oil.sqlite"
        config_path = root / "config.yaml"
        calculated_input_path = root / "processed" / "calculated_input.json"
        quality_report_path = root / "processed" / "quality_report.json"
        evidence_list_path = root / "processed" / "evidence_list.json"
        daily_report_path = root / "reports" / "SC_daily.md"
        summary_path = root / "processed" / "business_summary.json"
        report_id = "RPT-BUSINESS-PIPELINE"
        snapshot_id = "SNAP-BUSINESS-PIPELINE"

        write_config(config_path)
        exit_code = main(
            pipeline_args(
                EXAMPLE_INPUT,
                PROJECT_DICTIONARY,
                db_path,
                config_path,
                calculated_input_path,
                quality_report_path,
                evidence_list_path,
                daily_report_path,
                extra_args=[
                    "--init-db",
                    "--snapshot-id",
                    snapshot_id,
                    "--report-id",
                    report_id,
                    "--write-business-tables",
                    "--business-write-summary-output",
                    str(summary_path),
                ],
            )
        )
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        reports = research_report_rows(db_path)
        evidence = evidence_rows(db_path)
        market_count = table_count(db_path, "market_prices")
        fx_count = table_count(db_path, "fx_rates")
        spread_count = table_count(db_path, "spread_table")
        with sqlite3.connect(db_path) as conn:
            market_symbols = [
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT symbol FROM market_prices ORDER BY symbol;"
                ).fetchall()
            ]

    assert_equal(exit_code, 0, "business table pipeline should succeed")
    assert_equal(len(reports), 1, "research report should be written first")
    assert_equal(reports[0]["report_id"], report_id, "explicit report id")
    assert_equal(summary["research_report_id"], report_id, "summary report id")
    assert_equal(summary["data_snapshot_id"], snapshot_id, "summary snapshot id")
    assert_equal(summary["market_prices_written"], 3, "market rows")
    assert_equal(summary["fx_rates_written"], 1, "fx rows")
    assert_equal(summary["spreads_written"], 1, "spread rows")
    assert_equal(market_count, 3, "market_prices count")
    assert_equal(market_symbols, ["SC"], "market_prices should contain SC only")
    assert_equal(fx_count, 1, "fx_rates count")
    assert_equal(spread_count, 1, "spread_table count")
    assert_equal(summary["evidence_written"], len(evidence), "evidence summary count")
    assert_equal(evidence[0]["report_id"], report_id, "evidence report FK")
    assert_equal(evidence[0]["data_snapshot_id"], snapshot_id, "evidence snapshot FK")


def test_fail_status_writes_fail_report_without_snapshot_or_evidence() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "daily_input.json"
        dictionary_path = root / "dictionary.yaml"
        db_path = root / "sc_oil.sqlite"
        config_path = root / "config.yaml"
        calculated_input_path = root / "processed" / "calculated_input.json"
        quality_report_path = root / "processed" / "quality_report.json"
        evidence_list_path = root / "processed" / "evidence_list.json"
        daily_report_path = root / "reports" / "SC_daily.md"

        write_json(input_path, failing_daily_input())
        write_text(dictionary_path, dictionary_yaml())
        write_config(config_path)

        exit_code = main(
            pipeline_args(
                input_path,
                dictionary_path,
                db_path,
                config_path,
                calculated_input_path,
                quality_report_path,
                evidence_list_path,
                daily_report_path,
                extra_args=["--init-db"],
            )
        )

        quality_report = json.loads(quality_report_path.read_text(encoding="utf-8"))
        markdown = daily_report_path.read_text(encoding="utf-8")
        calculated_exists = calculated_input_path.exists()
        evidence_exists = evidence_list_path.exists()
        count = snapshot_count(db_path)
        reports = research_report_rows(db_path)

    assert_equal(exit_code, 2, "quality fail should return 2")
    assert_equal(calculated_exists, True, "calculated input should still be written")
    assert_equal(quality_report["overall_status"], "fail", "quality report should fail")
    assert_equal(count, 0, "fail status should not write data_snapshot")
    assert_equal(evidence_exists, False, "fail status should not generate evidence list")
    assert_equal(len(reports), 1, "fail report should be written for review")
    assert_equal(reports[0]["data_snapshot_id"], None, "fail report should not link a snapshot")
    assert_equal(reports[0]["evidence_ids"], "[]", "fail report evidence ids should be empty")
    assert_equal(
        reports[0]["conclusion"],
        "数据质量未通过，不能生成正常研究结论。",
        "fail report conclusion should be fixed",
    )
    assert_contains(markdown, "数据质量状态为 fail", "fail Markdown should explain failure")


def test_fail_status_write_business_tables_does_not_write_core_tables() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "daily_input.json"
        dictionary_path = root / "dictionary.yaml"
        db_path = root / "sc_oil.sqlite"
        config_path = root / "config.yaml"
        calculated_input_path = root / "processed" / "calculated_input.json"
        quality_report_path = root / "processed" / "quality_report.json"
        evidence_list_path = root / "processed" / "evidence_list.json"
        daily_report_path = root / "reports" / "SC_daily.md"
        summary_path = root / "processed" / "business_summary.json"

        write_json(input_path, failing_daily_input())
        write_text(dictionary_path, dictionary_yaml())
        write_config(config_path)

        exit_code = main(
            pipeline_args(
                input_path,
                dictionary_path,
                db_path,
                config_path,
                calculated_input_path,
                quality_report_path,
                evidence_list_path,
                daily_report_path,
                extra_args=[
                    "--init-db",
                    "--write-business-tables",
                    "--business-write-summary-output",
                    str(summary_path),
                ],
            )
        )
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        reports = research_report_rows(db_path)
        market_count = table_count(db_path, "market_prices")
        fx_count = table_count(db_path, "fx_rates")
        spread_count = table_count(db_path, "spread_table")
        evidence_count = table_count(db_path, "evidence_database")

    assert_equal(exit_code, 2, "quality fail should still return 2")
    assert_equal(len(reports), 1, "fail report should be written")
    assert_equal(summary["core_tables_written"], False, "fail path should not write core tables")
    assert_equal(summary["evidence_database_written"], False, "fail path should not write absent evidence")
    assert_equal(summary["market_prices_written"], 0, "fail market rows")
    assert_equal(summary["fx_rates_written"], 0, "fail fx rows")
    assert_equal(summary["spreads_written"], 0, "fail spread rows")
    assert_equal(summary["evidence_written"], 0, "fail evidence rows")
    assert_contains(
        "; ".join(summary["warnings"]),
        "evidence_database write skipped because evidence_list is absent",
        "fail business summary should explain absent evidence",
    )
    assert_equal(market_count, 0, "market_prices empty")
    assert_equal(fx_count, 0, "fx_rates empty")
    assert_equal(spread_count, 0, "spread_table empty")
    assert_equal(evidence_count, 0, "evidence_database empty")


def test_warning_status_generates_llm_input_package() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "sc_oil.sqlite"
        config_path = root / "config.yaml"
        calculated_input_path = root / "processed" / "calculated_input.json"
        quality_report_path = root / "processed" / "quality_report.json"
        evidence_list_path = root / "processed" / "evidence_list.json"
        daily_report_path = root / "reports" / "SC_daily.md"
        llm_package_path = root / "processed" / "llm_input_package.json"
        report_id = "RPT-LLM-PIPELINE"
        snapshot_id = "SNAP-LLM-PIPELINE"

        write_config(config_path)
        exit_code = main(
            pipeline_args(
                EXAMPLE_INPUT,
                PROJECT_DICTIONARY,
                db_path,
                config_path,
                calculated_input_path,
                quality_report_path,
                evidence_list_path,
                daily_report_path,
                extra_args=[
                    "--init-db",
                    "--snapshot-id",
                    snapshot_id,
                    "--report-id",
                    report_id,
                    "--generate-llm-input-package",
                    "--llm-input-package-output",
                    str(llm_package_path),
                ],
            )
        )
        package = json.loads(llm_package_path.read_text(encoding="utf-8"))

    assert_equal(exit_code, 0, "LLM package pipeline run should succeed")
    assert_equal(package["schema_version"], "llm_input_package_v1", "LLM package schema")
    assert_equal(package["data_snapshot_id"], snapshot_id, "LLM package snapshot id")
    assert_equal(package["research_report_id"], report_id, "LLM package report id")
    assert_equal(package["pipeline_status"]["overall_status"], "warning", "LLM package status")
    assert_equal(len(package["evidence_items"]) > 0, True, "LLM package evidence included")


def test_fail_status_can_generate_llm_input_package() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "daily_input.json"
        dictionary_path = root / "dictionary.yaml"
        db_path = root / "sc_oil.sqlite"
        config_path = root / "config.yaml"
        calculated_input_path = root / "processed" / "calculated_input.json"
        quality_report_path = root / "processed" / "quality_report.json"
        evidence_list_path = root / "processed" / "evidence_list.json"
        daily_report_path = root / "reports" / "SC_daily.md"
        llm_package_path = root / "processed" / "llm_input_package.json"

        write_json(input_path, failing_daily_input())
        write_text(dictionary_path, dictionary_yaml())
        write_config(config_path)

        exit_code = main(
            pipeline_args(
                input_path,
                dictionary_path,
                db_path,
                config_path,
                calculated_input_path,
                quality_report_path,
                evidence_list_path,
                daily_report_path,
                extra_args=[
                    "--init-db",
                    "--generate-llm-input-package",
                    "--llm-input-package-output",
                    str(llm_package_path),
                ],
            )
        )
        package = json.loads(llm_package_path.read_text(encoding="utf-8"))

    assert_equal(exit_code, 2, "quality fail should still return 2")
    assert_equal(package["pipeline_status"]["overall_status"], "fail", "fail package status")
    assert_equal(package["evidence_items"], [], "fail package has no evidence list")
    assert_equal(package["quality_constraints"]["normal_market_explanation_allowed"], False, "fail package blocks explanation")
    assert_contains(
        "; ".join(package["notes"]),
        "future LLM must not generate normal market explanation",
        "fail package note",
    )


def test_init_db_checks_existing_database_without_clearing_outputs() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "sc_oil.sqlite"
        config_path = root / "config.yaml"
        first_calculated = root / "processed" / "calculated_1.json"
        first_quality = root / "processed" / "quality_1.json"
        first_evidence = root / "processed" / "evidence_1.json"
        first_report = root / "reports" / "SC_daily_1.md"
        second_calculated = root / "processed" / "calculated_2.json"
        second_quality = root / "processed" / "quality_2.json"
        second_evidence = root / "processed" / "evidence_2.json"
        second_report = root / "reports" / "SC_daily_2.md"

        create_database(db_path)
        write_config(config_path)

        first_exit = main(
            pipeline_args(
                EXAMPLE_INPUT,
                PROJECT_DICTIONARY,
                db_path,
                config_path,
                first_calculated,
                first_quality,
                first_evidence,
                first_report,
            )
        )
        second_exit = main(
            pipeline_args(
                EXAMPLE_INPUT,
                PROJECT_DICTIONARY,
                db_path,
                config_path,
                second_calculated,
                second_quality,
                second_evidence,
                second_report,
                extra_args=["--init-db"],
            )
        )
        ids = snapshot_ids(db_path)
        reports = research_report_rows(db_path)

    assert_equal(first_exit, 0, "first run should succeed")
    assert_equal(second_exit, 0, "--init-db should check existing db and continue")
    assert_equal(ids, ["SNAP-20260522-001", "SNAP-20260522-002"], "snapshots should accumulate")
    assert_equal(len(reports), 2, "research reports should accumulate")


def test_missing_database_without_init_returns_one() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "missing.sqlite"
        config_path = root / "config.yaml"
        calculated_input_path = root / "processed" / "calculated_input.json"
        quality_report_path = root / "processed" / "quality_report.json"
        evidence_list_path = root / "processed" / "evidence_list.json"
        daily_report_path = root / "reports" / "SC_daily.md"

        write_config(config_path)
        exit_code = main(
            pipeline_args(
                EXAMPLE_INPUT,
                PROJECT_DICTIONARY,
                db_path,
                config_path,
                calculated_input_path,
                quality_report_path,
                evidence_list_path,
                daily_report_path,
            )
        )

    assert_equal(exit_code, 1, "missing db without --init-db should be program error")


def test_preserve_existing_calculations_keeps_input_values() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "sc_oil.sqlite"
        config_path = root / "config.yaml"
        calculated_input_path = root / "processed" / "calculated_input.json"
        quality_report_path = root / "processed" / "quality_report.json"
        evidence_list_path = root / "processed" / "evidence_list.json"
        daily_report_path = root / "reports" / "SC_daily.md"

        write_config(config_path)
        exit_code = main(
            pipeline_args(
                EXAMPLE_INPUT,
                PROJECT_DICTIONARY,
                db_path,
                config_path,
                calculated_input_path,
                quality_report_path,
                evidence_list_path,
                daily_report_path,
                extra_args=["--init-db", "--preserve-existing-calculations"],
            )
        )
        calculated = json.loads(calculated_input_path.read_text(encoding="utf-8"))

    assert_equal(exit_code, 0, "preserve calculation run should succeed")
    assert_equal(
        calculated["fields"]["SC_Brent_spread_simple"]["value"],
        4.02,
        "preserve flag should keep existing spread value",
    )


def test_report_id_requires_replace_to_overwrite() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "sc_oil.sqlite"
        config_path = root / "config.yaml"
        calculated_input_path = root / "processed" / "calculated_input.json"
        quality_report_path = root / "processed" / "quality_report.json"
        evidence_list_path = root / "processed" / "evidence_list.json"
        daily_report_path = root / "reports" / "SC_daily.md"
        report_id = "RPT-CUSTOM-PIPELINE"

        write_config(config_path)
        first_exit = main(
            pipeline_args(
                EXAMPLE_INPUT,
                PROJECT_DICTIONARY,
                db_path,
                config_path,
                calculated_input_path,
                quality_report_path,
                evidence_list_path,
                daily_report_path,
                extra_args=["--init-db", "--report-id", report_id],
            )
        )
        duplicate_exit = main(
            pipeline_args(
                EXAMPLE_INPUT,
                PROJECT_DICTIONARY,
                db_path,
                config_path,
                calculated_input_path,
                quality_report_path,
                evidence_list_path,
                daily_report_path,
                extra_args=["--report-id", report_id],
            )
        )
        replace_exit = main(
            pipeline_args(
                EXAMPLE_INPUT,
                PROJECT_DICTIONARY,
                db_path,
                config_path,
                calculated_input_path,
                quality_report_path,
                evidence_list_path,
                daily_report_path,
                extra_args=["--report-id", report_id, "--replace"],
            )
        )
        reports = research_report_rows(db_path)

    assert_equal(first_exit, 0, "first explicit report id should succeed")
    assert_equal(duplicate_exit, 1, "duplicate explicit report id should fail without replace")
    assert_equal(replace_exit, 0, "replace should allow explicit report id overwrite")
    assert_equal(len(reports), 1, "replace should keep one explicit report row")
    assert_equal(reports[0]["report_id"], report_id, "explicit report id should be stored")


def run() -> None:
    tests = [
        test_warning_status_runs_complete_pipeline,
        test_warning_status_writes_business_tables_after_research_report,
        test_fail_status_writes_fail_report_without_snapshot_or_evidence,
        test_fail_status_write_business_tables_does_not_write_core_tables,
        test_warning_status_generates_llm_input_package,
        test_fail_status_can_generate_llm_input_package,
        test_init_db_checks_existing_database_without_clearing_outputs,
        test_missing_database_without_init_returns_one,
        test_preserve_existing_calculations_keeps_input_values,
        test_report_id_requires_replace_to_overwrite,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
