"""Static prompt templates for future LLM nodes.

These are inert strings for design and testing. This module does not import or
call any LLM, Agent, or LangGraph runtime.
"""

from __future__ import annotations

from src.llm.langgraph_contracts import FUTURE_NODE_NAMES
from src.llm.reasoning_policy import FIELD_LEVEL_EVIDENCE_NOTE


BASE_GUARDRAILS = f"""
You are consuming deterministic llm_input_package_v1 context.
Do not provide trading instructions, position sizing, or final directional conclusions.
Do not invent missing causes.
Respect overall_status, source_status, confidence, fallback_used, and data_alignment_note.
{FIELD_LEVEL_EVIDENCE_NOTE}
Allowed draft types: price_estimate_range, spread_explanation, market_structure_description, uncertainty_summary, risk_challenge.
Prohibited draft types: trading_instruction, position_sizing, guaranteed_direction, unsupported_causal_claim.
""".strip()


def data_quality_reader_template() -> str:
    return _template("DataQualityReader", "Summarize quality constraints, failed fields, warning fields, and required caveats.")


def evidence_reader_template() -> str:
    return _template("EvidenceReader", "Summarize field-level evidence availability and source traceability only.")


def market_context_draft_template() -> str:
    return _template("MarketContextDraft", "Draft caveated price-estimate or market-structure context from verified fields only.")


def risk_challenge_template() -> str:
    return _template("RiskChallenge", "Identify uncertainty, stale fields, unsupported claims, and human-review blockers.")


def human_review_gate_template() -> str:
    return _template("HumanReviewGate", "List what a human reviewer must approve before any downstream narrative is used.")


def report_draft_refiner_template() -> str:
    return _template("ReportDraftRefiner", "Refine caveated wording without adding new facts or directional conclusions.")


def build_prompt_templates() -> dict[str, str]:
    return {
        "DataQualityReader": data_quality_reader_template(),
        "EvidenceReader": evidence_reader_template(),
        "MarketContextDraft": market_context_draft_template(),
        "RiskChallenge": risk_challenge_template(),
        "HumanReviewGate": human_review_gate_template(),
        "ReportDraftRefiner": report_draft_refiner_template(),
    }


def _template(node_name: str, task: str) -> str:
    if node_name not in FUTURE_NODE_NAMES:
        raise ValueError(f"unknown future node: {node_name}")
    return f"""
Node: {node_name}
Task: {task}

Guardrails:
{BASE_GUARDRAILS}

Output must be a draft object compatible with validate_llm_draft_output.
contains_trading_signal must be false.
prohibited_final_conclusion must be null.
""".strip()
