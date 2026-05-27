"""Declarative future LangGraph node contracts.

These contracts are plain data. They do not import LangGraph or execute agents.
"""

from __future__ import annotations

from typing import Any

from src.llm.reasoning_policy import (
    ALLOWED_DRAFT_TYPES,
    FIELD_LEVEL_EVIDENCE_NOTE,
    PROHIBITED_DRAFT_TYPES,
)


FUTURE_NODE_NAMES = [
    "DataQualityReader",
    "EvidenceReader",
    "MarketContextDraft",
    "RiskChallenge",
    "HumanReviewGate",
    "ReportDraftRefiner",
]


def build_node_contracts() -> dict[str, dict[str, Any]]:
    """Return deterministic contracts for future LangGraph nodes."""

    return {name: _contract(name) for name in FUTURE_NODE_NAMES}


def _contract(node_name: str) -> dict[str, Any]:
    return {
        "node_name": node_name,
        "input_sections": [
            "pipeline_status",
            "field_facts",
            "calculated_indicators",
            "evidence_items",
            "quality_constraints",
            "business_persistence",
            "allowed_reasoning_scope",
        ],
        "output_shape": {
            "draft_type": "one of allowed_draft_types",
            "claims": "list[dict]",
            "caveats": "list[str]",
            "uses_evidence_ids": "list[str]",
            "contains_trading_signal": False,
            "prohibited_final_conclusion": None,
        },
        "allowed_draft_types": list(ALLOWED_DRAFT_TYPES),
        "prohibited_draft_types": list(PROHIBITED_DRAFT_TYPES),
        "may_generate": [
            "field summaries",
            "price estimate range drafts with caveats",
            "spread explanation drafts with cited structured facts",
            "uncertainty summaries",
            "risk challenges for human review",
        ],
        "must_not_generate": [
            "trading signals",
            "position sizing",
            "final directional conclusions",
            "guaranteed direction",
            "unsupported causal claims",
            "conclusion-level use of field-level evidence",
        ],
        "requires_human_review": True,
        "policy_checks": [
            "validate_llm_input_package",
            "validate_llm_draft_output",
            "forbidden_trading_instruction_terms",
            "field_level_evidence_only",
            FIELD_LEVEL_EVIDENCE_NOTE,
        ],
    }


NODE_CONTRACTS = build_node_contracts()
