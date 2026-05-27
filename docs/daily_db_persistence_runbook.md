# Daily DB Persistence Runbook

This runbook covers v0.7 daily-frequency persistence from Auto Daily Preflight into SQLite business tables. It proves the operational path, but it does not add scheduling, real-time streaming, trading signals, Agent behavior, LLM interpretation, or new providers.

## What It Writes

When `--write-business-tables` is explicitly enabled, the pipeline writes:

- `data_snapshot`
- `research_reports`
- `market_prices`
- `fx_rates`
- `spread_table`
- `evidence_database`

The execution order is fixed:

```text
run_auto_daily.py
→ raw_data
→ daily_input
→ calculated_input
→ quality_report
→ data_snapshot
→ evidence_list
→ Markdown report
→ research_reports
→ business tables
```

`evidence_database` is written only after the referenced `research_reports` and `data_snapshot` rows are ready. Evidence remains field-level evidence; no conclusion-level evidence is generated.

## Mode A: Reproducible Local Run

Use this mode for acceptance testing and personal replay. It requires local raw input files and does not require live network access.

```bash
python src/pipeline/run_auto_daily.py \
  --report-date YYYY-MM-DD \
  --akshare-raw-input path/to/akshare_raw.json \
  --market-fx-raw-input path/to/market_fx_raw.json \
  --write-business-tables \
  --business-write-summary-output data/processed/business_write_summary_YYYY-MM-DD.json \
  --init-db
```

Recommended deterministic form:

```bash
python src/pipeline/run_auto_daily.py \
  --report-date YYYY-MM-DD \
  --akshare-raw-input data/raw/akshare_sc_YYYY-MM-DD.json \
  --market-fx-raw-input data/raw/market_fx_YYYY-MM-DD.json \
  --report-id RPT-YYYYMMDD-SC-DAILY-001 \
  --replace \
  --write-business-tables \
  --business-write-summary-output data/processed/business_write_summary_YYYY-MM-DD.json \
  --init-db
```

Use `--report-id` with `--replace` for repeatable daily replays. Business table writes are idempotent through table uniqueness constraints and upsert logic, so repeated runs update existing business rows instead of multiplying them.

## Mode B: Live Auto Run

Use this only as a manual smoke test when local dependencies and provider access are available.

```bash
python src/pipeline/run_auto_daily.py \
  --report-date YYYY-MM-DD \
  --write-business-tables \
  --business-write-summary-output data/processed/business_write_summary_YYYY-MM-DD.json \
  --init-db
```

Mode B may fail or warn because live providers are free/public and can be stale, unavailable, rate-limited, or misaligned with holidays and trading sessions. Yahoo/yfinance is a free public convenience provider, not an official exchange source or terminal-grade data source.

For v0.7.1 real-date smoke validation, use `docs/real_date_smoke_test_runbook.md` and the helper command:

```bash
python scripts/run_real_date_smoke.py --report-date YYYY-MM-DD --init-db
```

## Summary Audit

The business write summary is the row-count audit trail. It includes:

```json
{
  "market_prices_written": 0,
  "fx_rates_written": 0,
  "spreads_written": 0,
  "evidence_written": 0,
  "core_tables_written": true,
  "evidence_database_written": true,
  "research_report_id": "...",
  "data_snapshot_id": "...",
  "warnings": [],
  "errors": []
}
```

Review `warnings` and `errors` after every run. A warning run can still write business tables, but source status and quality warnings must remain visible in artifacts.

## Fail Quality Policy

If `quality_report.overall_status == "fail"`:

- the fail Markdown report is written;
- the `research_reports` row is written for review;
- `data_snapshot` is not written;
- `market_prices`, `fx_rates`, and `spread_table` are not written by default;
- `evidence_database` is written only if an Evidence List exists and FK readiness passes.

Do not use fail-quality output as market history unless the standalone writer is intentionally run with `--allow-fail-write`.

## Scope Boundaries

This is daily persistence, not intraday streaming. It does not generate trading signals, does not interpret news, does not run an Agent or LLM, and does not change the SQLite schema.
