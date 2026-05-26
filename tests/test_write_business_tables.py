"""Tests for src/database/write_business_tables.py."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.calculators.spreads import calculate_spreads_file  # noqa: E402
from src.database.init_db import create_database  # noqa: E402
from src.database.write_business_tables import BusinessTableWriteError, write_business_tables  # noqa: E402
from src.database.write_research_report import write_research_report  # noqa: E402
from src.database.write_snapshot import write_snapshot  # noqa: E402
from src.evidence.generate_evidence_list import generate_evidence_list  # noqa: E402
from src.validators.run_quality_validation import run_validation  # noqa: E402


EXAMPLE_INPUT = PROJECT_ROOT / "data" / "manual" / "daily_input_example.json"
PROJECT_DICTIONARY = PROJECT_ROOT / "config" / "data_dictionary.yaml"
SUMMARY_KEYS = [
    "market_prices_written",
    "fx_rates_written",
    "spreads_written",
    "evidence_written",
    "core_tables_written",
    "evidence_database_written",
    "research_report_id",
    "data_snapshot_id",
    "warnings",
    "errors",
]


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(text: str, expected_fragment: str, message: str) -> None:
    if expected_fragment not in text:
        raise AssertionError(f"{message}: {expected_fragment!r} not found in {text!r}")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_config(path: Path) -> None:
    write_text(
        path,
        """
report:
  prompt_version: test_prompt_v1
  calculation_version: test_calc_v1
