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


def fetch_rows(db_path: Path, query: str, params: tuple = ()) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def evidence_report_ids(db_path: Path) -> list[str | None]:
    with sqlite3.connect(db_path) as conn:
        return [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT report_id FROM evidence_database ORDER BY report_id;"
            ).fetchall()
        ]


def evidence_fact_rows(db_path: Path) -> list[dict]:
    return fetch_rows(
        db_path,
        """
        SELECT evidence_id, report_id, data_snapshot_id, extracted_fact
        FROM evidence_database
        ORDER BY evidence_id;
        """,
    )


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
        market_rows = fetch_rows(
            db_path,
            """
            SELECT symbol, contract, close, settlement, volume, open_interest, currency, source
            FROM market_prices
            ORDER BY contract;
            """,
        )

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
    assert_equal([row["symbol"] for row in market_rows], ["SC", "SC", "SC"], "market_prices should be SC only")
    assert_equal(
        [row["contract"] for row in market_rows],
        ["SC_MAIN_UNKNOWN", "SC_NEAR_UNKNOWN", "SC_NEXT_UNKNOWN"],
        "SC contract defaults",
    )
    assert_equal(market_rows[0]["close"], 620.5, "SC main close")
    assert_equal(market_rows[0]["settlement"], 619.8, "SC main settlement")
    assert_equal(market_rows[0]["volume"], 128000.0, "SC main volume")
    assert_equal(market_rows[0]["open_interest"], 54000.0, "SC main open interest")
    assert_equal(market_rows[0]["currency"], "CNY", "SC main currency")
    assert_equal(market_rows[0]["source"], "unknown", "default source")
    assert_equal(market_rows[1]["close"], 621.0, "SC near close")
    assert_equal(market_rows[2]["close"], 617.2, "SC next close")


def test_writer_repeated_runs_do_not_duplicate_rows() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = prepare_success_files(root)
        db_path = Path(paths["db_path"])

        first_summary = write_business_tables(
            calculated_input_path=paths["calculated_input_path"],
            quality_report_path=paths["quality_report_path"],
            evidence_list_path=paths["evidence_list_path"],
            db_path=db_path,
            data_snapshot_id=str(paths["data_snapshot_id"]),
            research_report_id=str(paths["research_report_id"]),
        )
        counts_after_first = {
            "market": table_count(db_path, "market_prices"),
            "fx": table_count(db_path, "fx_rates"),
            "spread": table_count(db_path, "spread_table"),
            "evidence": table_count(db_path, "evidence_database"),
        }
        second_summary = write_business_tables(
            calculated_input_path=paths["calculated_input_path"],
            quality_report_path=paths["quality_report_path"],
            evidence_list_path=paths["evidence_list_path"],
            db_path=db_path,
            data_snapshot_id=str(paths["data_snapshot_id"]),
            research_report_id=str(paths["research_report_id"]),
        )
        counts_after_second = {
            "market": table_count(db_path, "market_prices"),
            "fx": table_count(db_path, "fx_rates"),
            "spread": table_count(db_path, "spread_table"),
            "evidence": table_count(db_path, "evidence_database"),
        }

    assert_equal(first_summary["market_prices_written"], 3, "first market write count")
    assert_equal(second_summary["market_prices_written"], 3, "second market upsert count")
    assert_equal(counts_after_second, counts_after_first, "repeated writes should not duplicate rows")


def test_writer_warns_for_missing_optional_fields_without_crashing() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = prepare_success_files(root, report_id=None)
        calculated = json.loads(Path(paths["calculated_input_path"]).read_text(encoding="utf-8"))
        for field_name in ("SC_near_price", "SC_next_price", "USD_CNY", "Brent_close", "WTI_close"):
            calculated["fields"].pop(field_name, None)
        missing_calculated_path = root / "processed" / "calculated_missing_optional.json"
        write_json(missing_calculated_path, calculated)

        summary = write_business_tables(
            calculated_input_path=missing_calculated_path,
            quality_report_path=paths["quality_report_path"],
            evidence_list_path=None,
            db_path=paths["db_path"],
            write_evidence_database=False,
        )
        warnings = "; ".join(summary["warnings"])

    assert_equal(summary["market_prices_written"], 1, "only SC main row should be written")
    assert_equal(summary["fx_rates_written"], 0, "missing USD_CNY should skip fx")
    assert_equal(summary["spreads_written"], 1, "spread row should keep available values")
    assert_contains(warnings, "SC_near_price missing", "near warning")
    assert_contains(warnings, "SC_next_price missing", "next warning")
    assert_contains(warnings, "USD_CNY missing", "fx warning")
    assert_contains(warnings, "Brent_close missing", "Brent warning")
    assert_contains(warnings, "WTI_close missing", "WTI warning")


