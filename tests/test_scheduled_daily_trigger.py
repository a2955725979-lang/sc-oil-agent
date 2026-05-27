"""Offline tests for scripts/run_scheduled_daily.py.

Run from the project root:
    python tests/test_scheduled_daily_trigger.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_scheduled_daily.py"
sys.path.insert(0, str(PROJECT_ROOT))

spec = importlib.util.spec_from_file_location("run_scheduled_daily", SCRIPT_PATH)
scheduled = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(scheduled)

REPORT_DATE = "2026-05-22"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(items, expected, message: str) -> None:
    if expected not in items:
        raise AssertionError(f"{message}: {expected!r} not found in {items!r}")


def assert_text_contains(text: str, fragment: str, message: str) -> None:
    if fragment not in text:
        raise AssertionError(f"{message}: {fragment!r} not found in {text!r}")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_default_report_date_and_id_generation() -> None:
    shanghai_now = datetime(2026, 5, 22, 9, 0, tzinfo=scheduled.ZoneInfo("Asia/Shanghai"))
    assert_equal(scheduled.default_report_date(shanghai_now), REPORT_DATE, "default report date")
    assert_equal(
        scheduled.default_report_id(REPORT_DATE),
        "RPT-20260522-SC-DAILY-SCHEDULED",
        "default scheduled report id",
    )


def test_run_auto_daily_args_include_required_flags_and_pass_through() -> None:
    args = scheduled.parse_args(
        [
            "--report-date",
            REPORT_DATE,
            "--db",
            "/tmp/sc_oil.sqlite",
            "--config",
            "/tmp/config.yaml",
            "--dictionary",
            "/tmp/dictionary.yaml",
            "--replace",
            "--init-db",
        ]
    )
    artifacts = scheduled.build_artifact_paths(REPORT_DATE, project_root=Path("/tmp/sc-oil-agent"))
    run_args = scheduled.build_run_auto_daily_args(args, REPORT_DATE, "RPT-SCHEDULED", artifacts)

    assert_contains(run_args, "--write-business-tables", "business table flag")
    assert_contains(run_args, "--generate-llm-input-package", "LLM package flag")
    assert_contains(run_args, "--business-write-summary-output", "business summary output flag")
    assert_contains(run_args, "--llm-input-package-output", "LLM output flag")
    assert_contains(run_args, "--replace", "replace pass-through")
    assert_contains(run_args, "--init-db", "init-db pass-through")
    assert_equal(run_args[run_args.index("--db") + 1], "/tmp/sc_oil.sqlite", "db pass-through")
    assert_equal(run_args[run_args.index("--config") + 1], "/tmp/config.yaml", "config pass-through")
    assert_equal(run_args[run_args.index("--dictionary") + 1], "/tmp/dictionary.yaml", "dictionary pass-through")


def test_lock_file_contains_audit_metadata_and_releases() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        lock_path = root / "scheduled.lock"
        result = scheduled.acquire_lock(
            lock_path=lock_path,
            report_date=REPORT_DATE,
            command=["--report-date", REPORT_DATE],
            timeout_minutes=120,
            force_unlock=False,
        )
        payload = load_json(lock_path)
        scheduled.release_lock(lock_path, result["lock_id"])
        exists_after_release = lock_path.exists()

    assert_equal(result["acquired"], True, "lock acquired")
    assert_equal(payload["lock_id"], result["lock_id"], "lock id")
    assert_equal(payload["report_date"], REPORT_DATE, "lock report date")
    assert_equal(payload["command"], ["--report-date", REPORT_DATE], "lock command")
    assert_equal("pid" in payload, True, "lock pid")
    assert_equal("started_at" in payload, True, "lock started_at")
    assert_equal(exists_after_release, False, "lock released")


def test_failed_lock_acquirer_does_not_delete_existing_owner_lock() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        lock_path = root / "scheduled.lock"
        owner = scheduled.acquire_lock(
            lock_path=lock_path,
            report_date=REPORT_DATE,
            command=["process-a"],
            timeout_minutes=120,
            force_unlock=False,
        )
        owner_payload = load_json(lock_path)
        contender = scheduled.acquire_lock(
            lock_path=lock_path,
            report_date=REPORT_DATE,
            command=["process-b"],
            timeout_minutes=120,
            force_unlock=False,
        )
        scheduled.release_lock(lock_path, contender.get("lock_id"))
        payload_after_contender_exit = load_json(lock_path)
        scheduled.release_lock(lock_path, owner["lock_id"])
        exists_after_owner_release = lock_path.exists()

    assert_equal(owner["acquired"], True, "owner acquired")
    assert_equal(contender["acquired"], False, "contender blocked")
    assert_equal(payload_after_contender_exit, owner_payload, "owner lock preserved")
    assert_equal(exists_after_owner_release, False, "owner can release")


def test_active_lock_exits_with_scheduler_guard_code() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        lock_path = root / "scheduled.lock"
        summary_path = root / "scheduled_summary.json"
        write_json(
            lock_path,
            {
                "pid": 123,
                "report_date": REPORT_DATE,
                "started_at": scheduled.utc_now_iso(),
                "command": ["existing"],
            },
        )
        exit_code = scheduled.main(
            [
                "--report-date",
                REPORT_DATE,
                "--lock-path",
                str(lock_path),
                "--summary-output",
                str(summary_path),
            ]
        )
        summary = load_json(summary_path)
        lock_exists = lock_path.exists()

    assert_equal(exit_code, scheduled.EXIT_SCHEDULER_GUARD, "active lock exit")
    assert_equal(lock_exists, True, "active lock preserved")
    assert_text_contains("; ".join(summary["errors"]), "active scheduler lock", "active lock error")


def test_stale_lock_requires_force_unlock_and_preserves_lock_without_it() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        lock_path = root / "scheduled.lock"
        summary_path = root / "scheduled_summary.json"
        stale_started = (datetime.now(timezone.utc) - timedelta(minutes=180)).isoformat()
        write_json(
            lock_path,
            {
                "pid": 123,
                "report_date": REPORT_DATE,
                "started_at": stale_started,
                "command": ["existing"],
            },
        )
        exit_code = scheduled.main(
            [
                "--report-date",
                REPORT_DATE,
                "--lock-path",
                str(lock_path),
                "--summary-output",
                str(summary_path),
                "--lock-timeout-minutes",
                "120",
            ]
        )
        summary = load_json(summary_path)
        lock_exists = lock_path.exists()

    assert_equal(exit_code, scheduled.EXIT_SCHEDULER_GUARD, "stale lock without force exit")
    assert_equal(lock_exists, True, "stale lock preserved")
    assert_text_contains("; ".join(summary["warnings"]), "stale scheduler lock detected", "stale lock warning")
    assert_text_contains("; ".join(summary["errors"]), "--force-unlock", "force unlock error")


def test_stale_lock_with_force_unlock_runs_and_preserves_exit_code() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        lock_path = root / "scheduled.lock"
        summary_path = root / "scheduled_summary.json"
        artifacts = scheduled.build_artifact_paths(REPORT_DATE, summary_output=summary_path, project_root=root)
        stale_started = (datetime.now(timezone.utc) - timedelta(minutes=180)).isoformat()
        captured_args: list[str] = []
        write_json(
            lock_path,
            {
                "pid": 123,
                "report_date": REPORT_DATE,
                "started_at": stale_started,
                "command": ["existing"],
            },
        )

        original_main = scheduled.run_auto_daily.main
        original_build_artifact_paths = scheduled.build_artifact_paths

        def fake_build_artifact_paths(report_date, summary_output=None, project_root=scheduled.PROJECT_ROOT):
            assert_equal(report_date, REPORT_DATE, "fake report date")
            return artifacts

        def fake_run_auto_daily(run_args: list[str]) -> int:
            captured_args.extend(run_args)
            write_json(artifacts["quality_report"], {"overall_status": "warning"})
            write_json(artifacts["business_write_summary"], {"market_prices_written": 1})
            write_json(artifacts["llm_input_package"], {"schema_version": "llm_input_package_v1"})
            artifacts["daily_report"].parent.mkdir(parents=True, exist_ok=True)
            artifacts["daily_report"].write_text("# Daily report\n", encoding="utf-8")
            return 2

        scheduled.run_auto_daily.main = fake_run_auto_daily
        scheduled.build_artifact_paths = fake_build_artifact_paths
        try:
            exit_code = scheduled.main(
                [
                    "--report-date",
                    REPORT_DATE,
                    "--lock-path",
                    str(lock_path),
                    "--summary-output",
                    str(summary_path),
                    "--force-unlock",
                ]
            )
        finally:
            scheduled.run_auto_daily.main = original_main
            scheduled.build_artifact_paths = original_build_artifact_paths

        summary = load_json(summary_path)

    assert_equal(exit_code, 2, "run_auto_daily exit code preserved")
    assert_equal(lock_path.exists(), False, "lock cleaned after run")
    assert_contains(captured_args, "--write-business-tables", "business flag captured")
    assert_contains(captured_args, "--generate-llm-input-package", "LLM flag captured")
    assert_equal(summary["schema_version"], "scheduled_daily_summary_v1", "summary schema")
    assert_equal(summary["trigger_mode"], "scheduled_trigger", "trigger mode")
    assert_equal(summary["exit_code"], 2, "summary exit")
    assert_equal(summary["exit_code_meaning"], "controlled_data_or_quality_failure", "summary exit meaning")
    assert_equal(summary["overall_status"], "warning", "summary quality status")
    assert_text_contains("; ".join(summary["warnings"]), "stale scheduler lock removed", "force unlock warning")


def test_summary_shape_for_missing_artifacts() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        artifacts = scheduled.build_artifact_paths(REPORT_DATE, project_root=root)
        summary = scheduled.build_scheduled_summary(
            report_date=REPORT_DATE,
            report_id="RPT-SCHEDULED",
            started_at=scheduled.utc_now_iso(),
            exit_code=0,
            run_args=["--report-date", REPORT_DATE],
            artifacts=artifacts,
            warnings=[],
            errors=[],
        )

    expected_keys = {
        "schema_version",
        "trigger_mode",
        "report_date",
        "report_id",
        "started_at",
        "finished_at",
        "duration_seconds",
        "exit_code",
        "exit_code_meaning",
        "run_auto_daily_args",
        "artifact_paths",
        "overall_status",
        "business_write_summary_path",
        "llm_input_package_path",
        "warnings",
        "errors",
    }
    assert_equal(set(summary), expected_keys, "scheduled summary keys")
    assert_equal(summary["trigger_mode"], "scheduled_trigger", "trigger mode")
    assert_text_contains("; ".join(summary["warnings"]), "artifact missing", "missing artifact warnings")


def run() -> None:
    tests = [
        test_default_report_date_and_id_generation,
        test_run_auto_daily_args_include_required_flags_and_pass_through,
        test_lock_file_contains_audit_metadata_and_releases,
        test_failed_lock_acquirer_does_not_delete_existing_owner_lock,
        test_active_lock_exits_with_scheduler_guard_code,
        test_stale_lock_requires_force_unlock_and_preserves_lock_without_it,
        test_stale_lock_with_force_unlock_runs_and_preserves_exit_code,
        test_summary_shape_for_missing_artifacts,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
