"""Smoke tests for src/pipeline/run_auto_daily.py.

Run from the project root:
    python tests/test_run_auto_daily.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.akshare_sc import build_fetch_result_from_rows as build_akshare_fetch_result  # noqa: E402
from src.fetchers.base import DAILY_INPUT_SCHEMA_VERSION  # noqa: E402
from src.fetchers.market_fx import build_fetch_result_from_rows as build_market_fx_fetch_result  # noqa: E402
from src.pipeline import run_auto_daily as workflow  # noqa: E402
from src.report_generator.generate_daily_report import FORBIDDEN_TERMS  # noqa: E402


FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "akshare_sc" / "ine_sc_rows.json"
PROJECT_DICTIONARY = PROJECT_ROOT / "config" / "data_dictionary.yaml"
REPORT_DATE = "2026-01-15"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_akshare_raw_data(report_date: str = REPORT_DATE) -> dict:
    rows = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return build_akshare_fetch_result(
        rows=rows,
        report_date=report_date,
        fetched_at=f"{report_date}T16:00:00+08:00",
    )


def build_akshare_raw_fail(report_date: str = REPORT_DATE) -> dict:
    return build_akshare_fetch_result(
        rows=[],
        report_date=report_date,
        fetched_at=f"{report_date}T16:00:00+08:00",
    )


def build_market_fx_raw_data(report_date: str = REPORT_DATE) -> dict:
    return build_market_fx_fetch_result(
        rows={
            "date": report_date,
            "USD_CNY": 7.18,
            "Brent_close": 82.4,
            "WTI_close": 78.6,
            "source_name": "fixture_market_fx",
            "url_or_reference": "fixture://market_fx",
        },
        report_date=report_date,
        fetched_at=f"{report_date}T16:30:00+08:00",
    )


def build_market_fx_raw_fallback(report_date: str = REPORT_DATE) -> dict:
    return build_market_fx_fetch_result(
        rows={
            "date": "2026-01-14",
            "USD_CNY": 7.18,
            "Brent_close": 82.4,
            "WTI_close": 78.6,
            "source_name": "fixture_market_fx",
            "url_or_reference": "fixture://market_fx",
        },
        report_date=report_date,
        fetched_at=f"{report_date}T16:30:00+08:00",
    )


def build_market_fx_raw_fail(report_date: str = REPORT_DATE) -> dict:
    row = {
        "date": report_date,
        "USD_CNY": 7.18,
        "Brent_close": 82.4,
        "source_name": "fixture_market_fx",
        "url_or_reference": "fixture://market_fx",
    }
    return build_market_fx_fetch_result(
        rows=row,
        report_date=report_date,
        fetched_at=f"{report_date}T16:30:00+08:00",
    )


def manual_supplement(report_date: str = REPORT_DATE) -> dict:
    return {
        "schema_version": DAILY_INPUT_SCHEMA_VERSION,
        "report_date": report_date,
        "context": {
            "required_for_topic": [],
            "manual_context": "test-only manual supplement",
        },
        "fields": {
            "manual_notes": {
                "value": "Human reviewed note for auto daily smoke.",
                "metadata": {
                    "unit": "text",
                    "date": report_date,
                    "timezone": "Asia/Shanghai",
                    "source_level": "manual",
                },
            },
            "EIA_crude_inventory": {
                "value": 443.2,
                "metadata": {
                    "unit": "million_barrels",
                    "date": report_date,
                    "publish_time": f"{report_date} 22:30:00",
                    "timezone": "America/New_York",
                    "source_level": "manual",
                },
            },
        },
    }


def manual_supplement_with_sc_override(report_date: str = REPORT_DATE) -> dict:
    supplement = manual_supplement(report_date)
    supplement["fields"]["SC_close"] = {
        "value": 999.0,
        "metadata": {
            "unit": "CNY/barrel",
            "date": report_date,
            "timezone": "Asia/Shanghai",
            "source_level": "manual",
        },
    }
    return supplement


def manual_supplement_with_fx_overrides(report_date: str = REPORT_DATE) -> dict:
    supplement = manual_supplement(report_date)
    for field_name, value, unit in [
        ("USD_CNY", 7.99, "CNY/USD"),
        ("Brent_close", 99.9, "USD/barrel"),
        ("WTI_close", 95.5, "USD/barrel"),
    ]:
        supplement["fields"][field_name] = {
            "value": value,
            "metadata": {
                "unit": unit,
                "date": report_date,
                "timezone": "Asia/Shanghai",
                "source_level": "manual",
            },
        }
    return supplement


def manual_supplement_with_calculated_override(report_date: str = REPORT_DATE) -> dict:
    supplement = manual_supplement(report_date)
    for field_name, value, unit in [
        ("SC_USD", 88.88, "USD/barrel"),
        ("SC_calendar_spread", 12.34, "CNY/barrel"),
        ("SC_Brent_spread_simple", 6.78, "USD/barrel"),
        ("SC_WTI_spread_simple", 9.87, "USD/barrel"),
    ]:
        supplement["fields"][field_name] = {
            "value": value,
            "metadata": {
                "unit": unit,
                "date": report_date,
                "timezone": "Asia/Shanghai",
                "source_level": "manual",
            },
        }
    return supplement


def manual_supplement_with_added_field(report_date: str = REPORT_DATE) -> dict:
    supplement = manual_supplement(report_date)
    supplement["fields"]["analyst_custom_observation"] = {
        "value": "Manual-only observation for audit trail.",
        "metadata": {
            "unit": "text",
            "date": report_date,
            "timezone": "Asia/Shanghai",
            "source_level": "manual",
        },
    }
    return supplement


def assert_manual_override_metadata(
    field_payload: dict,
    previous_value,
    new_value,
    message: str,
) -> None:
    metadata = field_payload["metadata"]
    assert_equal(metadata["manual_override_used"], True, f"{message} override marker")
    assert_equal(metadata["manual_override_source"], "manual_supplement", f"{message} override source")
    assert_equal(metadata["manual_override_previous_value"], previous_value, f"{message} previous value")
    assert_equal(metadata["manual_override_new_value"], new_value, f"{message} new value")
    assert_equal(
        metadata["manual_override_warning"],
        "manual_supplement replaced an existing auto/fetched/default/calculated field",
        f"{message} override warning",
    )


def write_config(path: Path) -> None:
    write_text(
        path,
        """
