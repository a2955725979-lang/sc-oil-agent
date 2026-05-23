"""Smoke tests for src/database/write_research_report.py.

Run from the project root:
    python tests/test_write_research_report.py
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
from src.database.write_research_report import (  # noqa: E402
    FAIL_CONCLUSION,
    ResearchReportWriteError,
    write_research_report,
)


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
        "overall_status": status,
        "field_results": [],
        "warnings": [],
        "errors": [],
    }


def evidence_report() -> dict:
    return {
        "report_date": "2026-05-22",
        "evidence_scope": "field_level_only",
        "evidence_list": [
            {"evidence_id": "EVID-20260522-001"},
            {"evidence_id": "EVID-20260522-002"},
        ],
    }


def fetch_reports(db_path: Path) -> list[sqlite3.Row]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT *
            FROM research_reports
            ORDER BY report_id;
            """
        ).fetchall()


def test_auto_report_id_starts_at_001_and_maps_fields() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "test.sqlite"
        markdown_path = root / "SC_daily.md"
        quality_report_path = root / "quality_report.json"
        evidence_path = root / "evidence_list.json"
        config_path = root / "config.yaml"

        create_database(db_path)
        markdown_path.write_text("# SC 中国原油期货日报\n\n示例正文", encoding="utf-8")
        write_json(quality_report_path, quality_report(status="warning"))
        write_json(evidence_path, evidence_report())
        write_config(config_path)

        report_id = write_research_report(
            markdown_path=markdown_path,
            quality_report_path=quality_report_path,
            evidence_list_path=evidence_path,
            db_path=db_path,
            config_path=config_path,
        )
        rows = fetch_reports(db_path)

    assert_equal(report_id, "RPT-20260522-SC-DAILY-001", "first auto report id")
    assert_equal(len(rows), 1, "one report should be inserted")
    row = rows[0]
    assert_equal(row["report_id"], "RPT-20260522-SC-DAILY-001", "stored report id")
    assert_equal(row["data_snapshot_id"], None, "missing snapshot id should be NULL")
    assert_equal(row["date"], "2026-05-22", "date should map report_date")
    assert_equal(row["topic"], "SC 中国原油期货日报", "topic")
    assert_equal(row["confidence"], "低", "warning confidence")
    assert_equal(row["report_status"], "warning", "report status")
    assert_equal(row["prompt_version"], "test_prompt_v1", "prompt version from config")
    assert_equal(row["calculation_version"], "test_calc_v1", "calculation version from config")
    assert_equal(json.loads(row["evidence_ids"]), ["EVID-20260522-001", "EVID-20260522-002"], "evidence ids")
    assert_contains(row["report_markdown"], "示例正文", "markdown body should be stored")


def test_auto_report_id_increments_without_replacing() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "test.sqlite"
        markdown_path = root / "SC_daily.md"
        quality_report_path = root / "quality_report.json"
        config_path = root / "config.yaml"

        create_database(db_path)
        markdown_path.write_text("first", encoding="utf-8")
        write_json(quality_report_path, quality_report())
        write_config(config_path)

        first_id = write_research_report(markdown_path, quality_report_path, db_path=db_path, config_path=config_path)
        second_id = write_research_report(markdown_path, quality_report_path, db_path=db_path, config_path=config_path)
        rows = fetch_reports(db_path)

    assert_equal(first_id, "RPT-20260522-SC-DAILY-001", "first auto id")
    assert_equal(second_id, "RPT-20260522-SC-DAILY-002", "second auto id")
    assert_equal(len(rows), 2, "auto insert should preserve history")


