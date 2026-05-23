"""Run the one-command daily SC oil data pipeline.

The pipeline orchestrates existing modules:
daily input JSON -> calculated input JSON -> quality report JSON
-> SQLite data_snapshot -> Evidence List -> Markdown report -> research_reports.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.init_db import (  # noqa: E402
    DEFAULT_SCHEMA_PATH,
    DatabaseCheckError,
    check_database,
    create_database,
)
from src.database.write_snapshot import (  # noqa: E402
    DEFAULT_CONFIG_PATH,
    DEFAULT_DB_PATH,
    SnapshotWriteError,
    write_snapshot,
)
from src.database.write_research_report import (  # noqa: E402
    ResearchReportWriteError,
    write_research_report,
)
from src.calculators.spreads import (  # noqa: E402
    SpreadCalculationError,
    build_default_output_path as build_default_calculated_input_path,
    calculate_spreads_file,
)
from src.evidence.generate_evidence_list import (  # noqa: E402
    EvidenceListGenerationError,
    build_default_output_path as build_default_evidence_list_path,
    generate_evidence_list,
)
from src.report_generator.generate_daily_report import (  # noqa: E402
    DailyReportGenerationError,
    build_default_output_path as build_default_daily_report_path,
    generate_daily_report,
)
from src.validators.run_quality_validation import (  # noqa: E402
    DEFAULT_DICTIONARY_PATH,
    build_default_input_path,
    build_default_output_path as build_default_quality_report_path,
    run_validation,
)


EXIT_SUCCESS = 0
EXIT_PROGRAM_ERROR = 1
EXIT_QUALITY_FAIL = 2


class DailyPipelineError(RuntimeError):
    """Raised when the daily pipeline cannot complete because of environment errors."""


def run_daily_pipeline(
    report_date: str | None = None,
    input_path: str | Path | None = None,
    calculated_input_output: str | Path | None = None,
    quality_report_output: str | Path | None = None,
    evidence_list_output: str | Path | None = None,
    daily_report_output: str | Path | None = None,
    dictionary_path: str | Path = DEFAULT_DICTIONARY_PATH,
    db_path: str | Path = DEFAULT_DB_PATH,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    snapshot_id: str | None = None,
    preserve_existing_calculations: bool = False,
    report_id: str | None = None,
    replace: bool = False,
    init_db: bool = False,
) -> dict[str, str | None]:
    """Run the complete local daily pipeline."""

    final_report_date = report_date or date.today().isoformat()
    final_input_path = Path(input_path) if input_path else build_default_input_path(final_report_date)
    final_calculated_input_path = (
        Path(calculated_input_output)
        if calculated_input_output
        else build_default_calculated_input_path(final_report_date)
    )
    final_quality_report_path = (
        Path(quality_report_output)
        if quality_report_output
        else build_default_quality_report_path(final_report_date)
    )
    final_evidence_list_path = (
        Path(evidence_list_output)
        if evidence_list_output
        else build_default_evidence_list_path(final_report_date)
    )
    final_daily_report_path = (
        Path(daily_report_output)
        if daily_report_output
        else build_default_daily_report_path(final_report_date)
    )
    final_db_path = Path(db_path)

    if init_db:
        ensure_database(final_db_path)
    if not final_db_path.expanduser().resolve().exists():
        raise DailyPipelineError(
            f"Database file not found: {final_db_path}. "
            "Run with --init-db or run `python src/database/init_db.py` first."
        )
    validate_report_write_request(final_db_path, report_id=report_id, replace=replace)

    calculate_spreads_file(
        input_path=final_input_path,
        output_path=final_calculated_input_path,
        preserve_existing=preserve_existing_calculations,
    )

    quality_report = run_validation(
        input_path=final_calculated_input_path,
        data_dictionary_path=dictionary_path,
        output_path=final_quality_report_path,
        report_date=report_date,
    )

    overall_status = quality_report["overall_status"]
    result = {
        "report_date": quality_report["report_date"],
        "calculated_input_path": _display_path(final_calculated_input_path),
        "quality_report_path": _display_path(final_quality_report_path),
        "overall_status": overall_status,
        "data_snapshot_id": None,
        "evidence_list_path": None,
        "daily_report_path": _display_path(final_daily_report_path),
        "research_report_id": None,
        "exit_code_meaning": "success",
    }

    if overall_status == "fail":
        result["exit_code_meaning"] = "quality_failed_no_snapshot_written"
        generate_daily_report(
            daily_input_path=final_calculated_input_path,
            quality_report_path=final_quality_report_path,
            output_path=final_daily_report_path,
            data_snapshot_id=None,
            evidence_list_path=None,
            write_db=False,
        )
        result["research_report_id"] = write_research_report(
            markdown_path=final_daily_report_path,
            quality_report_path=final_quality_report_path,
            db_path=final_db_path,
            config_path=config_path,
            evidence_list_path=None,
            data_snapshot_id=None,
            report_id=report_id,
            replace=replace,
        )
        return result

    data_snapshot_id = write_snapshot(
        quality_report_path=final_quality_report_path,
        db_path=final_db_path,
        config_path=config_path,
        snapshot_id=snapshot_id,
    )
    result["data_snapshot_id"] = data_snapshot_id
    generate_evidence_list(
        daily_input_path=final_calculated_input_path,
        quality_report_path=final_quality_report_path,
        output_path=final_evidence_list_path,
        data_snapshot_id=data_snapshot_id,
    )
    result["evidence_list_path"] = _display_path(final_evidence_list_path)
    generate_daily_report(
        daily_input_path=final_calculated_input_path,
        quality_report_path=final_quality_report_path,
        output_path=final_daily_report_path,
        data_snapshot_id=data_snapshot_id,
        evidence_list_path=final_evidence_list_path,
        write_db=False,
    )
    result["research_report_id"] = write_research_report(
        markdown_path=final_daily_report_path,
        quality_report_path=final_quality_report_path,
        db_path=final_db_path,
        config_path=config_path,
        evidence_list_path=final_evidence_list_path,
        data_snapshot_id=data_snapshot_id,
        report_id=report_id,
        replace=replace,
    )
    result["exit_code_meaning"] = "success_quality_pass_or_warning"
    return result


def ensure_database(db_path: str | Path) -> None:
    """Safely initialize or check the database without resetting it."""

    db_path = Path(db_path).expanduser().resolve()
    if db_path.exists():
        check_database(db_path)
        return
    create_database(db_path, DEFAULT_SCHEMA_PATH, reset=False)


def validate_report_write_request(db_path: str | Path, report_id: str | None, replace: bool) -> None:
    """Fail early for report overwrite mistakes before writing intermediate rows."""

    if replace and not report_id:
        raise DailyPipelineError("--replace requires an explicit --report-id")
    if not report_id or replace:
        return

    db_path = Path(db_path).expanduser().resolve()
    with sqlite3.connect(db_path) as conn:
        exists = conn.execute(
            "SELECT 1 FROM research_reports WHERE report_id = ? LIMIT 1;",
            (report_id,),
        ).fetchone()
    if exists:
        raise DailyPipelineError(
            f"report_id already exists: {report_id}. "
            "Use --replace with --report-id to overwrite."
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the complete local daily SC oil pipeline.")
    parser.add_argument("--report-date", help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--input", help="Daily input JSON path.")
    parser.add_argument("--calculated-input-output", help="Calculated input JSON output path.")
    parser.add_argument("--quality-report-output", help="Quality report JSON output path.")
    parser.add_argument("--evidence-list-output", help="Evidence List JSON output path.")
    parser.add_argument("--daily-report-output", help="Markdown daily report output path.")
    parser.add_argument("--dictionary", default=str(DEFAULT_DICTIONARY_PATH), help="Data dictionary YAML path.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Project config YAML path.")
    parser.add_argument("--snapshot-id", help="Explicit snapshot id. Enables INSERT OR REPLACE.")
    parser.add_argument(
        "--preserve-existing-calculations",
        action="store_true",
        help="Keep existing calculated fields instead of recalculating them.",
    )
    parser.add_argument("--report-id", help="Explicit research report id.")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Allow replacing an existing research report. Requires --report-id.",
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Safely create missing DB or check existing DB. Never resets or deletes data.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run_daily_pipeline(
            report_date=args.report_date,
            input_path=args.input,
            calculated_input_output=args.calculated_input_output,
            quality_report_output=args.quality_report_output,
            evidence_list_output=args.evidence_list_output,
            daily_report_output=args.daily_report_output,
            dictionary_path=args.dictionary,
            db_path=args.db,
            config_path=args.config,
            snapshot_id=args.snapshot_id,
            preserve_existing_calculations=args.preserve_existing_calculations,
            report_id=args.report_id,
            replace=args.replace,
            init_db=args.init_db,
        )
    except (
        DailyPipelineError,
        DatabaseCheckError,
        DailyReportGenerationError,
        EvidenceListGenerationError,
        ResearchReportWriteError,
        SnapshotWriteError,
        SpreadCalculationError,
        FileNotFoundError,
        OSError,
        sqlite3.Error,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        print(f"ERROR: {exc}")
        print("exit_code_meaning: program_or_environment_error")
        return EXIT_PROGRAM_ERROR

    _print_result(result)
    if result["overall_status"] == "fail":
        return EXIT_QUALITY_FAIL
    return EXIT_SUCCESS


def _print_result(result: dict[str, str | None]) -> None:
    print(f"report_date: {result['report_date']}")
    print(f"calculated_input_path: {result['calculated_input_path']}")
    print(f"quality_report_path: {result['quality_report_path']}")
    print(f"overall_status: {result['overall_status']}")
    print(f"data_snapshot_id: {result['data_snapshot_id'] or ''}")
    print(f"evidence_list_path: {result['evidence_list_path'] or ''}")
    print(f"daily_report_path: {result['daily_report_path']}")
    print(f"research_report_id: {result['research_report_id'] or ''}")
    print(f"exit_code_meaning: {result['exit_code_meaning']}")


def _display_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    raise SystemExit(main())
