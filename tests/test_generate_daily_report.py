"""Smoke tests for the non-Agent daily Markdown report generator.

Run from the project root:
    python tests/test_generate_daily_report.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.report_generator.generate_daily_report import (  # noqa: E402
    FORBIDDEN_TERMS,
    generate_daily_report,
    main,
)
from src.evidence.generate_evidence_list import generate_evidence_list  # noqa: E402
from src.validators.run_quality_validation import run_validation  # noqa: E402


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(text: str, expected_fragment: str, message: str) -> None:
    if expected_fragment not in text:
        raise AssertionError(f"{message}: {expected_fragment!r} not found")


def assert_not_contains(text: str, forbidden_fragment: str, message: str) -> None:
    if forbidden_fragment in text:
        raise AssertionError(f"{message}: {forbidden_fragment!r} found")


def assert_in_order(text: str, fragments: list[str], message: str) -> None:
    cursor = -1
    for fragment in fragments:
        next_cursor = text.find(fragment, cursor + 1)
        if next_cursor == -1:
            raise AssertionError(f"{message}: {fragment!r} not found after offset {cursor}")
        cursor = next_cursor


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_example_warning_report_contains_required_sections() -> None:
    input_path = PROJECT_ROOT / "data" / "manual" / "daily_input_example.json"
    dictionary_path = PROJECT_ROOT / "config" / "data_dictionary.yaml"

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        quality_report_path = root / "quality_report_example.json"
        output_path = root / "SC_daily_example.md"

        run_validation(
            input_path=input_path,
            data_dictionary_path=dictionary_path,
            output_path=quality_report_path,
        )
        markdown = generate_daily_report(
            daily_input_path=input_path,
            quality_report_path=quality_report_path,
            output_path=output_path,
            data_snapshot_id="SNAP-EXAMPLE-001",
        )
        saved_markdown = output_path.read_text(encoding="utf-8")

    assert_equal(markdown, saved_markdown, "generated markdown should be written unchanged")
    assert_contains(markdown, "SC 中国原油期货日报", "title should be present")
    assert_contains(markdown, "日报状态", "daily status should be present")
    assert_contains(markdown, "数据快照编号", "snapshot id should be present")
    assert_contains(markdown, "数据完整性提示", "quality section should be present")
    assert_contains(markdown, "证据链", "evidence section should be present")
    assert_contains(
        markdown,
        "正式 Evidence ID 尚未自动生成",
        "evidence placeholder should be explicit",
    )
    assert_contains(markdown, "人工审核区", "manual review section should be present")
    assert_contains(markdown, "Oman / Dubai 尚未接入", "Oman/Dubai limitation should be present")
    assert_contains(markdown, "结论降级原因", "warning report should include downgrade reason")
    assert_contains(
        markdown,
        "当前不依赖 Agent、LLM 或外部 skill",
        "generator should state it has no Agent/LLM/skill dependency",
    )
    assert_in_order(
        markdown,
        [
            "## 1. 数据状态与结论约束",
            "## 2. SC 主力行情",
            "## 3. SC 期限结构与月差",
            "## 4. Brent / WTI 外盘简化参考",
            "## 5. USD/CNY 汇率影响",
            "## 6. SC 简化价差",
            "## 7. EIA 库存与海外供需摘要",
            "## 8. 公告、新闻与人工备注",
            "## 9. 证据链",
            "## 10. 风险反例、下一交易日关注与人工审核区",
        ],
        "report should follow the fixed SC daily judgement order",
    )

    for term in FORBIDDEN_TERMS:
        assert_not_contains(markdown, term, "report should not contain forbidden trading terms")


def test_fail_report_has_no_directional_conclusion() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "daily_input_fail.json"
        quality_report_path = root / "quality_report_fail.json"
        output_path = root / "SC_daily_fail.md"

        write_json(
            input_path,
            {
                "report_date": "2026-05-22",
                "fields": {
                    "SC_close": {"value": None, "metadata": {}},
                    "Brent_close": {"value": 82.0, "metadata": {"unit": "USD/barrel"}},
                },
            },
        )
        write_json(
            quality_report_path,
            {
                "report_date": "2026-05-22",
                "overall_status": "fail",
                "field_results": [
                    {
                        "field": "SC_close",
                        "source_status": "fail",
                        "warnings": [],
                        "errors": ["missing required field"],
                    }
                ],
                "warnings": [],
                "errors": ["SC_close: missing required field"],
            },
        )

        markdown = generate_daily_report(
            daily_input_path=input_path,
            quality_report_path=quality_report_path,
            output_path=output_path,
        )

    assert_contains(markdown, "日报状态：fail", "fail status should be shown")
    assert_contains(markdown, "数据质量未通过", "fail report should state data failure")
    assert_contains(markdown, "本报告不进行行情归因", "fail report should avoid attribution")
    assert_not_contains(markdown, "利多", "fail report should not contain bullish language")
    assert_not_contains(markdown, "利空", "fail report should not contain bearish language")

    for term in FORBIDDEN_TERMS:
        assert_not_contains(markdown, term, "fail report should not contain forbidden trading terms")


def test_report_can_reference_field_level_evidence_list() -> None:
    input_path = PROJECT_ROOT / "data" / "manual" / "daily_input_example.json"
    dictionary_path = PROJECT_ROOT / "config" / "data_dictionary.yaml"

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        quality_report_path = root / "quality_report_example.json"
        evidence_list_path = root / "evidence_list_example.json"
        output_path = root / "SC_daily_with_evidence.md"

        run_validation(
            input_path=input_path,
            data_dictionary_path=dictionary_path,
            output_path=quality_report_path,
        )
        generate_evidence_list(
            daily_input_path=input_path,
            quality_report_path=quality_report_path,
            output_path=evidence_list_path,
            data_snapshot_id="SNAP-EXAMPLE-001",
        )
        markdown = generate_daily_report(
            daily_input_path=input_path,
            quality_report_path=quality_report_path,
            output_path=output_path,
            data_snapshot_id="SNAP-EXAMPLE-001",
            evidence_list_path=evidence_list_path,
        )

    assert_contains(markdown, "EVID-20260522-001", "report should reference evidence ids")
    assert_contains(markdown, "Evidence List v1 为字段级证据", "field-level scope should be explicit")
    assert_contains(markdown, "source_status=warning", "warning evidence status should be visible")
    assert_contains(markdown, "warning evidence，仅作降级依据", "warning evidence should be downgraded")
    assert_not_contains(markdown, "强依据", "warning evidence should not be described as strong evidence")


def test_cli_generates_report_with_custom_paths() -> None:
    input_path = PROJECT_ROOT / "data" / "manual" / "daily_input_example.json"
    dictionary_path = PROJECT_ROOT / "config" / "data_dictionary.yaml"

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        quality_report_path = root / "quality_report_example.json"
        output_path = root / "nested" / "SC_daily_example.md"

        run_validation(
            input_path=input_path,
            data_dictionary_path=dictionary_path,
            output_path=quality_report_path,
        )
        exit_code = main(
            [
                "--daily-input",
                str(input_path),
                "--quality-report",
                str(quality_report_path),
                "--output",
                str(output_path),
                "--data-snapshot-id",
                "SNAP-EXAMPLE-CLI",
            ]
        )
        markdown = output_path.read_text(encoding="utf-8")

    assert_equal(exit_code, 0, "CLI should return success")
    assert_contains(markdown, "SNAP-EXAMPLE-CLI", "CLI snapshot id should be used")


def run() -> None:
    tests = [
        test_example_warning_report_contains_required_sections,
        test_fail_report_has_no_directional_conclusion,
        test_report_can_reference_field_level_evidence_list,
        test_cli_generates_report_with_custom_paths,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
