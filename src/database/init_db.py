"""Create, reset, and inspect the SC oil research SQLite database."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "sc_oil_research.sqlite"
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"

REQUIRED_TABLES = {
    "data_snapshot",
    "market_prices",
    "fx_rates",
    "spread_table",
    "inventory_data",
    "china_fundamental_data",
    "sentiment_data",
    "oil_events",
    "research_reports",
    "evidence_database",
}


class DatabaseCheckError(RuntimeError):
    """Raised when the SQLite database fails a structural check."""


def create_database(
    db_path: Path = DEFAULT_DB_PATH,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    reset: bool = False,
) -> Path:
    """Safely create or explicitly reset a SQLite database.

    Without reset, an existing database is checked but never rebuilt. This is
    important because schema.sql contains DROP TABLE statements for reset use.
    """

    db_path = db_path.expanduser().resolve()
    schema_path = schema_path.expanduser().resolve()

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    if db_path.exists() and not reset:
        check_database(db_path)
        return db_path

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    schema_sql = schema_path.read_text(encoding="utf-8")
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(schema_sql)
        conn.commit()

    return db_path


def list_tables(db_path: Path) -> set[str]:
    """Return user-created table names in the database."""

    db_path = db_path.expanduser().resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name;
            """
        ).fetchall()

    return {row[0] for row in rows}


def check_database(db_path: Path = DEFAULT_DB_PATH) -> dict[str, object]:
    """Validate that the database exists and contains required tables."""

    db_path = db_path.expanduser().resolve()
    tables = list_tables(db_path)
    missing = sorted(REQUIRED_TABLES - tables)

    with sqlite3.connect(db_path) as conn:
        foreign_keys_enabled = conn.execute("PRAGMA foreign_keys;").fetchone()[0] == 1
        if not foreign_keys_enabled:
            conn.execute("PRAGMA foreign_keys = ON;")
            foreign_keys_enabled = conn.execute("PRAGMA foreign_keys;").fetchone()[0] == 1

    result = {
        "db_path": str(db_path),
        "tables": sorted(tables),
        "missing_tables": missing,
        "foreign_keys_enabled": foreign_keys_enabled,
        "ok": not missing and foreign_keys_enabled,
    }

    if not result["ok"]:
        details = []
        if missing:
            details.append(f"missing tables: {', '.join(missing)}")
        if not foreign_keys_enabled:
            details.append("foreign keys are disabled")
        raise DatabaseCheckError("; ".join(details))

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely create, reset, or check the SC oil research SQLite database."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path. Default: {DEFAULT_DB_PATH}",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA_PATH,
        help=f"Schema SQL path. Default: {DEFAULT_SCHEMA_PATH}",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Destructive rebuild: delete the existing database file before recreating it.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check an existing database; do not create, reset, or rebuild it.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.check:
            result = check_database(args.db)
            print(f"OK: database is ready at {result['db_path']}")
            print(f"Tables: {', '.join(result['tables'])}")
            return 0

        db_path = create_database(args.db, args.schema, reset=args.reset)
        result = check_database(db_path)
        action = "Reset" if args.reset else "Ready"
        print(f"{action}: {result['db_path']}")
        print(f"Tables: {', '.join(result['tables'])}")
        return 0
    except (DatabaseCheckError, FileNotFoundError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
