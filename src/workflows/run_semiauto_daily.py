"""Run the semi-auto daily SC oil workflow.

This workflow composes the existing AKShare fetcher, raw_data converter,
daily_input merger, and local daily pipeline. It does not introduce new data
sources or duplicate business logic from those modules.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.calculators.spreads import SpreadCalculationError  # noqa: E402
from src.database.init_db import DatabaseCheckError  # noqa: E402
from src.database.write_research_report import ResearchReportWriteError  # noqa: E402
from src.database.write_snapshot import SnapshotWriteError  # noqa: E402
from src.evidence.generate_evidence_list import EvidenceListGenerationError  # noqa: E402
from src.fetchers.akshare_sc import (  # noqa: E402
    build_default_output_path as build_default_raw_output_path,
    fetch_akshare_sc_daily,
    write_raw_data,
)
from src.fetchers.merge_daily_input import DailyInputMergeError, merge_daily_input_file  # noqa: E402
from src.fetchers.transform import RawDataTransformError, convert_raw_data_file  # noqa: E402
from src.pipeline.run_daily_pipeline import DailyPipelineError, run_daily_pipeline  # noqa: E402
from src.report_generator.generate_daily_report import DailyReportGenerationError  # noqa: E402


EXIT_SUCCESS = 0
EXIT_PROGRAM_ERROR = 1
EXIT_CONTROLLED_DATA_FAILURE = 2


class SemiautoDailyWorkflowError(RuntimeError):
    """Raised when the semi-auto workflow has a program/environment error."""


def build_default_akshare_daily_input_path(report_date: str) -> Path:
    return PROJECT_ROOT / "data" / "processed" / f"akshare_daily_input_{report_date}.json"


def build_default_conversion_result_path(report_date: str) -> Path:
    return PROJECT_ROOT / "data" / "processed" / f"conversion_result_{report_date}.json"


def build_default_merged_daily_input_path(report_date: str) -> Path:
    return PROJECT_ROOT / "data" / "manual" / f"daily_input_{report_date}.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the semi-auto daily SC oil workflow.")
    parser.add_argument("--report-date", required=True, help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--manual-supplement", required=True, help="Manual supplement daily_input JSON path.")
    parser.add_argument("--raw-input", help="Existing AKShare raw_data JSON path. Skips live AKShare fetch.")
    parser.add_argument("--raw-output", help="AKShare raw_data output JSON path when fetching live data.")
    parser.add_argument("--akshare-daily-input-output", help="AKShare partial daily_input output JSON path.")
    parser.add_argument("--conversion-result-output", help="Raw conversion diagnostics output JSON path.")
    parser.add_argument("--merged-daily-input-output", help="Merged daily_input output JSON path.")
    parser.add_argument("--calculated-input-output", help="Calculated input JSON output path.")
    parser.add_argument("--quality-report-output", help="Quality report JSON output path.")
    parser.add_argument("--evidence-list-output", help="Evidence List JSON output path.")
    parser.add_argument("--daily-report-output", help="Markdown daily report output path.")
    parser.add_argument("--db", help="SQLite database path.")
    parser.add_argument("--config", help="Project config YAML path.")
    parser.add_argument("--dictionary", help="Data dictionary YAML path.")
    parser.add_argument("--report-id", help="Explicit research report id.")
    parser.add_argument("--replace", action="store_true", help="Allow replacing an existing research report.")
    parser.add_argument("--init-db", action="store_true", help="Safely initialize or check the SQLite DB.")
    parser.add_argument(
        "--preserve-existing-calculations",
        action="store_true",
        help="Keep existing calculated fields instead of recalculating them.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = _initial_summary(args)
    exit_code = EXIT_PROGRAM_ERROR

    try:
        exit_code = run_semiauto_daily(args, summary)
    except (
        SemiautoDailyWorkflowError,
        RawDataTransformError,
        DailyInputMergeError,
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
        summary["exit_code_meaning"] = "program_or_environment_error"
        exit_code = EXIT_PROGRAM_ERROR

    if exit_code == EXIT_CONTROLLED_DATA_FAILURE and not summary.get("exit_code_meaning"):
        summary["exit_code_meaning"] = "controlled_data_failure"
    _print_summary(summary)
    return exit_code


def run_semiauto_daily(args: argparse.Namespace, summary: dict[str, str | None]) -> int:
    report_date = args.report_date
    manual_supplement_path = Path(args.manual_supplement)
    if not manual_supplement_path.exists():
        raise SemiautoDailyWorkflowError(f"manual supplement not found: {manual_supplement_path}")

    raw_data_path = _resolve_raw_data(args, summary)

    akshare_daily_input_path = Path(args.akshare_daily_input_output) if args.akshare_daily_input_output else (
        build_default_akshare_daily_input_path(report_date)
    )
    conversion_result_path = Path(args.conversion_result_output) if args.conversion_result_output else (
        build_default_conversion_result_path(report_date)
    )
    merged_daily_input_path = Path(args.merged_daily_input_output) if args.merged_daily_input_output else (
        build_default_merged_daily_input_path(report_date)
    )

    summary["conversion_result_path"] = _display_path(conversion_result_path)
    summary["akshare_daily_input_path"] = _display_path(akshare_daily_input_path)
    summary["merged_daily_input_path"] = _display_path(merged_daily_input_path)

    conversion = convert_raw_data_file(
        input_path=raw_data_path,
        output_path=akshare_daily_input_path,
        result_output_path=conversion_result_path,
    )
    _validate_conversion_report_date(conversion, report_date)

    if not conversion.get("usable_for_pipeline"):
        summary["overall_status"] = "conversion_unusable"
        summary["exit_code_meaning"] = "controlled_data_failure_conversion_unusable"
        return EXIT_CONTROLLED_DATA_FAILURE

    merge_daily_input_file(
        base_path=manual_supplement_path,
        overlay_path=akshare_daily_input_path,
        output_path=merged_daily_input_path,
    )

    pipeline_kwargs: dict[str, Any] = {
        "report_date": report_date,
        "input_path": merged_daily_input_path,
        "calculated_input_output": args.calculated_input_output,
        "quality_report_output": args.quality_report_output,
        "evidence_list_output": args.evidence_list_output,
        "daily_report_output": args.daily_report_output,
        "preserve_existing_calculations": args.preserve_existing_calculations,
        "report_id": args.report_id,
        "replace": args.replace,
        "init_db": args.init_db,
    }
    if args.dictionary:
        pipeline_kwargs["dictionary_path"] = args.dictionary
    if args.db:
        pipeline_kwargs["db_path"] = args.db
    if args.config:
        pipeline_kwargs["config_path"] = args.config

    pipeline_result = run_daily_pipeline(**pipeline_kwargs)
    _copy_pipeline_result(summary, pipeline_result)
    return EXIT_CONTROLLED_DATA_FAILURE if pipeline_result["overall_status"] == "fail" else EXIT_SUCCESS


def _resolve_raw_data(args: argparse.Namespace, summary: dict[str, str | None]) -> Path:
    if args.raw_input:
        raw_data_path = Path(args.raw_input)
        if not raw_data_path.exists():
            raise SemiautoDailyWorkflowError(f"raw input not found: {raw_data_path}")
        summary["raw_data_path"] = _display_path(raw_data_path)
        return raw_data_path

    raw_data_path = Path(args.raw_output) if args.raw_output else build_default_raw_output_path(args.report_date)
    raw_data = fetch_akshare_sc_daily(args.report_date)
    write_raw_data(raw_data, raw_data_path)
    summary["raw_data_path"] = _display_path(raw_data_path)
    return raw_data_path


def _validate_conversion_report_date(conversion: dict[str, Any], requested_report_date: str) -> None:
    daily_input = conversion.get("daily_input")
    converted_report_date = ""
    if isinstance(daily_input, dict):
        converted_report_date = str(daily_input.get("report_date") or "")
    if converted_report_date != requested_report_date:
        raise SemiautoDailyWorkflowError(
            f"report_date mismatch: requested={requested_report_date}, raw_data={converted_report_date}"
        )


def _initial_summary(args: argparse.Namespace) -> dict[str, str | None]:
    return {
        "report_date": args.report_date,
        "raw_data_path": _display_path(args.raw_input) if args.raw_input else _display_path(
            args.raw_output or build_default_raw_output_path(args.report_date)
        ),
        "conversion_result_path": _display_path(
            args.conversion_result_output or build_default_conversion_result_path(args.report_date)
        ),
        "akshare_daily_input_path": _display_path(
            args.akshare_daily_input_output or build_default_akshare_daily_input_path(args.report_date)
        ),
        "merged_daily_input_path": _display_path(
            args.merged_daily_input_output or build_default_merged_daily_input_path(args.report_date)
        ),
        "quality_report_path": "",
        "overall_status": "",
        "data_snapshot_id": "",
        "evidence_list_path": "",
        "daily_report_path": "",
        "research_report_id": "",
        "exit_code_meaning": "",
    }


def _copy_pipeline_result(summary: dict[str, str | None], pipeline_result: dict[str, str | None]) -> None:
    summary["quality_report_path"] = pipeline_result.get("quality_report_path") or ""
    summary["overall_status"] = pipeline_result.get("overall_status") or ""
    summary["data_snapshot_id"] = pipeline_result.get("data_snapshot_id") or ""
    summary["evidence_list_path"] = pipeline_result.get("evidence_list_path") or ""
    summary["daily_report_path"] = pipeline_result.get("daily_report_path") or ""
    summary["research_report_id"] = pipeline_result.get("research_report_id") or ""
    summary["exit_code_meaning"] = pipeline_result.get("exit_code_meaning") or ""


def _print_summary(summary: dict[str, str | None]) -> None:
    print(f"report_date: {summary.get('report_date') or ''}")
    print(f"raw_data_path: {summary.get('raw_data_path') or ''}")
    print(f"conversion_result_path: {summary.get('conversion_result_path') or ''}")
    print(f"akshare_daily_input_path: {summary.get('akshare_daily_input_path') or ''}")
    print(f"merged_daily_input_path: {summary.get('merged_daily_input_path') or ''}")
    print(f"quality_report_path: {summary.get('quality_report_path') or ''}")
    print(f"overall_status: {summary.get('overall_status') or ''}")
    print(f"data_snapshot_id: {summary.get('data_snapshot_id') or ''}")
    print(f"evidence_list_path: {summary.get('evidence_list_path') or ''}")
    print(f"daily_report_path: {summary.get('daily_report_path') or ''}")
    print(f"research_report_id: {summary.get('research_report_id') or ''}")
    print(f"exit_code_meaning: {summary.get('exit_code_meaning') or ''}")


def _display_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    raise SystemExit(main())