""",
    )


def prepare_success_files(root: Path, report_id: str | None = "RPT-BUSINESS-001") -> dict[str, Path | str | None]:
    db_path = root / "sc_oil.sqlite"
    config_path = root / "config.yaml"
    calculated_input_path = root / "processed" / "calculated_input.json"
    quality_report_path = root / "processed" / "quality_report.json"
    evidence_list_path = root / "processed" / "evidence_list.json"
    markdown_path = root / "reports" / "SC_daily.md"

    create_database(db_path)
    write_config(config_path)
    calculate_spreads_file(EXAMPLE_INPUT, calculated_input_path)
    run_validation(
        input_path=calculated_input_path,
        data_dictionary_path=PROJECT_DICTIONARY,
        output_path=quality_report_path,
    )
    snapshot_id = write_snapshot(
        quality_report_path,
        db_path=db_path,
        config_path=config_path,
        snapshot_id="SNAP-BUSINESS-001",
    )
    generate_evidence_list(
        daily_input_path=calculated_input_path,
        quality_report_path=quality_report_path,
        output_path=evidence_list_path,
        data_snapshot_id=snapshot_id,
    )
    final_report_id = None
    if report_id:
        write_text(markdown_path, "# Test report\n")
        final_report_id = write_research_report(
            markdown_path=markdown_path,
            quality_report_path=quality_report_path,
            db_path=db_path,
            config_path=config_path,
            evidence_list_path=evidence_list_path,
            data_snapshot_id=snapshot_id,
            report_id=report_id,
        )
    return {
        "db_path": db_path,
        "config_path": config_path,
        "calculated_input_path": calculated_input_path,
        "quality_report_path": quality_report_path,
        "evidence_list_path": evidence_list_path,
        "data_snapshot_id": snapshot_id,
        "research_report_id": final_report_id,
    }


def table_count(db_path: Path, table_name: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table_name};").fetchone()[0]


def evidence_report_ids(db_path: Path) -> list[str | None]:
    with sqlite3.connect(db_path) as conn:
        return [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT report_id FROM evidence_database ORDER BY report_id;"
            ).fetchall()
        ]


def test_writer_writes_core_tables_and_evidence_after_report_exists() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = prepare_success_files(root)
        summary_path = root / "business_summary.json"

        summary = write_business_tables(
            calculated_input_path=paths["calculated_input_path"],
            quality_report_path=paths["quality_report_path"],
            evidence_list_path=paths["evidence_list_path"],
            db_path=paths["db_path"],
            data_snapshot_id=str(paths["data_snapshot_id"]),
            research_report_id=str(paths["research_report_id"]),
            summary_output_path=summary_path,
        )
        saved_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        db_path = Path(paths["db_path"])
        evidence_count = table_count(db_path, "evidence_database")
        market_count = table_count(db_path, "market_prices")
        fx_count = table_count(db_path, "fx_rates")
        spread_count = table_count(db_path, "spread_table")
        report_ids = evidence_report_ids(db_path)

    assert_equal(list(summary.keys()), SUMMARY_KEYS, "summary shape")
    assert_equal(saved_summary, summary, "summary output should match return value")
    assert_equal(summary["market_prices_written"], 3, "market price rows")
    assert_equal(summary["fx_rates_written"], 1, "fx rows")
    assert_equal(summary["spreads_written"], 1, "spread rows")
    assert_equal(summary["evidence_written"], evidence_count, "evidence count")
    assert_equal(summary["core_tables_written"], True, "core write flag")
    assert_equal(summary["evidence_database_written"], True, "evidence write flag")
    assert_equal(market_count, 3, "market_prices count")
    assert_equal(fx_count, 1, "fx_rates count")
    assert_equal(spread_count, 1, "spread_table count")
    assert_equal(report_ids, ["RPT-BUSINESS-001"], "evidence report FK")


def test_writer_fails_evidence_readiness_when_report_id_missing() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = prepare_success_files(root, report_id=None)
        try:
            write_business_tables(
                calculated_input_path=paths["calculated_input_path"],
                quality_report_path=paths["quality_report_path"],
                evidence_list_path=paths["evidence_list_path"],
                db_path=paths["db_path"],
                data_snapshot_id=str(paths["data_snapshot_id"]),
                research_report_id="RPT-MISSING",
            )
        except BusinessTableWriteError as exc:
            message = str(exc)
        else:
            raise AssertionError("missing research_report_id should raise")

    assert_contains(message, "foreign-key readiness failed", "readiness error")
    assert_contains(message, "RPT-MISSING", "missing report id should be named")


def test_writer_allows_null_report_id_for_evidence_rows() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = prepare_success_files(root, report_id=None)

        summary = write_business_tables(
            calculated_input_path=paths["calculated_input_path"],
            quality_report_path=paths["quality_report_path"],
            evidence_list_path=paths["evidence_list_path"],
            db_path=paths["db_path"],
            data_snapshot_id=str(paths["data_snapshot_id"]),
            research_report_id=None,
        )
        db_path = Path(paths["db_path"])
        report_ids = evidence_report_ids(db_path)

    assert_equal(summary["evidence_written"] > 0, True, "evidence rows should be written")
    assert_equal(report_ids, [None], "evidence report id may be NULL")


def test_fail_quality_blocks_core_tables_by_default() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = prepare_success_files(root, report_id=None)
        fail_quality_path = root / "processed" / "quality_fail.json"
        write_json(
            fail_quality_path,
            {
                "report_date": "2026-05-22",
                "overall_status": "fail",
                "field_results": [{"field": "SC_close", "source_status": "pass", "warnings": [], "errors": []}],
                "warnings": [],
                "errors": ["forced failure"],
            },
        )

        summary = write_business_tables(
            calculated_input_path=paths["calculated_input_path"],
            quality_report_path=fail_quality_path,
            evidence_list_path=None,
            db_path=paths["db_path"],
        )
        db_path = Path(paths["db_path"])
        market_count = table_count(db_path, "market_prices")
        fx_count = table_count(db_path, "fx_rates")
        spread_count = table_count(db_path, "spread_table")

    assert_equal(summary["core_tables_written"], False, "fail quality should block core tables")
    assert_equal(summary["market_prices_written"], 0, "blocked market rows")
    assert_equal(summary["fx_rates_written"], 0, "blocked fx rows")
    assert_equal(summary["spreads_written"], 0, "blocked spread rows")
    assert_equal(market_count, 0, "market_prices remains empty")
    assert_equal(fx_count, 0, "fx_rates remains empty")
    assert_equal(spread_count, 0, "spread_table remains empty")
    assert_contains("; ".join(summary["warnings"]), "core business table write skipped", "fail warning")


def test_allow_fail_write_is_required_for_fail_core_rows() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = prepare_success_files(root, report_id=None)
        fail_quality_path = root / "processed" / "quality_fail.json"
        write_json(
            fail_quality_path,
            {
                "report_date": "2026-05-22",
                "overall_status": "fail",
                "field_results": [{"field": "SC_close", "source_status": "pass", "warnings": [], "errors": []}],
                "warnings": [],
                "errors": ["forced failure"],
            },
        )

        summary = write_business_tables(
            calculated_input_path=paths["calculated_input_path"],
            quality_report_path=fail_quality_path,
            evidence_list_path=None,
            db_path=paths["db_path"],
            write_evidence_database=False,
            allow_fail_write=True,
        )

    assert_equal(summary["core_tables_written"], True, "allow_fail_write should enable core writes")
    assert_equal(summary["market_prices_written"], 3, "fail core market rows")
    assert_equal(summary["fx_rates_written"], 1, "fail core fx rows")
    assert_equal(summary["spreads_written"], 1, "fail core spread rows")


def run() -> None:
    tests = [
        test_writer_writes_core_tables_and_evidence_after_report_exists,
        test_writer_fails_evidence_readiness_when_report_id_missing,
        test_writer_allows_null_report_id_for_evidence_rows,
        test_fail_quality_blocks_core_tables_by_default,
        test_allow_fail_write_is_required_for_fail_core_rows,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