report:
  prompt_version: test_prompt_v1
  calculation_version: test_calc_v1
""",
    )


def workflow_args(
    root: Path,
    akshare_raw_path: Path,
    market_fx_raw_path: Path,
    report_date: str = REPORT_DATE,
    extra_args: list[str] | None = None,
) -> list[str]:
    args = [
        "--report-date",
        report_date,
        "--raw-input",
        str(akshare_raw_path),
        "--market-fx-raw-input",
        str(market_fx_raw_path),
        "--akshare-raw-output",
        str(root / "raw" / "should_not_fetch_akshare.json"),
        "--market-fx-raw-output",
        str(root / "raw" / "should_not_fetch_market_fx.json"),
        "--eia-raw-output",
        str(root / "raw" / "eia_inventory.json"),
        "--akshare-daily-input-output",
        str(root / "processed" / "akshare_daily_input.json"),
        "--market-fx-daily-input-output",
        str(root / "processed" / "market_fx_daily_input.json"),
        "--eia-daily-input-output",
        str(root / "processed" / "eia_daily_input.json"),
        "--default-fields-output",
        str(root / "processed" / "default_fields.json"),
        "--akshare-conversion-result-output",
        str(root / "processed" / "akshare_conversion_result.json"),
        "--market-fx-conversion-result-output",
        str(root / "processed" / "market_fx_conversion_result.json"),
        "--eia-conversion-result-output",
        str(root / "processed" / "eia_conversion_result.json"),
        "--auto-daily-input-output",
        str(root / "manual" / "daily_input.json"),
        "--calculated-input-output",
        str(root / "processed" / "calculated_input.json"),
        "--quality-report-output",
        str(root / "processed" / "quality_report.json"),
        "--evidence-list-output",
        str(root / "processed" / "evidence_list.json"),
        "--daily-report-output",
        str(root / "reports" / "SC_daily.md"),
        "--db",
        str(root / "sc_oil.sqlite"),
        "--config",
        str(root / "config.yaml"),
        "--dictionary",
        str(PROJECT_DICTIONARY),
        "--init-db",
        "--report-id",
        "RPT-AUTO-TEST",
    ]
    if extra_args:
        args.extend(extra_args)
    return args


def workflow_args_live_market_fx(
    root: Path,
    akshare_raw_path: Path,
    report_date: str = REPORT_DATE,
    extra_args: list[str] | None = None,
) -> list[str]:
    args = workflow_args(root, akshare_raw_path, root / "raw" / "unused_market_fx_input.json", report_date, extra_args)
    market_fx_input_index = args.index("--market-fx-raw-input")
    del args[market_fx_input_index:market_fx_input_index + 2]
    market_fx_output_index = args.index("--market-fx-raw-output") + 1
    args[market_fx_output_index] = str(root / "raw" / "market_fx_live.json")
    return args


def research_report_rows(db_path: Path) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT report_id, data_snapshot_id, report_status, report_path
                FROM research_reports
                ORDER BY report_id;
                """
            ).fetchall()
        ]


