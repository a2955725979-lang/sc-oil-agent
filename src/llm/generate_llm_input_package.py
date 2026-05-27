"""Generate deterministic LLM input packages from existing pipeline artifacts.

This module does not call an LLM and does not infer market conclusions. It only
packages structured artifacts for a future reasoning layer.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SCHEMA_VERSION = "llm_input_package_v1"
CALCULATED_FIELDS = {
    "SC_USD",
    "SC_calendar_spread",
    "SC_Brent_spread_simple",
    "SC_WTI_spread_simple",
}
FORBIDDEN_OUTPUTS = [
    "buy",
    "sell",
    "must rise",
    "must fall",
    "guaranteed profit",
    "稳赚",
    "买入",
    "卖出",
    "必涨",
    "必跌",
]
FIELD_LEVEL_EVIDENCE_NOTE = (
    "These evidence items support field availability and source traceability only. "
    "They do not independently support directional market conclusions."
)


def generate_llm_input_package(
    calculated_input_path: str | Path,
    quality_report_path: str | Path,
    evidence_list_path: str | Path | None = None,
    business_write_summary_path: str | Path | None = None,
    daily_report_path: str | Path | None = None,
    smoke_summary_path: str | Path | None = None,
    output_path: str | Path | None = None,
    data_snapshot_id: str | None = None,
    research_report_id: str | None = None,
) -> dict[str, Any]:
    """Create and write an LLM input package from deterministic artifacts."""

    calculated_path = Path(calculated_input_path)
    quality_path = Path(quality_report_path)
    calculated_input = _load_json(calculated_path)
    quality_report = _load_json(quality_path)
    notes: list[str] = []

    report_date, source_priority = _resolve_report_date(quality_report, calculated_input)
    package_created_at = datetime.now(timezone.utc).isoformat()
    final_output_path = Path(output_path) if output_path else build_default_output_path(report_date)

    evidence_report = _load_optional_json(evidence_list_path, "evidence_list", notes)
    business_summary = _load_optional_json(business_write_summary_path, "business_write_summary", notes)
    smoke_summary = _load_optional_json(smoke_summary_path, "smoke_summary", notes)

    fields = calculated_input.get("fields", {})
    if not isinstance(fields, dict):
        fields = {}
        notes.append("calculated_input.fields is absent or invalid; no field facts were generated.")

    quality_by_field = _quality_by_field(quality_report)
    field_facts = _build_field_facts(fields, quality_by_field)
    calculated_indicators = _build_calculated_indicators(fields, quality_by_field)
    evidence_items = _build_evidence_items(evidence_report, notes)
    quality_constraints = _build_quality_constraints(quality_report, fields)
    business_persistence = _build_business_persistence(business_summary, notes)
    daily_report_info = _daily_report_info(daily_report_path, notes)

    overall_status = str(quality_report.get("overall_status") or "unknown")
    if overall_status == "fail":
        notes.append("Quality status is fail; future LLM must not generate normal market explanation.")
    if smoke_summary and str(smoke_summary.get("acceptance_status", "unknown")) == "red":
        notes.append("Smoke test red; future LLM must not treat this package as production-ready.")

    package = {
        "schema_version": SCHEMA_VERSION,
        "report_date": report_date,
        "package_created_at": package_created_at,
        "data_snapshot_id": data_snapshot_id,
        "research_report_id": research_report_id,
        "pipeline_status": {
            "report_date": report_date,
            "package_generated_at": package_created_at,
            "source_priority": source_priority,
            "overall_status": overall_status,
            "source_status_summary": _source_status_summary(field_facts, calculated_indicators),
            "quality_warning_count": len(_as_list(quality_report.get("warnings"))),
            "quality_error_count": len(_as_list(quality_report.get("errors"))),
            "business_write_status": _business_write_status(business_summary),
            "smoke_acceptance_status": str(smoke_summary.get("acceptance_status", "unknown"))
            if isinstance(smoke_summary, dict)
            else "unknown",
        },
        "inputs": {
            "calculated_input_path": _display_path(calculated_path),
            "quality_report_path": _display_path(quality_path),
            "evidence_list_path": _optional_display_path(evidence_list_path),
            "business_write_summary_path": _optional_display_path(business_write_summary_path),
            "daily_report_path": _optional_display_path(daily_report_path),
            "daily_report_exists": daily_report_info["exists"],
            "daily_report_preview": daily_report_info["preview"],
            "smoke_summary_path": _optional_display_path(smoke_summary_path),
        },
        "field_facts": field_facts,
        "calculated_indicators": calculated_indicators,
        "evidence_items": evidence_items,
        "quality_constraints": quality_constraints,
        "business_persistence": business_persistence,
        "allowed_reasoning_scope": _allowed_reasoning_scope(),
        "forbidden_outputs": list(FORBIDDEN_OUTPUTS),
        "langgraph_handoff": {
            "recommended_future_nodes": [
                "DataQualityReader",
                "EvidenceReader",
                "MarketContextDraft",
                "RiskChallenge",
                "HumanReviewGate",
                "ReportDraftRefiner",
            ],
            "current_step_is_llm_free": True,
            "agent_execution_allowed": False,
        },
        "notes": notes,
    }

    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    return package


def build_default_output_path(report_date: str) -> Path:
    return PROJECT_ROOT / "data" / "processed" / f"llm_input_package_{report_date}.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a deterministic LLM input package.")
    parser.add_argument("--calculated-input", required=True, help="Calculated input JSON path.")
    parser.add_argument("--quality-report", required=True, help="Quality report JSON path.")
    parser.add_argument("--evidence-list", help="Optional Evidence List JSON path.")
    parser.add_argument("--business-write-summary", help="Optional business write summary JSON path.")
    parser.add_argument("--daily-report", help="Optional Markdown daily report path.")
    parser.add_argument("--smoke-summary", help="Optional real-date smoke summary JSON path.")
    parser.add_argument("--data-snapshot-id", help="Optional data_snapshot id.")
    parser.add_argument("--research-report-id", help="Optional research_reports id.")
    parser.add_argument("--output", help="Output package JSON path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    package = generate_llm_input_package(
        calculated_input_path=args.calculated_input,
        quality_report_path=args.quality_report,
        evidence_list_path=args.evidence_list,
        business_write_summary_path=args.business_write_summary,
        daily_report_path=args.daily_report,
        smoke_summary_path=args.smoke_summary,
        output_path=args.output,
        data_snapshot_id=args.data_snapshot_id,
        research_report_id=args.research_report_id,
    )
    output_path = Path(args.output) if args.output else build_default_output_path(str(package["report_date"]))
    print(f"llm_input_package_path: {_display_path(output_path)}")
    print(f"overall_status: {package['pipeline_status']['overall_status']}")
    print(f"evidence_items: {len(package['evidence_items'])}")
    return 0


def _build_field_facts(fields: dict[str, Any], quality_by_field: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for field_name in sorted(fields):
        if field_name in CALCULATED_FIELDS:
            continue
        payload = fields.get(field_name)
        if not isinstance(payload, dict):
            continue
        metadata = _clean_metadata(payload.get("metadata", {}))
        source_status = _resolved_status(field_name, metadata, quality_by_field, default="unknown")
        usage_note = _field_usage_note(metadata, source_status)
        facts.append(
            {
                "field": field_name,
                "value": payload.get("value"),
                "unit": metadata.get("unit"),
                "date": metadata.get("date") or metadata.get("data_time"),
                "source_name": metadata.get("source_name"),
                "source_level": metadata.get("source_level"),
                "source_status": source_status,
                "confidence": metadata.get("confidence", "unknown"),
                "metadata": metadata,
                "quality_status": quality_by_field.get(field_name, {}).get("source_status", "unknown"),
                "llm_usage_note": usage_note,
            }
        )
    return facts


def _build_calculated_indicators(
    fields: dict[str, Any],
    quality_by_field: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    indicators: list[dict[str, Any]] = []
    for field_name in sorted(CALCULATED_FIELDS):
        payload = fields.get(field_name)
        if not isinstance(payload, dict):
            continue
        metadata = _clean_metadata(payload.get("metadata", {}))
        source_status = _resolved_status(field_name, metadata, quality_by_field, default="unknown")
        note = "Calculated indicator only; do not infer causal explanation without supporting evidence."
        if metadata.get("calculation_method") == "manual_override":
            source_status = "warning"
            note += " Manual override calculation requires human review."
        if metadata.get("fallback_used") is True or metadata.get("data_alignment_note"):
            source_status = "warning"
            note += " Source data contains fallback or date-alignment warnings."
        indicators.append(
            {
                "field": field_name,
                "value": payload.get("value"),
                "unit": metadata.get("unit"),
                "calculation_method": metadata.get("calculation_method", "unknown"),
                "calculation_version": metadata.get("calculation_version", "unknown"),
                "source_fields": metadata.get("calculation_inputs", []),
                "source_status": source_status,
                "confidence": metadata.get("confidence", "unknown"),
                "data_alignment_note": metadata.get("data_alignment_note"),
                "metadata": metadata,
                "llm_usage_note": note,
            }
        )
    return indicators


def _build_evidence_items(evidence_report: dict[str, Any] | None, notes: list[str]) -> list[dict[str, Any]]:
    if evidence_report is None:
        notes.append("evidence_list not provided; evidence_items is empty.")
        return []
    items = evidence_report.get("evidence_list", [])
    if not isinstance(items, list):
        notes.append("evidence_list payload is invalid; evidence_items is empty.")
        return []
    preserved_keys = [
        "evidence_id",
        "evidence_type",
        "field",
        "source_name",
        "source_level",
        "source_status",
        "confidence",
        "data_time",
        "publish_time",
        "raw_value",
        "normalized_value",
        "unit",
        "related_variable",
        "conclusion_impact",
        "url_or_reference",
    ]
    evidence_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        evidence_item = {key: item.get(key) for key in preserved_keys}
        evidence_item["evidence_scope"] = "field_level"
        evidence_item["llm_usage_note"] = FIELD_LEVEL_EVIDENCE_NOTE
        evidence_items.append(evidence_item)
    return evidence_items


def _build_quality_constraints(quality_report: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    overall_status = str(quality_report.get("overall_status") or "unknown")
    warnings = _as_list(quality_report.get("warnings"))
    errors = _as_list(quality_report.get("errors"))
    field_results = quality_report.get("field_results", [])
    if not isinstance(field_results, list):
        field_results = []

    failed_fields: list[str] = []
    warning_fields: list[str] = []
    for result in field_results:
        if not isinstance(result, dict):
            continue
        field_name = result.get("field")
        if not field_name:
            continue
        if result.get("source_status") == "fail":
            failed_fields.append(str(field_name))
        if result.get("source_status") == "warning":
            warning_fields.append(str(field_name))

    placeholder_checks = [
        str(item)
        for item in warnings + errors
        if "source_conflict_check" in str(item) or "revision_check" in str(item)
    ]
    normal_allowed = overall_status != "fail"
    constraints = {
        "warnings": warnings,
        "errors": errors,
        "failed_fields": failed_fields,
        "warning_fields": warning_fields,
        "stale_or_fallback_fields": _stale_or_fallback_fields(fields),
        "placeholder_checks": placeholder_checks,
        "normal_market_explanation_allowed": normal_allowed,
        "reason": "overall_status is fail" if not normal_allowed else "",
        "conclusion_strength_cap": "none" if not normal_allowed else (
            "low_to_medium" if overall_status == "warning" else "medium"
        ),
    }
    return constraints


def _build_business_persistence(business_summary: dict[str, Any] | None, notes: list[str]) -> dict[str, Any]:
    if business_summary is None:
        note = "business summary not provided; zero counts do not imply attempted writes"
        notes.append(note)
        return {
            "provided": False,
            "write_business_tables_requested": False,
            "market_prices_written": 0,
            "fx_rates_written": 0,
            "spreads_written": 0,
            "evidence_written": 0,
            "counts": {
                "market_prices": 0,
                "fx_rates": 0,
                "spread_table": 0,
                "evidence_database": 0,
            },
            "warnings": [],
            "errors": [],
            "note": note,
        }
    return {
        "provided": True,
        "write_business_tables_requested": True,
        "market_prices_written": _to_int(business_summary.get("market_prices_written")),
        "fx_rates_written": _to_int(business_summary.get("fx_rates_written")),
        "spreads_written": _to_int(business_summary.get("spreads_written")),
        "evidence_written": _to_int(business_summary.get("evidence_written")),
        "counts": {
            "market_prices": _to_int(business_summary.get("market_prices_written")),
            "fx_rates": _to_int(business_summary.get("fx_rates_written")),
            "spread_table": _to_int(business_summary.get("spreads_written")),
            "evidence_database": _to_int(business_summary.get("evidence_written")),
        },
        "warnings": _as_list(business_summary.get("warnings")),
        "errors": _as_list(business_summary.get("errors")),
        "note": "",
    }


def _allowed_reasoning_scope() -> dict[str, Any]:
    return {
        "can_use_evidence_only": True,
        "can_reference_field_values": True,
        "can_generate_candidate_explanation": True,
        "can_generate_trading_signal": False,
        "can_invent_missing_causes": False,
        "can_override_quality_status": False,
        "must_state_uncertainty": True,
        "must_respect_warning_fields": True,
        "must_not_treat_field_level_evidence_as_conclusion_level_evidence": True,
        "can_do": [
            "summarize_verified_facts",
            "explain_data_changes",
            "identify_contradictions",
            "draft_daily_report_with_caveats",
        ],
        "must_reference": [
            "field_facts",
            "calculated_indicators",
            "evidence_items",
            "quality_constraints",
        ],
        "must_respect": [
            "overall_status",
            "source_status",
            "confidence",
            "fallback_used",
            "data_alignment_note",
        ],
    }


def _source_status_summary(field_facts: list[dict[str, Any]], indicators: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"pass": 0, "warning": 0, "fail": 0, "unknown": 0}
    for item in field_facts + indicators:
        status = str(item.get("source_status") or "unknown")
        if status not in summary:
            status = "unknown"
        summary[status] += 1
    return summary


def _business_write_status(business_summary: dict[str, Any] | None) -> dict[str, Any]:
    if business_summary is None:
        return {"provided": False, "write_business_tables_requested": False}
    return {
        "provided": True,
        "write_business_tables_requested": True,
        "warnings": _as_list(business_summary.get("warnings")),
        "errors": _as_list(business_summary.get("errors")),
    }


def _daily_report_info(path: str | Path | None, notes: list[str]) -> dict[str, Any]:
    if path is None:
        notes.append("daily_report not provided; Markdown preview is unavailable.")
        return {"exists": False, "preview": ""}
    final_path = Path(path)
    if not final_path.exists():
        notes.append(f"daily_report missing: {_display_path(final_path)}")
        return {"exists": False, "preview": ""}
    text = final_path.read_text(encoding="utf-8")
    return {"exists": True, "preview": text[:500]}


def _resolve_report_date(quality_report: dict[str, Any], calculated_input: dict[str, Any]) -> tuple[str, str]:
    if quality_report.get("report_date"):
        return str(quality_report["report_date"]), "quality_report.report_date"
    if calculated_input.get("report_date"):
        return str(calculated_input["report_date"]), "calculated_input.report_date"
    return "UNKNOWN_DATE", "unknown"


def _quality_by_field(quality_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = quality_report.get("field_results", [])
    if not isinstance(results, list):
        return {}
    mapped: dict[str, dict[str, Any]] = {}
    for result in results:
        if isinstance(result, dict) and result.get("field"):
            mapped[str(result["field"])] = result
    return mapped


def _resolved_status(
    field_name: str,
    metadata: dict[str, Any],
    quality_by_field: dict[str, dict[str, Any]],
    default: str,
) -> str:
    status = metadata.get("source_status") or quality_by_field.get(field_name, {}).get("source_status") or default
    return str(status)


def _field_usage_note(metadata: dict[str, Any], source_status: str) -> str:
    notes = ["Use as structured field fact only; do not infer market direction from this field alone."]
    if source_status == "warning":
        notes.append("Field is warning-status and requires caveated use.")
    if metadata.get("fallback_used") is True or metadata.get("data_alignment_note"):
        notes.append("Field used fallback or has data alignment limitations.")
    if metadata.get("pending_manual_review") is True:
        notes.append("Field is pending manual review.")
    return " ".join(notes)


def _stale_or_fallback_fields(fields: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for field_name, payload in fields.items():
        if not isinstance(payload, dict):
            continue
        metadata = payload.get("metadata", {})
        if isinstance(metadata, dict) and (metadata.get("fallback_used") is True or metadata.get("data_alignment_note")):
            names.append(str(field_name))
    return sorted(names)


def _clean_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    return _omit_raw_payload(metadata)


def _omit_raw_payload(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, nested in value.items():
            if key == "raw_payload":
                cleaned["raw_payload_omitted"] = True
            else:
                cleaned[key] = _omit_raw_payload(nested)
        return cleaned
    if isinstance(value, list):
        return [_omit_raw_payload(item) for item in value]
    return value


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return payload


def _load_optional_json(path: str | Path | None, label: str, notes: list[str]) -> dict[str, Any] | None:
    if path is None:
        return None
    final_path = Path(path)
    if not final_path.exists():
        notes.append(f"{label} not found: {_display_path(final_path)}")
        return None
    return _load_json(final_path)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional_display_path(path: str | Path | None) -> str | None:
    return _display_path(path) if path is not None else None


def _display_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    raise SystemExit(main())
