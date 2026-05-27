# LangGraph Design Preparation

v0.8.2 prepares declarative contracts for a future LangGraph workflow. It does not add LangGraph as a dependency and does not create a running graph.

The future graph should consume `llm_input_package_v1` through the deterministic policy layer in `src/llm/reasoning_policy.py`.

## Future Nodes

The prepared contracts cover:

- `DataQualityReader`
- `EvidenceReader`
- `MarketContextDraft`
- `RiskChallenge`
- `HumanReviewGate`
- `ReportDraftRefiner`

Contracts live in `src/llm/langgraph_contracts.py` as plain dictionaries. Prompt templates live in `src/llm/prompt_templates.py` as static strings.

## Node Contract Shape

Each contract includes:

- `node_name`
- `input_sections`
- `output_shape`
- `allowed_draft_types`
- `prohibited_draft_types`
- `may_generate`
- `must_not_generate`
- `requires_human_review`
- `policy_checks`

The contracts are intentionally declarative. They are not executable graph nodes.

## Allowed Outputs

Future nodes may draft:

- price estimate ranges with caveats
- spread explanations based on structured fields
- market structure descriptions
- uncertainty summaries
- risk challenges for human review

These are draft artifacts only and must remain subject to policy validation.

## Prohibited Outputs

Future nodes must not produce:

- trading instructions
- position sizing
- final directional conclusions
- guaranteed direction
- unsupported causal claims
- conclusion-level use of field-level evidence

## Evidence Boundary

All future prompts and contracts must preserve this rule:

```text
These evidence items support field availability and source traceability only. They do not independently support directional market conclusions.
```

## Future Integration Notes

When LangGraph is added later, each node should:

1. Read the reasoning context built by `build_reasoning_context`.
2. Produce a draft object with an allowed `draft_type`.
3. Run `validate_llm_draft_output`.
4. Route failures to `HumanReviewGate`.
5. Never bypass `quality_constraints`, warning fields, fallback fields, or evidence-scope limits.

v0.8.2 stops before that runtime integration.
