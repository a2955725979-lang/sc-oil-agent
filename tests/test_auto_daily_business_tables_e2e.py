"""End-to-end tests for auto daily business table persistence.

Run from the project root:
    python tests/test_auto_daily_business_tables_e2e.py
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
from src.fetchers.market_fx import build_fetch_result_from_rows as build_market_fx_fetch_result  # noqa: E402
from src.pipeline import run_auto_daily as workflow  # noqa: E402


AKSHARE_ROWS_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "akshare_sc" / "ine_sc_rows.json"
PROJECT_DICTIONARY = PROJECT_ROOT / "config" / "data_dictionary.yaml"
REPORT_DATE = "2026-01-15"
REPORT_ID = "RPT-AUTO-DB-E2E"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def assert_contains(text: str, expected_fragment: str, message: str) -> None:
    if expected_fragment not in text:
        raise AssertionError(f"{message}: {expected_fragment!r} not found in {text!r}")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_config(path: Path) -> None:
    write_text(
        path,
        """
report:
  prompt_version: test_prompt_v1
  calculation_version: test_calc_v1
""",
    )


def write_fail_dictionary(path: Path) -> None:
    write_text(
        path,
        """
missing_required_for_e2e:
  required: true
  unit: text
  frequency: daily
  quality_checks: [missing_check]
