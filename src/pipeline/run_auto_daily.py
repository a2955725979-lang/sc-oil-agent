"""Run auto daily preflight without requiring manual daily_input."""

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
    build_default_output_path as build_default_akshare_raw_path,
    fetch_akshare_sc_daily,
    write_raw_data as write_akshare_raw_data,
)
from src.fetchers.default_fields import (  # noqa: E402
    build_default_daily_input as build_default_fields_daily_input,
    build_default_output_path as build_default_fields_path,
    write_daily_input,
)
from src.fetchers.market_fx import (  # noqa: E402
    build_default_output_path as build_default_market_fx_raw_path,
    fetch_market_fx_daily,
    write_raw_data as write_market_fx_raw_data,
)
from src.fetchers.merge_daily_input import DailyInputMergeError, merge_daily_inputs  # noqa: E402
from src.fetchers.transform import RawDataTransformError, convert_raw_data_file  # noqa: E402
from src.pipeline.run_daily_pipeline import DailyPipelineError, run_daily_pipeline  # noqa: E402
from src.report_generator.generate_daily_report import DailyReportGenerationError  # noqa: E402


EXIT_SUCCESS = 0
EXIT_PROGRAM_ERROR = 1
EXIT_CONTROLLED_DATA_FAILURE = 2


class AutoDailyWorkflowError(RuntimeError):
    """Raised when auto daily preflight has a program/environment error."""


def build_default_akshare_daily_input_path(report_date: str) -> Path:
    return PROJECT_ROOT / "data" / "processed" / f"akshare_daily_input_{report_date}.json"


def build_default_market_fx_daily_input_path(report_date: str) -> Path:
    return PROJECT_ROOT / "data" / "processed" / f"market_fx_daily_input_{report_date}.json"


def build_default_akshare_conversion_result_path(report_date: str) -> Path:
    return PROJECT_ROOT / "data" / "processed" / f"akshare_conversion_result_{report_date}.json"


def build_default_market_fx_conversion_result_path(report_date: str) -> Path:
    return PROJECT_ROOT / "data" / "processed" / f"market_fx_conversion_result_{report_date}.json"


