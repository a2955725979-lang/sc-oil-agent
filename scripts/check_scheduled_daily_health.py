"""Check health of a scheduled daily run."""

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

from src.database.write_snapshot import DEFAULT_DB_PATH  # noqa: E402


SCHEMA_VERSION = "scheduled_daily_health_v1"
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
    parser = argparse.ArgumentParser(description="Check scheduled daily run health.")
    parser.add_argument("--report-date", required=True, help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--summary", help="Scheduled daily summary JSON path.")
    parser.add_argument("--business-summary", help="Business write summary JSON path.")
    parser.add_argument("--llm-input-package", help="LLM input package JSON path.")
    parser.add_argument("--daily-report", help="Markdown daily report path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = build_health_summary(
        report_date=args.report_date,
        db_path=args.db,
        scheduled_summary_path=args.summary,
        business_summary_path=args.business_summary,
        llm_input_package_path=args.llm_input_package,
        daily_report_path=args.daily_report,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return exit_code_for_status(summary["status"])


def build_health_summary(
    report_date: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    scheduled_summary_path: str | Path | None = None,
    business_summary_path: str | Path | None = None,
    llm_input_package_path: str | Path | None = None,
    daily_report_path: str | Path | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    paths = default_paths(
        report_date=report_date,
        scheduled_summary_path=scheduled_summary_path,
        business_summary_path=business_summary_path,
        llm_input_package_path=llm_input_package_path,
        daily_report_path=daily_report_path,
    )
    scheduled_summary = read_json_if_exists(paths["scheduled_summary"], "scheduled summary", warnings, errors)
    business_summary = read_json_if_exists(paths["business_summary"], "business summary", warnings, [])
    db_counts = collect_db_counts(db_path, warnings)

    checks: dict[str, Any] = {
        "scheduled_summary_exists": paths["scheduled_summary"].exists(),
        "business_summary_exists": paths["business_summary"].exists(),
        "llm_input_package_exists": paths["llm_input_package"].exists(),
        "daily_report_exists": paths["daily_report"].exists(),
        "db_counts": db_counts,
        "scheduled_summary_exit_code": scheduled_summary.get("exit_code") if isinstance(scheduled_summary, dict) else None,
        "scheduled_summary_overall_status": scheduled_summary.get("overall_status")
        if isinstance(scheduled_summary, dict)
        else None,
        "business_counts": _business_counts(business_summary),
    }

    _apply_status_rules(checks, warnings, errors)
    status = "red" if errors else "yellow" if warnings else "green"
    return {
        "schema_version": SCHEMA_VERSION,
        "report_date": report_date,
        "status": status,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }


def default_paths(
    report_date: str,
    scheduled_summary_path: str | Path | None,
    business_summary_path: str | Path | None,
    llm_input_package_path: str | Path | None,
    daily_report_path: str | Path | None,
) -> dict[str, Path]:
    return {
        "scheduled_summary": Path(scheduled_summary_path) if scheduled_summary_path else (
            PROJECT_ROOT / "data" / "processed" / f"scheduled_daily_summary_{report_date}.json"
        ),
        "business_summary": Path(business_summary_path) if business_summary_path else (
            PROJECT_ROOT / "data" / "processed" / f"business_write_summary_{report_date}.json"
        ),
        "llm_input_package": Path(llm_input_package_path) if llm_input_package_path else (
            PROJECT_ROOT / "data" / "processed" / f"llm_input_package_{report_date}.json"
        ),
        "daily_report": Path(daily_report_path) if daily_report_path else (
            PROJECT_ROOT / "reports" / "daily" / f"SC_daily_{report_date}.md"
        ),
    }


def read_json_if_exists(path: Path, label: str, warnings: list[str], errors: list[str]) -> dict[str, Any]:
    if not path.exists():
        message = f"{label} missing: {display_path(path)}"
        if label == "scheduled summary":
            errors.append(message)
        else:
            warnings.append(message)
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label} unreadable: {display_path(path)} ({exc})")
        return {}
    return payload if isinstance(payload, dict) else {}


def collect_db_counts(db_path: str | Path, warnings: list[str]) -> dict[str, int]:
    counts = dict(DB_COUNT_DEFAULTS)
    final_db_path = Path(db_path).expanduser().resolve()
    if not final_db_path.exists():
        warnings.append(f"database missing for health DB counts: {display_path(final_db_path)}")
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


def _business_counts(payload: dict[str, Any]) -> dict[str, int]:
    keys = ("market_prices_written", "fx_rates_written", "spreads_written", "evidence_written")
    return {key: _to_int(payload.get(key)) for key in keys}


def _apply_status_rules(checks: dict[str, Any], warnings: list[str], errors: list[str]) -> None:
    exit_code = checks.get("scheduled_summary_exit_code")
    if exit_code in {1, 2, 3}:
        errors.append(f"scheduled summary exit_code is failure: {exit_code}")
    db_counts = checks["db_counts"]
    if db_counts["market_prices_sc"] == 0:
        errors.append("market_prices has no SC rows")
    if db_counts["fx_rates_usd_cny"] == 0:
        errors.append("fx_rates has no USD/CNY row")
    if db_counts["spread_table"] == 0:
        errors.append("spread_table has no rows")
    if db_counts["market_prices_brent_wti"] > 0:
        errors.append("market_prices contains Brent/WTI rows")
    if checks.get("scheduled_summary_overall_status") == "warning":
        warnings.append("scheduled summary overall_status is warning")
    if not checks.get("llm_input_package_exists"):
        warnings.append("llm_input_package missing")
    if not checks.get("daily_report_exists"):
        warnings.append("daily report missing")


def exit_code_for_status(status: str) -> int:
    return {"green": 0, "red": 1, "yellow": 2}.get(status, 1)


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def display_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    raise SystemExit(main())