def test_spread_structure_type_updates_for_backwardation_contango_flat() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = prepare_success_files(root, report_id=None)
        base_calculated = json.loads(Path(paths["calculated_input_path"]).read_text(encoding="utf-8"))
        calculated_path = root / "processed" / "calculated_structure.json"
        observed: list[str | None] = []

        for value in (1.0, -1.0, 0.0):
            calculated = json.loads(json.dumps(base_calculated))
            calculated["fields"]["SC_calendar_spread"]["value"] = value
            write_json(calculated_path, calculated)
            write_business_tables(
                calculated_input_path=calculated_path,
                quality_report_path=paths["quality_report_path"],
                evidence_list_path=None,
                db_path=paths["db_path"],
                write_evidence_database=False,
            )
            rows = fetch_rows(
                Path(paths["db_path"]),
                "SELECT structure_type FROM spread_table ORDER BY id;",
            )
            observed.append(rows[-1]["structure_type"])

    assert_equal(observed, ["Backwardation", "Contango", "Flat"], "calendar spread structure labels")


def test_field_status_prefers_metadata_over_quality_result() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = prepare_success_files(root, report_id=None)
        calculated = json.loads(Path(paths["calculated_input_path"]).read_text(encoding="utf-8"))
        calculated["fields"]["SC_close"]["metadata"]["source_status"] = "fail"
        calculated_path = root / "processed" / "calculated_metadata_status.json"
        write_json(calculated_path, calculated)

        write_business_tables(
            calculated_input_path=calculated_path,
            quality_report_path=paths["quality_report_path"],
            evidence_list_path=None,
            db_path=paths["db_path"],
            write_evidence_database=False,
        )
        rows = fetch_rows(
            Path(paths["db_path"]),
            """
            SELECT source_status
            FROM market_prices
            WHERE contract = 'SC_MAIN_UNKNOWN';
            """,
        )

    assert_equal(rows[0]["source_status"], "fail", "metadata source_status should win")


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


def test_writer_fails_evidence_readiness_when_snapshot_id_missing() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = prepare_success_files(root)
        try:
            write_business_tables(
                calculated_input_path=paths["calculated_input_path"],
                quality_report_path=paths["quality_report_path"],
                evidence_list_path=paths["evidence_list_path"],
                db_path=paths["db_path"],
                data_snapshot_id="SNAP-MISSING",
                research_report_id=str(paths["research_report_id"]),
            )
        except BusinessTableWriteError as exc:
            message = str(exc)
        else:
            raise AssertionError("missing data_snapshot_id should raise")

    assert_contains(message, "foreign-key readiness failed", "readiness error")
    assert_contains(message, "SNAP-MISSING", "missing snapshot id should be named")


def test_writer_missing_database_has_clear_error() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = prepare_success_files(root, report_id=None)
        missing_db = root / "missing.sqlite"
        try:
            write_business_tables(
                calculated_input_path=paths["calculated_input_path"],
                quality_report_path=paths["quality_report_path"],
                evidence_list_path=None,
                db_path=missing_db,
            )
        except BusinessTableWriteError as exc:
            message = str(exc)
        else:
            raise AssertionError("missing database should raise")

    assert_equal(
        message,
        "Database not found. Run python src/database/init_db.py first.",
        "missing database message",
    )


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


def test_evidence_missing_fact_uses_field_level_fallback_and_allows_null_ids() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = prepare_success_files(root, report_id=None)
        evidence = json.loads(Path(paths["evidence_list_path"]).read_text(encoding="utf-8"))
        first_item = evidence["evidence_list"][0]
        first_item.pop("extracted_fact", None)
        first_item["field"] = "SC_close"
        first_item["raw_value"] = 620.5
        evidence_path = root / "processed" / "evidence_without_fact.json"
        write_json(evidence_path, evidence)

        summary = write_business_tables(
            calculated_input_path=paths["calculated_input_path"],
            quality_report_path=paths["quality_report_path"],
            evidence_list_path=evidence_path,
            db_path=paths["db_path"],
            data_snapshot_id=None,
            research_report_id=None,
            write_core_tables=False,
        )
        rows = evidence_fact_rows(Path(paths["db_path"]))

    assert_equal(summary["evidence_written"] > 0, True, "evidence rows should be written")
    assert_equal(rows[0]["report_id"], None, "report id may be NULL")
    assert_equal(rows[0]["data_snapshot_id"], None, "snapshot id may be NULL")
    assert_equal(rows[0]["extracted_fact"], "Field SC_close validated with value 620.5", "fallback extracted fact")


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
        test_writer_repeated_runs_do_not_duplicate_rows,
        test_writer_warns_for_missing_optional_fields_without_crashing,
        test_spread_structure_type_updates_for_backwardation_contango_flat,
        test_field_status_prefers_metadata_over_quality_result,
        test_writer_fails_evidence_readiness_when_report_id_missing,
        test_writer_fails_evidence_readiness_when_snapshot_id_missing,
        test_writer_missing_database_has_clear_error,
        test_writer_allows_null_report_id_for_evidence_rows,
        test_evidence_missing_fact_uses_field_level_fallback_and_allows_null_ids,
        test_fail_quality_blocks_core_tables_by_default,
        test_allow_fail_write_is_required_for_fail_core_rows,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
