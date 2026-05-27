# Scheduler Trigger Runbook

v0.9 Step 0 adds a scheduler-safe trigger wrapper:

```bash
.venv/bin/python scripts/run_scheduled_daily.py --init-db
```

This script is not a scheduler daemon. It does not install cron jobs, LaunchAgents, GitHub Actions, or background services. External schedulers may call it.

For actual macOS local unattended scheduling with LaunchAgent helpers, see `docs/local_scheduler_runbook.md`.

The trigger runs the existing Auto Daily path with:

- business table writing enabled
- LLM input package generation enabled
- scheduled summary output enabled
- JSON lock protection enabled

It does not call an LLM, run an Agent, generate trading signals, generate final directional conclusions, or perform intraday streaming.

## Local Command

```bash
.venv/bin/python scripts/run_scheduled_daily.py \
  --report-date YYYY-MM-DD \
  --init-db
```

Same-day reruns use the default scheduled report ID:

```text
RPT-YYYYMMDD-SC-DAILY-SCHEDULED
```

If that report already exists, rerunning without `--replace` may fail. That is intentional safety behavior, not a bug. For local debugging:

```bash
.venv/bin/python scripts/run_scheduled_daily.py \
  --report-date YYYY-MM-DD \
  --replace \
  --init-db
```

Whether a production scheduler should use `--replace` is an operational decision. Leaving it off protects existing reports from silent replacement.

## Outputs

Default outputs include:

- `data/processed/business_write_summary_YYYY-MM-DD.json`
- `data/processed/llm_input_package_YYYY-MM-DD.json`
- `data/processed/scheduled_daily_summary_YYYY-MM-DD.json`
- existing Auto Daily artifacts such as quality report, evidence list, daily report, data snapshot, research report, and business table rows

The scheduled summary uses:

```json
{
  "schema_version": "scheduled_daily_summary_v1",
  "trigger_mode": "scheduled_trigger",
  "report_date": "YYYY-MM-DD",
  "report_id": "RPT-YYYYMMDD-SC-DAILY-SCHEDULED",
  "exit_code": 0,
  "exit_code_meaning": "success_or_warning_quality",
  "warnings": [],
  "errors": []
}
```

## Lock File

The default lock path is:

```text
.runtime/scheduled_daily.lock
```

The lock stores:

```json
{
  "pid": 12345,
  "report_date": "YYYY-MM-DD",
  "started_at": "...",
  "command": ["--report-date", "YYYY-MM-DD"]
}
```

Default timeout is 120 minutes:

```bash
.venv/bin/python scripts/run_scheduled_daily.py --lock-timeout-minutes 120
```

If the lock is younger than the timeout, the trigger exits with scheduler guard code `3`. If the lock is older than the timeout, it is reported as stale but is not deleted automatically. To remove a stale lock and run:

```bash
.venv/bin/python scripts/run_scheduled_daily.py \
  --report-date YYYY-MM-DD \
  --force-unlock \
  --init-db
```

## Cron Example

This example runs on weekdays at 18:30 local machine time. Adjust paths and environment activation as needed:

```cron
30 18 * * 1-5 cd /path/to/sc-oil-agent && /path/to/sc-oil-agent/.venv/bin/python scripts/run_scheduled_daily.py --init-db >> logs/scheduled_daily.log 2>&1
```

## macOS launchd Reference

No plist is installed by this repository. A LaunchAgent can call the same command:

```bash
cd /path/to/sc-oil-agent
/path/to/sc-oil-agent/.venv/bin/python scripts/run_scheduled_daily.py --init-db
```

Keep `WorkingDirectory` set to the repository root if you create a plist manually.

## Exit Codes

| Code | Meaning |
| --- | --- |
| 0 | Auto Daily completed with pass / warning quality. |
| 1 | Program or environment error. |
| 2 | Controlled data or quality failure. |
| 3 | Scheduler trigger guard failure, usually lock-related. |

Live providers may be stale or unavailable. Failures should remain explicit; the trigger must not fabricate market/fx or inventory data.

## Boundaries

- No scheduler daemon is added.
- No cron or launchd installer is added.
- No Agent or LLM call.
- No trading signal.
- No automatic final directional conclusion.
- No database schema change.
- Daily-frequency persistence only, not intraday streaming.
