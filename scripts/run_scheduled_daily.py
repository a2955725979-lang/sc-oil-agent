"""Scheduler-safe trigger for daily auto pipeline runs.

This script is a thin operational wrapper. It does not install a scheduler,
fetch data directly, call an LLM, or generate trading conclusions.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.write_snapshot import DEFAULT_CONFIG_PATH, DEFAULT_DB_PATH  # noqa: E402
from src.pipeline import run_auto_daily  # noqa: E402
from src.validators.run_quality_validation import DEFAULT_DICTIONARY_PATH  # noqa: E402


SCHEMA_VERSION = "scheduled_daily_summary_v1"
TRIGGER_MODE = "scheduled_trigger"
EXIT_SCHEDULER_GUARD = 3
DEFAULT_LOCK_TIMEOUT_MINUTES = 120
SUMMARY_ARTIFACT_KEYS = (
    "business_write_summary",
    "llm_input_package",
    "quality_report",
    "daily_report",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the scheduler-safe daily auto trigger.")
    parser.add_argument("--report-date", help="Report date in YYYY-MM-DD format. Defaults to Asia/Shanghai today.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Project config YAML path.")
    parser.add_argument("--dictionary", default=str(DEFAULT_DICTIONARY_PATH), help="Data dictionary YAML path.")
    parser.add_argument("--report-id", help="Explicit research report id.")
    parser.add_argument("--replace", action="store_true", help="Replace an existing report with the same id.")
    parser.add_argument("--init-db", action="store_true", help="Initialize/check SQLite DB before the run.")
    parser.add_argument("--summary-output", help="Scheduled summary JSON output path.")
    parser.add_argument("--lock-path", default=str(PROJECT_ROOT / ".runtime" / "scheduled_daily.lock"))
    parser.add_argument("--lock-timeout-minutes", type=int, default=DEFAULT_LOCK_TIMEOUT_MINUTES)
    parser.add_argument("--force-unlock", action="store_true", help="Remove a stale lock before running.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_scheduled_daily(args, command=list(argv) if argv is not None else sys.argv[1:])


def run_scheduled_daily(args: argparse.Namespace, command: list[str]) -> int:
    report_date = args.report_date or default_report_date()
    report_id = args.report_id or default_report_id(report_date)
    artifacts = build_artifact_paths(report_date, args.summary_output)
    started_at = utc_now_iso()
    warnings: list[str] = []
    errors: list[str] = []
    lock_path = Path(args.lock_path)
    lock_id: str | None = None
    exit_code = EXIT_SCHEDULER_GUARD

    try:
        lock_result = acquire_lock(
            lock_path=lock_path,
            report_date=report_date,
            command=command,
            timeout_minutes=args.lock_timeout_minutes,
            force_unlock=args.force_unlock,
        )
        warnings.extend(lock_result["warnings"])
        errors.extend(lock_result["errors"])
        if not lock_result["acquired"]:
            exit_code = EXIT_SCHEDULER_GUARD
            return _finalize_summary(
                report_date=report_date,
                report_id=report_id,
                started_at=started_at,
                exit_code=exit_code,
                run_args=[],
                artifacts=artifacts,
                warnings=warnings,
                errors=errors,
            )
        lock_id = lock_result["lock_id"]

        run_args = build_run_auto_daily_args(args, report_date, report_id, artifacts)
        exit_code = run_auto_daily.main(run_args)
        return _finalize_summary(
            report_date=report_date,
            report_id=report_id,
            started_at=started_at,
            exit_code=exit_code,
            run_args=run_args,
            artifacts=artifacts,
            warnings=warnings,
            errors=errors,
        )
    finally:
        if lock_id:
            release_lock(lock_path, lock_id)


def default_report_date(now: datetime | None = None) -> str:
    current = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    return current.date().isoformat()


def default_report_id(report_date: str) -> str:
    return f"RPT-{report_date.replace('-', '')}-SC-DAILY-SCHEDULED"


def build_artifact_paths(
    report_date: str,
    summary_output: str | Path | None = None,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Path]:
    return {
        "business_write_summary": project_root / "data" / "processed" / f"business_write_summary_{report_date}.json",
        "llm_input_package": project_root / "data" / "processed" / f"llm_input_package_{report_date}.json",
        "quality_report": project_root / "data" / "processed" / f"quality_report_{report_date}.json",
        "daily_report": project_root / "reports" / "daily" / f"SC_daily_{report_date}.md",
        "scheduled_summary": Path(summary_output) if summary_output else (
            project_root / "data" / "processed" / f"scheduled_daily_summary_{report_date}.json"
        ),
    }


def build_run_auto_daily_args(
    args: argparse.Namespace,
    report_date: str,
    report_id: str,
    artifacts: dict[str, Path],
) -> list[str]:
    run_args = [
        "--report-date",
        report_date,
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
        "--generate-llm-input-package",
        "--llm-input-package-output",
        str(artifacts["llm_input_package"]),
    ]
    if args.init_db:
        run_args.append("--init-db")
    if args.replace:
        run_args.append("--replace")
    return run_args


def acquire_lock(
    lock_path: Path,
    report_date: str,
    command: list[str],
    timeout_minutes: int,
    force_unlock: bool,
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    lock_path = lock_path.expanduser().resolve()
    if lock_path.exists():
        lock_payload = read_lock(lock_path)
        stale = is_stale_lock(lock_payload, timeout_minutes)
        if not stale:
            errors.append(f"active scheduler lock exists: {display_path(lock_path)}")
            return {"acquired": False, "warnings": warnings, "errors": errors}
        warnings.append(f"stale scheduler lock detected: {display_path(lock_path)}")
        if not force_unlock:
            errors.append("stale scheduler lock requires --force-unlock")
            return {"acquired": False, "warnings": warnings, "errors": errors}
        lock_path.unlink()
        warnings.append("stale scheduler lock removed by --force-unlock")

    lock_id = uuid.uuid4().hex
    lock_payload = {
        "lock_id": lock_id,
        "pid": os.getpid(),
        "report_date": report_date,
        "started_at": utc_now_iso(),
        "command": command,
    }
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        errors.append(f"active scheduler lock exists: {display_path(lock_path)}")
        return {"acquired": False, "warnings": warnings, "errors": errors}
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(lock_payload, handle, ensure_ascii=False, indent=2)
    return {"acquired": True, "lock_id": lock_id, "warnings": warnings, "errors": errors}


def release_lock(lock_path: Path, lock_id: str | None) -> None:
    if not lock_id:
        return
    final_lock_path = lock_path.expanduser().resolve()
    if not final_lock_path.exists():
        return
    payload = read_lock(final_lock_path)
    if payload.get("lock_id") != lock_id:
        return
    try:
        final_lock_path.unlink()
    except OSError:
        pass


def read_lock(lock_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def is_stale_lock(lock_payload: dict[str, Any], timeout_minutes: int) -> bool:
    started_at = lock_payload.get("started_at")
    if not started_at:
        return True
    try:
        started = datetime.fromisoformat(str(started_at))
    except ValueError:
        return True
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - started.astimezone(timezone.utc)).total_seconds()
    return age_seconds > max(timeout_minutes, 0) * 60


def _finalize_summary(
    report_date: str,
    report_id: str,
    started_at: str,
    exit_code: int,
    run_args: list[str],
    artifacts: dict[str, Path],
    warnings: list[str],
    errors: list[str],
) -> int:
    summary = build_scheduled_summary(
        report_date=report_date,
        report_id=report_id,
        started_at=started_at,
        exit_code=exit_code,
        run_args=run_args,
        artifacts=artifacts,
        warnings=warnings,
        errors=errors,
    )
    write_summary(summary, artifacts["scheduled_summary"])
    print_summary(summary, artifacts["scheduled_summary"])
    return exit_code


def build_scheduled_summary(
    report_date: str,
    report_id: str,
    started_at: str,
    exit_code: int,
    run_args: list[str],
    artifacts: dict[str, Path],
    warnings: list[str],
    errors: list[str],
) -> dict[str, Any]:
    final_warnings = list(warnings)
    final_errors = list(errors)
    finished_at = utc_now_iso()
    overall_status = read_overall_status(artifacts["quality_report"], final_warnings)
    add_missing_artifact_warnings(artifacts, final_warnings)
    return {
        "schema_version": SCHEMA_VERSION,
        "trigger_mode": TRIGGER_MODE,
        "report_date": report_date,
        "report_id": report_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds(started_at, finished_at),
        "exit_code": exit_code,
        "exit_code_meaning": exit_code_meaning(exit_code),
        "run_auto_daily_args": run_args,
        "artifact_paths": {key: display_path(path) for key, path in artifacts.items()},
        "overall_status": overall_status,
        "business_write_summary_path": display_path(artifacts["business_write_summary"]),
        "llm_input_package_path": display_path(artifacts["llm_input_package"]),
        "warnings": final_warnings,
        "errors": final_errors,
    }


def read_overall_status(path: Path, warnings: list[str]) -> str | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(f"quality_report unreadable: {display_path(path)} ({exc})")
        return None
    if not isinstance(payload, dict):
        warnings.append(f"quality_report is not an object: {display_path(path)}")
        return None
    status = payload.get("overall_status")
    return str(status) if status is not None else None


def add_missing_artifact_warnings(artifacts: dict[str, Path], warnings: list[str]) -> None:
    for key in SUMMARY_ARTIFACT_KEYS:
        path = artifacts[key]
        if not path.exists():
            warnings.append(f"artifact missing: {key}={display_path(path)}")


def exit_code_meaning(exit_code: int) -> str:
    meanings = {
        0: "success_or_warning_quality",
        1: "program_or_environment_error",
        2: "controlled_data_or_quality_failure",
        3: "scheduler_trigger_guard_failure",
    }
    return meanings.get(exit_code, "unknown")


def duration_seconds(started_at: str, finished_at: str) -> float:
    try:
        started = datetime.fromisoformat(started_at)
        finished = datetime.fromisoformat(finished_at)
    except ValueError:
        return 0.0
    return round((finished - started).total_seconds(), 3)


def write_summary(summary: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def print_summary(summary: dict[str, Any], path: Path) -> None:
    print(f"scheduled_summary_path: {display_path(path)}")
    print(f"report_date: {summary['report_date']}")
    print(f"report_id: {summary['report_id']}")
    print(f"exit_code: {summary['exit_code']}")
    print(f"exit_code_meaning: {summary['exit_code_meaning']}")
    print(f"overall_status: {summary.get('overall_status') or ''}")
    print(f"warnings: {len(summary['warnings'])}")
    print(f"errors: {len(summary['errors'])}")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def display_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    raise SystemExit(main())
