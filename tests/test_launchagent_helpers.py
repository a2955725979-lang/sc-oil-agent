"""Offline tests for LaunchAgent helper scripts.

Run from the project root:
    python tests/test_launchagent_helpers.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALL_PATH = PROJECT_ROOT / "scripts" / "install_launchagent.py"
UNINSTALL_PATH = PROJECT_ROOT / "scripts" / "uninstall_launchagent.py"
sys.path.insert(0, str(PROJECT_ROOT))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


install = load_module("install_launchagent", INSTALL_PATH)
uninstall = load_module("uninstall_launchagent", UNINSTALL_PATH)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(text: str, fragment: str, message: str) -> None:
    if fragment not in text:
        raise AssertionError(f"{message}: {fragment!r} not found")


def make_python(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    return path


def test_template_rendering_replaces_placeholders() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        python_path = make_python(root / "venv" / "bin" / "python")
        rendered = install.render_plist(root, python_path, hour=18, minute=30)

    assert_contains(rendered, str(root), "project root rendered")
    assert_contains(rendered, str(python_path), "python executable rendered")
    assert_contains(rendered, "<integer>18</integer>", "hour rendered")
    assert_contains(rendered, "<integer>30</integer>", "minute rendered")
    assert_equal("{{PROJECT_ROOT}}" in rendered, False, "project placeholder removed")
    assert_equal("{{PYTHON_EXECUTABLE}}" in rendered, False, "python placeholder removed")


def test_invalid_hour_minute_and_missing_python_fail() -> None:
    for hour, minute in [(-1, 30), (24, 30), (18, -1), (18, 60)]:
        try:
            install.validate_time(hour, minute)
        except install.LaunchAgentInstallError:
            pass
        else:
            raise AssertionError(f"invalid time should fail: {hour}:{minute}")
    try:
        install.validate_python_executable("/tmp/sc-oil-agent-missing-python")
    except install.LaunchAgentInstallError:
        pass
    else:
        raise AssertionError("missing python executable should fail")


def test_install_dry_run_does_not_write_or_create_dirs() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        python_path = make_python(root / "bin" / "python")
        plist_path = root / "LaunchAgents" / "com.sc-oil-agent.daily.plist"
        args = install.parse_args(
            [
                "--project-root",
                str(root),
                "--python-executable",
                str(python_path),
                "--plist-output",
                str(plist_path),
                "--dry-run",
            ]
        )
        result = install.install_launchagent(args)

        assert_equal(result["dry_run"], True, "dry-run marker")
        assert_equal(plist_path.exists(), False, "dry-run plist absent")
        assert_equal((root / "logs" / "launchd").exists(), False, "dry-run logs absent")
        assert_equal((root / ".runtime").exists(), False, "dry-run runtime absent")


def test_install_writes_plist_and_runtime_dirs() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        python_path = make_python(root / "bin" / "python")
        plist_path = root / "LaunchAgents" / "com.sc-oil-agent.daily.plist"
        args = install.parse_args(
            [
                "--project-root",
                str(root),
                "--python-executable",
                str(python_path),
                "--plist-output",
                str(plist_path),
            ]
        )
        install.install_launchagent(args)
        rendered = plist_path.read_text(encoding="utf-8")

        assert_equal(plist_path.exists(), True, "plist written")
        assert_equal((root / "logs" / "launchd").exists(), True, "logs dir")
        assert_equal((root / ".runtime").exists(), True, "runtime dir")
        assert_contains(rendered, f"{root}/scripts/run_scheduled_daily.py", "absolute script path")
        assert_contains(rendered, "logs/launchd/sc-oil-agent.daily.out.log", "stdout path")
        assert_contains(rendered, "logs/launchd/sc-oil-agent.daily.err.log", "stderr path")
        assert_contains(rendered, "--init-db", "init db arg")
        assert_contains(rendered, "--lock-timeout-minutes", "lock timeout arg")
        assert_equal("--replace" in rendered, False, "replace absent by default")


def test_uninstall_dry_run_preserves_plist() -> None:
    with TemporaryDirectory() as tmp:
        plist_path = Path(tmp) / "com.sc-oil-agent.daily.plist"
        plist_path.write_text("plist", encoding="utf-8")
        args = uninstall.parse_args(["--plist-path", str(plist_path), "--dry-run"])
        uninstall.uninstall_launchagent(args)
        assert_equal(plist_path.exists(), True, "dry-run preserves plist")


def test_uninstall_removes_plist_with_mocked_launchctl() -> None:
    with TemporaryDirectory() as tmp:
        plist_path = Path(tmp) / "com.sc-oil-agent.daily.plist"
        plist_path.write_text("plist", encoding="utf-8")
        calls: list[list[str]] = []
        original = uninstall.run_launchctl

        def fake_run_launchctl(command: list[str], check: bool):
            calls.append(command)
            return None

        uninstall.run_launchctl = fake_run_launchctl
        try:
            args = uninstall.parse_args(["--plist-path", str(plist_path)])
            uninstall.uninstall_launchagent(args)
        finally:
            uninstall.run_launchctl = original

    assert_equal(plist_path.exists(), False, "plist removed")
    assert_equal(calls[0][0:2], ["launchctl", "unload"], "launchctl unload called")


def run() -> None:
    tests = [
        test_template_rendering_replaces_placeholders,
        test_invalid_hour_minute_and_missing_python_fail,
        test_install_dry_run_does_not_write_or_create_dirs,
        test_install_writes_plist_and_runtime_dirs,
        test_uninstall_dry_run_preserves_plist,
        test_uninstall_removes_plist_with_mocked_launchctl,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
