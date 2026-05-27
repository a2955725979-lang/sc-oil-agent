"""Render and optionally load the sc-oil-agent macOS LaunchAgent."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LABEL = "com.sc-oil-agent.daily"
DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "deploy" / "launchd" / "sc-oil-agent.daily.plist.template"


class LaunchAgentInstallError(RuntimeError):
    """Raised when LaunchAgent installation cannot proceed safely."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install the sc-oil-agent user LaunchAgent.")
    parser.add_argument("--project-root", required=True, help="Absolute path to the sc-oil-agent repository.")
    parser.add_argument("--python-executable", required=True, help="Absolute path to the project Python executable.")
    parser.add_argument("--hour", type=int, default=18, help="Local launch hour, 0-23.")
    parser.add_argument("--minute", type=int, default=30, help="Local launch minute, 0-59.")
    parser.add_argument("--label", default=DEFAULT_LABEL, help="LaunchAgent label.")
    parser.add_argument(
        "--plist-output",
        default=str(Path.home() / "Library" / "LaunchAgents" / f"{DEFAULT_LABEL}.plist"),
        help="Rendered LaunchAgent plist path.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Render and print instructions without writing.")
    parser.add_argument("--load", action="store_true", help="Best-effort unload then load the rendered plist.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        result = install_launchagent(parse_args(argv))
    except (LaunchAgentInstallError, OSError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print_install_result(result)
    return 0


def install_launchagent(args: argparse.Namespace) -> dict[str, object]:
    project_root = validate_project_root(args.project_root)
    python_executable = validate_python_executable(args.python_executable)
    validate_time(args.hour, args.minute)
    plist_output = Path(args.plist_output).expanduser()
    ensure_user_launchagent_path(plist_output)
    rendered = render_plist(
        project_root=project_root,
        python_executable=python_executable,
        hour=args.hour,
        minute=args.minute,
        label=args.label,
    )

    actions: list[str] = []
    if args.dry_run:
        actions.append("dry-run: plist not written")
    else:
        create_runtime_dirs(project_root)
        plist_output.parent.mkdir(parents=True, exist_ok=True)
        plist_output.write_text(rendered, encoding="utf-8")
        actions.append(f"wrote plist: {plist_output}")
        if args.load:
            run_launchctl(["launchctl", "unload", str(plist_output)], check=False)
            run_launchctl(["launchctl", "load", str(plist_output)], check=True)
            actions.append(f"loaded LaunchAgent: {args.label}")

    return {
        "label": args.label,
        "project_root": str(project_root),
        "python_executable": str(python_executable),
        "plist_output": str(plist_output),
        "dry_run": args.dry_run,
        "load": args.load,
        "plist_content": rendered,
        "actions": actions,
    }


def render_plist(
    project_root: Path,
    python_executable: Path,
    hour: int,
    minute: int,
    label: str = DEFAULT_LABEL,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
) -> str:
    template = template_path.read_text(encoding="utf-8")
    rendered = (
        template.replace("{{PROJECT_ROOT}}", str(project_root))
        .replace("{{PYTHON_EXECUTABLE}}", str(python_executable))
        .replace("{{HOUR}}", str(hour))
        .replace("{{MINUTE}}", str(minute))
    )
    if label != DEFAULT_LABEL:
        rendered = rendered.replace(DEFAULT_LABEL, label, 1)
    return rendered


def validate_project_root(path: str | Path) -> Path:
    project_root = Path(path).expanduser().resolve()
    if not project_root.exists() or not project_root.is_dir():
        raise LaunchAgentInstallError(f"project root does not exist or is not a directory: {project_root}")
    return project_root


def validate_python_executable(path: str | Path) -> Path:
    python_executable = Path(path).expanduser().resolve()
    if not python_executable.exists() or not python_executable.is_file():
        raise LaunchAgentInstallError(f"python executable does not exist or is not a file: {python_executable}")
    return python_executable


def validate_time(hour: int, minute: int) -> None:
    if not 0 <= hour <= 23:
        raise LaunchAgentInstallError(f"hour must be between 0 and 23: {hour}")
    if not 0 <= minute <= 59:
        raise LaunchAgentInstallError(f"minute must be between 0 and 59: {minute}")


def ensure_user_launchagent_path(path: Path) -> None:
    resolved = path.expanduser().resolve()
    launch_agents = (Path.home() / "Library" / "LaunchAgents").resolve()
    if str(resolved).startswith("/Library/LaunchDaemons"):
        raise LaunchAgentInstallError("refusing to write to /Library/LaunchDaemons; use a user LaunchAgent path")
    if "/Library/LaunchDaemons" in str(resolved):
        raise LaunchAgentInstallError("refusing to write LaunchDaemon plist path")
    if resolved.parent != launch_agents and "LaunchAgents" not in resolved.parts:
        return


def create_runtime_dirs(project_root: Path) -> None:
    (project_root / "logs" / "launchd").mkdir(parents=True, exist_ok=True)
    (project_root / ".runtime").mkdir(parents=True, exist_ok=True)


def run_launchctl(command: list[str], check: bool) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=check, capture_output=True, text=True)


def print_install_result(result: dict[str, object]) -> None:
    print(f"label: {result['label']}")
    print(f"plist_output: {result['plist_output']}")
    print(f"dry_run: {result['dry_run']}")
    for action in result["actions"]:
        print(f"action: {action}")
    if result["dry_run"]:
        print("generated_plist_preview:")
        print(result["plist_content"])
    print("next_steps:")
    print(f"  launchctl load {result['plist_output']}")
    print(f"  launchctl unload {result['plist_output']}")
    print("  tail -f logs/launchd/sc-oil-agent.daily.out.log")
    print("  tail -f logs/launchd/sc-oil-agent.daily.err.log")
    print("  python scripts/run_scheduled_daily.py --report-date YYYY-MM-DD --replace --init-db")


if __name__ == "__main__":
    raise SystemExit(main())