def table_count(db_path: Path, table_name: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table_name};").fetchone()[0]


def test_without_manual_supplement_runs_warning_daily_report_without_fetching() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        akshare_raw_path = root / "raw" / "akshare_sc.json"
        market_fx_raw_path = root / "raw" / "market_fx.json"
        write_json(akshare_raw_path, build_akshare_raw_data())
        write_json(market_fx_raw_path, build_market_fx_raw_data())
        write_config(root / "config.yaml")

        original_akshare_fetch = workflow.fetch_akshare_sc_daily
        original_market_fx_fetch = workflow.fetch_market_fx_daily

        def forbidden_fetch(_report_date: str) -> dict:
            raise AssertionError("fetch must not be called when raw input is provided")

        workflow.fetch_akshare_sc_daily = forbidden_fetch
        workflow.fetch_market_fx_daily = forbidden_fetch
        try:
            exit_code = workflow.main(workflow_args(root, akshare_raw_path, market_fx_raw_path))
        finally:
            workflow.fetch_akshare_sc_daily = original_akshare_fetch
            workflow.fetch_market_fx_daily = original_market_fx_fetch

        auto_daily_input_path = root / "manual" / "daily_input.json"
        quality_report_path = root / "processed" / "quality_report.json"
        evidence_list_path = root / "processed" / "evidence_list.json"
        daily_report_path = root / "reports" / "SC_daily.md"
        output_exists = {
            "auto_daily_input": auto_daily_input_path.exists(),
            "quality_report": quality_report_path.exists(),
            "evidence_list": evidence_list_path.exists(),
            "daily_report": daily_report_path.exists(),
        }
        auto_daily_input = load_json(auto_daily_input_path)
        quality_report = load_json(quality_report_path)
        markdown = daily_report_path.read_text(encoding="utf-8")
        reports = research_report_rows(root / "sc_oil.sqlite")

    assert_equal(exit_code, 0, "auto daily workflow should succeed with warning quality")
    assert_equal(output_exists["auto_daily_input"], True, "auto daily input should be written")
    assert_equal(output_exists["quality_report"], True, "quality report should be written")
    assert_equal(output_exists["evidence_list"], True, "evidence list should be written")
    assert_equal(output_exists["daily_report"], True, "daily report should be written")
    assert_equal(auto_daily_input["schema_version"], DAILY_INPUT_SCHEMA_VERSION, "auto daily schema version")
    assert_equal(auto_daily_input["context"]["manual_override_count"], 0, "no manual override count")
    assert_equal(auto_daily_input["context"]["manual_override_fields"], [], "no manual override fields")
    assert_equal(auto_daily_input["context"]["manual_override_applied"], False, "no manual override applied")
    assert_equal(auto_daily_input["context"]["manual_added_fields"], [], "no manual added fields")
    for field_name in ["SC_close", "USD_CNY", "Brent_close", "WTI_close", "EIA_crude_inventory", "important_oil_news"]:
        assert_equal(field_name in auto_daily_input["fields"], True, f"{field_name} should be present")
    assert_equal(auto_daily_input["fields"]["important_oil_news"]["metadata"]["source_status"], "warning", "news warning")
    assert_equal(auto_daily_input["fields"]["EIA_crude_inventory"]["value"], None, "EIA should be explicit empty stub")
    assert_equal(
        auto_daily_input["fields"]["EIA_crude_inventory"]["metadata"]["eia_warning_stub"],
        True,
        "EIA should be explicit warning stub",
    )
    assert_equal(
        auto_daily_input["fields"]["EIA_crude_inventory"]["metadata"]["pending_manual_review"],
        True,
        "EIA should require manual review",
    )
    assert_equal(quality_report["overall_status"], "warning", "auto preflight should produce warning report")
    assert_equal("利多" in markdown, False, "auto report should not contain bullish language")
    assert_equal("利空" in markdown, False, "auto report should not contain bearish language")
    for term in FORBIDDEN_TERMS:
        assert_equal(term in markdown, False, f"auto report should not contain forbidden term {term}")
    assert_equal(len(reports), 1, "research report row should be written")
    assert_equal(reports[0]["report_status"], "warning", "research report status")


