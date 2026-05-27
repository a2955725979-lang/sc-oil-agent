"""Offline tests for scheduled daily health checks.

Run from the project root:
    python tests/test_scheduled_daily_health.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "check_scheduled_daily_health.py"
sys.path.insert(0, str(PROJECT_ROOT))

spec = importlib.util.spec_from_file_location("check_scheduled_daily_health", SCRIPT_PATH)
health = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(health)

REPORT_DATE = "2026-05-22"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_text_contains(text: str, fragment: str, message: str) -> None:
    if fragment not in text:
        raise AssertionError(f"{message}: {fragment!r} not found in {text!r}")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def create_db(path: Path, sc_rows: int = 1, fx_rows: int = 1, spread_rows: int = 1, brent_wti_rows: int = 0) -> None:
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
        for _ in range(sc_rows):
            conn.execute("INSERT INTO market_prices VALUES ('SC');")
        for _ in range(brent_wti_rows):
            conn.execute("INSERT INTO market_prices VALUES ('Brent');")
        for _ in range(fx_rows):
            conn.execute("INSERT INTO fx_rates VALUES ('USD/CNY');")
        for _ in range(spread_rows):
            conn.execute("INSERT INTO spread_table VALUES (1);")
        conn.commit()


def create_artifacts(root: Path, overall_status: str = "pass", exit_code: int = 0) -> dict[str, Path]:
    paths = {
        "db": root / "sc_oil.sqlite",
        "summary": root / "scheduled_summary.json",
        "business": root / "business_summary.json",
        "llm": root / "llm_input_package.json",
        "daily": root / "SC_daily.md",
    }
    create_db(paths["db"])
    write_json(
        paths["summary"],
        {
            "schema_version": "scheduled_daily_summary_v1",
            "report_date": REPORT_DATE,
            "exit_code": exit_code,
            "overall_status": overall_status,
        },
    )
    write_json(paths["business"], {"market_prices_written": 1, "fx_rates_written": 1, "spreads_written": 1})
    write_json(paths["llm"], {"schema_version": "llm_input_package_v1"})
    write_text(paths["daily"], "# Daily report\n")
    return paths


def run_health(paths: dict[str, Path]) -> dict:
    return health.build_health_summary(
        report_date=REPORT_DATE,
        db_path=paths["db"],
        scheduled_summary_path=paths["summary"],
        business_summary_path=paths["business"],
        llm_input_package_path=paths["llm"],
        daily_report_path=paths["daily"],
    )


def test_green_health_when_required_rows_exist() -> None:
    with TemporaryDirectory() as tmp:
        summary = run_health(create_artifacts(Path(tmp)))
    assert_equal(summary["status"], "green", "green status")
    assert_equal(summary["checks"]["db_counts"]["market_prices_sc"], 1, "SC rows")


def test_yellow_when_overall_status_warning() -> None:
    with TemporaryDirectory() as tmp:
        summary = run_health(create_artifacts(Path(tmp), overall_status="warning"))
    assert_equal(summary["status"], "yellow", "warning status yellow")
    assert_text_contains("; ".join(summary["warnings"]), "overall_status is warning", "warning reason")


def test_red_when_scheduled_summary_missing() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = create_artifacts(root)
        paths["summary"].unlink()
        summary = run_health(paths)
    assert_equal(summary["status"], "red", "missing scheduled summary red")
    assert_text_contains("; ".join(summary["errors"]), "scheduled summary missing", "missing summary error")


def test_red_for_scheduled_exit_codes() -> None:
    for exit_code in [1, 2, 3]:
        with TemporaryDirectory() as tmp:
            summary = run_health(create_artifacts(Path(tmp), exit_code=exit_code))
        assert_equal(summary["status"], "red", f"exit {exit_code} red")


def test_red_when_core_db_rows_missing() -> None:
    cases = [
        ("market_prices_sc", {"sc_rows": 0}, "market_prices has no SC rows"),
        ("fx_rates_usd_cny", {"fx_rows": 0}, "fx_rates has no USD/CNY row"),
        ("spread_table", {"spread_rows": 0}, "spread_table has no rows"),
        ("market_prices_brent_wti", {"brent_wti_rows": 1}, "market_prices contains Brent/WTI rows"),
    ]
    for _key, kwargs, expected_error in cases:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = create_artifacts(root)
            paths["db"].unlink()
            create_db(paths["db"], **kwargs)
            summary = run_health(paths)
        assert_equal(summary["status"], "red", expected_error)
        assert_text_contains("; ".join(summary["errors"]), expected_error, expected_error)


def test_yellow_when_llm_input_package_missing_but_core_checks_pass() -> None:
    with TemporaryDirectory() as tmp:
        paths = create_artifacts(Path(tmp))
        paths["llm"].unlink()
        summary = run_health(paths)
    assert_equal(summary["status"], "yellow", "missing LLM yellow")
    assert_text_contains("; ".join(summary["warnings"]), "llm_input_package missing", "LLM warning")


def test_cli_prints_stable_summary_and_exit_codes() -> None:
    expected = [("pass", 0), ("warning", 2)]
    for overall_status, expected_exit in expected:
        with TemporaryDirectory() as tmp:
            paths = create_artifacts(Path(tmp), overall_status=overall_status)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = health.main(
                    [
                        "--report-date",
                        REPORT_DATE,
                        "--db",
                        str(paths["db"]),
                        "--summary",
                        str(paths["summary"]),
                        "--business-summary",
                        str(paths["business"]),
                        "--llm-input-package",
                        str(paths["llm"]),
                        "--daily-report",
                        str(paths["daily"]),
                    ]
                )
            payload = json.loads(output.getvalue())
        assert_equal(exit_code, expected_exit, f"CLI exit for {overall_status}")
        assert_equal(payload["schema_version"], "scheduled_daily_health_v1", "CLI schema")

    with TemporaryDirectory() as tmp:
        paths = create_artifacts(Path(tmp), exit_code=1)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = health.main(
                [
                    "--report-date",
                    REPORT_DATE,
                    "--db",
                    str(paths["db"]),
                    "--summary",
                    str(paths["summary"]),
                    "--business-summary",
                    str(paths["business"]),
                    "--llm-input-package",
                    str(paths["llm"]),
                    "--daily-report",
                    str(paths["daily"]),
                ]
            )
    assert_equal(exit_code, 1, "CLI red exit")


def run() -> None:
    tests = [
        test_green_health_when_required_rows_exist,
        test_yellow_when_overall_status_warning,
        test_red_when_scheduled_summary_missing,
        test_red_for_scheduled_exit_codes,
        test_red_when_core_db_rows_missing,
        test_yellow_when_llm_input_package_missing_but_core_checks_pass,
        test_cli_prints_stable_summary_and_exit_codes,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
