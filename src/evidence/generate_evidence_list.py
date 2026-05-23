"""Generate field-level Evidence List v1 from local daily inputs.

Evidence List v1 is intentionally limited: it records field-level data
references and must not be treated as conclusion-level research evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


CALCULATED_INDICATOR_FIELDS = {
    "SC_USD",
    "SC_calendar_spread",
    "SC_Brent_spread_simple",
    "SC_WTI_spread_simple",
}

FIELD_EVIDENCE_TYPES = {
    "OPEC_monthly_summary": "monthly_report_summary",
    "IEA_monthly_summary": "monthly_report_summary",
    "exchange_notice": "exchange_notice",
    "important_oil_news": "important_news",
    "manual_notes": "manual_note",
}


class EvidenceListGenerationError(RuntimeError):
    """Raised when an Evidence List cannot be generated."""


def load_json(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    with json_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise EvidenceListGenerationError(f"JSON file must be an object: {json_path}")
    return data


def build_default_output_path(report_date: str) -> Path:
    return PROJECT_ROOT / "data" / "processed" / f"evidence_list_{report_date}.json"


def generate_evidence_list(
    daily_input_path: str | Path,
    quality_report_path: str | Path,
    output_path: str | Path | None = None,
    data_snapshot_id: str | None = None,
) -> dict[str, Any]:
    daily_input = load_json(daily_input_path)
    quality_report = load_json(quality_report_path)
    evidence_report = build_evidence_report(
        daily_input=daily_input,
        quality_report=quality_report,
        data_snapshot_id=data_snapshot_id,
        daily_input_path=daily_input_path,
        quality_report_path=quality_report_path,
    )

    output = Path(output_path) if output_path else build_default_output_path(evidence_report["report_date"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as file:
        json.dump(evidence_report, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return evidence_report


def build_evidence_report(
    daily_input: dict[str, Any],
    quality_report: dict[str, Any],
    data_snapshot_id: str | None,
    daily_input_path: str | Path,
    quality_report_path: str | Path,
) -> dict[str, Any]:
    report_date = str(quality_report.get("report_date") or daily_input.get("report_date") or "UNKNOWN_DATE")
    fields = daily_input.get("fields", {})
    if not isinstance(fields, dict):
        fields = {}

    field_results = quality_report.get("field_results", [])
    if not isinstance(field_results, list):
        field_results = []
    status_by_field = {
        str(result.get("field")): result
        for result in field_results
        if isinstance(result, dict) and result.get("field")
    }

    evidence_items = []
    skipped_fields = []
    sequence = 1
    for field_name, payload in fields.items():
        field_result = status_by_field.get(field_name)
        if not field_result:
            skipped_fields.append(f"{field_name}: not in quality_report field_results")
            continue

        source_status = str(field_result.get("source_status", "warning"))
        if source_status == "fail":
            skipped_fields.append(f"{field_name}: source_status=fail")
            continue

        if not isinstance(payload, dict):
            skipped_fields.append(f"{field_name}: payload is not an object")
            continue
        value = payload.get("value")
        if value is None or (isinstance(value, str) and not value.strip()):
            skipped_fields.append(f"{field_name}: missing value")
            continue

        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        evidence_items.append(
            _build_evidence_item(
                field_name=field_name,
                value=value,
                metadata=metadata,
                field_result=field_result,
                report_date=report_date,
                sequence=sequence,
                data_snapshot_id=data_snapshot_id,
            )
        )
        sequence += 1

    return {
        "report_date": report_date,
        "data_snapshot_id": data_snapshot_id,
        "daily_input_path": _display_path(daily_input_path),
        "quality_report_path": _display_path(quality_report_path),
        "evidence_scope": "field_level_only",
        "limitations": [
            "Evidence List v1 is field-level evidence, not conclusion-level research evidence.",
            "Evidence List v1 must not directly support directional research or trading conclusions.",
            "warning evidence must be treated as downgraded and reviewed manually.",
        ],
        "evidence_list": evidence_items,
        "skipped_fields": skipped_fields,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate field-level Evidence List v1.")
    parser.add_argument("--daily-input", required=True, help="Daily input JSON path.")
    parser.add_argument("--quality-report", required=True, help="Quality report JSON path.")
    parser.add_argument("--output", help="Evidence List output JSON path.")
    parser.add_argument("--data-snapshot-id", help="Optional data snapshot id.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = generate_evidence_list(
            daily_input_path=args.daily_input,
            quality_report_path=args.quality_report,
            output_path=args.output,
            data_snapshot_id=args.data_snapshot_id,
        )
    except (EvidenceListGenerationError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1

    counts = _count_evidence_types(report["evidence_list"])
    print(f"report_date: {report['report_date']}")
    print(f"evidence_count: {len(report['evidence_list'])}")
    print(f"evidence_types: {counts}")
    print(f"skipped_fields: {len(report['skipped_fields'])}")
    return 0


def _build_evidence_item(
    field_name: str,
    value: Any,
    metadata: dict[str, Any],
    field_result: dict[str, Any],
    report_date: str,
    sequence: int,
    data_snapshot_id: str | None,
) -> dict[str, Any]:
    source_status = str(field_result.get("source_status", "warning"))
    evidence_type = _evidence_type_for_field(field_name)
    unit = metadata.get("unit")
    data_time = metadata.get("data_time") or metadata.get("date")
    publish_time = metadata.get("publish_time") or metadata.get("update_time")

    return {
        "evidence_id": _evidence_id(report_date, sequence),
        "evidence_type": evidence_type,
        "evidence_scope": "field_level_only",
        "field": field_name,
        "source_status": source_status,
        "confidence": _confidence_for_status(source_status),
        "data_snapshot_id": data_snapshot_id,
        "data_time": data_time,
        "publish_time": publish_time,
        "timezone": metadata.get("timezone") or metadata.get("time_zone"),
        "raw_value": value,
        "normalized_value": value,
        "unit": unit,
        "extracted_fact": _extracted_fact(field_name, value, unit),
        "limitations": [
            "field-level evidence only",
            "not a conclusion-level evidence item",
        ],
        "warnings": list(field_result.get("warnings", [])),
        "errors": list(field_result.get("errors", [])),
    }


def _evidence_type_for_field(field_name: str) -> str:
    if field_name in CALCULATED_INDICATOR_FIELDS:
        return "calculated_indicator"
    return FIELD_EVIDENCE_TYPES.get(field_name, "validated_field")


def _confidence_for_status(source_status: str) -> str:
    if source_status == "pass":
        return "medium"
    return "low"


def _evidence_id(report_date: str, sequence: int) -> str:
    compact_date = report_date.replace("-", "")
    return f"EVID-{compact_date}-{sequence:03d}"


def _extracted_fact(field_name: str, value: Any, unit: Any) -> str:
    suffix = f" {unit}" if unit else ""
    return f"{field_name}={value}{suffix}"


def _display_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())


def _count_evidence_types(evidence_items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in evidence_items:
        evidence_type = str(item.get("evidence_type", "unknown"))
        counts[evidence_type] = counts.get(evidence_type, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
