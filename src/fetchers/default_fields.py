"""Generate conservative default daily_input fields for auto daily preflight."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.base import DAILY_INPUT_SCHEMA_VERSION  # noqa: E402


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_TEXTS = {
    "exchange_notice": "无新增交易所公告，待人工确认；不得用于强结论或交易判断。",
    "important_oil_news": "未提供自动新闻摘要，待人工补充；不得用于强结论或交易判断。",
    "manual_notes": "未提供人工备注；不得用于强结论或交易判断。",
    "OPEC_monthly_summary": "未提供最新 OPEC 月报摘要，待人工确认；不得用于强结论或交易判断。",
    "IEA_monthly_summary": "未提供最新 IEA 月报摘要，待人工确认；不得用于强结论或交易判断。",
}


def build_default_daily_input(report_date: str, fetched_at: str | None = None) -> dict[str, Any]:
    final_fetched_at = fetched_at or _now_shanghai()
    fields = {
        field_name: {
            "value": text,
            "metadata": {
                "unit": "text",
                "date": report_date,
                "timezone": "Asia/Shanghai",
                "source_level": "derived",
                "source_status": "warning",
                "confidence": "low",
                "fetched_at": final_fetched_at,
                "default_field": True,
                "default_reason": "auto_daily_preflight_placeholder",
            },
        }
        for field_name, text in DEFAULT_TEXTS.items()
    }
    return {
        "schema_version": DAILY_INPUT_SCHEMA_VERSION,
        "report_date": report_date,
        "context": {
            "required_for_topic": [],
            "default_fields_policy": "text placeholders are warning/low confidence and require human review",
        },
        "fields": fields,
    }


def write_daily_input(daily_input: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(daily_input, file, ensure_ascii=False, indent=2)
        file.write("\n")


def build_default_output_path(report_date: str) -> Path:
    return DEFAULT_OUTPUT_DIR / f"default_fields_{report_date}.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate conservative default daily_input text fields.")
    parser.add_argument("--report-date", required=True, help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--output", help="Default daily_input output JSON path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_path = Path(args.output) if args.output else build_default_output_path(args.report_date)
    daily_input = build_default_daily_input(args.report_date)
    write_daily_input(daily_input, output_path)
    print(f"report_date: {daily_input['report_date']}")
    print(f"schema_version: {daily_input['schema_version']}")
    print(f"fields: {len(daily_input['fields'])}")
    print(f"output_path: {output_path}")
    return 0


def _now_shanghai() -> str:
    shanghai = timezone(timedelta(hours=8))
    return datetime.now(tz=shanghai).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