def test_auto_daily_passes_business_table_flags_to_pipeline() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        akshare_raw_path = root / "raw" / "akshare_sc.json"
        market_fx_raw_path = root / "raw" / "market_fx.json"
        business_summary_path = root / "processed" / "business_summary.json"
        write_json(akshare_raw_path, build_akshare_raw_data())
        write_json(market_fx_raw_path, build_market_fx_raw_data())
        write_config(root / "config.yaml")

        exit_code = workflow.main(
            workflow_args(
                root,
                akshare_raw_path,
                market_fx_raw_path,
                extra_args=[
                    "--write-business-tables",
                    "--business-write-summary-output",
                    str(business_summary_path),
                ],
            )
        )
        summary = load_json(business_summary_path)
        db_path = root / "sc_oil.sqlite"
        reports = research_report_rows(db_path)
        market_count = table_count(db_path, "market_prices")
        fx_count = table_count(db_path, "fx_rates")
        spread_count = table_count(db_path, "spread_table")
        evidence_count = table_count(db_path, "evidence_database")

    assert_equal(exit_code, 0, "auto daily business write pass-through should succeed")
    assert_equal(summary["research_report_id"], "RPT-AUTO-TEST", "business summary report id")
    assert_equal(summary["market_prices_written"], market_count, "auto daily market rows")
    assert_equal(market_count >= 2, True, "auto daily should write available SC market rows")
    assert_equal(summary["fx_rates_written"], 1, "auto daily fx rows")
    assert_equal(summary["spreads_written"], 1, "auto daily spread rows")
    assert_equal(summary["evidence_written"], evidence_count, "auto daily evidence rows")
    assert_equal(len(reports), 1, "research report written before business tables")
    assert_equal(fx_count, 1, "fx_rates row count")
    assert_equal(spread_count, 1, "spread_table row count")


def test_auto_daily_passes_llm_input_package_flags_to_pipeline() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        akshare_raw_path = root / "raw" / "akshare_sc.json"
        market_fx_raw_path = root / "raw" / "market_fx.json"
        llm_package_path = root / "processed" / "llm_input_package.json"
        write_json(akshare_raw_path, build_akshare_raw_data())
        write_json(market_fx_raw_path, build_market_fx_raw_data())
        write_config(root / "config.yaml")

        exit_code = workflow.main(
            workflow_args(
                root,
                akshare_raw_path,
                market_fx_raw_path,
                extra_args=[
                    "--generate-llm-input-package",
                    "--llm-input-package-output",
                    str(llm_package_path),
                ],
            )
        )
        package = load_json(llm_package_path)

    assert_equal(exit_code, 0, "auto daily LLM package pass-through should succeed")
    assert_equal(package["schema_version"], "llm_input_package_v1", "LLM package schema")
    assert_equal(package["pipeline_status"]["overall_status"], "warning", "LLM package status")
    assert_equal(package["research_report_id"], "RPT-AUTO-TEST", "LLM package report id")
    assert_equal(len(package["field_facts"]) > 0, True, "LLM package field facts")


def test_without_market_fx_raw_input_uses_live_fetch_and_runs_pipeline() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        akshare_raw_path = root / "raw" / "akshare_sc.json"
        write_json(akshare_raw_path, build_akshare_raw_data())
        write_config(root / "config.yaml")
        calls: list[str] = []

        original_market_fx_fetch = workflow.fetch_market_fx_daily

        def fake_live_market_fx(report_date: str) -> dict:
            calls.append(report_date)
            return build_market_fx_fetch_result(
                rows={
                    "date": report_date,
                    "USD_CNY": 7.18,
                    "Brent_close": 82.4,
                    "WTI_close": 78.6,
                    "source_name": "Yahoo Finance via yfinance",
                    "source_level": "third_party",
                    "is_real_provider": True,
                    "url_or_reference": "fixture://mocked-live-market-fx",
                },
                report_date=report_date,
                fetched_at=f"{report_date}T16:30:00+08:00",
            )

        workflow.fetch_market_fx_daily = fake_live_market_fx
        try:
            exit_code = workflow.main(workflow_args_live_market_fx(root, akshare_raw_path))
        finally:
            workflow.fetch_market_fx_daily = original_market_fx_fetch

        auto_daily_input = load_json(root / "manual" / "daily_input.json")
        quality_report_path = root / "processed" / "quality_report.json"
        evidence_list_path = root / "processed" / "evidence_list.json"
        daily_report_path = root / "reports" / "SC_daily.md"
        output_exists = {
            "quality_report": quality_report_path.exists(),
            "evidence_list": evidence_list_path.exists(),
            "daily_report": daily_report_path.exists(),
        }
        reports = research_report_rows(root / "sc_oil.sqlite")

    assert_equal(exit_code, 0, "auto daily workflow should succeed with mocked live market_fx")
    assert_equal(calls, [REPORT_DATE], "live market_fx should be called once")
    assert_equal(output_exists["quality_report"], True, "quality report should be written")
    assert_equal(output_exists["evidence_list"], True, "evidence list should be written")
    assert_equal(output_exists["daily_report"], True, "daily report should be written")
    assert_equal(auto_daily_input["fields"]["USD_CNY"]["metadata"]["source_name"], "Yahoo Finance via yfinance", "live FX source")
    assert_equal(auto_daily_input["fields"]["USD_CNY"]["metadata"]["is_real_provider"], True, "live FX provider marker")
    assert_equal(len(reports), 1, "research report row should be written")


