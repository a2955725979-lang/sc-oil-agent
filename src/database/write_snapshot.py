"""Write quality validation reports into the data_snapshot table."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "sc_oil_research.sqlite"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
VALID_STATUSES = {"pass", "warning", "fail"}


class SnapshotWriteError(RuntimeError):
    """Raised when a quality report cannot be written as a data snapshot."""


def load_quality_report(path: str | Path) -> dict[str, Any]:
    report_path = Path(path)
    with report_path.open("r", encoding="utf-8") as file:
        report = json.load(file)
    if not isinstance(report, dict):
        raise SnapshotWriteError(f"Quality report must be a JSON object: {report_path}")
    return report


def load_project_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    if not isinstance(config, dict):
        raise SnapshotWriteError(f"Config must be a YAML object: {config_path}")
    return config


def write_snapshot(
    quality_report_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    snapshot_id: str | None = None,
) -> str:
    """Write a quality report to data_snapshot and return data_snapshot_id."""

    quality_report_path = Path(quality_report_path).expanduser().resolve()
    db_path = Path(db_path).expanduser().resolve()
    config_path = Path(config_path).expanduser().resolve()

    if not db_path.exists():
        raise SnapshotWriteError(
            f"Database file not found: {db_path}. "
            "Run `python src/database/init_db.py` first."
        )

    report = load_quality_report(quality_report_path)
    config = load_project_config(config_path)
    row = build_snapshot_row(
        quality_report=report,
        quality_report_path=quality_report_path,
        config=config,
        db_path=db_path,
        snapshot_id=snapshot_id,
    )

    if snapshot_id:
        _replace_snapshot(db_path, row)
    else:
        _insert_snapshot(db_path, row)

    return row["data_snapshot_id"]


def build_snapshot_row(
    quality_report: dict[str, Any],
    quality_report_path: str | Path,
    config: dict[str, Any] | None,
    db_path: str | Path,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    report_date = _required_text(quality_report, "report_date")
    status = _required_text(quality_report, "overall_status")
    if status not in VALID_STATUSES:
        raise SnapshotWriteError(f"Invalid overall_status in quality report: {status}")

    config = config or {}
    report_config = config.get("report", {})
    if not isinstance(report_config, dict):
        report_config = {}

    final_snapshot_id = snapshot_id or generate_snapshot_id(db_path, report_date)
    return {
        "data_snapshot_id": final_snapshot_id,
        "snapshot_date": report_date,
        "report_date": report_date,
        "raw_data_version": quality_report.get("input_path"),
        "processed_data_version": _display_path(quality_report_path),
        "prompt_version": report_config.get("prompt_version"),
        "calculation_version": report_config.get("calculation_version"),
        "code_version": get_git_commit_hash(),
        "source_status": status,
        "quality_warnings": json.dumps(_quality_warning_payload(quality_report), ensure_ascii=False),
    }


def generate_snapshot_id(db_path: str | Path, report_date: str) -> str:
    prefix = f"SNAP-{report_date.replace('-', '')}-"
    db_path = Path(db_path).expanduser().resolve()
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT data_snapshot_id
            FROM data_snapshot
            WHERE data_snapshot_id LIKE ?
            ORDER BY data_snapshot_id;
            """,
            (f"{prefix}%",),
        ).fetchall()

    max_seq = 0
    for (snapshot_id,) in rows:
        suffix = str(snapshot_id).replace(prefix, "", 1)
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))
    return f"{prefix}{max_seq + 1:03d}"


def get_git_commit_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"
    commit_hash = result.stdout.strip()
    return commit_hash or "unknown"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a quality report to SQLite data_snapshot.")
    parser.add_argument("--quality-report", required=True, help="Quality report JSON path.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Project config YAML path.")
    parser.add_argument("--snapshot-id", help="Explicit snapshot id. Enables INSERT OR REPLACE.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        data_snapshot_id = write_snapshot(
            quality_report_path=args.quality_report,
            db_path=args.db,
            config_path=args.config,
            snapshot_id=args.snapshot_id,
        )
    except (SnapshotWriteError, sqlite3.Error, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Wrote data_snapshot: {data_snapshot_id}")
    return 0


def _insert_snapshot(db_path: Path, row: dict[str, Any]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            """
            INSERT INTO data_snapshot (
                data_snapshot_id,
                snapshot_date,
                report_date,
                raw_data_version,
                processed_data_version,
                prompt_version,
                calculation_version,
                code_version,
                source_status,
                quality_warnings
            )
            VALUES (
                :data_snapshot_id,
                :snapshot_date,
                :report_date,
                :raw_data_version,
                :processed_data_version,
                :prompt_version,
                :calculation_version,
                :code_version,
                :source_status,
                :quality_warnings
            );
            """,
            row,
        )
        conn.commit()


def _replace_snapshot(db_path: Path, row: dict[str, Any]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            """
            INSERT OR REPLACE INTO data_snapshot (
                data_snapshot_id,
                snapshot_date,
                report_date,
                raw_data_version,
                processed_data_version,
                prompt_version,
                calculation_version,
                code_version,
                source_status,
                quality_warnings
            )
            VALUES (
                :data_snapshot_id,
                :snapshot_date,
                :report_date,
                :raw_data_version,
                :processed_data_version,
                :prompt_version,
                :calculation_version,
                :code_version,
                :source_status,
                :quality_warnings
            );
            """,
            row,
        )
        conn.commit()


def _quality_warning_payload(quality_report: dict[str, Any]) -> dict[str, Any]:
    field_results = quality_report.get("field_results", [])
    status_counts = {"pass": 0, "warning": 0, "fail": 0}
    if isinstance(field_results, list):
        for field_result in field_results:
            if not isinstance(field_result, dict):
                continue
            status = field_result.get("source_status")
            if status in status_counts:
                status_counts[status] += 1

    return {
        "warnings": quality_report.get("warnings", []),
        "errors": quality_report.get("errors", []),
        "field_status_counts": status_counts,
    }


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if value is None or str(value).strip() == "":
        raise SnapshotWriteError(f"Quality report missing required field: {key}")
    return str(value)


def _display_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    raise SystemExit(main())