def test_existing_data_snapshot_id_is_stored() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "test.sqlite"
        markdown_path = root / "SC_daily.md"
        quality_report_path = root / "quality_report.json"
        config_path = root / "config.yaml"

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
                VALUES ('SNAP-20260522-001', '2026-05-22', '2026-05-22', 'warning');
                """
            )
            conn.commit()
        markdown_path.write_text("report", encoding="utf-8")
        write_json(quality_report_path, quality_report())
        write_config(config_path)

        write_research_report(
            markdown_path,
            quality_report_path,
            db_path=db_path,
            config_path=config_path,
            data_snapshot_id="SNAP-20260522-001",
        )
        rows = fetch_reports(db_path)

    assert_equal(rows[0]["data_snapshot_id"], "SNAP-20260522-001", "existing snapshot id should be stored")


def test_explicit_report_id_without_replace_errors_on_duplicate() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "test.sqlite"
        markdown_path = root / "SC_daily.md"
        quality_report_path = root / "quality_report.json"
        config_path = root / "config.yaml"

        create_database(db_path)
        markdown_path.write_text("first", encoding="utf-8")
        write_json(quality_report_path, quality_report())
        write_config(config_path)

        first_id = write_research_report(
            markdown_path,
            quality_report_path,
            db_path=db_path,
            config_path=config_path,
            report_id="RPT-CUSTOM-001",
        )
        try:
            write_research_report(
                markdown_path,
                quality_report_path,
                db_path=db_path,
                config_path=config_path,
                report_id="RPT-CUSTOM-001",
            )
        except ResearchReportWriteError as exc:
            message = str(exc)
        else:
            raise AssertionError("duplicate explicit report_id should raise without replace")

    assert_equal(first_id, "RPT-CUSTOM-001", "first explicit id")
    assert_contains(message, "already exists", "duplicate message")
    assert_contains(message, "--replace", "replace hint")


def test_explicit_report_id_with_replace_overwrites() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "test.sqlite"
        markdown_path = root / "SC_daily.md"
        quality_report_path = root / "quality_report.json"
        config_path = root / "config.yaml"

        create_database(db_path)
        write_json(quality_report_path, quality_report(status="warning"))
        write_config(config_path)

        markdown_path.write_text("first", encoding="utf-8")
        write_research_report(
            markdown_path,
            quality_report_path,
            db_path=db_path,
            config_path=config_path,
            report_id="RPT-CUSTOM-001",
        )
        markdown_path.write_text("second", encoding="utf-8")
        replaced_id = write_research_report(
            markdown_path,
            quality_report_path,
            db_path=db_path,
            config_path=config_path,
            report_id="RPT-CUSTOM-001",
            replace=True,
        )
        rows = fetch_reports(db_path)

    assert_equal(replaced_id, "RPT-CUSTOM-001", "replace id")
    assert_equal(len(rows), 1, "replace should not add a second row")
    assert_equal(rows[0]["report_markdown"], "second", "markdown should be replaced")


def test_replace_requires_explicit_report_id() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "test.sqlite"
        markdown_path = root / "SC_daily.md"
        quality_report_path = root / "quality_report.json"
        config_path = root / "config.yaml"

        create_database(db_path)
        markdown_path.write_text("report", encoding="utf-8")
        write_json(quality_report_path, quality_report())
        write_config(config_path)

        try:
            write_research_report(
                markdown_path,
                quality_report_path,
                db_path=db_path,
                config_path=config_path,
                replace=True,
            )
        except ResearchReportWriteError as exc:
            message = str(exc)
        else:
            raise AssertionError("replace without report_id should raise")

    assert_contains(message, "--replace requires an explicit --report-id", "replace safety message")


def test_fail_report_conclusion_is_fixed() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "test.sqlite"
        markdown_path = root / "SC_daily_fail.md"
        quality_report_path = root / "quality_report_fail.json"
        config_path = root / "config.yaml"

        create_database(db_path)
        markdown_path.write_text("fail report", encoding="utf-8")
        write_json(quality_report_path, quality_report(status="fail"))
        write_config(config_path)

        write_research_report(markdown_path, quality_report_path, db_path=db_path, config_path=config_path)
        rows = fetch_reports(db_path)

    assert_equal(rows[0]["conclusion"], FAIL_CONCLUSION, "fail conclusion should be fixed")
    assert_equal(rows[0]["report_status"], "fail", "fail status should be stored")
    assert_equal(rows[0]["confidence"], "低", "fail confidence should be low")


def test_missing_database_error_is_clear() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "missing.sqlite"
        markdown_path = root / "SC_daily.md"
        quality_report_path = root / "quality_report.json"
        config_path = root / "config.yaml"

        markdown_path.write_text("report", encoding="utf-8")
        write_json(quality_report_path, quality_report())
        write_config(config_path)

        try:
            write_research_report(markdown_path, quality_report_path, db_path=db_path, config_path=config_path)
        except ResearchReportWriteError as exc:
            message = str(exc)
        else:
            raise AssertionError("missing database should raise ResearchReportWriteError")

    assert_contains(message, "Database file not found", "missing database message")
    assert_contains(message, "python src/database/init_db.py", "init hint")


def run() -> None:
    tests = [
        test_auto_report_id_starts_at_001_and_maps_fields,
        test_auto_report_id_increments_without_replacing,
        test_existing_data_snapshot_id_is_stored,
        test_explicit_report_id_without_replace_errors_on_duplicate,
        test_explicit_report_id_with_replace_overwrites,
        test_replace_requires_explicit_report_id,
        test_fail_report_conclusion_is_fixed,
        test_missing_database_error_is_clear,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