def test_optional_manual_supplement_can_override_default_text_and_add_eia() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        akshare_raw_path = root / "raw" / "akshare_sc.json"
        market_fx_raw_path = root / "raw" / "market_fx.json"
        manual_path = root / "manual" / "manual_supplement.json"
        write_json(akshare_raw_path, build_akshare_raw_data())
        write_json(market_fx_raw_path, build_market_fx_raw_data())
        write_json(manual_path, manual_supplement())
        write_config(root / "config.yaml")

        exit_code = workflow.main(
            workflow_args(root, akshare_raw_path, market_fx_raw_path, extra_args=["--manual-supplement", str(manual_path)])
        )
        auto_daily_input = load_json(root / "manual" / "daily_input.json")

    assert_equal(exit_code, 0, "auto daily workflow with manual supplement")
    assert_equal(auto_daily_input["fields"]["manual_notes"]["value"], "Human reviewed note for auto daily smoke.", "manual override")
    assert_equal(
        auto_daily_input["fields"]["manual_notes"]["metadata"]["merge_source"],
        "manual_supplement_override",
        "manual override source",
    )
    assert_manual_override_metadata(
        auto_daily_input["fields"]["manual_notes"],
        "未提供人工备注；不得用于强结论或交易判断。",
        "Human reviewed note for auto daily smoke.",
        "manual_notes",
    )
    assert_equal(
        auto_daily_input["fields"]["manual_notes"]["metadata"]["previous_source_status"],
        "warning",
        "manual_notes previous source status",
    )
    assert_equal(
        auto_daily_input["fields"]["manual_notes"]["metadata"]["previous_confidence"],
        "low",
        "manual_notes previous confidence",
    )
    assert_equal(
        auto_daily_input["fields"]["manual_notes"]["metadata"]["previous_unit"],
        "text",
        "manual_notes previous unit",
    )
    assert_equal(
        auto_daily_input["fields"]["manual_notes"]["metadata"]["previous_data_time"],
        REPORT_DATE,
        "manual_notes previous data time",
    )
    assert_equal(
        auto_daily_input["fields"]["manual_notes"]["metadata"]["source_name"],
        "manual_supplement",
        "manual text source name default",
    )
    assert_equal(
        auto_daily_input["fields"]["manual_notes"]["metadata"]["confidence"],
        "low",
        "manual text confidence default",
    )
    assert_equal(
        auto_daily_input["fields"]["manual_notes"]["metadata"]["source_status"],
        "warning",
        "manual text override downgraded by default",
    )
    assert_equal(
        auto_daily_input["fields"]["manual_notes"]["metadata"]["pending_manual_review"],
        True,
        "manual text override pending review by default",
    )
    assert_equal(auto_daily_input["fields"]["EIA_crude_inventory"]["value"], 443.2, "manual EIA supplement")
    assert_manual_override_metadata(
        auto_daily_input["fields"]["EIA_crude_inventory"],
        None,
        443.2,
        "EIA_crude_inventory",
    )
    assert_equal(auto_daily_input["context"]["manual_override_count"], 2, "manual override count")
    assert_equal(
        auto_daily_input["context"]["manual_override_fields"],
        ["EIA_crude_inventory", "manual_notes"],
        "manual override fields",
    )
    assert_equal(auto_daily_input["context"]["manual_override_applied"], True, "manual override applied")
    assert_equal(auto_daily_input["context"]["manual_added_fields"], [], "manual added fields")


