"""Deterministic reasoning policy for future LLM/LangGraph consumers.

The functions in this module validate and reshape existing llm_input_package_v1
data. They do not call an LLM, run LangGraph, or generate market conclusions.
"""

from __future__ import annotations

from typing import Any


PACKAGE_SCHEMA_VERSION = "llm_input_package_v1"
FIELD_LEVEL_EVIDENCE_NOTE = (
    "These evidence items support field availability and source traceability only. "
    "They do not independently support directional market conclusions."
)
ALLOWED_DRAFT_TYPES = [
    "price_estimate_range",
    "spread_explanation",
    "market_structure_description",
    "uncertainty_summary",
    "risk_challenge",
]
PROHIBITED_DRAFT_TYPES = [
    "trading_instruction",
    "position_sizing",
    "guaranteed_direction",
    "unsupported_causal_claim",
]
CORE_FORBIDDEN_TRADING_TERMS = ["buy", "sell", "买入", "卖出"]
EXTRA_DIRECTIONAL_TERMS = [
    "must rise",
    "must fall",
    "guaranteed profit",
    "稳赚",
    "必涨",
    "必跌",
]
REQUIRED_TOP_LEVEL_KEYS = [
    "schema_version",
    "report_date",
    "pipeline_status",
    "field_facts",
    "calculated_indicators",
    "evidence_items",
    "quality_constraints",
    "business_persistence",
    "allowed_reasoning_scope",
    "forbidden_outputs",
    "langgraph_handoff",
]


def validate_llm_input_package(package: dict) -> dict:
    """Validate llm_input_package_v1 guardrails for future reasoning use."""

    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(package, dict):
        return _validation_result(
            status="fail",
            errors=["package must be an object"],
            warnings=[],
            allowed_for_reasoning=False,
            normal_market_explanation_allowed=False,
            forbidden_terms=[],
        )

    _validate_required_package_shape(package, errors)
    forbidden_terms = _forbidden_terms(package)
    _validate_policy_guardrails(package, forbidden_terms, errors)

    overall_status = _overall_status(package)
    smoke_status = _smoke_status(package)
    constraints = package.get("quality_constraints", {})
    if not isinstance(constraints, dict):
        constraints = {}

    if overall_status == "fail":
        errors.append("overall_status is fail; normal reasoning is blocked")
    elif overall_status == "warning":
        warnings.append("overall_status is warning; future reasoning must include caveats")
    elif overall_status not in {"pass", "warning", "fail"}:
        warnings.append(f"overall_status is unknown or unsupported: {overall_status}")

    if smoke_status == "red":
        errors.append("smoke_acceptance_status is red; package is not allowed for reasoning")
    elif smoke_status == "unknown":
        warnings.append("smoke_acceptance_status is unknown")

    business = package.get("business_persistence", {})
    if not isinstance(business, dict) or business.get("provided") is not True:
        warnings.append("business persistence summary is absent or not provided")

    evidence_items = package.get("evidence_items", [])
    if not isinstance(evidence_items, list) or not evidence_items:
        warnings.append("evidence_items is absent or empty")

    stale_fields = constraints.get("stale_or_fallback_fields", [])
    if isinstance(stale_fields, list) and stale_fields:
        warnings.append("stale or fallback fields are present: " + ", ".join(str(item) for item in stale_fields))

    normal_market_explanation_allowed = bool(constraints.get("normal_market_explanation_allowed", True))
    if overall_status == "fail" or smoke_status == "red":
        normal_market_explanation_allowed = False

    return _validation_result(
        status="fail" if errors else "warning" if warnings else "pass",
        errors=errors,
        warnings=warnings,
        allowed_for_reasoning=not errors,
        normal_market_explanation_allowed=normal_market_explanation_allowed,
        forbidden_terms=forbidden_terms,
    )


