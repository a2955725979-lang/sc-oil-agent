"""Tests for future LangGraph contracts and prompt templates.

Run from the project root:
    python tests/test_langgraph_contracts.py
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.llm import prompt_templates  # noqa: E402
from src.llm.langgraph_contracts import FUTURE_NODE_NAMES, NODE_CONTRACTS  # noqa: E402
from src.llm.reasoning_policy import FIELD_LEVEL_EVIDENCE_NOTE  # noqa: E402


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(items, expected, message: str) -> None:
    if expected not in items:
        raise AssertionError(f"{message}: {expected!r} not found in {items!r}")


def assert_text_contains(text: str, fragment: str, message: str) -> None:
    if fragment not in text:
        raise AssertionError(f"{message}: {fragment!r} not found")


def test_every_future_node_has_contract_and_template() -> None:
    templates = prompt_templates.build_prompt_templates()
    assert_equal(set(NODE_CONTRACTS), set(FUTURE_NODE_NAMES), "contract nodes")
    assert_equal(set(templates), set(FUTURE_NODE_NAMES), "template nodes")


def test_contracts_forbid_trading_and_final_directional_conclusions() -> None:
    for node_name, contract in NODE_CONTRACTS.items():
        assert_contains(contract["prohibited_draft_types"], "trading_instruction", f"{node_name} trading type")
        assert_contains(contract["prohibited_draft_types"], "position_sizing", f"{node_name} position type")
        assert_contains(contract["prohibited_draft_types"], "guaranteed_direction", f"{node_name} direction type")
        assert_contains(contract["must_not_generate"], "trading signals", f"{node_name} trading signal")
        assert_contains(contract["must_not_generate"], "final directional conclusions", f"{node_name} final conclusion")
        assert_equal(contract["output_shape"]["contains_trading_signal"], False, f"{node_name} no signal")
        assert_equal(contract["output_shape"]["prohibited_final_conclusion"], None, f"{node_name} no final conclusion")


def test_contracts_include_allowed_types_and_policy_boundaries() -> None:
    for node_name, contract in NODE_CONTRACTS.items():
        assert_contains(contract["allowed_draft_types"], "price_estimate_range", f"{node_name} price estimate")
        assert_contains(contract["allowed_draft_types"], "spread_explanation", f"{node_name} spread explanation")
        assert_contains(contract["input_sections"], "quality_constraints", f"{node_name} quality input")
        assert_contains(contract["input_sections"], "evidence_items", f"{node_name} evidence input")
        assert_contains(contract["policy_checks"], "field_level_evidence_only", f"{node_name} field level policy")
        assert_contains(contract["policy_checks"], FIELD_LEVEL_EVIDENCE_NOTE, f"{node_name} evidence note")


def test_templates_include_required_guardrails() -> None:
    templates = prompt_templates.build_prompt_templates()
    for node_name, template in templates.items():
        assert_text_contains(template, "Do not provide trading instructions", f"{node_name} no trading")
        assert_text_contains(template, "final directional conclusions", f"{node_name} no final conclusion")
        assert_text_contains(template, "Do not invent missing causes", f"{node_name} no invented causes")
        assert_text_contains(template, FIELD_LEVEL_EVIDENCE_NOTE, f"{node_name} evidence boundary")
        assert_text_contains(template, "prohibited_final_conclusion must be null", f"{node_name} output guardrail")


def test_templates_do_not_import_or_call_runtime_llm_or_langgraph() -> None:
    source = inspect.getsource(prompt_templates)
    forbidden_fragments = [
        "import langgraph",
        "from langgraph",
        "openai",
        "ChatOpenAI",
        ".invoke(",
        ".stream(",
    ]
    for fragment in forbidden_fragments:
        assert_equal(fragment in source, False, f"template source must not contain {fragment}")


def run() -> None:
    tests = [
        test_every_future_node_has_contract_and_template,
        test_contracts_forbid_trading_and_final_directional_conclusions,
        test_contracts_include_allowed_types_and_policy_boundaries,
        test_templates_include_required_guardrails,
        test_templates_do_not_import_or_call_runtime_llm_or_langgraph,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