def test_manual_supplement_can_override_sc_prices_with_audit_by_default() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        akshare_raw_path = root / "raw" / "akshare_sc.json"
        market_fx_raw_path = root / "raw" / "market_fx.json"
        manual_path = root / "manual" / "manual_supplement.json"
        write_json(akshare_raw_path, build_akshare_raw_data())
        write_json(market_fx_raw_path, build_market_fx_raw_data())
        write_json(manual_path, manual_supplement_with_sc_override())
        write_config(root / "config.yaml")

        exit_code = workflow.main(
            workflow_args(root, akshare_raw_path, market_fx_raw_path, extra_args=["--manual-supplement", str(manual_path)])
        )
        auto_daily_input = load_json(root / "manual" / "daily_input.json")

    assert_equal(exit_code, 0, "manual SC price override should be allowed")
    assert_equal(auto_daily_input["fields"]["SC_close"]["value"], 999.0, "manual SC_close override")
    assert_equal(
        auto_daily_input["fields"]["SC_close"]["metadata"]["merge_source"],
        "manual_supplement_override",
        "manual override source",
    )
    assert_manual_override_metadata(auto_daily_input["fields"]["SC_close"], 620.5, 999.0, "SC_close")
    assert_equal(auto_daily_input["fields"]["SC_close"]["metadata"]["previous_source_name"], "AKShare", "SC previous source")
    assert_equal(auto_daily_input["fields"]["SC_close"]["metadata"]["previous_unit"], "CNY/barrel", "SC previous unit")
    assert_equal(
        auto_daily_input["fields"]["SC_close"]["metadata"]["previous_fetched_at"],
        f"{REPORT_DATE}T16:00:00+08:00",
        "SC previous fetched_at",
    )
    assert_equal(auto_daily_input["fields"]["SC_close"]["metadata"]["source_status"], "warning", "SC override warning")
    assert_equal(auto_daily_input["fields"]["SC_close"]["metadata"]["pending_manual_review"], True, "SC override review")


def test_manual_supplement_can_override_fx_prices_with_audit_by_default() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        akshare_raw_path = root / "raw" / "akshare_sc.json"
        market_fx_raw_path = root / "raw" / "market_fx.json"
        manual_path = root / "manual" / "manual_supplement.json"
        write_json(akshare_raw_path, build_akshare_raw_data())
        write_json(market_fx_raw_path, build_market_fx_raw_data())
        write_json(manual_path, manual_supplement_with_fx_overrides())
        write_config(root / "config.yaml")

        exit_code = workflow.main(
            workflow_args(root, akshare_raw_path, market_fx_raw_path, extra_args=["--manual-supplement", str(manual_path)])
        )
        auto_daily_input = load_json(root / "manual" / "daily_input.json")

    assert_equal(exit_code, 0, "manual FX price override should be allowed")
    expected = {
        "USD_CNY": (7.18, 7.99),
        "Brent_close": (82.4, 99.9),
        "WTI_close": (78.6, 95.5),
    }
    for field_name, (previous_value, new_value) in expected.items():
        metadata = auto_daily_input["fields"][field_name]["metadata"]
        assert_equal(metadata["merge_source"], "manual_supplement_override", f"{field_name} manual override source")
        assert_manual_override_metadata(auto_daily_input["fields"][field_name], previous_value, new_value, field_name)
        assert_equal(metadata["previous_source_name"], "market_fx_stub", f"{field_name} previous source name")
        assert_equal(metadata["previous_fetched_at"], f"{REPORT_DATE}T16:30:00+08:00", f"{field_name} previous fetched_at")
        assert_equal(metadata["source_status"], "warning", f"{field_name} override warning")
        assert_equal(metadata["pending_manual_review"], True, f"{field_name} override review")


def test_manual_supplement_override_preserves_reviewed_metadata() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        akshare_raw_path = root / "raw" / "akshare_sc.json"
        market_fx_raw_path = root / "raw" / "market_fx.json"
        manual_path = root / "manual" / "manual_supplement.json"
        supplement = manual_supplement_with_sc_override()
        supplement["fields"]["SC_close"]["metadata"]["source_status"] = "pass"
        supplement["fields"]["SC_close"]["metadata"]["human_reviewed"] = True
        supplement["fields"]["SC_close"]["metadata"]["pending_manual_review"] = False
        write_json(akshare_raw_path, build_akshare_raw_data())
        write_json(market_fx_raw_path, build_market_fx_raw_data())
        write_json(manual_path, supplement)
        write_config(root / "config.yaml")

        exit_code = workflow.main(
            workflow_args(root, akshare_raw_path, market_fx_raw_path, extra_args=["--manual-supplement", str(manual_path)])
        )
        auto_daily_input = load_json(root / "manual" / "daily_input.json")

    metadata = auto_daily_input["fields"]["SC_close"]["metadata"]
    assert_equal(exit_code, 0, "reviewed manual override should be allowed")
    assert_equal(metadata["source_status"], "pass", "reviewed manual override keeps pass")
    assert_equal(metadata["pending_manual_review"], False, "reviewed manual override clears pending review")
    assert_equal(metadata["human_reviewed"], True, "reviewed marker preserved")
    assert_manual_override_metadata(auto_daily_input["fields"]["SC_close"], 620.5, 999.0, "SC_close")


