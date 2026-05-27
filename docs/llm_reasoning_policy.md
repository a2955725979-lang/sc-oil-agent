# LLM Reasoning Policy

v0.8.2 defines a deterministic reasoning policy for future price-estimation and daily-report assistance. It does not call an LLM, does not run an Agent, and does not import LangGraph.

The policy consumes existing `llm_input_package_v1` files. It does not change that schema. In particular, the package field `forbidden_outputs` remains unchanged; `src/llm/reasoning_policy.py` maps it to the clearer policy name `forbidden_trading_instruction_terms`.

## Public Functions

```python
validate_llm_input_package(package: dict) -> dict
build_reasoning_context(package: dict) -> dict
validate_llm_draft_output(draft: dict, package: dict) -> dict
```

These functions only validate and reshape deterministic data. They never create new facts, causes, trading instructions, final directional conclusions, or market advice.

## Package Validation

`validate_llm_input_package` checks:

- `schema_version == "llm_input_package_v1"`
- required top-level sections are present
- `allowed_reasoning_scope.can_generate_trading_signal` is `false`
- `allowed_reasoning_scope.must_not_treat_field_level_evidence_as_conclusion_level_evidence` is `true`
- `langgraph_handoff.agent_execution_allowed` is `false`
- `forbidden_outputs` includes core trading-instruction terms such as `buy`, `sell`, `买入`, and `卖出`

`overall_status == "fail"` blocks normal reasoning. Smoke status `red` also blocks reasoning. Smoke status `unknown`, missing business persistence, missing evidence, and stale / fallback fields create warnings.

## Reasoning Context

`build_reasoning_context` returns a compact context for future nodes:

- `report_date`
- `overall_status`
- `allowed_draft_types`
- `prohibited_draft_types`
- `normal_market_explanation_allowed`
- `field_facts_by_name`
- `calculated_indicators_by_name`
- `field_level_evidence_by_field`
- `quality_constraints`
- `business_persistence`
- `forbidden_trading_instruction_terms`
- `required_caveats`
- `policy_warnings`

The context is only a safer view of existing package data. It is not an interpretation engine.

## Draft Validation

`validate_llm_draft_output` validates a hypothetical future draft object. It does not generate one.

Allowed draft types:

- `price_estimate_range`
- `spread_explanation`
- `market_structure_description`
- `uncertainty_summary`
- `risk_challenge`

Prohibited draft types:

- `trading_instruction`
- `position_sizing`
- `guaranteed_direction`
- `unsupported_causal_claim`

Drafts fail if they contain trading-instruction terms, set `contains_trading_signal: true`, include a non-empty `prohibited_final_conclusion`, reference unknown evidence IDs, or attempt normal explanation when package quality has failed.

## Evidence Boundary

Evidence remains field-level only:

```text
These evidence items support field availability and source traceability only. They do not independently support directional market conclusions.
```

Future LLM or LangGraph layers must not treat field-level evidence as conclusion-level evidence.

## Boundaries

- No LLM call.
- No Agent.
- No LangGraph import.
- No trading instruction.
- No position sizing.
- No final directional conclusion.
- No invented missing causes.
- No schema migration.
- No changes to validation, reporting, evidence generation, business table writing, or smoke-test behavior.
