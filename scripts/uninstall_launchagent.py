"""Unload and optionally remove the sc-oil-agent user LaunchAgent plist."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


DEFAULT_LABEL = "com.sc-oil-agent.daily"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Uninstall the sc-oil-agent user LaunchAgent.")
    parser.add_argument("--label", default=DEFAULT_LABEL, help="LaunchAgent label.")
    parser.add_argument(
        "--plist-path",
        default=str(Path.home() / "Library" / "LaunchAgents" / f"{DEFAULT_LABEL}.plist"),
        help="Rendered LaunchAgent plist path.",
    )
    parser.add_argument("--keep-plist", action="store_true", help="Unload but keep the plist file.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without changing files.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    result = uninstall_launchagent(parse_args(argv))
    print_uninstall_result(result)
    return 0


def uninstall_launchagent(args: argparse.Namespace) -> dict[str, object]:
    plist_path = Path(args.plist_path).expanduser()
    actions: list[str] = []
    if args.dry_run:
        actions.append(f"dry-run: would unload {plist_path}")
        if not args.keep_plist:
            actions.append(f"dry-run: would remove {plist_path}")
        return {
            "label": args.label,
            "plist_path": str(plist_path),
            "dry_run": True,
            "keep_plist": args.keep_plist,
            "actions": actions,
        }

    run_launchctl(["launchctl", "unload", str(plist_path)], check=False)
    actions.append(f"unload attempted: {plist_path}")
    if args.keep_plist:
        actions.append("plist kept")
    elif plist_path.exists():
        plist_path.unlink()
        actions.append(f"removed plist: {plist_path}")
    else:
        actions.append(f"plist not found: {plist_path}")
    return {
        "label": args.label,
        "plist_path": str(plist_path),
        "dry_run": False,
        "keep_plist": args.keep_plist,
        "actions": actions,
    }


def run_launchctl(command: list[str], check: bool) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=check, capture_output=True, text=True)


def print_uninstall_result(result: dict[str, object]) -> None:
    print(f"label: {result['label']}")
    print(f"plist_path: {result['plist_path']}")
    print(f"dry_run: {result['dry_run']}")
    for action in result["actions"]:
        print(f"action: {action}")
    print("logs, database, reports, and processed outputs were not deleted.")


if __name__ == "__main__":
    raise SystemExit(main())
