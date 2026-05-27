"""Tests for deterministic LLM reasoning policy.

Run from the project root:
    python tests/test_reasoning_policy.py
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.llm.reasoning_policy import (  # noqa: E402
    FIELD_LEVEL_EVIDENCE_NOTE,
    build_reasoning_context,
    validate_llm_draft_output,
    validate_llm_input_package,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(items, expected, message: str) -> None:
    if expected not in items:
        raise AssertionError(f"{message}: {expected!r} not found in {items!r}")


def assert_text_contains(text: str, fragment: str, message: str) -> None:
    if fragment not in text:
        raise AssertionError(f"{message}: {fragment!r} not found in {text!r}")


def valid_package() -> dict:
    return {
        "schema_version": "llm_input_package_v1",
        "report_date": "2026-05-22",
        "package_created_at": "2026-05-22T00:00:00+00:00",
        "data_snapshot_id": "SNAP-TEST",
        "research_report_id": "RPT-TEST",
        "pipeline_status": {
            "report_date": "2026-05-22",
            "overall_status": "pass",
            "smoke_acceptance_status": "green",
        },
        "inputs": {},
        "field_facts": [
            {
                "field": "SC_close",
                "value": 620.5,
                "source_status": "pass",
                "confidence": "medium",
                "metadata": {},
            },
            {
                "field": "USD_CNY",
                "value": 7.18,
                "source_status": "warning",
                "confidence": "low",
                "metadata": {"fallback_used": True},
            },
        ],
        "calculated_indicators": [
            {
                "field": "SC_Brent_spread_simple",
                "value": 4.02,
                "source_status": "pass",
                "confidence": "medium",
            }
        ],
        "evidence_items": [
            {
                "evidence_id": "EVID-001",
                "field": "SC_close",
                "evidence_scope": "field_level",
                "llm_usage_note": FIELD_LEVEL_EVIDENCE_NOTE,
            }
        ],
        "quality_constraints": {
            "warnings": [],
            "errors": [],
            "failed_fields": [],
            "warning_fields": ["USD_CNY"],
            "stale_or_fallback_fields": ["USD_CNY"],
            "placeholder_checks": [],
            "normal_market_explanation_allowed": True,
        },
        "business_persistence": {"provided": True},
        "allowed_reasoning_scope": {
            "can_generate_trading_signal": False,
            "can_invent_missing_causes": False,
            "must_not_treat_field_level_evidence_as_conclusion_level_evidence": True,
        },
        "forbidden_outputs": ["buy", "sell", "must rise", "must fall", "买入", "卖出"],
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
        "notes": [],
    }


def valid_draft() -> dict:
    return {
        "draft_type": "price_estimate_range",
        "claims": [{"field": "SC_close", "text": "SC_close is available as a field-level fact."}],
        "caveats": ["Uses field-level evidence only and respects warning fields."],
        "uses_fields": ["SC_close"],
        "uses_evidence_ids": ["EVID-001"],
        "contains_trading_signal": False,
        "prohibited_final_conclusion": None,
    }


def test_valid_package_warns_for_fallback_but_allows_reasoning() -> None:
    result = validate_llm_input_package(valid_package())
    assert_equal(result["status"], "warning", "fallback package status")
    assert_equal(result["allowed_for_reasoning"], True, "reasoning allowed")
    assert_contains(result["forbidden_trading_instruction_terms"], "buy", "forbidden term mapping")
    assert_text_contains("; ".join(result["warnings"]), "stale or fallback", "fallback warning")


def test_missing_schema_or_required_sections_fail() -> None:
    package = valid_package()
    package["schema_version"] = "bad"
    del package["field_facts"]
    result = validate_llm_input_package(package)
    assert_equal(result["status"], "fail", "bad schema fails")
    assert_text_contains("; ".join(result["errors"]), "schema_version", "schema error")
    assert_text_contains("; ".join(result["errors"]), "field_facts", "missing section error")


def test_missing_core_forbidden_terms_fails() -> None:
    package = valid_package()
    package["forbidden_outputs"] = ["must rise"]
    result = validate_llm_input_package(package)
    assert_equal(result["status"], "fail", "missing forbidden trading terms fails")
    assert_text_contains("; ".join(result["errors"]), "missing core trading-instruction terms", "forbidden term error")


def test_fail_quality_and_smoke_red_block_reasoning() -> None:
    fail_package = valid_package()
    fail_package["pipeline_status"]["overall_status"] = "fail"
    fail_result = validate_llm_input_package(fail_package)
    assert_equal(fail_result["status"], "fail", "quality fail package fails")
    assert_equal(fail_result["allowed_for_reasoning"], False, "quality fail blocks reasoning")
    assert_equal(fail_result["normal_market_explanation_allowed"], False, "quality fail blocks normal explanation")

    smoke_package = valid_package()
    smoke_package["pipeline_status"]["smoke_acceptance_status"] = "red"
    smoke_result = validate_llm_input_package(smoke_package)
    assert_equal(smoke_result["status"], "fail", "smoke red fails")
    assert_equal(smoke_result["allowed_for_reasoning"], False, "smoke red blocks reasoning")


def test_smoke_unknown_and_missing_business_warn_only() -> None:
    package = valid_package()
    package["pipeline_status"]["smoke_acceptance_status"] = "unknown"
    package["business_persistence"] = {"provided": False}
    result = validate_llm_input_package(package)
    assert_equal(result["status"], "warning", "unknown smoke warns")
    assert_text_contains("; ".join(result["warnings"]), "smoke_acceptance_status is unknown", "smoke warning")
    assert_text_contains("; ".join(result["warnings"]), "business persistence", "business warning")


def test_build_reasoning_context_maps_sections() -> None:
    context = build_reasoning_context(valid_package())
    assert_equal(context["overall_status"], "pass", "context status")
    assert_contains(context["allowed_draft_types"], "price_estimate_range", "allowed draft type")
    assert_contains(context["prohibited_draft_types"], "trading_instruction", "prohibited draft type")
    assert_equal(context["field_facts_by_name"]["SC_close"]["value"], 620.5, "field facts by name")
    assert_equal(context["field_level_evidence_by_field"]["SC_close"][0]["evidence_id"], "EVID-001", "evidence by field")
    assert_contains(context["forbidden_trading_instruction_terms"], "卖出", "mapped forbidden terms")


def test_valid_caveated_draft_passes() -> None:
    result = validate_llm_draft_output(valid_draft(), valid_package())
    assert_equal(result["status"], "pass", "valid draft")
    assert_equal(result["allowed"], True, "valid draft allowed")


def test_draft_type_and_trading_terms_fail() -> None:
    package = valid_package()
    for draft_type in ["trading_instruction", "position_sizing", "guaranteed_direction"]:
        draft = valid_draft()
        draft["draft_type"] = draft_type
        result = validate_llm_draft_output(draft, package)
        assert_equal(result["status"], "fail", f"{draft_type} fails")

    draft = valid_draft()
    draft["claims"] = [{"text": "buy now"}]
    result = validate_llm_draft_output(draft, package)
    assert_equal(result["status"], "fail", "forbidden term fails")
    assert_text_contains("; ".join(result["errors"]), "buy", "buy term error")


def test_draft_final_conclusion_unknown_evidence_and_signal_fail() -> None:
    draft = valid_draft()
    draft["contains_trading_signal"] = True
    draft["prohibited_final_conclusion"] = "SC must rise"
    draft["uses_evidence_ids"] = ["MISSING-EVID"]
    result = validate_llm_draft_output(draft, valid_package())
    assert_equal(result["status"], "fail", "multiple draft violations fail")
    errors = "; ".join(result["errors"])
    assert_text_contains(errors, "trading signal", "signal error")
    assert_text_contains(errors, "prohibited_final_conclusion", "final conclusion error")
    assert_text_contains(errors, "unknown evidence_ids", "unknown evidence error")


def test_draft_with_warning_field_without_caveat_warns() -> None:
    draft = valid_draft()
    draft["uses_fields"] = ["USD_CNY"]
    draft["uses_evidence_ids"] = []
    draft["caveats"] = []
    result = validate_llm_draft_output(draft, valid_package())
    assert_equal(result["status"], "warning", "warning field without caveat warns")
    assert_text_contains("; ".join(result["warnings"]), "without caveats", "caveat warning")


def test_field_level_evidence_misuse_warns() -> None:
    draft = valid_draft()
    draft["claims"] = [{"field": "SC_close", "text": "SC_close is available."}]
    draft["caveats"] = ["Some caveat without the required evidence-scope wording."]
    result = validate_llm_draft_output(draft, valid_package())
    assert_equal(result["status"], "warning", "field-level evidence misuse warns")
    assert_text_contains("; ".join(result["warnings"]), "field-level-only", "field level warning")


def test_fail_package_blocks_normal_draft() -> None:
    package = deepcopy(valid_package())
    package["pipeline_status"]["overall_status"] = "fail"
    result = validate_llm_draft_output(valid_draft(), package)
    assert_equal(result["status"], "fail", "fail package blocks normal draft")
    assert_text_contains("; ".join(result["errors"]), "package validation failed", "package validation error")


def run() -> None:
    tests = [
        test_valid_package_warns_for_fallback_but_allows_reasoning,
        test_missing_schema_or_required_sections_fail,
        test_missing_core_forbidden_terms_fails,
        test_fail_quality_and_smoke_red_block_reasoning,
        test_smoke_unknown_and_missing_business_warn_only,
        test_build_reasoning_context_maps_sections,
        test_valid_caveated_draft_passes,
        test_draft_type_and_trading_terms_fail,
        test_draft_final_conclusion_unknown_evidence_and_signal_fail,
        test_draft_with_warning_field_without_caveat_warns,
        test_field_level_evidence_misuse_warns,
        test_fail_package_blocks_normal_draft,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
