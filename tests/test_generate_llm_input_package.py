"""Tests for src/llm/generate_llm_input_package.py.

Run from the project root:
    python tests/test_generate_llm_input_package.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.llm import generate_llm_input_package as package_module  # noqa: E402


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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def calculated_input(overall_status: str = "warning") -> dict:
    return {
        "report_date": REPORT_DATE,
        "fields": {
            "SC_close": {
                "value": 620.5,
                "metadata": {
                    "unit": "CNY/barrel",
                    "date": REPORT_DATE,
                    "source_name": "AKShare",
                    "source_level": "third_party",
                    "source_status": "pass",
                    "confidence": "medium",
                    "raw_payload": {"large": "omitted"},
                },
            },
            "USD_CNY": {
                "value": 7.18,
                "metadata": {
                    "unit": "CNY/USD",
                    "date": "2026-05-21",
                    "source_name": "Yahoo Finance via yfinance",
                    "source_status": "warning",
                    "confidence": "low",
                    "fallback_used": True,
                    "data_alignment_note": "latest available previous trading day",
                },
            },
            "manual_notes": {
                "value": "Pending review note.",
                "metadata": {
                    "unit": "text",
                    "date": REPORT_DATE,
                    "source_status": "warning",
                    "pending_manual_review": True,
                },
            },
            "SC_USD": {
                "value": 86.4206,
                "metadata": {
                    "unit": "USD/barrel",
                    "calculation_method": "simple_fx_adjusted_v1",
                    "calculation_version": "test_calc_v1",
                    "calculation_inputs": ["SC_close", "USD_CNY"],
                    "confidence": "medium",
                },
            },
            "SC_calendar_spread": {
                "value": 3.8,
                "metadata": {
                    "unit": "CNY/barrel",
                    "calculation_method": "simple_fx_adjusted_v1",
                    "calculation_inputs": ["SC_near_price", "SC_next_price"],
                },
            },
            "SC_Brent_spread_simple": {
                "value": 4.0206,
                "metadata": {
                    "unit": "USD/barrel",
                    "calculation_method": "simple_fx_adjusted_v1",
                    "calculation_inputs": ["SC_USD", "Brent_close"],
                },
            },
            "SC_WTI_spread_simple": {
                "value": 7.8206,
                "metadata": {
                    "unit": "USD/barrel",
                    "calculation_method": "manual_override",
                    "calculation_version": "manual_override_v1",
                    "calculation_inputs": ["SC_USD", "WTI_close"],
                    "pending_manual_review": True,
                },
            },
        },
        "context": {"overall_status": overall_status},
    }


def quality_report(overall_status: str = "warning") -> dict:
    return {
        "report_date": REPORT_DATE,
        "overall_status": overall_status,
        "field_results": [
            {"field": "SC_close", "source_status": "pass", "warnings": [], "errors": []},
            {"field": "USD_CNY", "source_status": "warning", "warnings": ["fallback"], "errors": []},
            {"field": "manual_notes", "source_status": "warning", "warnings": ["pending"], "errors": []},
            {"field": "SC_USD", "source_status": "pass", "warnings": [], "errors": []},
            {"field": "SC_WTI_spread_simple", "source_status": "warning", "warnings": [], "errors": []},
        ],
        "warnings": [
            "important_oil_news source_conflict_check requires multi-source data; v1 placeholder",
            "EIA_crude_inventory revision_check requires versioned source data; v1 placeholder",
        ],
        "errors": ["SC_close: forced error"] if overall_status == "fail" else [],
    }


def evidence_list() -> dict:
    return {
        "report_date": REPORT_DATE,
        "evidence_list": [
            {
                "evidence_id": "EVID-20260522-001",
                "evidence_type": "validated_field",
                "field": "SC_close",
                "source_name": "AKShare",
                "source_level": "third_party",
                "source_status": "pass",
                "confidence": "medium",
                "data_time": REPORT_DATE,
                "raw_value": 620.5,
                "normalized_value": 620.5,
                "unit": "CNY/barrel",
                "related_variable": "SC_close",
                "conclusion_impact": None,
                "url_or_reference": "fixture://akshare",
            }
        ],
    }


def business_summary() -> dict:
    return {
        "market_prices_written": 3,
        "fx_rates_written": 1,
        "spreads_written": 1,
        "evidence_written": 5,
        "warnings": ["business warning"],
        "errors": [],
    }


def test_generates_package_with_expected_schema_and_sections() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        calculated_path = root / "calculated.json"
        quality_path = root / "quality.json"
        evidence_path = root / "evidence.json"
        business_path = root / "business.json"
        daily_report_path = root / "SC_daily.md"
        output_path = root / "llm_input_package.json"
        write_json(calculated_path, calculated_input())
        write_json(quality_path, quality_report())
        write_json(evidence_path, evidence_list())
        write_json(business_path, business_summary())
        write_text(daily_report_path, "# Daily report\nStructured preview text.\n")

        package = package_module.generate_llm_input_package(
            calculated_input_path=calculated_path,
            quality_report_path=quality_path,
            evidence_list_path=evidence_path,
            business_write_summary_path=business_path,
            daily_report_path=daily_report_path,
            output_path=output_path,
            data_snapshot_id="SNAP-TEST",
            research_report_id="RPT-TEST",
        )
        saved = load_json(output_path)

    assert_equal(saved["schema_version"], "llm_input_package_v1", "schema version")
    assert_equal(package["report_date"], REPORT_DATE, "report date")
    assert_equal(saved["pipeline_status"]["source_priority"], "quality_report.report_date", "date priority")
    assert_equal(saved["data_snapshot_id"], "SNAP-TEST", "snapshot id")
    assert_equal(saved["research_report_id"], "RPT-TEST", "report id")
    assert_equal(saved["business_persistence"]["provided"], True, "business summary provided")
    assert_equal(saved["business_persistence"]["market_prices_written"], 3, "business market count")
    assert_equal(saved["inputs"]["daily_report_exists"], True, "daily report exists")
    assert_text_contains(saved["inputs"]["daily_report_preview"], "Structured preview", "daily report preview")


def test_field_facts_and_calculated_indicators_are_separated() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        calculated_path = root / "calculated.json"
        quality_path = root / "quality.json"
        output_path = root / "package.json"
        write_json(calculated_path, calculated_input())
        write_json(quality_path, quality_report())

        package = package_module.generate_llm_input_package(calculated_path, quality_path, output_path=output_path)

    fact_fields = {item["field"] for item in package["field_facts"]}
    indicator_fields = {item["field"] for item in package["calculated_indicators"]}
    assert_contains(fact_fields, "SC_close", "SC_close fact")
    assert_contains(fact_fields, "USD_CNY", "USD_CNY fact")
    assert_equal("SC_USD" in fact_fields, False, "SC_USD excluded from facts")
    assert_equal(
        indicator_fields,
        {"SC_USD", "SC_calendar_spread", "SC_Brent_spread_simple", "SC_WTI_spread_simple"},
        "calculated indicators",
    )
    sc_close = next(item for item in package["field_facts"] if item["field"] == "SC_close")
    assert_equal("raw_payload" in sc_close["metadata"], False, "raw payload omitted")
    assert_equal(sc_close["metadata"]["raw_payload_omitted"], True, "raw payload omission marker")
    wti_spread = next(item for item in package["calculated_indicators"] if item["field"] == "SC_WTI_spread_simple")
    assert_equal(wti_spread["source_status"], "warning", "manual override calculated warning")
    assert_text_contains(wti_spread["llm_usage_note"], "Manual override", "manual override usage note")


def test_evidence_and_reasoning_guardrails_are_explicit() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        calculated_path = root / "calculated.json"
        quality_path = root / "quality.json"
        evidence_path = root / "evidence.json"
        output_path = root / "package.json"
        write_json(calculated_path, calculated_input())
        write_json(quality_path, quality_report())
        write_json(evidence_path, evidence_list())

        package = package_module.generate_llm_input_package(
            calculated_path,
            quality_path,
            evidence_list_path=evidence_path,
            output_path=output_path,
        )

    evidence = package["evidence_items"][0]
    assert_equal(evidence["evidence_id"], "EVID-20260522-001", "evidence id")
    assert_equal(evidence["evidence_scope"], "field_level", "evidence scope")
    assert_text_contains(evidence["llm_usage_note"], "do not independently support directional", "evidence usage note")
    scope = package["allowed_reasoning_scope"]
    assert_equal(scope["can_generate_trading_signal"], False, "no trading signal")
    assert_equal(scope["can_invent_missing_causes"], False, "no invented causes")
    assert_contains(scope["must_reference"], "quality_constraints", "must reference quality")
    assert_contains(package["forbidden_outputs"], "买入", "forbidden Chinese term")


def test_quality_constraints_detect_warning_fail_fallback_and_placeholders() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        calculated_path = root / "calculated.json"
        quality_path = root / "quality.json"
        output_path = root / "package.json"
        write_json(calculated_path, calculated_input())
        write_json(quality_path, quality_report())

        package = package_module.generate_llm_input_package(calculated_path, quality_path, output_path=output_path)

    constraints = package["quality_constraints"]
    assert_contains(constraints["warning_fields"], "USD_CNY", "warning field")
    assert_contains(constraints["stale_or_fallback_fields"], "USD_CNY", "fallback field")
    assert_text_contains("; ".join(constraints["placeholder_checks"]), "source_conflict_check", "source conflict placeholder")
    assert_text_contains("; ".join(constraints["placeholder_checks"]), "revision_check", "revision placeholder")
    assert_equal(constraints["normal_market_explanation_allowed"], True, "warning can allow caveated explanation")
    assert_equal(constraints["conclusion_strength_cap"], "low_to_medium", "warning strength cap")


def test_fail_quality_package_blocks_normal_market_explanation() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        calculated_path = root / "calculated.json"
        quality_path = root / "quality.json"
        output_path = root / "package.json"
        write_json(calculated_path, calculated_input(overall_status="fail"))
        fail_quality = quality_report(overall_status="fail")
        fail_quality["field_results"][0]["source_status"] = "fail"
        write_json(quality_path, fail_quality)

        package = package_module.generate_llm_input_package(calculated_path, quality_path, output_path=output_path)

    constraints = package["quality_constraints"]
    assert_equal(package["pipeline_status"]["overall_status"], "fail", "fail status")
    assert_contains(constraints["failed_fields"], "SC_close", "failed field")
    assert_equal(constraints["normal_market_explanation_allowed"], False, "fail blocks explanation")
    assert_equal(constraints["reason"], "overall_status is fail", "fail reason")
    assert_text_contains("; ".join(package["notes"]), "future LLM must not generate normal market explanation", "fail note")


def test_missing_optional_artifacts_and_business_summary_absence_are_notes_not_errors() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        calculated_path = root / "calculated.json"
        quality_path = root / "quality.json"
        output_path = root / "package.json"
        write_json(calculated_path, calculated_input())
        write_json(quality_path, quality_report())

        package = package_module.generate_llm_input_package(
            calculated_path,
            quality_path,
            evidence_list_path=root / "missing_evidence.json",
            daily_report_path=root / "missing_report.md",
            output_path=output_path,
        )

    assert_equal(package["evidence_items"], [], "missing evidence gives empty list")
    assert_equal(package["business_persistence"]["provided"], False, "business summary absent")
    assert_equal(package["business_persistence"]["write_business_tables_requested"], False, "business not requested")
    assert_equal(package["business_persistence"]["counts"]["market_prices"], 0, "business zero count")
    assert_text_contains(package["business_persistence"]["note"], "zero counts do not imply attempted writes", "business note")
    assert_text_contains("; ".join(package["notes"]), "business summary not provided", "business absence note")
    assert_text_contains("; ".join(package["notes"]), "daily_report missing", "missing report note")


def test_default_output_path_uses_report_date() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        original_project_root = package_module.PROJECT_ROOT
        calculated_path = root / "calculated.json"
        quality_path = root / "quality.json"
        write_json(calculated_path, calculated_input())
        write_json(quality_path, quality_report())
        package_module.PROJECT_ROOT = root
        try:
            package = package_module.generate_llm_input_package(calculated_path, quality_path)
            output_path = root / "data" / "processed" / f"llm_input_package_{REPORT_DATE}.json"
            exists = output_path.exists()
        finally:
            package_module.PROJECT_ROOT = original_project_root

    assert_equal(package["report_date"], REPORT_DATE, "default output report date")
    assert_equal(exists, True, "default output path exists")


def run() -> None:
    tests = [
        test_generates_package_with_expected_schema_and_sections,
        test_field_facts_and_calculated_indicators_are_separated,
        test_evidence_and_reasoning_guardrails_are_explicit,
        test_quality_constraints_detect_warning_fail_fallback_and_placeholders,
        test_fail_quality_package_blocks_normal_market_explanation,
        test_missing_optional_artifacts_and_business_summary_absence_are_notes_not_errors,
        test_default_output_path_uses_report_date,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
