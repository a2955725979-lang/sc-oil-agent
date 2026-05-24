"""Merge manual and fetcher-generated daily_input JSON files."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.base import DAILY_INPUT_SCHEMA_VERSION, validate_daily_input_schema  # noqa: E402


OVERLAY_CONTEXT_KEYS = {
    "raw_data_contract_version",
    "source_name",
    "fetcher_name",
    "fetcher_version",
    "fetched_at",
    "fetch_status",
}


class DailyInputMergeError(RuntimeError):
    """Raised when daily_input files cannot be safely merged."""


def merge_daily_inputs(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge manual base daily_input with fetcher overlay daily_input."""

    errors = []
    errors.extend(f"base: {error}" for error in validate_daily_input_schema(base))
    errors.extend(f"overlay: {error}" for error in validate_daily_input_schema(overlay, require_version=True))
    if errors:
        raise DailyInputMergeError("; ".join(errors))

    base_report_date = str(base.get("report_date", ""))
    overlay_report_date = str(overlay.get("report_date", ""))
    if base_report_date != overlay_report_date:
        raise DailyInputMergeError(
            f"report_date mismatch: base={base_report_date}, overlay={overlay_report_date}"
        )

    context = _merge_context(base.get("context", {}), overlay.get("context", {}))
    fields = _merge_fields(base.get("fields", {}), overlay.get("fields", {}), context["merge_warnings"])

    return {
        "schema_version": DAILY_INPUT_SCHEMA_VERSION,
        "report_date": base_report_date,
        "context": context,
        "fields": fields,
    }


def merge_daily_input_file(
    base_path: str | Path,
    overlay_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    base = load_daily_input(base_path)
    overlay = load_daily_input(overlay_path)
    merged = merge_daily_inputs(base, overlay)
    write_json(merged, output_path)
    return merged


def load_daily_input(path: str | Path) -> dict[str, Any]:
    input_path = Path(path)
    with input_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise DailyInputMergeError(f"daily_input JSON must be an object: {input_path}")
    return data


def write_json(data: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge manual and fetcher-generated daily_input JSON files.")
    parser.add_argument("--base", required=True, help="Manual supplement daily_input JSON path.")
    parser.add_argument("--overlay", required=True, help="Fetcher-generated daily_input JSON path.")
    parser.add_argument("--output", required=True, help="Merged daily_input JSON output path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        merged = merge_daily_input_file(
            base_path=args.base,
            overlay_path=args.overlay,
            output_path=args.output,
        )
    except (OSError, json.JSONDecodeError, DailyInputMergeError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print_summary(merged, args.output)
    return 0


def print_summary(merged: dict[str, Any], output_path: str | Path) -> None:
    context = merged.get("context", {})
    merge_warnings = context.get("merge_warnings", []) if isinstance(context, dict) else []
    fields = merged.get("fields", {})
    print(f"report_date: {merged.get('report_date', '')}")
    print(f"schema_version: {merged.get('schema_version', '')}")
    print(f"fields: {len(fields) if isinstance(fields, dict) else 0}")
    print(f"merge_warnings: {len(merge_warnings) if isinstance(merge_warnings, list) else 0}")
    print(f"output_path: {output_path}")


def _merge_context(base_context: Any, overlay_context: Any) -> dict[str, Any]:
    context = copy.deepcopy(base_context) if isinstance(base_context, dict) else {}
    overlay = overlay_context if isinstance(overlay_context, dict) else {}

    existing_warnings = context.get("merge_warnings", [])
    merge_warnings = list(existing_warnings) if isinstance(existing_warnings, list) else []

    for key in sorted(OVERLAY_CONTEXT_KEYS):
        if key not in overlay:
            continue
        if key in context and context[key] != overlay[key]:
            merge_warnings.append(f"context.{key}: overlay value ignored because base context wins")
            continue
        context.setdefault(key, overlay[key])

    context["merge_warnings"] = merge_warnings
    return context


def _merge_fields(
    base_fields: Any,
    overlay_fields: Any,
    merge_warnings: list[str],
) -> dict[str, Any]:
    base = base_fields if isinstance(base_fields, dict) else {}
    overlay = overlay_fields if isinstance(overlay_fields, dict) else {}

    fields: dict[str, Any] = {}
    for field_name, payload in base.items():
        fields[field_name] = _copy_payload_with_merge_source(payload, "manual")

    for field_name, payload in overlay.items():
        overlay_payload = _copy_payload_with_merge_source(payload, "overlay")
        if field_name in fields:
            base_payload = fields[field_name]
            overlay_metadata = overlay_payload.setdefault("metadata", {})
            overlay_metadata["manual_value_before_merge"] = base_payload.get("value")
            overlay_metadata["manual_source_before_merge"] = "base"
            merge_warnings.append(f"{field_name}: overlay replaced base field")
        fields[field_name] = overlay_payload

    return fields


def _copy_payload_with_merge_source(payload: Any, merge_source: str) -> dict[str, Any]:
    copied = copy.deepcopy(payload) if isinstance(payload, dict) else {"value": None, "metadata": {}}
    metadata = copied.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["merge_source"] = merge_source
    copied["metadata"] = metadata
    return copied


if __name__ == "__main__":
    raise SystemExit(main())
