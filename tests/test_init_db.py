"""Smoke tests for src/database/init_db.py.

Run from the project root:
    python tests/test_init_db.py
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.database.init_db import (  # noqa: E402
    DatabaseCheckError,
    REQUIRED_TABLES,
    check_database,
    create_database,
    list_tables,
)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_create_and_check_database() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_sc_oil.sqlite"

        create_database(db_path)
        result = check_database(db_path)

        assert_true(result["ok"] is True, "database check should pass")
        assert_true(
            REQUIRED_TABLES.issubset(set(result["tables"])),
            "all required tables should exist",
        )
        assert_true(db_path.exists(), "database file should exist")


def test_reset_recreates_schema() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_reset.sqlite"

        create_database(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO data_snapshot (
                    data_snapshot_id,
                    snapshot_date,
                    report_date,
                    source_status
                )
                VALUES ('SNAP-TEST-001', '2026-05-22', '2026-05-22', 'pass');
                """
            )
            conn.commit()

        create_database(db_path, reset=True)
        tables = list_tables(db_path)
        with sqlite3.connect(db_path) as conn:
            row_count = conn.execute("SELECT COUNT(*) FROM data_snapshot;").fetchone()[0]

        assert_true(REQUIRED_TABLES.issubset(tables), "reset should recreate all tables")
        assert_true(row_count == 0, "reset should remove previous rows")


def test_safe_init_preserves_existing_rows_without_reset() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_safe_init.sqlite"

        create_database(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO data_snapshot (
                    data_snapshot_id,
                    snapshot_date,
                    report_date,
                    source_status
                )
                VALUES ('SNAP-SAFE-001', '2026-05-22', '2026-05-22', 'warning');
                """
            )
            conn.commit()

        create_database(db_path)
        result = check_database(db_path)
        with sqlite3.connect(db_path) as conn:
            row_count = conn.execute("SELECT COUNT(*) FROM data_snapshot;").fetchone()[0]

        assert_true(result["ok"] is True, "safe init should still pass check")
        assert_true(row_count == 1, "safe init should preserve existing rows")


def test_safe_init_does_not_rebuild_incomplete_database() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_incomplete.sqlite"

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE data_snapshot (
                    data_snapshot_id TEXT PRIMARY KEY,
                    snapshot_date TEXT NOT NULL,
                    report_date TEXT NOT NULL,
                    source_status TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                INSERT INTO data_snapshot (
                    data_snapshot_id,
                    snapshot_date,
                    report_date,
                    source_status
                )
                VALUES ('SNAP-INCOMPLETE-001', '2026-05-22', '2026-05-22', 'warning');
                """
            )
            conn.commit()

        try:
            create_database(db_path)
        except DatabaseCheckError as exc:
            message = str(exc)
        else:
            raise AssertionError("safe init should fail rather than rebuild incomplete database")

        with sqlite3.connect(db_path) as conn:
            row_count = conn.execute("SELECT COUNT(*) FROM data_snapshot;").fetchone()[0]

        assert_true("missing tables" in message, "safe init should report missing tables")
        assert_true(row_count == 1, "safe init should not drop existing incomplete data")


def run() -> None:
    tests = [
        test_create_and_check_database,
        test_reset_recreates_schema,
        test_safe_init_preserves_existing_rows_without_reset,
        test_safe_init_does_not_rebuild_incomplete_database,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