def build_reasoning_context(package: dict) -> dict:
    """Build a compact, policy-aware context for future deterministic handoff."""

    validation = validate_llm_input_package(package)
    field_facts = package.get("field_facts", []) if isinstance(package, dict) else []
    indicators = package.get("calculated_indicators", []) if isinstance(package, dict) else []
    evidence_items = package.get("evidence_items", []) if isinstance(package, dict) else []

    return {
        "report_date": package.get("report_date") if isinstance(package, dict) else None,
        "overall_status": _overall_status(package) if isinstance(package, dict) else "unknown",
        "allowed_draft_types": list(ALLOWED_DRAFT_TYPES),
        "prohibited_draft_types": list(PROHIBITED_DRAFT_TYPES),
        "normal_market_explanation_allowed": validation["normal_market_explanation_allowed"],
        "field_facts_by_name": _items_by_key(field_facts, "field"),
        "calculated_indicators_by_name": _items_by_key(indicators, "field"),
        "field_level_evidence_by_field": _evidence_by_field(evidence_items),
        "quality_constraints": package.get("quality_constraints", {}) if isinstance(package, dict) else {},
        "business_persistence": package.get("business_persistence", {}) if isinstance(package, dict) else {},
        "forbidden_trading_instruction_terms": validation["forbidden_trading_instruction_terms"],
        "required_caveats": _required_caveats(package, validation),
        "policy_warnings": validation["warnings"],
        "policy_errors": validation["errors"],
        "allowed_for_reasoning": validation["allowed_for_reasoning"],
    }


def validate_llm_draft_output(draft: dict, package: dict) -> dict:
    """Validate a future draft object against deterministic policy rules."""

    errors: list[str] = []
    warnings: list[str] = []
    package_validation = validate_llm_input_package(package)
    if package_validation["status"] == "fail":
        errors.append("package validation failed; draft reasoning is blocked")

    if not isinstance(draft, dict):
        return {
            "status": "fail",
            "errors": ["draft must be an object"],
            "warnings": warnings,
            "allowed": False,
        }

    draft_type = str(draft.get("draft_type") or "")
    if draft_type in PROHIBITED_DRAFT_TYPES:
        errors.append(f"draft_type is prohibited: {draft_type}")
    elif draft_type not in ALLOWED_DRAFT_TYPES:
        errors.append(f"draft_type is not allowed: {draft_type}")

    if draft.get("contains_trading_signal") is True:
        errors.append("draft contains a trading signal")
    if draft.get("prohibited_final_conclusion"):
        errors.append("prohibited_final_conclusion must be empty")

    draft_text = _draft_text(draft)
    for term in package_validation["forbidden_trading_instruction_terms"] + EXTRA_DIRECTIONAL_TERMS:
        if _contains_term(draft_text, term):
            errors.append(f"draft contains forbidden trading-instruction term: {term}")

    unknown_ids = sorted(set(_as_str_list(draft.get("uses_evidence_ids"))) - _known_evidence_ids(package))
    if unknown_ids:
        errors.append("draft references unknown evidence_ids: " + ", ".join(unknown_ids))

    if package_validation["normal_market_explanation_allowed"] is False and _attempts_normal_explanation(draft):
        errors.append("normal market explanation is not allowed for this package")

    if draft.get("uses_evidence_ids") and not _draft_acknowledges_field_level_scope(draft_text):
        warnings.append("draft uses evidence IDs without acknowledging field-level-only evidence scope")

    if _uses_warning_or_fallback_fields(draft, package) and not _has_caveats(draft):
        warnings.append("draft uses warning or fallback fields without caveats")

    return {
        "status": "fail" if errors else "warning" if warnings else "pass",
        "errors": errors,
        "warnings": warnings,
        "allowed": not errors,
    }


def _validation_result(
    status: str,
    errors: list[str],
    warnings: list[str],
    allowed_for_reasoning: bool,
    normal_market_explanation_allowed: bool,
    forbidden_terms: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "allowed_for_reasoning": allowed_for_reasoning,
        "normal_market_explanation_allowed": normal_market_explanation_allowed,
        "field_level_evidence_only": True,
        "forbidden_trading_instruction_terms": forbidden_terms,
    }


def _validate_required_package_shape(package: dict, errors: list[str]) -> None:
    if package.get("schema_version") != PACKAGE_SCHEMA_VERSION:
        errors.append("schema_version must be llm_input_package_v1")
    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in package:
            errors.append(f"missing top-level section: {key}")


