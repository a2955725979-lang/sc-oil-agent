"""Smoke tests for src/database/write_snapshot.py.

Run from the project root:
    python tests/test_write_snapshot.py
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
from src.database.write_snapshot import SnapshotWriteError, write_snapshot  # noqa: E402


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(text: str, expected_fragment: str, message: str) -> None:
    if expected_fragment not in text:
        raise AssertionError(f"{message}: {expected_fragment!r} not found in {text!r}")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_config(path: Path) -> None:
    path.write_text(
        """
report:
  prompt_version: test_prompt_v1
  calculation_version: test_calc_v1
""",
        encoding="utf-8",
    )


def quality_report(status: str = "warning", report_date: str = "2026-05-22") -> dict:
    return {
        "report_date": report_date,
        "input_path": "data/manual/daily_input_example.json",
        "data_dictionary_path": "config/data_dictionary.yaml",
        "overall_status": status,
        "field_results": [
            {"field": "SC_close", "source_status": "pass", "warnings": [], "errors": []},
            {
                "field": "OPEC_monthly_summary",
                "source_status": "warning",
                "warnings": ["source_conflict_check requires multi-source data; v1 placeholder"],
                "errors": [],
            },
        ],
        "warnings": ["OPEC_monthly_summary: source_conflict_check requires multi-source data"],
        "errors": [],
    }


def fetch_snapshots(db_path: Path) -> list[sqlite3.Row]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT *
            FROM data_snapshot
            ORDER BY data_snapshot_id;
            """
        ).fetchall()


def test_auto_snapshot_id_starts_at_001_and_maps_fields() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "test.sqlite"
        report_path = root / "quality_report.json"
        config_path = root / "config.yaml"

        create_database(db_path)
        write_json(report_path, quality_report())
        write_config(config_path)

        snapshot_id = write_snapshot(report_path, db_path=db_path, config_path=config_path)
        rows = fetch_snapshots(db_path)

    assert_equal(snapshot_id, "SNAP-20260522-001", "first auto snapshot id")
    assert_equal(len(rows), 1, "one snapshot should be inserted")
    row = rows[0]
    assert_equal(row["data_snapshot_id"], "SNAP-20260522-001", "stored snapshot id")
    assert_equal(row["snapshot_date"], "2026-05-22", "snapshot_date should map report_date")
    assert_equal(row["report_date"], "2026-05-22", "report_date should map report_date")
    assert_equal(row["raw_data_version"], "data/manual/daily_input_example.json", "raw data path")
    assert_equal(row["processed_data_version"], str(report_path.resolve()), "quality report path")
    assert_equal(row["prompt_version"], "test_prompt_v1", "prompt version from config")
    assert_equal(row["calculation_version"], "test_calc_v1", "calculation version from config")
    assert_equal(row["source_status"], "warning", "overall_status maps to source_status")
    quality_warnings = json.loads(row["quality_warnings"])
    assert_equal(quality_warnings["field_status_counts"]["pass"], 1, "pass count")
    assert_equal(quality_warnings["field_status_counts"]["warning"], 1, "warning count")


def test_auto_snapshot_id_increments_without_replacing() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "test.sqlite"
        report_path = root / "quality_report.json"
        config_path = root / "config.yaml"

        create_database(db_path)
        write_json(report_path, quality_report())
        write_config(config_path)

        first_id = write_snapshot(report_path, db_path=db_path, config_path=config_path)
        second_id = write_snapshot(report_path, db_path=db_path, config_path=config_path)
        rows = fetch_snapshots(db_path)

    assert_equal(first_id, "SNAP-20260522-001", "first auto id")
    assert_equal(second_id, "SNAP-20260522-002", "second auto id")
    assert_equal(len(rows), 2, "auto insert should not replace previous snapshot")


def test_explicit_snapshot_id_replaces_existing_row() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "test.sqlite"
        report_path = root / "quality_report.json"
        config_path = root / "config.yaml"

        create_database(db_path)
        write_config(config_path)

        write_json(report_path, quality_report(status="warning"))
        first_id = write_snapshot(
            report_path,
            db_path=db_path,
            config_path=config_path,
            snapshot_id="SNAP-CUSTOM-001",
        )

        write_json(report_path, quality_report(status="pass"))
        second_id = write_snapshot(
            report_path,
            db_path=db_path,
            config_path=config_path,
            snapshot_id="SNAP-CUSTOM-001",
        )
        rows = fetch_snapshots(db_path)

    assert_equal(first_id, "SNAP-CUSTOM-001", "first explicit id")
    assert_equal(second_id, "SNAP-CUSTOM-001", "second explicit id")
    assert_equal(len(rows), 1, "explicit id should replace")
    assert_equal(rows[0]["source_status"], "pass", "replacement should update source_status")


def test_missing_database_error_is_clear() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "missing.sqlite"
        report_path = root / "quality_report.json"
        config_path = root / "config.yaml"

        write_json(report_path, quality_report())
        write_config(config_path)

        try:
            write_snapshot(report_path, db_path=db_path, config_path=config_path)
        except SnapshotWriteError as exc:
            message = str(exc)
        else:
            raise AssertionError("missing database should raise SnapshotWriteError")

    assert_contains(message, "Database file not found", "missing database message")
    assert_contains(message, "python src/database/init_db.py", "init hint")


def run() -> None:
    tests = [
        test_auto_snapshot_id_starts_at_001_and_maps_fields,
        test_auto_snapshot_id_increments_without_replacing,
        test_explicit_snapshot_id_replaces_existing_row,
        test_missing_database_error_is_clear,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
