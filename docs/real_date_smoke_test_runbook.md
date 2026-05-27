# Real-Date Smoke Test Runbook

v0.7.1 validates that real AKShare SC data and real market/fx provider data can flow through Auto Daily Preflight, quality validation, DB persistence, and report generation.

This is a manual smoke test only. It is not CI, not a scheduler, not production automation, and not a trading or research agent.

## Prerequisites

- Install dependencies:

```bash
pip install -r requirements.txt
```

- Use an initialized SQLite DB, or pass `--init-db`.
- Ensure network access is available.
- Expect live provider fragility: AKShare and Yahoo/yfinance may be unavailable, stale, rate-limited, or session/holiday misaligned.
- Remember Yahoo/yfinance is a free public convenience provider, not an official exchange source or terminal-grade data source.

## Mode A: Live Real-Date Smoke

```bash
python scripts/run_real_date_smoke.py --report-date YYYY-MM-DD --init-db
```

The helper script calls the existing Auto Daily workflow with live providers and always enables business table writing. It writes:

```text
data/processed/real_date_smoke_summary_YYYY-MM-DD.json
```

Use an explicit report id and replacement for repeatable manual replay:

```bash
python scripts/run_real_date_smoke.py \
  --report-date YYYY-MM-DD \
  --report-id RPT-YYYYMMDD-SC-DAILY-SMOKE \
  --replace \
  --init-db
```

## Mode B: Deterministic Replay

If raw files already exist, bypass live providers and replay through the existing pipeline:

```bash
python src/pipeline/run_auto_daily.py \
  --report-date YYYY-MM-DD \
  --akshare-raw-input data/raw/akshare_sc_YYYY-MM-DD.json \
  --market-fx-raw-input data/raw/market_fx_YYYY-MM-DD.json \
  --report-id RPT-YYYYMMDD-SC-DAILY-SMOKE \
  --replace \
  --write-business-tables \
  --business-write-summary-output data/processed/business_write_summary_YYYY-MM-DD.json \
  --init-db
```

## Expected Outputs

- `data/raw/akshare_sc_YYYY-MM-DD.json`
- `data/raw/market_fx_YYYY-MM-DD.json`
- `data/manual/daily_input_YYYY-MM-DD.json`
- `data/processed/calculated_input_YYYY-MM-DD.json`
- `data/processed/quality_report_YYYY-MM-DD.json`
- `data/processed/evidence_list_YYYY-MM-DD.json`
- `data/processed/business_write_summary_YYYY-MM-DD.json`
- `data/processed/real_date_smoke_summary_YYYY-MM-DD.json`
- `reports/daily/SC_daily_YYYY-MM-DD.md`
- SQLite rows in `data_snapshot`, `research_reports`, `market_prices`, `fx_rates`, `spread_table`, and `evidence_database`

## Acceptance Criteria

Green:

- exit code `0`
- quality `overall_status` is `pass`
- `business_write_summary` shows nonzero `market_prices_written`, `fx_rates_written`, `spreads_written`, and `evidence_written`
- report file exists

Yellow:

- exit code `0` and quality `overall_status` is `warning`
- stale or latest-available market/fx data is clearly marked
- EIA/default text fields remain warning
- acceptable for v0.7.1 if core DB rows are written

Red:

- exit code `1` program/environment error
- exit code `2` controlled data failure
- no SC rows in `market_prices`
- no USD/CNY row in `fx_rates`
- no spread row in `spread_table`
- any foreign-key readiness error
- any Brent or WTI row in `market_prices`

## Manual SQL Checks

```bash
sqlite3 db/sc_oil_research.sqlite
```

```sql
SELECT COUNT(*) FROM data_snapshot;
SELECT COUNT(*) FROM research_reports;
SELECT COUNT(*) FROM market_prices WHERE symbol='SC';
SELECT COUNT(*) FROM market_prices WHERE symbol IN ('Brent','WTI');
SELECT COUNT(*) FROM fx_rates WHERE pair='USD/CNY';
SELECT COUNT(*) FROM spread_table;
SELECT COUNT(*) FROM evidence_database;
```

`market_prices` should not contain Brent or WTI. Brent and WTI belong in `spread_table` as reference prices.

## Boundaries

This smoke test does not generate trading signals, does not run an LLM or Agent, does not interpret news, does not schedule anything, and does not perform intraday streaming. It only validates daily-frequency live fetch, pipeline processing, report generation, and DB persistence.
