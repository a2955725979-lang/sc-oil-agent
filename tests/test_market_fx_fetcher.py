"""Smoke tests for src/fetchers/market_fx.py.

Run from the project root:
    python tests/test_market_fx_fetcher.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetchers.base import DAILY_INPUT_SCHEMA_VERSION, RAW_DATA_CONTRACT_VERSION, validate_raw_data_contract  # noqa: E402
from src.fetchers.market_fx import build_fetch_result_from_rows, fetch_market_fx_daily  # noqa: E402
from src.fetchers.providers.market_fx_provider import fetch_market_fx_live_rows  # noqa: E402
from src.fetchers.transform import convert_raw_data_to_daily_input  # noqa: E402


REPORT_DATE = "2026-05-22"
FETCHED_AT = "2026-05-22T16:30:00+08:00"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(items: list[str], expected_fragment: str, message: str) -> None:
    if not any(expected_fragment in item for item in items):
        raise AssertionError(f"{message}: {expected_fragment!r} not found in {items!r}")


def fixture_row(report_date: str = REPORT_DATE) -> dict:
    return {
        "date": report_date,
        "USD_CNY": 7.18,
        "Brent_close": 82.4,
        "WTI_close": 78.6,
        "source_name": "fixture_market_fx",
        "url_or_reference": "fixture://market_fx",
    }


class FakeMarketFxClient:
    def __init__(self, histories: dict[str, list[dict] | Exception]) -> None:
        self.histories = histories
        self.calls: list[str] = []

    def history(self, symbol: str, start: str, end: str) -> list[dict]:
        self.calls.append(symbol)
        result = self.histories.get(symbol, [])
        if isinstance(result, Exception):
            raise result
        return result


def history_row(date: str, close: float) -> dict:
    return {"Date": date, "Close": close}


def fake_success_client(report_date: str = REPORT_DATE) -> FakeMarketFxClient:
    return FakeMarketFxClient(
        {
            "CNY=X": [history_row(report_date, 7.18)],
            "BZ=F": [history_row(report_date, 82.4)],
            "CL=F": [history_row(report_date, 78.6)],
        }
    )


def test_fixture_rows_emit_frozen_raw_data_contract() -> None:
    raw_data = build_fetch_result_from_rows(fixture_row(), REPORT_DATE, FETCHED_AT)
    fields = [record["field"] for record in raw_data["records"]]
    first_metadata = raw_data["records"][0]["metadata"]

    assert_equal(raw_data["contract_version"], RAW_DATA_CONTRACT_VERSION, "raw_data contract version")
    assert_equal(raw_data["fetch_status"], "pass", "fixture raw_data status")
    assert_equal(fields, ["USD_CNY", "Brent_close", "WTI_close"], "market/fx fields")
    assert_equal(validate_raw_data_contract(raw_data), [], "raw_data contract errors")
    assert_equal(raw_data["source_name"], "market_fx_stub", "stub source name")
    assert_equal(first_metadata["source_name"], "market_fx_stub", "source name metadata")
    assert_equal(first_metadata["source_field"], "usd_cny", "source field metadata")
    assert_equal(first_metadata["source_level"], "test", "source level metadata")
    assert_equal(first_metadata["is_real_provider"], False, "stub provider marker")
    assert_equal(first_metadata["source_status"], "pass", "stub source status")
    assert_equal(first_metadata["confidence"], "medium", "stub confidence")
    assert_equal(first_metadata["data_time"], REPORT_DATE, "stub data time")
    assert_equal(first_metadata["fallback_used"], False, "fresh stub fallback marker")
    assert_equal(first_metadata["fetched_at"], FETCHED_AT, "fetched_at metadata")
    assert_equal(first_metadata["url_or_reference"], "fixture://market_fx", "reference metadata")


def test_live_provider_success_with_mocked_yfinance_client() -> None:
    raw_data = fetch_market_fx_daily(REPORT_DATE, fetched_at=FETCHED_AT, provider_client=fake_success_client())
    fields = {record["field"]: record for record in raw_data["records"]}

    assert_equal(raw_data["contract_version"], RAW_DATA_CONTRACT_VERSION, "raw_data contract version")
    assert_equal(raw_data["fetch_status"], "pass", "live provider status")
    assert_equal(raw_data["source_name"], "Yahoo Finance via yfinance", "live source name")
    assert_equal(validate_raw_data_contract(raw_data), [], "raw_data contract errors")
    assert_equal(sorted(fields), ["Brent_close", "USD_CNY", "WTI_close"], "live fields")
    assert_equal(fields["USD_CNY"]["metadata"]["unit"], "CNY/USD", "USD_CNY unit")
    assert_equal(fields["Brent_close"]["metadata"]["unit"], "USD/barrel", "Brent unit")
    assert_equal(fields["WTI_close"]["metadata"]["unit"], "USD/barrel", "WTI unit")
    for field_name, payload in fields.items():
        metadata = payload["metadata"]
        assert_equal(metadata["is_real_provider"], True, f"{field_name} real provider marker")
        assert_equal(metadata["source_level"], "third_party", f"{field_name} source level")
        assert_equal(metadata["source_status"], "pass", f"{field_name} source status")
        assert_equal(metadata["confidence"], "medium", f"{field_name} confidence")
        assert_equal(metadata["fallback_used"], False, f"{field_name} fallback marker")
        assert_equal(bool(metadata["provider_metadata"]), True, f"{field_name} provider metadata")


def test_live_provider_tries_usdcny_symbol_if_primary_cny_symbol_missing() -> None:
    client = FakeMarketFxClient(
        {
            "CNY=X": [],
            "USDCNY=X": [history_row(REPORT_DATE, 7.19)],
            "BZ=F": [history_row(REPORT_DATE, 82.4)],
            "CL=F": [history_row(REPORT_DATE, 78.6)],
        }
    )

    raw_data = fetch_market_fx_daily(REPORT_DATE, fetched_at=FETCHED_AT, provider_client=client)
    usd_record = next(record for record in raw_data["records"] if record["field"] == "USD_CNY")
    metadata = usd_record["metadata"]

    assert_equal(raw_data["fetch_status"], "pass", "USDCNY fallback symbol should fetch")
    assert_equal(usd_record["value"], 7.19, "USDCNY fallback value")
    assert_equal(metadata["source_field"], "USDCNY=X", "same-provider fallback symbol")
    assert_equal(metadata["provider_metadata"]["attempted_symbols"], ["CNY=X", "USDCNY=X"], "attempted symbols")
    assert_equal(client.calls[:2], ["CNY=X", "USDCNY=X"], "CNY symbol attempted first")


def test_live_provider_fails_when_both_usd_cny_symbols_missing() -> None:
    client = FakeMarketFxClient(
        {
            "CNY=X": [],
            "USDCNY=X": [],
            "BZ=F": [history_row(REPORT_DATE, 82.4)],
            "CL=F": [history_row(REPORT_DATE, 78.6)],
        }
    )

    raw_data = fetch_market_fx_daily(REPORT_DATE, fetched_at=FETCHED_AT, provider_client=client)

    assert_equal(raw_data["fetch_status"], "fail", "missing USD_CNY symbols should fail")
    assert_equal(raw_data["records"], [], "failed live provider should not emit placeholder records")
    assert_contains(raw_data["errors"], "USD_CNY", "USD_CNY error")
    assert_contains(raw_data["errors"], "CNY=X", "primary CNY symbol error")
    assert_contains(raw_data["errors"], "USDCNY=X", "fallback CNY symbol error")


def test_live_provider_latest_available_previous_trading_day_is_warning_fallback() -> None:
    client = FakeMarketFxClient(
        {
            "CNY=X": [history_row("2026-05-22", 7.18)],
            "BZ=F": [history_row("2026-05-22", 82.4)],
            "CL=F": [history_row("2026-05-22", 78.6)],
        }
    )

    raw_data = fetch_market_fx_daily("2026-05-24", fetched_at=FETCHED_AT, provider_client=client)

    assert_equal(raw_data["fetch_status"], "warning", "weekend latest available should be warning")
    for record in raw_data["records"]:
        metadata = record["metadata"]
        assert_equal(metadata["fallback_used"], True, f"{record['field']} fallback marker")
        assert_equal(metadata["source_status"], "warning", f"{record['field']} warning status")
        assert_equal(metadata["confidence"], "low", f"{record['field']} fallback confidence")
        assert_equal(metadata["original_report_date"], "2026-05-24", f"{record['field']} original date")
        assert_equal(metadata["actual_data_date"], "2026-05-22", f"{record['field']} actual date")
        assert_equal("data_alignment_note" in metadata, True, f"{record['field']} alignment note")


def test_live_provider_required_brent_missing_returns_controlled_fail() -> None:
    client = FakeMarketFxClient(
        {
            "CNY=X": [history_row(REPORT_DATE, 7.18)],
            "BZ=F": [],
            "CL=F": [history_row(REPORT_DATE, 78.6)],
        }
    )

    raw_data = fetch_market_fx_daily(REPORT_DATE, fetched_at=FETCHED_AT, provider_client=client)

    assert_equal(raw_data["fetch_status"], "fail", "missing Brent should fail")
    assert_equal(raw_data["records"], [], "failed live provider should not silently omit Brent")
    assert_contains(raw_data["errors"], "Brent_close", "Brent error")


def test_latest_available_date_marks_warning_and_fallback_metadata() -> None:
    raw_data = build_fetch_result_from_rows(fixture_row("2026-05-21"), REPORT_DATE, FETCHED_AT)
    usd_metadata = raw_data["records"][0]["metadata"]

    assert_equal(raw_data["fetch_status"], "warning", "stale row should mark warning")
    assert_equal(usd_metadata["fallback_used"], True, "fallback marker")
    assert_equal(usd_metadata["original_report_date"], REPORT_DATE, "fallback original report date")
    assert_equal(usd_metadata["actual_data_date"], "2026-05-21", "fallback actual data date")
    assert_equal("data_alignment_note" in usd_metadata, True, "fallback alignment note")
    assert_contains(raw_data["warnings"], "using latest available date", "stale date warning")


def test_missing_field_returns_structured_fail() -> None:
    row = fixture_row()
    row.pop("WTI_close")
    raw_data = build_fetch_result_from_rows(row, REPORT_DATE, FETCHED_AT)

    assert_equal(raw_data["fetch_status"], "fail", "missing required field should fail")
    assert_equal([record["field"] for record in raw_data["records"]], ["USD_CNY", "Brent_close"], "valid records remain")
    assert_contains(raw_data["errors"], "WTI_close", "missing WTI error")


def test_provider_exception_returns_structured_fail() -> None:
    def broken_provider(_report_date: str) -> list[dict]:
        raise RuntimeError("provider unavailable")

    raw_data = fetch_market_fx_daily(REPORT_DATE, rows_provider=broken_provider, fetched_at=FETCHED_AT)

    assert_equal(raw_data["fetch_status"], "fail", "provider exception should be structured fail")
    assert_equal(raw_data["records"], [], "provider exception should not emit records")
    assert_contains(raw_data["errors"], "provider unavailable", "provider error message")


def test_output_can_transform_to_daily_input_schema_v1() -> None:
    raw_data = build_fetch_result_from_rows(fixture_row(), REPORT_DATE, FETCHED_AT)
    conversion = convert_raw_data_to_daily_input(raw_data)
    daily_input = conversion["daily_input"]

    assert_equal(conversion["usable_for_pipeline"], True, "market/fx conversion should be usable")
    assert_equal(conversion["conversion_errors"], [], "market/fx conversion errors")
    assert_equal(daily_input["schema_version"], DAILY_INPUT_SCHEMA_VERSION, "daily_input schema version")
    assert_equal(sorted(daily_input["fields"].keys()), ["Brent_close", "USD_CNY", "WTI_close"], "converted fields")


def test_provider_adapter_can_emit_normalized_rows_without_building_contract() -> None:
    rows = fetch_market_fx_live_rows(REPORT_DATE, client=fake_success_client())

    assert_equal(rows["USD_CNY"], 7.18, "adapter USD_CNY value")
    assert_equal(rows["Brent_close"], 82.4, "adapter Brent value")
    assert_equal(rows["WTI_close"], 78.6, "adapter WTI value")
    assert_equal(rows["field_metadata"]["USD_CNY"]["source_field"], "CNY=X", "adapter source field")
    assert_equal(rows["field_metadata"]["USD_CNY"]["confidence"], "medium", "adapter confidence")


def run() -> None:
    tests = [
        test_fixture_rows_emit_frozen_raw_data_contract,
        test_live_provider_success_with_mocked_yfinance_client,
        test_live_provider_tries_usdcny_symbol_if_primary_cny_symbol_missing,
        test_live_provider_fails_when_both_usd_cny_symbols_missing,
        test_live_provider_latest_available_previous_trading_day_is_warning_fallback,
        test_live_provider_required_brent_missing_returns_controlled_fail,
        test_latest_available_date_marks_warning_and_fallback_metadata,
        test_missing_field_returns_structured_fail,
        test_provider_exception_returns_structured_fail,
        test_output_can_transform_to_daily_input_schema_v1,
        test_provider_adapter_can_emit_normalized_rows_without_building_contract,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
