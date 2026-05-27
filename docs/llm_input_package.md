# LLM Input Package

v0.8.1 adds `llm_input_package_v1`, a deterministic JSON boundary between the local Python pipeline and any future LangGraph / LLM layer.

This package does not call an LLM, does not run an Agent, does not create trading signals, and does not generate market conclusions. It only repackages existing structured artifacts so a future reasoning layer can read facts, quality constraints, and evidence boundaries safely.

## Command

```bash
python src/llm/generate_llm_input_package.py \
  --calculated-input data/processed/calculated_input_YYYY-MM-DD.json \
  --quality-report data/processed/quality_report_YYYY-MM-DD.json \
  --evidence-list data/processed/evidence_list_YYYY-MM-DD.json \
  --business-write-summary data/processed/business_write_summary_YYYY-MM-DD.json \
  --daily-report reports/daily/SC_daily_YYYY-MM-DD.md \
  --smoke-summary data/processed/real_date_smoke_summary_YYYY-MM-DD.json \
  --data-snapshot-id SNAP-YYYYMMDD-001 \
  --research-report-id RPT-YYYYMMDD-SC-DAILY-001 \
  --output data/processed/llm_input_package_YYYY-MM-DD.json
```

If `--output` is omitted, the default is:

```text
data/processed/llm_input_package_YYYY-MM-DD.json
```

The date comes from `quality_report.report_date` first, then `calculated_input.report_date`.

## Schema Overview

The top-level package includes:

- `schema_version: "llm_input_package_v1"`
- `report_date`
- `package_created_at`
- `data_snapshot_id`
- `research_report_id`
- `pipeline_status`
- `inputs`
- `field_facts`
- `calculated_indicators`
- `evidence_items`
- `quality_constraints`
- `business_persistence`
- `allowed_reasoning_scope`
- `forbidden_outputs`
- `langgraph_handoff`
- `notes`

`field_facts` contains non-calculated fields from `calculated_input.fields`. `calculated_indicators` contains only calculated spread / conversion fields such as `SC_USD`, `SC_calendar_spread`, `SC_Brent_spread_simple`, and `SC_WTI_spread_simple`.

Large `raw_payload` metadata is omitted and replaced with `raw_payload_omitted: true` to keep the package compact.

## Evidence Boundary

Evidence remains field-level only. Each evidence item is marked:

```json
{
  "evidence_scope": "field_level",
  "llm_usage_note": "These evidence items support field availability and source traceability only. They do not independently support directional market conclusions."
}
```

Future LangGraph or LLM nodes must not treat field-level evidence as conclusion-level evidence.

## Quality Constraints

The package preserves:

- `overall_status`
- quality warnings and errors
- failed fields
- warning fields
- stale or fallback fields
- placeholder checks such as `source_conflict_check` and `revision_check`

If `overall_status == "fail"`, `quality_constraints.normal_market_explanation_allowed` is `false`, and future LLM layers must not generate a normal market explanation.

If `overall_status == "warning"`, normal explanation is allowed only with caveats and `conclusion_strength_cap: "low_to_medium"`.

## Business Persistence

If `business_write_summary` is provided, row counts and write warnings are preserved.

If it is absent, zero counts mean “not provided / not attempted,” not “attempted and wrote zero rows.” The package records:

```json
{
  "provided": false,
  "write_business_tables_requested": false,
  "note": "business summary not provided; zero counts do not imply attempted writes"
}
```

## Future LangGraph Handoff

The package recommends future nodes such as:

- `DataQualityReader`
- `EvidenceReader`
- `MarketContextDraft`
- `RiskChallenge`
- `HumanReviewGate`
- `ReportDraftRefiner`

Current v0.8.1 remains LLM-free and Agent-free. No LangGraph execution is added yet.

## Boundaries

- No Agent.
- No LangGraph execution yet.
- No LLM call.
- No trading advice.
- No invented missing causes.
- No causal explanation unless supporting evidence exists.
- No override of quality status.
