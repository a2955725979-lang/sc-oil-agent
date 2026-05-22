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


def test_schema_is_rerunnable_without_reset() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_rerunnable.sqlite"

        create_database(db_path)
        create_database(db_path)
        result = check_database(db_path)

        assert_true(result["ok"] is True, "schema should be rerunnable")


def run() -> None:
    tests = [
        test_create_and_check_database,
        test_reset_recreates_schema,
        test_schema_is_rerunnable_without_reset,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
