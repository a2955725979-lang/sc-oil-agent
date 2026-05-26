"""Smoke tests for src/validators/quality_checks.py.

Run from the project root:
    python tests/test_quality_checks.py
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.validators.quality_checks import (  # noqa: E402
    aggregate_status,
    validate_field,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_contains(items: list[str], expected_fragment: str, message: str) -> None:
    if not any(expected_fragment in item for item in items):
        raise AssertionError(f"{message}: {expected_fragment!r} not found in {items!r}")


def test_required_missing_without_downgrade_fails() -> None:
    result = validate_field(
        "SC_close",
        None,
        metadata={},
        rule_config={
            "required": True,
            "quality_checks": ["missing_check"],
            "fail_action": "report_as_missing",
        },
    )
    assert_equal(result["source_status"], "fail", "required missing field should fail")


def test_required_missing_fails_even_without_explicit_missing_check() -> None:
    result = validate_field(
        "SC_close",
        None,
        metadata={},
        rule_config={
            "required": True,
            "quality_checks": ["range_check"],
            "fail_action": "report_as_missing",
        },
    )
    assert_equal(result["source_status"], "fail", "missing base status should always apply")


def test_required_missing_with_downgrade_warns() -> None:
    result = validate_field(
        "Brent_close",
        None,
        metadata={},
        rule_config={
            "required": True,
            "quality_checks": ["missing_check"],
            "fail_action": "use_latest_with_warning",
        },
    )
    assert_equal(result["source_status"], "warning", "downgradable required missing field")


def test_eia_explicit_warning_stub_warns_not_fails() -> None:
    result = validate_field(
        "EIA_crude_inventory",
        None,
        metadata={
            "source_status": "warning",
            "confidence": "low",
            "eia_warning_stub": True,
            "fallback_used": True,
            "pending_manual_review": True,
        },
        rule_config={
            "required": True,
            "quality_checks": ["missing_check", "stale_check", "revision_check"],
            "fail_action": "report_as_missing",
        },
    )
    assert_equal(result["source_status"], "warning", "explicit EIA stub should warn")
    assert_contains(result["warnings"], "not confirmed inventory data", "stub warning should be explicit")


def test_eia_null_without_explicit_stub_can_still_fail() -> None:
    result = validate_field(
        "EIA_crude_inventory",
        None,
        metadata={"source_status": "warning", "fallback_used": True},
        rule_config={
            "required": True,
            "quality_checks": ["missing_check"],
            "fail_action": "report_as_missing",
        },
    )
    assert_equal(result["source_status"], "fail", "plain null EIA should not pass as stub")


def test_optional_allow_empty_passes() -> None:
    result = validate_field(
        "manual_notes",
        "",
        metadata={},
        rule_config={
            "required": False,
            "quality_checks": ["missing_check"],
            "fail_action": "allow_empty",
        },
    )
    assert_equal(result["source_status"], "pass", "allow_empty should pass when missing")


def test_optional_write_no_update_passes() -> None:
    result = validate_field(
        "exchange_notice",
        None,
        metadata={},
        rule_config={
            "required": False,
            "quality_checks": ["missing_check"],
            "fail_action": "write_no_update",
        },
    )
    assert_equal(result["source_status"], "pass", "write_no_update should pass when missing")


def test_optional_lower_confidence_warns() -> None:
    result = validate_field(
        "important_oil_news",
        None,
        metadata={},
        rule_config={
            "required": False,
            "quality_checks": ["missing_check"],
            "fail_action": "lower_confidence",
        },
    )
    assert_equal(result["source_status"], "warning", "lower_confidence should warn")


def test_context_required_for_topic_upgrades_missing_to_fail() -> None:
    result = validate_field(
        "OPEC_monthly_summary",
        None,
        metadata={},
        rule_config={
            "required": False,
            "quality_checks": ["missing_check"],
            "fail_action": "mark_missing",
        },
        context={
            "required_for_topic": ["OPEC_monthly_summary", "important_oil_news"],
            "report_date": "2026-05-22",
        },
    )
    assert_equal(result["source_status"], "fail", "topic-required missing field should fail")


def test_context_required_for_topic_accepts_string_but_standard_is_list() -> None:
    result = validate_field(
        "important_oil_news",
        None,
        metadata={},
        rule_config={
            "required": False,
            "quality_checks": ["missing_check"],
            "fail_action": "lower_confidence",
        },
        context={"required_for_topic": "important_oil_news"},
    )
    assert_equal(result["source_status"], "fail", "string context should be normalized")


def test_aggregate_status_fail_wins() -> None:
    assert_equal(
        aggregate_status(["pass", "warning", "fail"]),
        "fail",
        "fail should dominate aggregation",
    )


def test_aggregate_status_warning_wins_without_fail() -> None:
    assert_equal(
        aggregate_status(["pass", "warning"]),
        "warning",
        "warning should dominate pass",
    )


def test_range_check_uses_explicit_configured_range() -> None:
    result = validate_field(
        "USD_CNY",
        11.0,
        metadata={},
        rule_config={"required": True, "quality_checks": ["range_check"]},
    )
    assert_equal(result["source_status"], "fail", "USD_CNY outside explicit range should fail")
    assert_contains(result["errors"], "outside configured range", "range error should be explicit")


def test_range_check_unconfigured_field_passes() -> None:
    result = validate_field(
        "unknown_price_like_name",
        999999.0,
        metadata={},
        rule_config={"required": False, "quality_checks": ["range_check"]},
    )
    assert_equal(result["source_status"], "pass", "unconfigured range should pass")


def test_price_range_check_detects_outlier() -> None:
    result = validate_field(
        "SC_close",
        10.0,
        metadata={},
        rule_config={"required": True, "quality_checks": ["range_check"]},
    )
    assert_equal(result["source_status"], "fail", "SC_close outlier should fail")


def test_unit_mismatch_fails() -> None:
    result = validate_field(
        "SC_close",
        600.0,
        metadata={"unit": "USD/barrel"},
        rule_config={"required": True, "unit": "CNY/barrel", "quality_checks": ["unit_check"]},
    )
    assert_equal(result["source_status"], "fail", "unit mismatch should fail")


def test_spread_date_mismatch_warns() -> None:
    result = validate_field(
        "SC_Brent_spread_simple",
        3.2,
        metadata={
            "sc_date": "2026-05-22",
            "external_date": "2026-05-21",
            "fx_date": "2026-05-22",
        },
        rule_config={"required": True, "quality_checks": ["spread_check"]},
    )
    assert_equal(result["source_status"], "warning", "spread date mismatch should warn")


def test_stale_daily_data_warns() -> None:
    result = validate_field(
        "SC_close",
        600.0,
        metadata={"date": "2026-05-01"},
        rule_config={"required": True, "frequency": "daily", "quality_checks": ["stale_check"]},
        context={"report_date": "2026-05-22"},
    )
    assert_equal(result["source_status"], "warning", "stale daily data should warn")


def test_timezone_missing_warns() -> None:
    result = validate_field(
        "Brent_close",
        82.0,
        metadata={},
        rule_config={"required": True, "quality_checks": ["timezone_check"]},
    )
    assert_equal(result["source_status"], "warning", "missing timezone should warn")


def test_source_conflict_placeholder_warns() -> None:
    result = validate_field(
        "OPEC_monthly_summary",
        "summary",
        metadata={},
        rule_config={"required": False, "quality_checks": ["source_conflict_check"]},
    )
    assert_equal(result["source_status"], "warning", "source conflict placeholder should warn")
    assert_contains(result["warnings"], "v1 placeholder", "placeholder warning should be explicit")


def test_revision_placeholder_warns() -> None:
    result = validate_field(
        "EIA_crude_inventory",
        443.2,
        metadata={},
        rule_config={"required": True, "quality_checks": ["revision_check"]},
    )
    assert_equal(result["source_status"], "warning", "revision placeholder should warn")
    assert_contains(result["warnings"], "v1 placeholder", "placeholder warning should be explicit")


def run() -> None:
    tests = [
        test_required_missing_without_downgrade_fails,
        test_required_missing_fails_even_without_explicit_missing_check,
        test_required_missing_with_downgrade_warns,
        test_optional_allow_empty_passes,
        test_optional_write_no_update_passes,
        test_optional_lower_confidence_warns,
        test_context_required_for_topic_upgrades_missing_to_fail,
        test_context_required_for_topic_accepts_string_but_standard_is_list,
        test_aggregate_status_fail_wins,
        test_aggregate_status_warning_wins_without_fail,
        test_range_check_uses_explicit_configured_range,
        test_range_check_unconfigured_field_passes,
        test_price_range_check_detects_outlier,
        test_unit_mismatch_fails,
        test_spread_date_mismatch_warns,
        test_stale_daily_data_warns,
        test_timezone_missing_warns,
        test_source_conflict_placeholder_warns,
        test_revision_placeholder_warns,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run()
