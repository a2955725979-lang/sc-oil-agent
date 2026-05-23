"""Smoke tests for src/pipeline/run_daily_pipeline.py.

Run from the project root:
    python tests/test_run_daily_pipeline.py
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
from src.pipeline.run_daily_pipeline import main  # noqa: E402


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def dictionary_yaml(required: bool = True, fail_action: str = "report_as_missing") -> str:
    return f"""
SC_close:
  required: {str(required).lower()}
  unit: CNY/barrel
  frequency: daily
  quality_checks: [missing_check, unit_check]
  fail_action: {fail_action}
"""


def valid_daily_input(report_date: str = "2026-05-22") -> dict:
    return {
        "report_date": report_date,
        "fields": {
            "SC_close": {
                "value": 620.5,
                "metadata": {"unit": "CNY/barrel", "date": report_date},
            },
            "Oman_price_experimental": {
                "value": 81.7,
                "metadata": {"unit": "USD/barrel", "date": report_date},
            },
        },
    }


def failing_daily_input(report_date: str = "2026-05-22") -> dict:
    return {"report_date": report_date, "fields": {}}


def write_config(path: Path) -> None:
    write_text(
        path,
        """
report:
  prompt_version: test_prompt_v1
  calculation_version: test_calc_v1
""",
    )


def snapshot_count(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM data_snapshot;").fetchone()[0]


def snapshot_ids(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        return [
            row[0]
            for row in conn.execute(
                "SELECT data_snapshot_id FROM data_snapshot ORDER BY data_snapshot_id;"
            ).fetchall()
        ]


def pipeline_args(
    input_path: Path,
    dictionary_path: Path,
    db_path: Path,
    config_path: Path,
    output_path: Path,
    extra_args: list[str] | None = None,
) -> list[str]:
    args = [
        "--input",
        str(input_path),
        "--dictionary",
        str(dictionary_path),
        "--db",
        str(db_path),
        "--config",
        str(config_path),
        "--quality-report-output",
        str(output_path),
    ]
    if extra_args:
        args.extend(extra_args)
    return args


def test_warning_status_returns_zero_and_writes_snapshot() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "daily_input.json"
        dictionary_path = root / "dictionary.yaml"
        db_path = root / "sc_oil.sqlite"
        config_path = root / "config.yaml"
        output_path = root / "quality_report.json"

        write_json(input_path, valid_daily_input())
        write_text(dictionary_path, dictionary_yaml())
        write_config(config_path)

        exit_code = main(
            pipeline_args(
                input_path,
                dictionary_path,
                db_path,
                config_path,
                output_path,
                extra_args=["--init-db"],
            )
        )
        report = json.loads(output_path.read_text(encoding="utf-8"))
        ids = snapshot_ids(db_path)

    assert_equal(exit_code, 0, "warning quality should be a successful pipeline run")
    assert_equal(report["overall_status"], "warning", "extra field should make report warning")
    assert_equal(ids, ["SNAP-20260522-001"], "snapshot should be written")


def test_fail_status_returns_two_and_does_not_write_snapshot() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "daily_input.json"
        dictionary_path = root / "dictionary.yaml"
        db_path = root / "sc_oil.sqlite"
        config_path = root / "config.yaml"
        output_path = root / "quality_report.json"

        write_json(input_path, failing_daily_input())
        write_text(dictionary_path, dictionary_yaml())
        write_config(config_path)

        exit_code = main(
            pipeline_args(
                input_path,
                dictionary_path,
                db_path,
                config_path,
                output_path,
                extra_args=["--init-db"],
            )
        )
        report = json.loads(output_path.read_text(encoding="utf-8"))
        count = snapshot_count(db_path)

    assert_equal(exit_code, 2, "quality fail should return 2")
    assert_equal(report["overall_status"], "fail", "report should be generated with fail status")
    assert_equal(count, 0, "fail status should not write data_snapshot")


def test_init_db_checks_existing_database_without_clearing_snapshots() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "daily_input.json"
        dictionary_path = root / "dictionary.yaml"
        db_path = root / "sc_oil.sqlite"
        config_path = root / "config.yaml"
        first_output = root / "quality_report_1.json"
        second_output = root / "quality_report_2.json"

        create_database(db_path)
        write_json(input_path, valid_daily_input())
        write_text(dictionary_path, dictionary_yaml())
        write_config(config_path)

        first_exit = main(
            pipeline_args(
                input_path,
                dictionary_path,
                db_path,
                config_path,
                first_output,
            )
        )
        second_exit = main(
            pipeline_args(
                input_path,
                dictionary_path,
                db_path,
                config_path,
                second_output,
                extra_args=["--init-db"],
            )
        )
        ids = snapshot_ids(db_path)

    assert_equal(first_exit, 0, "first run should succeed")
    assert_equal(second_exit, 0, "--init-db should check existing db and continue")
    assert_equal(
        ids,
        ["SNAP-20260522-001", "SNAP-20260522-002"],
        "--init-db should not clear existing snapshots",
    )


def test_missing_database_without_init_returns_one() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "daily_input.json"
        dictionary_path = root / "dictionary.yaml"
        db_path = root / "missing.sqlite"
        config_path = root / "config.yaml"
        output_path = root / "quality_report.json"

        write_json(input_path, valid_daily_input())
        write_text(dictionary_path, dictionary_yaml())
        write_config(config_path)

        exit_code = main(
            pipeline_args(input_path, dictionary_path, db_path, config_path, output_path)
        )

    assert_equal(exit_code, 1, "missing db without --init-db should be program error")


def test_explicit_snapshot_id_is_forwarded() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "daily_input.json"
        dictionary_path = root / "dictionary.yaml"
        db_path = root / "sc_oil.sqlite"
        config_path = root / "config.yaml"
        output_path = root / "quality_report.json"

        write_json(input_path, valid_daily_input())
        write_text(dictionary_path, dictionary_yaml())
        write_config(config_path)

        exit_code = main(
            pipeline_args(
                input_path,
                dictionary_path,
                db_path,
                config_path,
                output_path,
                extra_args=["--init-db", "--snapshot-id", "SNAP-CUSTOM-PIPELINE"],
            )
        )
        ids = snapshot_ids(db_path)

    assert_equal(exit_code, 0, "explicit snapshot id run should succeed")
    assert_equal(ids, ["SNAP-CUSTOM-PIPELINE"], "snapshot id should be forwarded")


def run() -> None:
    tests = [
        test_warning_status_returns_zero_and_writes_snapshot,
        test_fail_status_returns_two_and_does_not_write_snapshot,
        test_init_db_checks_existing_database_without_clearing_snapshots,
        test_missing_database_without_init_returns_one,
        test_explicit_snapshot_id_is_forwarded,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