def test_manual_supplement_can_override_calculated_field_with_manual_override_method() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        akshare_raw_path = root / "raw" / "akshare_sc.json"
        market_fx_raw_path = root / "raw" / "market_fx.json"
        manual_path = root / "manual" / "manual_supplement.json"
        write_json(akshare_raw_path, build_akshare_raw_data())
        write_json(market_fx_raw_path, build_market_fx_raw_data())
        write_json(manual_path, manual_supplement_with_calculated_override())
        write_config(root / "config.yaml")

        exit_code = workflow.main(
            workflow_args(root, akshare_raw_path, market_fx_raw_path, extra_args=["--manual-supplement", str(manual_path)])
        )
        calculated_input = load_json(root / "processed" / "calculated_input.json")

    assert_equal(exit_code, 0, "manual calculated field override should be allowed")
    expected = {
        "SC_USD": 88.88,
        "SC_calendar_spread": 12.34,
        "SC_Brent_spread_simple": 6.78,
        "SC_WTI_spread_simple": 9.87,
    }
    for field_name, value in expected.items():
        assert_equal(calculated_input["fields"][field_name]["value"], value, f"manual {field_name} preserved")
        metadata = calculated_input["fields"][field_name]["metadata"]
        assert_manual_override_metadata(calculated_input["fields"][field_name], None, value, field_name)
        assert_equal(metadata["merge_source"], "manual_supplement_override", f"{field_name} manual override source")
        assert_equal(metadata["calculation_method"], "manual_override", f"{field_name} manual calculation method")
        assert_equal(metadata["calculation_version"], "manual_override_v1", f"{field_name} manual calculation version")
        assert_equal(metadata["source_status"], "warning", f"{field_name} manual calculated override warning")
        assert_equal(metadata["confidence"], "low", f"{field_name} manual calculated confidence")
        assert_equal(metadata["pending_manual_review"], True, f"{field_name} manual calculated override review")
    assert_equal(
        calculated_input["context"]["manual_override_fields"],
        ["EIA_crude_inventory", "SC_Brent_spread_simple", "SC_USD", "SC_WTI_spread_simple", "SC_calendar_spread", "manual_notes"],
        "manual calculated override fields",
    )


def test_manual_supplement_can_add_new_field_without_override_marker() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        akshare_raw_path = root / "raw" / "akshare_sc.json"
        market_fx_raw_path = root / "raw" / "market_fx.json"
        manual_path = root / "manual" / "manual_supplement.json"
        write_json(akshare_raw_path, build_akshare_raw_data())
        write_json(market_fx_raw_path, build_market_fx_raw_data())
        write_json(manual_path, manual_supplement_with_added_field())
        write_config(root / "config.yaml")

        exit_code = workflow.main(
            workflow_args(root, akshare_raw_path, market_fx_raw_path, extra_args=["--manual-supplement", str(manual_path)])
        )
        auto_daily_input = load_json(root / "manual" / "daily_input.json")

    field_payload = auto_daily_input["fields"]["analyst_custom_observation"]
    metadata = field_payload["metadata"]
    assert_equal(exit_code, 0, "manual added field should be allowed")
    assert_equal(field_payload["value"], "Manual-only observation for audit trail.", "manual added field value")
    assert_equal(metadata["merge_source"], "manual_supplement_added", "manual added merge source")
    assert_equal("manual_override_used" in metadata, False, "manual added field should not be an override")
    assert_equal(metadata["source_name"], "manual_supplement", "manual added source name default")
    assert_equal(metadata["source_status"], "warning", "manual added source status default")
    assert_equal(metadata["confidence"], "low", "manual added confidence default")
    assert_equal(metadata["pending_manual_review"], True, "manual added pending review default")
    assert_equal(auto_daily_input["context"]["manual_added_fields"], ["analyst_custom_observation"], "manual added fields")
    assert_equal(
        auto_daily_input["context"]["manual_override_fields"],
        ["EIA_crude_inventory", "manual_notes"],
        "manual overrides exclude added field",
    )


