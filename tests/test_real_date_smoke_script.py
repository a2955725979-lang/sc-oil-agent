"""Offline tests for scripts/run_real_date_smoke.py.

Run from the project root:
    python tests/test_real_date_smoke_script.py
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_real_date_smoke.py"
sys.path.insert(0, str(PROJECT_ROOT))

spec = importlib.util.spec_from_file_location("run_real_date_smoke", SCRIPT_PATH)
smoke = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(smoke)

REPORT_DATE = "2026-05-22"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(items, expected, message: str) -> None:
    if expected not in items:
        raise AssertionError(f"{message}: {expected!r} not found in {items!r}")


def assert_text_contains(text: str, fragment: str, message: str) -> None:
    if fragment not in text:
        raise AssertionError(f"{message}: {fragment!r} not found in {text!r}")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def create_minimal_db(path: Path, include_core_rows: bool = True, brent_wti_rows: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE data_snapshot (id INTEGER);")
        conn.execute("CREATE TABLE research_reports (id INTEGER);")
        conn.execute("CREATE TABLE market_prices (symbol TEXT);")
        conn.execute("CREATE TABLE fx_rates (pair TEXT);")
        conn.execute("CREATE TABLE spread_table (id INTEGER);")
        conn.execute("CREATE TABLE evidence_database (id INTEGER);")
        conn.execute("INSERT INTO data_snapshot VALUES (1);")
        conn.execute("INSERT INTO research_reports VALUES (1);")
        conn.execute("INSERT INTO evidence_database VALUES (1);")
        if include_core_rows:
            conn.execute("INSERT INTO market_prices VALUES ('SC');")
            conn.execute("INSERT INTO fx_rates VALUES ('USD/CNY');")
            conn.execute("INSERT INTO spread_table VALUES (1);")
        for _ in range(brent_wti_rows):
            conn.execute("INSERT INTO market_prices VALUES ('Brent');")
        conn.commit()


def test_default_report_id_generation() -> None:
    assert_equal(
        smoke.default_report_id("2026-05-22"),
        "RPT-20260522-SC-DAILY-SMOKE",
        "default report id",
    )


def test_run_auto_daily_args_include_business_write_flags() -> None:
    args = smoke.parse_args(
        [
            "--report-date",
            REPORT_DATE,
            "--db",
            "/tmp/smoke.sqlite",
            "--config",
            "/tmp/config.yaml",
            "--dictionary",
            "/tmp/dictionary.yaml",
            "--init-db",
            "--replace",
        ]
    )
    artifacts = smoke.build_artifact_paths(REPORT_DATE, project_root=Path("/tmp/sc-oil-agent"))
    run_args = smoke.build_run_auto_daily_args(args, "RPT-SMOKE", artifacts)

    assert_contains(run_args, "--write-business-tables", "business table flag")
    assert_contains(run_args, "--business-write-summary-output", "business summary flag")
    assert_contains(run_args, "--akshare-raw-output", "akshare raw output flag")
    assert_contains(run_args, "--market-fx-raw-output", "market/fx raw output flag")
    assert_contains(run_args, "--init-db", "init db flag")
    assert_contains(run_args, "--replace", "replace flag")
    assert_equal(run_args[run_args.index("--report-id") + 1], "RPT-SMOKE", "report id arg")


def test_acceptance_status_green_yellow_red_cases() -> None:
    green_counts = {
        "market_prices_sc": 1,
        "fx_rates_usd_cny": 1,
        "spread_table": 1,
        "market_prices_brent_wti": 0,
    }
    yellow_counts = dict(green_counts)
    red_zero_counts = dict(green_counts)
    red_zero_counts["spread_table"] = 0
    red_brent_counts = dict(green_counts)
    red_brent_counts["market_prices_brent_wti"] = 1

    assert_equal(smoke.determine_acceptance_status(0, "pass", green_counts)[0], "green", "pass green")
    assert_equal(smoke.determine_acceptance_status(0, "warning", yellow_counts)[0], "yellow", "warning yellow")
    assert_equal(smoke.determine_acceptance_status(2, "warning", green_counts)[0], "red", "exit red")
    assert_equal(smoke.determine_acceptance_status(0, "pass", red_zero_counts)[0], "red", "zero core red")
    assert_equal(smoke.determine_acceptance_status(0, "pass", red_brent_counts)[0], "red", "Brent/WTI red")
    missing_status = smoke.determine_acceptance_status(0, None, green_counts)
    assert_equal(missing_status[0], "yellow", "missing status yellow")
    assert_text_contains("; ".join(missing_status[1]), "overall_status missing", "missing status warning")


def test_db_count_collection_from_temp_sqlite() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "smoke.sqlite"
        create_minimal_db(db_path, brent_wti_rows=1)
        warnings: list[str] = []
        counts = smoke.collect_db_counts(db_path, warnings)

    assert_equal(counts["data_snapshot"], 1, "data_snapshot count")
    assert_equal(counts["research_reports"], 1, "research_reports count")
    assert_equal(counts["market_prices_sc"], 1, "SC market count")
    assert_equal(counts["market_prices_brent_wti"], 1, "Brent/WTI market count")
    assert_equal(counts["fx_rates_usd_cny"], 1, "USD/CNY count")
    assert_equal(counts["spread_table"], 1, "spread count")
    assert_equal(counts["evidence_database"], 1, "evidence count")
    assert_equal(warnings, [], "no DB warnings")


def test_missing_artifacts_produce_warnings_not_exceptions() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        artifacts = smoke.build_artifact_paths(REPORT_DATE, project_root=root)
        summary = smoke.build_smoke_summary(
            report_date=REPORT_DATE,
            report_id="RPT-SMOKE",
            exit_code=0,
            artifacts=artifacts,
            db_path=root / "missing.sqlite",
        )

    assert_equal(summary["acceptance_status"], "red", "missing DB core counts should be red")
    assert_text_contains("; ".join(summary["warnings"]), "artifact missing", "missing artifact warning")
    assert_text_contains("; ".join(summary["warnings"]), "database missing", "missing DB warning")


def test_main_uses_mocked_run_auto_daily_and_writes_summary() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "smoke.sqlite"
        smoke_summary_path = root / "real_date_smoke_summary.json"
        artifacts = smoke.build_artifact_paths(REPORT_DATE, output_summary=smoke_summary_path, project_root=root)
        captured_args: list[str] = []

        original_main = smoke.run_auto_daily.main
        original_build_artifact_paths = smoke.build_artifact_paths

        def fake_build_artifact_paths(report_date, output_summary=None, project_root=smoke.PROJECT_ROOT):
            assert_equal(report_date, REPORT_DATE, "fake build report date")
            if output_summary:
                artifacts["smoke_summary"] = Path(output_summary)
            return artifacts

        def fake_run_auto_daily(run_args: list[str]) -> int:
            captured_args.extend(run_args)
            write_json(artifacts["akshare_raw"], {"ok": True})
            write_json(artifacts["market_fx_raw"], {"ok": True})
            write_json(artifacts["daily_input"], {"ok": True})
            write_json(artifacts["calculated_input"], {"ok": True})
            write_json(artifacts["quality_report"], {"overall_status": "warning"})
            write_json(artifacts["evidence_list"], {"evidence_list": []})
            write_text(artifacts["daily_report"], "# Smoke report\n")
            write_json(
                artifacts["business_write_summary"],
                {
                    "market_prices_written": 1,
                    "fx_rates_written": 1,
                    "spreads_written": 1,
                    "evidence_written": 1,
                },
            )
            create_minimal_db(db_path)
            return 0

        smoke.run_auto_daily.main = fake_run_auto_daily
        smoke.build_artifact_paths = fake_build_artifact_paths
        try:
            exit_code = smoke.main(
                [
                    "--report-date",
                    REPORT_DATE,
                    "--db",
                    str(db_path),
                    "--output-summary",
                    str(smoke_summary_path),
                    "--init-db",
                ]
            )
        finally:
            smoke.run_auto_daily.main = original_main
            smoke.build_artifact_paths = original_build_artifact_paths

        summary = load_json(smoke_summary_path)

    assert_equal(exit_code, 0, "mocked smoke exit code")
    assert_contains(captured_args, "--write-business-tables", "captured business table flag")
    assert_contains(captured_args, "--business-write-summary-output", "captured business summary flag")
    assert_equal(summary["schema_version"], "real_date_smoke_summary_v1", "summary schema")
    assert_equal(summary["overall_status"], "warning", "summary status")
    assert_equal(summary["acceptance_status"], "yellow", "warning run is yellow")
    assert_equal(summary["business_counts"]["market_prices_written"], 1, "business market count")
    assert_equal(summary["db_counts"]["market_prices_sc"], 1, "DB SC count")


def run() -> None:
    tests = [
        test_default_report_id_generation,
        test_run_auto_daily_args_include_business_write_flags,
        test_acceptance_status_green_yellow_red_cases,
        test_db_count_collection_from_temp_sqlite,
        test_missing_artifacts_produce_warnings_not_exceptions,
        test_main_uses_mocked_run_auto_daily_and_writes_summary,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
