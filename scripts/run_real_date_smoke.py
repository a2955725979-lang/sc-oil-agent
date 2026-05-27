"""Manual real-date smoke test for auto daily DB persistence."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.write_snapshot import DEFAULT_CONFIG_PATH, DEFAULT_DB_PATH  # noqa: E402
from src.pipeline import run_auto_daily  # noqa: E402
from src.validators.run_quality_validation import DEFAULT_DICTIONARY_PATH  # noqa: E402


SCHEMA_VERSION = "real_date_smoke_summary_v1"
ARTIFACT_KEYS_TO_CHECK = (
    "akshare_raw",
    "market_fx_raw",
    "daily_input",
    "calculated_input",
    "quality_report",
    "evidence_list",
    "daily_report",
    "business_write_summary",
)
BUSINESS_COUNT_KEYS = (
    "market_prices_written",
    "fx_rates_written",
    "spreads_written",
    "evidence_written",
)
DB_COUNT_DEFAULTS = {
    "data_snapshot": 0,
    "research_reports": 0,
    "market_prices_sc": 0,
    "market_prices_brent_wti": 0,
    "fx_rates_usd_cny": 0,
    "spread_table": 0,
    "evidence_database": 0,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a manual real-date auto daily DB persistence smoke test.")
    parser.add_argument("--report-date", required=True, help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Project config YAML path.")
    parser.add_argument("--dictionary", default=str(DEFAULT_DICTIONARY_PATH), help="Data dictionary YAML path.")
    parser.add_argument("--report-id", help="Explicit smoke research report id.")
    parser.add_argument("--replace", action="store_true", help="Replace an existing smoke report with the same id.")
    parser.add_argument("--init-db", action="store_true", help="Initialize/check SQLite DB before the smoke run.")
    parser.add_argument("--output-summary", help="Smoke summary JSON output path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    exit_code = run_smoke(args)
    return exit_code


def run_smoke(args: argparse.Namespace) -> int:
    report_id = args.report_id or default_report_id(args.report_date)
    artifacts = build_artifact_paths(args.report_date, args.output_summary)
    run_args = build_run_auto_daily_args(args, report_id, artifacts)

    exit_code = run_auto_daily.main(run_args)
    summary = build_smoke_summary(
        report_date=args.report_date,
        report_id=report_id,
        exit_code=exit_code,
        artifacts=artifacts,
        db_path=Path(args.db),
    )
    write_smoke_summary(summary, artifacts["smoke_summary"])
    print_smoke_summary(summary, artifacts["smoke_summary"])
    return exit_code


def default_report_id(report_date: str) -> str:
    return f"RPT-{report_date.replace('-', '')}-SC-DAILY-SMOKE"


def build_artifact_paths(
    report_date: str,
    output_summary: str | Path | None = None,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Path]:
    return {
        "akshare_raw": project_root / "data" / "raw" / f"akshare_sc_{report_date}.json",
        "market_fx_raw": project_root / "data" / "raw" / f"market_fx_{report_date}.json",
        "eia_raw": project_root / "data" / "raw" / f"eia_inventory_{report_date}.json",
        "daily_input": project_root / "data" / "manual" / f"daily_input_{report_date}.json",
        "calculated_input": project_root / "data" / "processed" / f"calculated_input_{report_date}.json",
        "quality_report": project_root / "data" / "processed" / f"quality_report_{report_date}.json",
        "evidence_list": project_root / "data" / "processed" / f"evidence_list_{report_date}.json",
        "daily_report": project_root / "reports" / "daily" / f"SC_daily_{report_date}.md",
        "business_write_summary": project_root / "data" / "processed" / f"business_write_summary_{report_date}.json",
        "smoke_summary": Path(output_summary) if output_summary else (
            project_root / "data" / "processed" / f"real_date_smoke_summary_{report_date}.json"
        ),
    }


def build_run_auto_daily_args(
    args: argparse.Namespace,
    report_id: str,
    artifacts: dict[str, Path],
) -> list[str]:
    run_args = [
        "--report-date",
        args.report_date,
        "--akshare-raw-output",
        str(artifacts["akshare_raw"]),
        "--market-fx-raw-output",
        str(artifacts["market_fx_raw"]),
        "--eia-raw-output",
        str(artifacts["eia_raw"]),
        "--auto-daily-input-output",
        str(artifacts["daily_input"]),
        "--calculated-input-output",
        str(artifacts["calculated_input"]),
        "--quality-report-output",
        str(artifacts["quality_report"]),
        "--evidence-list-output",
        str(artifacts["evidence_list"]),
        "--daily-report-output",
        str(artifacts["daily_report"]),
        "--db",
        str(args.db),
        "--config",
        str(args.config),
        "--dictionary",
        str(args.dictionary),
        "--report-id",
        report_id,
        "--write-business-tables",
        "--business-write-summary-output",
        str(artifacts["business_write_summary"]),
    ]
    if args.init_db:
        run_args.append("--init-db")
    if args.replace:
        run_args.append("--replace")
    return run_args


def build_smoke_summary(
    report_date: str,
    report_id: str,
    exit_code: int,
    artifacts: dict[str, Path],
    db_path: str | Path,
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    overall_status = read_overall_status(artifacts["quality_report"], warnings)
    business_counts = read_business_counts(artifacts["business_write_summary"], warnings)
    db_counts = collect_db_counts(db_path, warnings)
    add_missing_artifact_warnings(artifacts, warnings)
    acceptance_status, acceptance_warnings, acceptance_errors = determine_acceptance_status(
        exit_code=exit_code,
        overall_status=overall_status,
        db_counts=db_counts,
    )
    warnings.extend(acceptance_warnings)
    errors.extend(acceptance_errors)

    return {
        "schema_version": SCHEMA_VERSION,
        "report_date": report_date,
        "report_id": report_id,
        "exit_code": exit_code,
        "overall_status": overall_status,
        "artifacts": {key: display_path(path) for key, path in artifacts.items()},
        "business_counts": business_counts,
        "db_counts": db_counts,
        "acceptance_status": acceptance_status,
        "warnings": warnings,
        "errors": errors,
    }


def read_overall_status(path: Path, warnings: list[str]) -> str | None:
    payload = read_json_if_exists(path, warnings, "quality_report")
    if not isinstance(payload, dict):
        return None
    status = payload.get("overall_status")
    if status is None:
        warnings.append(f"quality_report missing overall_status: {display_path(path)}")
        return None
    return str(status)


def read_business_counts(path: Path, warnings: list[str]) -> dict[str, int]:
    counts = {key: 0 for key in BUSINESS_COUNT_KEYS}
    payload = read_json_if_exists(path, warnings, "business_write_summary")
    if not isinstance(payload, dict):
        return counts
    for key in counts:
        counts[key] = to_int(payload.get(key))
    return counts


def read_json_if_exists(path: Path, warnings: list[str], label: str) -> dict[str, Any] | None:
    if not path.exists():
        warnings.append(f"{label} artifact missing: {display_path(path)}")
        return None
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(f"{label} artifact unreadable: {display_path(path)} ({exc})")
        return None
    return payload if isinstance(payload, dict) else None


def collect_db_counts(db_path: str | Path, warnings: list[str]) -> dict[str, int]:
    counts = dict(DB_COUNT_DEFAULTS)
    final_db_path = Path(db_path).expanduser().resolve()
    if not final_db_path.exists():
        warnings.append(f"database missing for smoke DB counts: {display_path(final_db_path)}")
        return counts

    queries = {
        "data_snapshot": "SELECT COUNT(*) FROM data_snapshot;",
        "research_reports": "SELECT COUNT(*) FROM research_reports;",
        "market_prices_sc": "SELECT COUNT(*) FROM market_prices WHERE symbol = 'SC';",
        "market_prices_brent_wti": "SELECT COUNT(*) FROM market_prices WHERE symbol IN ('Brent', 'WTI');",
        "fx_rates_usd_cny": "SELECT COUNT(*) FROM fx_rates WHERE pair = 'USD/CNY';",
        "spread_table": "SELECT COUNT(*) FROM spread_table;",
        "evidence_database": "SELECT COUNT(*) FROM evidence_database;",
    }
    try:
        with sqlite3.connect(final_db_path) as conn:
            for key, query in queries.items():
                row = conn.execute(query).fetchone()
                counts[key] = int(row[0]) if row else 0
    except sqlite3.Error as exc:
        warnings.append(f"database count collection failed: {exc}")
    return counts


def add_missing_artifact_warnings(artifacts: dict[str, Path], warnings: list[str]) -> None:
    for key in ARTIFACT_KEYS_TO_CHECK:
        path = artifacts[key]
        message = f"artifact missing: {key}={display_path(path)}"
        if not path.exists() and message not in warnings:
            warnings.append(message)


def determine_acceptance_status(
    exit_code: int,
    overall_status: str | None,
    db_counts: dict[str, int],
) -> tuple[str, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    if exit_code != 0:
        errors.append(f"run_auto_daily exit_code={exit_code}")
        return "red", warnings, errors

    required_counts = {
        "market_prices_sc": "no SC rows in market_prices",
        "fx_rates_usd_cny": "no USD/CNY row in fx_rates",
        "spread_table": "no spread row in spread_table",
    }
    for key, message in required_counts.items():
        if db_counts.get(key, 0) == 0:
            errors.append(message)
    if db_counts.get("market_prices_brent_wti", 0) > 0:
        errors.append("market_prices contains Brent or WTI rows")
    if errors:
        return "red", warnings, errors

    if overall_status == "pass":
        return "green", warnings, errors
    if overall_status == "warning":
        return "yellow", warnings, errors
    if overall_status is None:
        warnings.append("overall_status missing after successful smoke run")
        return "yellow", warnings, errors
    if overall_status == "fail":
        errors.append("overall_status=fail after exit_code=0")
        return "red", warnings, errors
    warnings.append(f"unrecognized overall_status after successful smoke run: {overall_status}")
    return "yellow", warnings, errors


def write_smoke_summary(summary: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)
        file.write("\n")


def print_smoke_summary(summary: dict[str, Any], path: Path) -> None:
    print(f"real_date_smoke_summary_path: {display_path(path)}")
    print(f"acceptance_status: {summary['acceptance_status']}")
    print(f"exit_code: {summary['exit_code']}")
    print(f"overall_status: {summary.get('overall_status') or ''}")
    print(f"report_id: {summary['report_id']}")
    print(f"warnings: {len(summary['warnings'])}")
    print(f"errors: {len(summary['errors'])}")


def to_int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def display_path(path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    raise SystemExit(main())