def test_akshare_fail_returns_controlled_data_failure_without_pipeline_outputs() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        akshare_raw_path = root / "raw" / "akshare_sc_fail.json"
        market_fx_raw_path = root / "raw" / "market_fx.json"
        write_json(akshare_raw_path, build_akshare_raw_fail())
        write_json(market_fx_raw_path, build_market_fx_raw_data())
        write_config(root / "config.yaml")

        exit_code = workflow.main(workflow_args(root, akshare_raw_path, market_fx_raw_path))
        akshare_conversion_result_exists = (root / "processed" / "akshare_conversion_result.json").exists()
        auto_daily_input_exists = (root / "manual" / "daily_input.json").exists()
        quality_report_exists = (root / "processed" / "quality_report.json").exists()
        evidence_list_exists = (root / "processed" / "evidence_list.json").exists()
        db_exists = (root / "sc_oil.sqlite").exists()

    assert_equal(exit_code, 2, "AKShare fail should be controlled data failure")
    assert_equal(akshare_conversion_result_exists, True, "AKShare conversion result should be written")
    assert_equal(auto_daily_input_exists, False, "final daily input should not be written")
    assert_equal(quality_report_exists, False, "pipeline should not run")
    assert_equal(evidence_list_exists, False, "evidence should not be written")
    assert_equal(db_exists, False, "DB should not be initialized")


def test_market_fx_recent_fallback_runs_warning_and_marks_metadata() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        akshare_raw_path = root / "raw" / "akshare_sc.json"
        market_fx_raw_path = root / "raw" / "market_fx_fallback.json"
        write_json(akshare_raw_path, build_akshare_raw_data())
        write_json(market_fx_raw_path, build_market_fx_raw_fallback())
        write_config(root / "config.yaml")

        exit_code = workflow.main(workflow_args(root, akshare_raw_path, market_fx_raw_path))
        market_fx_daily_input = load_json(root / "processed" / "market_fx_daily_input.json")
        quality_report = load_json(root / "processed" / "quality_report.json")

    assert_equal(exit_code, 0, "fallback market/fx should still run auto daily")
    assert_equal(quality_report["overall_status"], "warning", "fallback market/fx should downgrade report")
    for field_name in ["USD_CNY", "Brent_close", "WTI_close"]:
        metadata = market_fx_daily_input["fields"][field_name]["metadata"]
        assert_equal(metadata["fallback_used"], True, f"{field_name} fallback marker")
        assert_equal(metadata["date"], "2026-01-14", f"{field_name} fallback date")


def test_market_fx_fail_returns_controlled_data_failure_without_pipeline_outputs() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        akshare_raw_path = root / "raw" / "akshare_sc.json"
        market_fx_raw_path = root / "raw" / "market_fx_fail.json"
        write_json(akshare_raw_path, build_akshare_raw_data())
        write_json(market_fx_raw_path, build_market_fx_raw_fail())
        write_config(root / "config.yaml")

        exit_code = workflow.main(workflow_args(root, akshare_raw_path, market_fx_raw_path))
        market_fx_conversion_result_exists = (root / "processed" / "market_fx_conversion_result.json").exists()
        auto_daily_input_exists = (root / "manual" / "daily_input.json").exists()
        quality_report_exists = (root / "processed" / "quality_report.json").exists()
        evidence_list_exists = (root / "processed" / "evidence_list.json").exists()
        db_exists = (root / "sc_oil.sqlite").exists()

    assert_equal(exit_code, 2, "market/fx fail should be controlled data failure")
    assert_equal(market_fx_conversion_result_exists, True, "market/fx conversion result should be written")
    assert_equal(auto_daily_input_exists, False, "final daily input should not be written")
    assert_equal(quality_report_exists, False, "pipeline should not run")
    assert_equal(evidence_list_exists, False, "evidence should not be written")
    assert_equal(db_exists, False, "DB should not be initialized")


def run() -> None:
    tests = [
        test_without_manual_supplement_runs_warning_daily_report_without_fetching,
        test_auto_daily_passes_business_table_flags_to_pipeline,
        test_auto_daily_passes_llm_input_package_flags_to_pipeline,
        test_without_market_fx_raw_input_uses_live_fetch_and_runs_pipeline,
        test_optional_manual_supplement_can_override_default_text_and_add_eia,
        test_manual_supplement_can_override_sc_prices_with_audit_by_default,
        test_manual_supplement_can_override_fx_prices_with_audit_by_default,
        test_manual_supplement_override_preserves_reviewed_metadata,
        test_manual_supplement_can_override_calculated_field_with_manual_override_method,
        test_manual_supplement_can_add_new_field_without_override_marker,
        test_akshare_fail_returns_controlled_data_failure_without_pipeline_outputs,
        test_market_fx_recent_fallback_runs_warning_and_marks_metadata,
        test_market_fx_fail_returns_controlled_data_failure_without_pipeline_outputs,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
