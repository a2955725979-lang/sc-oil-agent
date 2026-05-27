# Local Scheduler v1.0 Runbook

v1.0 uses macOS LaunchAgent as the first supported local scheduler. The LaunchAgent calls:

```bash
.venv/bin/python scripts/run_scheduled_daily.py
```

This is daily-frequency automation, not intraday streaming. It does not call an LLM, run an Agent, generate trading signals, or generate automatic final directional conclusions.

## Important Environment Note

macOS LaunchAgent runs with a minimal environment and may not inherit your Terminal shell, conda/base activation, or custom `PATH`.

Recommended local project environment:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Get the repository path:

```bash
pwd
```

For the local `.venv`, pass:

```text
/absolute/path/to/sc-oil-agent/.venv/bin/python
```

or a conda environment path such as:

```text
/Users/xxx/miniconda3/envs/xxx/bin/python
```

## Dry Run

```bash
python scripts/install_launchagent.py \
  --project-root "$(pwd)" \
  --python-executable "$(pwd)/.venv/bin/python" \
  --dry-run
```

Dry run renders the plist preview and prints next steps without writing files or creating runtime directories.

## Install

```bash
python scripts/install_launchagent.py \
  --project-root "$(pwd)" \
  --python-executable "$(pwd)/.venv/bin/python" \
  --hour 18 \
  --minute 30
```

The default LaunchAgent path is:

```text
~/Library/LaunchAgents/com.sc-oil-agent.daily.plist
```

The default schedule is 18:30 local machine time. Because launchd uses local machine time, set the Mac timezone correctly for the intended Asia/Shanghai-style schedule.

The installer creates:

- `logs/launchd/`
- `.runtime/`

It does not require sudo and does not write to `/Library/LaunchDaemons`.

If you use `--label`, it changes the LaunchAgent service label. Custom plist file names or log paths should still be provided explicitly with the relevant helper options or template changes.

## Load And Unload

```bash
launchctl load ~/Library/LaunchAgents/com.sc-oil-agent.daily.plist
```

```bash
launchctl unload ~/Library/LaunchAgents/com.sc-oil-agent.daily.plist
```

You can also ask the helper to load after rendering:

```bash
python scripts/install_launchagent.py \
  --project-root "$(pwd)" \
  --python-executable "$(pwd)/.venv/bin/python" \
  --hour 18 \
  --minute 30 \
  --load
```

## Logs

```bash
tail -f logs/launchd/sc-oil-agent.daily.out.log
```

```bash
tail -f logs/launchd/sc-oil-agent.daily.err.log
```

## Manual One-Off Run

Same-day reruns with the default scheduled report ID may fail unless `--replace` is used. That is intentional safety behavior to avoid silent replacement.

For local debugging:

```bash
python scripts/run_scheduled_daily.py \
  --report-date YYYY-MM-DD \
  --replace \
  --init-db
```

## Health Check

```bash
python scripts/check_scheduled_daily_health.py --report-date YYYY-MM-DD
```

Health check exit codes:

| Code | Meaning |
| --- | --- |
| 0 | green |
| 1 | red |
| 2 | yellow |

It checks scheduled summary, business summary, DB rows, LLM input package, and daily report.

## Scheduled Trigger Exit Codes

| Code | Meaning |
| --- | --- |
| 0 | success or warning-quality accepted |
| 1 | program or environment error |
| 2 | controlled data or quality failure |
| 3 | scheduler guard failure |

## Lock Handling

Default lock:

```text
.runtime/scheduled_daily.lock
```

If a lock exists, inspect it before forcing unlock. It contains `pid`, `report_date`, `started_at`, and command details.

The scheduled trigger creates the lock atomically and records an owner token. A process that fails to acquire the lock will not delete another process's lock during cleanup.

Use `--force-unlock` only after verifying no scheduled run is still active:

```bash
python scripts/run_scheduled_daily.py \
  --report-date YYYY-MM-DD \
  --force-unlock \
  --init-db
```

## Uninstall

```bash
python scripts/uninstall_launchagent.py
```

This unloads and removes the user plist by default. It does not delete logs, database files, reports, or processed outputs.

To unload but keep the plist:

```bash
python scripts/uninstall_launchagent.py --keep-plist
```

## Rollback

1. Unload the LaunchAgent.
2. Run `python scripts/uninstall_launchagent.py`.
3. Keep logs, DB, reports, and summaries for debugging.

No schema rollback is needed because v1.0 does not change the database.