def build_default_auto_daily_input_path(report_date: str) -> Path:
    return PROJECT_ROOT / "data" / "manual" / f"daily_input_{report_date}.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run auto daily preflight for SC oil.")
    parser.add_argument("--report-date", required=True, help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--manual-supplement", help="Optional manual supplement daily_input JSON path.")
    parser.add_argument(
        "--raw-input",
        "--akshare-raw-input",
        dest="akshare_raw_input",
        help="Existing AKShare raw_data JSON path. Skips live AKShare fetch.",
    )
    parser.add_argument("--market-fx-raw-input", help="Existing market/fx raw_data JSON path. Skips live market/fx fetch.")
    parser.add_argument("--akshare-raw-output", help="AKShare raw_data output JSON path.")
    parser.add_argument("--market-fx-raw-output", help="Market/fx raw_data output JSON path.")
    parser.add_argument("--akshare-daily-input-output", help="AKShare partial daily_input output JSON path.")
    parser.add_argument("--market-fx-daily-input-output", help="Market/fx partial daily_input output JSON path.")
    parser.add_argument("--default-fields-output", help="Default fields daily_input output JSON path.")
    parser.add_argument("--akshare-conversion-result-output", help="AKShare conversion diagnostics output JSON path.")
    parser.add_argument("--market-fx-conversion-result-output", help="Market/fx conversion diagnostics output JSON path.")
    parser.add_argument("--auto-daily-input-output", help="Final auto daily_input output JSON path.")
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
        exit_code = run_auto_daily(args, summary)
    except (
        AutoDailyWorkflowError,
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

    _print_summary(summary)
    return exit_code


def run_auto_daily(args: argparse.Namespace, summary: dict[str, str | None]) -> int:
    report_date = args.report_date

    akshare_raw_path = _resolve_akshare_raw_data(args, summary)
    market_fx_raw_path = _resolve_market_fx_raw_data(args, summary)

    akshare_daily_input_path = Path(args.akshare_daily_input_output) if args.akshare_daily_input_output else (
        build_default_akshare_daily_input_path(report_date)
    )
    market_fx_daily_input_path = Path(args.market_fx_daily_input_output) if args.market_fx_daily_input_output else (
        build_default_market_fx_daily_input_path(report_date)
    )
    default_fields_path = Path(args.default_fields_output) if args.default_fields_output else (
        build_default_fields_path(report_date)
    )
    akshare_conversion_result_path = (
        Path(args.akshare_conversion_result_output)
        if args.akshare_conversion_result_output
        else build_default_akshare_conversion_result_path(report_date)
    )
    market_fx_conversion_result_path = (
        Path(args.market_fx_conversion_result_output)
        if args.market_fx_conversion_result_output
        else build_default_market_fx_conversion_result_path(report_date)
    )
    auto_daily_input_path = Path(args.auto_daily_input_output) if args.auto_daily_input_output else (
        build_default_auto_daily_input_path(report_date)
    )

    _set_paths(
        summary,
        {
            "akshare_daily_input_path": akshare_daily_input_path,
            "market_fx_daily_input_path": market_fx_daily_input_path,
            "default_fields_path": default_fields_path,
            "akshare_conversion_result_path": akshare_conversion_result_path,
            "market_fx_conversion_result_path": market_fx_conversion_result_path,
            "auto_daily_input_path": auto_daily_input_path,
        },
    )

    akshare_conversion = convert_raw_data_file(
        input_path=akshare_raw_path,
        output_path=akshare_daily_input_path,
        result_output_path=akshare_conversion_result_path,
    )
    _validate_conversion_report_date(akshare_conversion, report_date, "akshare")
    if not akshare_conversion.get("usable_for_pipeline"):
        summary["overall_status"] = "akshare_conversion_unusable"
        summary["exit_code_meaning"] = "controlled_data_failure_akshare_unusable"
        return EXIT_CONTROLLED_DATA_FAILURE

    market_fx_conversion = convert_raw_data_file(
        input_path=market_fx_raw_path,
        output_path=market_fx_daily_input_path,
        result_output_path=market_fx_conversion_result_path,
    )
    _validate_conversion_report_date(market_fx_conversion, report_date, "market_fx")
    if not market_fx_conversion.get("usable_for_pipeline"):
        summary["overall_status"] = "market_fx_conversion_unusable"
        summary["exit_code_meaning"] = "controlled_data_failure_market_fx_unusable"
        return EXIT_CONTROLLED_DATA_FAILURE

    default_daily_input = build_default_fields_daily_input(report_date)
    write_daily_input(default_daily_input, default_fields_path)
    market_fx_daily_input = _load_json(market_fx_daily_input_path)
    akshare_daily_input = _load_json(akshare_daily_input_path)

    merged = merge_daily_inputs(default_daily_input, market_fx_daily_input)
    merged = merge_daily_inputs(merged, akshare_daily_input)

    if args.manual_supplement:
        manual_path = Path(args.manual_supplement)
        if not manual_path.exists():
            raise AutoDailyWorkflowError(f"manual supplement not found: {manual_path}")
        merged = merge_daily_inputs(merged, _load_json(manual_path))

    write_daily_input(merged, auto_daily_input_path)

    pipeline_kwargs: dict[str, Any] = {
        "report_date": report_date,
        "input_path": auto_daily_input_path,
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


def _resolve_akshare_raw_data(args: argparse.Namespace, summary: dict[str, str | None]) -> Path:
    raw_input = args.akshare_raw_input
    if raw_input:
        raw_path = Path(raw_input)
        if not raw_path.exists():
            raise AutoDailyWorkflowError(f"AKShare raw input not found: {raw_path}")
        summary["akshare_raw_data_path"] = _display_path(raw_path)
        return raw_path

    raw_path = Path(args.akshare_raw_output) if args.akshare_raw_output else build_default_akshare_raw_path(args.report_date)
    raw_data = fetch_akshare_sc_daily(args.report_date)
    write_akshare_raw_data(raw_data, raw_path)
    summary["akshare_raw_data_path"] = _display_path(raw_path)
    return raw_path


def _resolve_market_fx_raw_data(args: argparse.Namespace, summary: dict[str, str | None]) -> Path:
    if args.market_fx_raw_input:
        raw_path = Path(args.market_fx_raw_input)
        if not raw_path.exists():
            raise AutoDailyWorkflowError(f"market_fx raw input not found: {raw_path}")
        summary["market_fx_raw_data_path"] = _display_path(raw_path)
        return raw_path

    raw_path = Path(args.market_fx_raw_output) if args.market_fx_raw_output else build_default_market_fx_raw_path(args.report_date)
    raw_data = fetch_market_fx_daily(args.report_date)
    write_market_fx_raw_data(raw_data, raw_path)
    summary["market_fx_raw_data_path"] = _display_path(raw_path)
    return raw_path


def _validate_conversion_report_date(conversion: dict[str, Any], requested_report_date: str, label: str) -> None:
    daily_input = conversion.get("daily_input")
    converted_report_date = ""
    if isinstance(daily_input, dict):
        converted_report_date = str(daily_input.get("report_date") or "")
    if converted_report_date != requested_report_date:
        raise AutoDailyWorkflowError(
            f"{label} report_date mismatch: requested={requested_report_date}, raw_data={converted_report_date}"
        )


def _load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise AutoDailyWorkflowError(f"JSON must be an object: {path}")
    return data


def _initial_summary(args: argparse.Namespace) -> dict[str, str | None]:
    return {
        "report_date": args.report_date,
        "akshare_raw_data_path": _display_path(
            args.akshare_raw_input or args.akshare_raw_output or build_default_akshare_raw_path(args.report_date)
        ),
        "market_fx_raw_data_path": _display_path(
            args.market_fx_raw_input or args.market_fx_raw_output or build_default_market_fx_raw_path(args.report_date)
        ),
        "akshare_conversion_result_path": _display_path(
            args.akshare_conversion_result_output or build_default_akshare_conversion_result_path(args.report_date)
        ),
        "market_fx_conversion_result_path": _display_path(
            args.market_fx_conversion_result_output or build_default_market_fx_conversion_result_path(args.report_date)
        ),
        "akshare_daily_input_path": _display_path(
            args.akshare_daily_input_output or build_default_akshare_daily_input_path(args.report_date)
        ),
        "market_fx_daily_input_path": _display_path(
            args.market_fx_daily_input_output or build_default_market_fx_daily_input_path(args.report_date)
        ),
        "default_fields_path": _display_path(args.default_fields_output or build_default_fields_path(args.report_date)),
        "auto_daily_input_path": _display_path(
            args.auto_daily_input_output or build_default_auto_daily_input_path(args.report_date)
        ),
        "quality_report_path": "",
        "overall_status": "",
        "data_snapshot_id": "",
        "evidence_list_path": "",
        "daily_report_path": "",
        "research_report_id": "",
        "exit_code_meaning": "",
    }


def _set_paths(summary: dict[str, str | None], paths: dict[str, Path]) -> None:
    for key, value in paths.items():
        summary[key] = _display_path(value)


def _copy_pipeline_result(summary: dict[str, str | None], pipeline_result: dict[str, str | None]) -> None:
    summary["quality_report_path"] = pipeline_result.get("quality_report_path") or ""
    summary["overall_status"] = pipeline_result.get("overall_status") or ""
    summary["data_snapshot_id"] = pipeline_result.get("data_snapshot_id") or ""
    summary["evidence_list_path"] = pipeline_result.get("evidence_list_path") or ""
    summary["daily_report_path"] = pipeline_result.get("daily_report_path") or ""
    summary["research_report_id"] = pipeline_result.get("research_report_id") or ""
    summary["exit_code_meaning"] = pipeline_result.get("exit_code_meaning") or ""


def _print_summary(summary: dict[str, str | None]) -> None:
    for key in (
        "report_date",
        "akshare_raw_data_path",
        "market_fx_raw_data_path",
        "akshare_conversion_result_path",
        "market_fx_conversion_result_path",
        "akshare_daily_input_path",
        "market_fx_daily_input_path",
        "default_fields_path",
        "auto_daily_input_path",
        "quality_report_path",
        "overall_status",
        "data_snapshot_id",
        "evidence_list_path",
        "daily_report_path",
        "research_report_id",
        "exit_code_meaning",
    ):
        print(f"{key}: {summary.get(key) or ''}")


def _display_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    raise SystemExit(main())