""",
    )


def build_akshare_raw_data(report_date: str = REPORT_DATE) -> dict:
    rows = json.loads(AKSHARE_ROWS_FIXTURE.read_text(encoding="utf-8"))
    return build_akshare_fetch_result(
        rows=rows,
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


def write_raw_inputs(root: Path) -> tuple[Path, Path]:
    akshare_raw_path = root / "raw" / "akshare_sc.json"
    market_fx_raw_path = root / "raw" / "market_fx.json"
    write_json(akshare_raw_path, build_akshare_raw_data())
    write_json(market_fx_raw_path, build_market_fx_raw_data())
    return akshare_raw_path, market_fx_raw_path


def auto_daily_args(
    root: Path,
    akshare_raw_path: Path,
    market_fx_raw_path: Path,
    dictionary_path: Path = PROJECT_DICTIONARY,
    extra_args: list[str] | None = None,
) -> list[str]:
    args = [
        "--report-date",
        REPORT_DATE,
        "--akshare-raw-input",
        str(akshare_raw_path),
        "--market-fx-raw-input",
        str(market_fx_raw_path),
        "--akshare-raw-output",
        str(root / "raw" / "should_not_fetch_akshare.json"),
        "--market-fx-raw-output",
        str(root / "raw" / "should_not_fetch_market_fx.json"),
        "--eia-raw-output",
        str(root / "raw" / "eia_inventory.json"),
        "--akshare-daily-input-output",
        str(root / "processed" / "akshare_daily_input.json"),
        "--market-fx-daily-input-output",
        str(root / "processed" / "market_fx_daily_input.json"),
        "--eia-daily-input-output",
        str(root / "processed" / "eia_daily_input.json"),
        "--default-fields-output",
        str(root / "processed" / "default_fields.json"),
        "--akshare-conversion-result-output",
        str(root / "processed" / "akshare_conversion_result.json"),
        "--market-fx-conversion-result-output",
        str(root / "processed" / "market_fx_conversion_result.json"),
        "--eia-conversion-result-output",
        str(root / "processed" / "eia_conversion_result.json"),
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
        str(dictionary_path),
        "--report-id",
        REPORT_ID,
        "--replace",
        "--init-db",
        "--write-business-tables",
        "--business-write-summary-output",
        str(root / "processed" / "business_write_summary.json"),
    ]
    if extra_args:
        args.extend(extra_args)
    return args


def table_count(db_path: Path, table_name: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table_name};").fetchone()[0]


def table_counts(db_path: Path) -> dict[str, int]:
    return {
        "research_reports": table_count(db_path, "research_reports"),
        "data_snapshot": table_count(db_path, "data_snapshot"),
        "market_prices": table_count(db_path, "market_prices"),
        "fx_rates": table_count(db_path, "fx_rates"),
        "spread_table": table_count(db_path, "spread_table"),
        "evidence_database": table_count(db_path, "evidence_database"),
    }


def fetch_rows(db_path: Path, query: str) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(query).fetchall()]


def test_auto_daily_business_table_persistence_is_e2e_and_idempotent() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_config(root / "config.yaml")
        akshare_raw_path, market_fx_raw_path = write_raw_inputs(root)
        args = auto_daily_args(root, akshare_raw_path, market_fx_raw_path)

        first_exit = workflow.main(args)
        calculated_exists = (root / "processed" / "calculated_input.json").exists()
        quality_exists = (root / "processed" / "quality_report.json").exists()
        evidence_exists = (root / "processed" / "evidence_list.json").exists()
        markdown_exists = (root / "reports" / "SC_daily.md").exists()
        summary_path = root / "processed" / "business_write_summary.json"
        summary_exists = summary_path.exists()
        first_summary = load_json(summary_path)
        db_path = root / "sc_oil.sqlite"
        first_counts = table_counts(db_path)
        first_snapshot_ids = [
            row["data_snapshot_id"]
            for row in fetch_rows(db_path, "SELECT data_snapshot_id FROM data_snapshot ORDER BY data_snapshot_id;")
        ]
        market_symbols = [
            row["symbol"]
            for row in fetch_rows(db_path, "SELECT DISTINCT symbol FROM market_prices ORDER BY symbol;")
        ]
        evidence_fk_rows = fetch_rows(
            db_path,
            """
            SELECT evidence_id, report_id, data_snapshot_id
            FROM evidence_database
            ORDER BY evidence_id;
            """,
        )

        second_exit = workflow.main(args)
        second_summary = load_json(summary_path)
        second_counts = table_counts(db_path)
        snapshot_ids_after_second = {
            row["data_snapshot_id"]
            for row in fetch_rows(db_path, "SELECT data_snapshot_id FROM data_snapshot;")
        }
        evidence_fk_rows_after_second = fetch_rows(
            db_path,
            """
            SELECT evidence_id, report_id, data_snapshot_id
            FROM evidence_database
            ORDER BY evidence_id;
            """,
        )

    assert_equal(first_exit, 0, "first auto daily run should pass with warning data")
    assert_equal(calculated_exists, True, "calculated input should be written")
    assert_equal(quality_exists, True, "quality report should be written")
    assert_equal(evidence_exists, True, "evidence list should be written")
    assert_equal(markdown_exists, True, "Markdown daily report should be written")
    assert_equal(summary_exists, True, "business write summary should be written")

    assert_equal(first_counts["research_reports"], 1, "one research report row")
    assert_equal(first_counts["data_snapshot"], 1, "one data snapshot row")
    assert_true(first_counts["market_prices"] >= 1, "SC market rows should be written")
    assert_equal(first_counts["fx_rates"], 1, "one USD/CNY row should be written")
    assert_equal(first_counts["spread_table"], 1, "one spread row should be written")
    assert_true(first_counts["evidence_database"] > 0, "evidence rows should be written")
    assert_equal(market_symbols, ["SC"], "market_prices must not contain Brent or WTI symbols")

    assert_equal(first_summary["market_prices_written"], first_counts["market_prices"], "summary market count")
    assert_equal(first_summary["fx_rates_written"], 1, "summary fx count")
    assert_equal(first_summary["spreads_written"], 1, "summary spread count")
    assert_equal(first_summary["evidence_written"], first_counts["evidence_database"], "summary evidence count")
    assert_equal(first_summary["research_report_id"], REPORT_ID, "summary report id")
    assert_equal(first_summary["data_snapshot_id"], first_snapshot_ids[0], "summary snapshot id")
    assert_equal(isinstance(first_summary["warnings"], list), True, "summary warnings should be stable list")
    assert_equal(isinstance(first_summary["errors"], list), True, "summary errors should be stable list")

    assert_true(evidence_fk_rows, "evidence FK rows should exist")
    for row in evidence_fk_rows:
        assert_equal(row["report_id"], REPORT_ID, "evidence should reference research_reports")
        assert_equal(row["data_snapshot_id"], first_snapshot_ids[0], "evidence should reference data_snapshot")

    assert_equal(second_exit, 0, "second auto daily run with --replace should succeed")
    assert_equal(second_counts["research_reports"], 1, "replace should keep one research report")
    assert_equal(second_counts["market_prices"], first_counts["market_prices"], "market rows should not duplicate")
    assert_equal(second_counts["fx_rates"], first_counts["fx_rates"], "fx rows should not duplicate")
    assert_equal(second_counts["spread_table"], first_counts["spread_table"], "spread rows should not duplicate")
    assert_equal(
        second_counts["evidence_database"],
        first_counts["evidence_database"],
        "evidence rows should not duplicate",
    )
    assert_equal(second_summary["research_report_id"], REPORT_ID, "second summary report id")
    for row in evidence_fk_rows_after_second:
        assert_equal(row["report_id"], REPORT_ID, "updated evidence report FK")
        assert_true(row["data_snapshot_id"] in snapshot_ids_after_second, "updated evidence snapshot FK")


def test_auto_daily_quality_fail_does_not_write_core_business_tables() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_config(root / "config.yaml")
        fail_dictionary_path = root / "fail_dictionary.yaml"
        write_fail_dictionary(fail_dictionary_path)
        akshare_raw_path, market_fx_raw_path = write_raw_inputs(root)

        exit_code = workflow.main(
            auto_daily_args(root, akshare_raw_path, market_fx_raw_path, dictionary_path=fail_dictionary_path)
        )
        db_path = root / "sc_oil.sqlite"
        summary_path = root / "processed" / "business_write_summary.json"
        quality_report = load_json(root / "processed" / "quality_report.json")
        summary = load_json(summary_path)
        markdown = (root / "reports" / "SC_daily.md").read_text(encoding="utf-8")
        counts = table_counts(db_path)

    assert_equal(exit_code, 2, "quality fail should return controlled failure")
    assert_equal(quality_report["overall_status"], "fail", "quality report should fail")
    assert_contains(markdown, "数据质量状态为 fail", "fail Markdown should be written")
    assert_equal(counts["research_reports"], 1, "fail research report should be written")
    assert_equal(counts["data_snapshot"], 0, "fail path should not write data_snapshot")
    assert_equal(counts["market_prices"], 0, "fail path should not write market_prices")
    assert_equal(counts["fx_rates"], 0, "fail path should not write fx_rates")
    assert_equal(counts["spread_table"], 0, "fail path should not write spread_table")
    assert_equal(counts["evidence_database"], 0, "fail path should not write evidence without evidence list")
    assert_equal(summary["market_prices_written"], 0, "fail summary market count")
    assert_equal(summary["fx_rates_written"], 0, "fail summary fx count")
    assert_equal(summary["spreads_written"], 0, "fail summary spread count")
    assert_equal(summary["evidence_written"], 0, "fail summary evidence count")
    assert_contains(
        "; ".join(summary["warnings"]),
        "evidence_database write skipped because evidence_list is absent",
        "fail summary should explain skipped evidence",
    )


def run() -> None:
    tests = [
        test_auto_daily_business_table_persistence_is_e2e_and_idempotent,
        test_auto_daily_quality_fail_does_not_write_core_business_tables,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
