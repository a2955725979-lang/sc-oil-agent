"""Run daily batch quality validation for SC oil research inputs.

This script reads a daily JSON input file, validates fields against
config/data_dictionary.yaml, and writes a structured quality report.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.validators.quality_checks import aggregate_status, validate_field  # noqa: E402


DEFAULT_DICTIONARY_PATH = PROJECT_ROOT / "config" / "data_dictionary.yaml"
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "manual"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"


def load_data_dictionary(path: str | Path) -> dict[str, Any]:
    dictionary_path = Path(path)
    with dictionary_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"data dictionary must be an object: {dictionary_path}")
    return data


def load_daily_input(path: str | Path) -> dict[str, Any]:
    input_path = Path(path)
    with input_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        return {"__structure_error__": "daily input JSON must be an object"}
    return data


def build_default_input_path(report_date: str) -> Path:
    return DEFAULT_INPUT_DIR / f"daily_input_{report_date}.json"


def build_default_output_path(report_date: str) -> Path:
    return DEFAULT_OUTPUT_DIR / f"quality_report_{report_date}.json"


def validate_daily_input(
    daily_input: dict[str, Any],
    data_dictionary: dict[str, Any],
    report_date: str,
    input_path: str | Path,
    data_dictionary_path: str | Path,
) -> dict[str, Any]:
    """Validate a loaded daily input object against the data dictionary."""

    report = {
        "report_date": report_date,
        "input_path": _display_path(input_path),
        "data_dictionary_path": _display_path(data_dictionary_path),
        "overall_status": "pass",
        "field_results": [],
        "warnings": [],
        "errors": [],
    }

    structure_error = daily_input.get("__structure_error__")
    if structure_error:
        report["overall_status"] = "fail"
        report["errors"].append(structure_error)
        return report

    fields = daily_input.get("fields")
    if not isinstance(fields, dict):
        report["overall_status"] = "fail"
        report["errors"].append("daily input must include a fields object")
        return report

    context = daily_input.get("context", {})
    if context is None:
        context = {}
    if not isinstance(context, dict):
        report["warnings"].append("daily input context must be an object; ignored")
        context = {}
    context = dict(context)
    context["report_date"] = report_date

    for extra_field in sorted(set(fields) - set(data_dictionary)):
        report["warnings"].append(
            f"{extra_field} is not in data dictionary; skipped official validation"
        )

    for field_name, rule_config in data_dictionary.items():
        if not isinstance(rule_config, dict):
            field_result = {
                "field": field_name,
                "source_status": "fail",
                "warnings": [],
                "errors": [f"{field_name} rule_config must be an object"],
            }
        else:
            if field_name in fields:
                value, metadata, payload_warnings = _extract_field_payload(
                    field_name,
                    fields[field_name],
                )
            else:
                value, metadata, payload_warnings = None, {}, []
            field_result = validate_field(
                field_name=field_name,
                value=value,
                metadata=metadata,
                rule_config=rule_config,
                context=context,
            )
            field_result["warnings"].extend(payload_warnings)
            if payload_warnings and field_result["source_status"] == "pass":
                field_result["source_status"] = "warning"

        report["field_results"].append(field_result)
        report["warnings"].extend(
            f"{field_result['field']}: {warning}" for warning in field_result["warnings"]
        )
        report["errors"].extend(
            f"{field_result['field']}: {error}" for error in field_result["errors"]
        )

    report["overall_status"] = _overall_status(report)
    return report


def run_validation(
    input_path: str | Path,
    data_dictionary_path: str | Path = DEFAULT_DICTIONARY_PATH,
    output_path: str | Path | None = None,
    report_date: str | None = None,
) -> dict[str, Any]:
    """Load input, validate it, write a report, and return the report object."""

    daily_input = load_daily_input(input_path)
    data_dictionary = load_data_dictionary(data_dictionary_path)
    final_report_date = _resolve_report_date(report_date, daily_input)
    final_output_path = Path(output_path) if output_path else build_default_output_path(final_report_date)

    report = validate_daily_input(
        daily_input=daily_input,
        data_dictionary=data_dictionary,
        report_date=final_report_date,
        input_path=input_path,
        data_dictionary_path=data_dictionary_path,
    )
    write_quality_report(report, final_output_path)
    return report


def write_quality_report(report: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")


def print_summary(report: dict[str, Any]) -> None:
    counts = {"pass": 0, "warning": 0, "fail": 0}
    for field_result in report["field_results"]:
        counts[field_result["source_status"]] += 1

    print(f"report_date: {report['report_date']}")
    print(f"overall_status: {report['overall_status']}")
    print(
        "field_results: "
        f"pass={counts['pass']} warning={counts['warning']} fail={counts['fail']}"
    )
    print(f"warnings: {len(report['warnings'])}")
    print(f"errors: {len(report['errors'])}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily SC oil data quality validation.")
    parser.add_argument("--report-date", help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--input", help="Daily input JSON path.")
    parser.add_argument("--dictionary", default=str(DEFAULT_DICTIONARY_PATH), help="Data dictionary YAML path.")
    parser.add_argument("--output", help="Quality report output JSON path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report_date = args.report_date or date.today().isoformat()
    input_path = Path(args.input) if args.input else build_default_input_path(report_date)

    report = run_validation(
        input_path=input_path,
        data_dictionary_path=args.dictionary,
        output_path=args.output,
        report_date=args.report_date,
    )
    print_summary(report)
    return 0


def _extract_field_payload(
    field_name: str,
    field_payload: Any,
) -> tuple[Any, dict[str, Any], list[str]]:
    if not isinstance(field_payload, dict):
        return None, {}, [f"{field_name} payload must be an object with value and metadata"]

    warnings = []
    if "value" not in field_payload:
        warnings.append(f"{field_name} payload missing value")

    metadata = field_payload.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        warnings.append(f"{field_name} metadata must be an object; ignored")
        metadata = {}

    return field_payload.get("value"), metadata, warnings


def _resolve_report_date(report_date: str | None, daily_input: dict[str, Any]) -> str:
    if report_date:
        return report_date
    input_report_date = daily_input.get("report_date")
    if input_report_date:
        return str(input_report_date)
    return date.today().isoformat()


def _overall_status(report: dict[str, Any]) -> str:
    if report["errors"]:
        return "fail"

    statuses = [result["source_status"] for result in report["field_results"]]
    if report["warnings"]:
        statuses.append("warning")
    return aggregate_status(statuses)


def _display_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    raise SystemExit(main())
