"""Write generated Markdown reports into the research_reports table."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.write_snapshot import (  # noqa: E402
    DEFAULT_CONFIG_PATH,
    DEFAULT_DB_PATH,
    SnapshotWriteError,
    get_git_commit_hash,
    load_project_config,
)


VALID_STATUSES = {"pass", "warning", "fail"}
FAIL_CONCLUSION = "数据质量未通过，不能生成正常研究结论。"
TOPIC = "SC 中国原油期货日报"


class ResearchReportWriteError(RuntimeError):
    """Raised when a Markdown research report cannot be written."""


def load_json(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    with json_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ResearchReportWriteError(f"JSON file must be an object: {json_path}")
    return data


def write_research_report(
    markdown_path: str | Path,
    quality_report_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    evidence_list_path: str | Path | None = None,
    data_snapshot_id: str | None = None,
    report_id: str | None = None,
    replace: bool = False,
) -> str:
    """Write a generated Markdown report to research_reports and return report_id."""

    markdown_path = Path(markdown_path).expanduser().resolve()
    quality_report_path = Path(quality_report_path).expanduser().resolve()
    db_path = Path(db_path).expanduser().resolve()
    config_path = Path(config_path).expanduser().resolve()
    evidence_list_path = Path(evidence_list_path).expanduser().resolve() if evidence_list_path else None

    if replace and not report_id:
        raise ResearchReportWriteError("--replace requires an explicit --report-id")
    if not db_path.exists():
        raise ResearchReportWriteError(
            f"Database file not found: {db_path}. "
            "Run `python src/database/init_db.py` first."
        )
    if not markdown_path.exists():
        raise ResearchReportWriteError(f"Markdown report not found: {markdown_path}")

    quality_report = load_json(quality_report_path)
    evidence_report = load_json(evidence_list_path) if evidence_list_path else None
    try:
        config = load_project_config(config_path)
    except SnapshotWriteError as exc:
        raise ResearchReportWriteError(str(exc)) from exc
    markdown = markdown_path.read_text(encoding="utf-8")

    row = build_research_report_row(
        markdown=markdown,
        markdown_path=markdown_path,
        quality_report=quality_report,
        evidence_report=evidence_report,
        config=config,
        db_path=db_path,
        data_snapshot_id=data_snapshot_id,
        report_id=report_id,
    )

    if replace:
        _replace_report(db_path, row)
    else:
        _insert_report(db_path, row)
    return row["report_id"]


def build_research_report_row(
    markdown: str,
    markdown_path: str | Path,
    quality_report: dict[str, Any],
    evidence_report: dict[str, Any] | None,
    config: dict[str, Any] | None,
    db_path: str | Path,
    data_snapshot_id: str | None = None,
    report_id: str | None = None,
) -> dict[str, Any]:
    report_date = _required_text(quality_report, "report_date")
    status = _required_text(quality_report, "overall_status")
    if status not in VALID_STATUSES:
        raise ResearchReportWriteError(f"Invalid overall_status in quality report: {status}")

    config = config or {}
    report_config = config.get("report", {})
    if not isinstance(report_config, dict):
        report_config = {}

    final_report_id = report_id or generate_report_id(db_path, report_date)
    final_snapshot_id = _resolve_snapshot_id_for_db(
        db_path=db_path,
        candidate=data_snapshot_id or quality_report.get("data_snapshot_id"),
    )

    return {
        "report_id": final_report_id,
        "data_snapshot_id": final_snapshot_id,
        "date": report_date,
        "topic": TOPIC,
        "conclusion": _conclusion_for_status(status),
        "evidence_ids": json.dumps(_evidence_ids(evidence_report), ensure_ascii=False),
        "confidence": "中" if status == "pass" else "低",
        "report_status": status,
        "prompt_version": report_config.get("prompt_version"),
        "calculation_version": report_config.get("calculation_version"),
        "code_version": get_git_commit_hash(),
        "report_path": _display_path(markdown_path),
        "report_markdown": markdown,
    }


def generate_report_id(db_path: str | Path, report_date: str) -> str:
    prefix = f"RPT-{report_date.replace('-', '')}-SC-DAILY-"
    db_path = Path(db_path).expanduser().resolve()
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT report_id
            FROM research_reports
            WHERE report_id LIKE ?
            ORDER BY report_id;
            """,
            (f"{prefix}%",),
        ).fetchall()

    max_seq = 0
    for (existing_report_id,) in rows:
        suffix = str(existing_report_id).replace(prefix, "", 1)
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))
    return f"{prefix}{max_seq + 1:03d}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a generated Markdown report to research_reports.")
    parser.add_argument("--markdown-report", required=True, help="Generated Markdown report path.")
    parser.add_argument("--quality-report", required=True, help="Quality report JSON path.")
    parser.add_argument("--evidence-list", help="Optional field-level Evidence List JSON path.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Project config YAML path.")
    parser.add_argument("--data-snapshot-id", help="Optional data_snapshot_id.")
    parser.add_argument("--report-id", help="Explicit report_id.")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Allow INSERT OR REPLACE. Requires --report-id.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report_id = write_research_report(
            markdown_path=args.markdown_report,
            quality_report_path=args.quality_report,
            db_path=args.db,
            config_path=args.config,
            evidence_list_path=args.evidence_list,
            data_snapshot_id=args.data_snapshot_id,
            report_id=args.report_id,
            replace=args.replace,
        )
    except (ResearchReportWriteError, sqlite3.Error, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Wrote research_report: {report_id}")
    return 0


def _insert_report(db_path: Path, row: dict[str, Any]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            conn.execute(_insert_sql("INSERT"), row)
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc).upper():
                raise ResearchReportWriteError(
                    f"report_id already exists: {row['report_id']}. "
                    "Use --replace with --report-id to overwrite."
                ) from exc
            raise
        conn.commit()


def _replace_report(db_path: Path, row: dict[str, Any]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(_insert_sql("INSERT OR REPLACE"), row)
        conn.commit()


def _insert_sql(verb: str) -> str:
    return f"""
        {verb} INTO research_reports (
            report_id,
            data_snapshot_id,
            date,
            topic,
            conclusion,
            evidence_ids,
            confidence,
            report_status,
            prompt_version,
            calculation_version,
            code_version,
            report_path,
            report_markdown
        )
        VALUES (
            :report_id,
            :data_snapshot_id,
            :date,
            :topic,
            :conclusion,
            :evidence_ids,
            :confidence,
            :report_status,
            :prompt_version,
            :calculation_version,
            :code_version,
            :report_path,
            :report_markdown
        );
    """


def _resolve_snapshot_id_for_db(db_path: str | Path, candidate: Any) -> str | None:
    if candidate is None or str(candidate).strip() in {"", "未写入 data_snapshot"}:
        return None

    snapshot_id = str(candidate)
    with sqlite3.connect(Path(db_path).expanduser().resolve()) as conn:
        row = conn.execute(
            "SELECT 1 FROM data_snapshot WHERE data_snapshot_id = ?;",
            (snapshot_id,),
        ).fetchone()
    if row is None:
        return None
    return snapshot_id


def _evidence_ids(evidence_report: dict[str, Any] | None) -> list[str]:
    if not evidence_report:
        return []
    evidence_items = evidence_report.get("evidence_list", [])
    if not isinstance(evidence_items, list):
        return []

    ids = []
    for item in evidence_items:
        if isinstance(item, dict) and item.get("evidence_id"):
            ids.append(str(item["evidence_id"]))
    return ids


def _conclusion_for_status(status: str) -> str:
    if status == "fail":
        return FAIL_CONCLUSION
    if status == "warning":
        return "数据可用于结构化日报，但存在 warning，结论需保持保守并等待人工审核。"
    return "数据质量状态为 pass，可生成描述性日报，仍需人工审核。"


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if value is None or str(value).strip() == "":
        raise ResearchReportWriteError(f"Quality report missing required field: {key}")
    return str(value)


def _display_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    raise SystemExit(main())