def _validate_policy_guardrails(package: dict, forbidden_terms: list[str], errors: list[str]) -> None:
    scope = package.get("allowed_reasoning_scope", {})
    if not isinstance(scope, dict):
        errors.append("allowed_reasoning_scope must be an object")
    else:
        if scope.get("can_generate_trading_signal") is not False:
            errors.append("allowed_reasoning_scope.can_generate_trading_signal must be false")
        if scope.get("must_not_treat_field_level_evidence_as_conclusion_level_evidence") is not True:
            errors.append(
                "allowed_reasoning_scope.must_not_treat_field_level_evidence_as_conclusion_level_evidence must be true"
            )

    handoff = package.get("langgraph_handoff", {})
    if not isinstance(handoff, dict):
        errors.append("langgraph_handoff must be an object")
    elif handoff.get("agent_execution_allowed") is not False:
        errors.append("langgraph_handoff.agent_execution_allowed must be false")

    if not forbidden_terms:
        errors.append("forbidden_outputs must be present")
        return
    missing = [term for term in CORE_FORBIDDEN_TRADING_TERMS if term not in forbidden_terms]
    if missing:
        errors.append("forbidden_outputs missing core trading-instruction terms: " + ", ".join(missing))


def _required_caveats(package: dict, validation: dict) -> list[str]:
    caveats: list[str] = []
    if validation["status"] == "warning":
        caveats.append("State uncertainty and preserve all warning-status limitations.")
    constraints = package.get("quality_constraints", {}) if isinstance(package, dict) else {}
    if isinstance(constraints, dict) and constraints.get("stale_or_fallback_fields"):
        caveats.append("Mention stale/fallback fields and data-alignment limits.")
    if package.get("evidence_items") if isinstance(package, dict) else False:
        caveats.append(FIELD_LEVEL_EVIDENCE_NOTE)
    return caveats


def _overall_status(package: dict) -> str:
    pipeline_status = package.get("pipeline_status", {})
    if isinstance(pipeline_status, dict):
        return str(pipeline_status.get("overall_status") or "unknown")
    return "unknown"


def _smoke_status(package: dict) -> str:
    pipeline_status = package.get("pipeline_status", {})
    if isinstance(pipeline_status, dict):
        return str(pipeline_status.get("smoke_acceptance_status") or "unknown")
    return "unknown"


def _forbidden_terms(package: dict) -> list[str]:
    terms = package.get("forbidden_outputs", [])
    return [str(term) for term in terms] if isinstance(terms, list) else []


def _items_by_key(items: Any, key: str) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, dict) and item.get(key):
            result[str(item[key])] = dict(item)
    return result


def _evidence_by_field(items: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(items, list):
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        if isinstance(item, dict) and item.get("field"):
            result.setdefault(str(item["field"]), []).append(dict(item))
    return result


def _known_evidence_ids(package: dict) -> set[str]:
    evidence = package.get("evidence_items", []) if isinstance(package, dict) else []
    if not isinstance(evidence, list):
        return set()
    return {str(item["evidence_id"]) for item in evidence if isinstance(item, dict) and item.get("evidence_id")}


def _draft_text(draft: dict) -> str:
    parts: list[str] = []
    for key in ("draft_type", "prohibited_final_conclusion", "summary", "text"):
        value = draft.get(key)
        if value is not None:
            parts.append(str(value))
    for claim in draft.get("claims", []) if isinstance(draft.get("claims"), list) else []:
        parts.append(str(claim))
    for caveat in draft.get("caveats", []) if isinstance(draft.get("caveats"), list) else []:
        parts.append(str(caveat))
    return "\n".join(parts)


def _contains_term(text: str, term: str) -> bool:
    return term.lower() in text.lower()


def _attempts_normal_explanation(draft: dict) -> bool:
    return bool(draft.get("claims") or draft.get("summary") or draft.get("text"))


def _draft_acknowledges_field_level_scope(text: str) -> bool:
    lowered = text.lower()
    return "field-level" in lowered or "field level" in lowered or "字段级" in lowered


def _uses_warning_or_fallback_fields(draft: dict, package: dict) -> bool:
    used_fields = set(_as_str_list(draft.get("uses_fields")))
    if not used_fields:
        return False
    constraints = package.get("quality_constraints", {}) if isinstance(package, dict) else {}
    if not isinstance(constraints, dict):
        return False
    warning_fields = set(_as_str_list(constraints.get("warning_fields")))
    stale_fields = set(_as_str_list(constraints.get("stale_or_fallback_fields")))
    return bool(used_fields & (warning_fields | stale_fields))


def _has_caveats(draft: dict) -> bool:
    caveats = draft.get("caveats", [])
    return isinstance(caveats, list) and bool(caveats)


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
