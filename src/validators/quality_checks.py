"""Data quality checks for SC oil research inputs.

The module is intentionally dependency-free. It validates already-fetched
values and returns a normalized source_status that later fetchers, database
writers, and report generators can consume.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


VALID_STATUSES = {"pass", "warning", "fail"}

FIELD_RANGES = {
    "USD_CNY": {"min": 4.0, "max": 10.0},
    "SC_close": {"min": 100.0, "max": 1500.0},
    "SC_settlement": {"min": 100.0, "max": 1500.0},
    "SC_near_price": {"min": 100.0, "max": 1500.0},
    "SC_next_price": {"min": 100.0, "max": 1500.0},
    "Brent_close": {"min": 0.0, "max": 300.0},
    "WTI_close": {"min": -100.0, "max": 300.0},
}

WARNING_FAIL_ACTIONS = {
    "mark_warning",
    "skip_calculation",
    "use_close_with_warning",
    "use_latest_with_warning",
    "use_mid_price_with_warning",
    "use_previous_with_warning",
}

PASS_FAIL_ACTIONS = {"allow_empty", "write_no_update"}
WARNING_OPTIONAL_FAIL_ACTIONS = {"lower_confidence", "mark_missing"}

STALE_LIMIT_DAYS = {
    "daily": 3,
    "weekly": 10,
    "monthly": 45,
}


def validate_field(
    field_name: str,
    value: Any,
    metadata: dict[str, Any] | None,
    rule_config: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate one field and return a normalized status report."""

    metadata = metadata or {}
    rule_config = rule_config or {}
    context = context or {}
    required_for_topic = _required_for_topic_set(context)

    check_names = rule_config.get("quality_checks") or []
    if isinstance(check_names, str):
        check_names = [check_names]

    results = []
    if _is_missing(value) or "missing_check" in check_names:
        if _is_explicit_warning_stub(field_name, value, metadata):
            results.append(
                _result(
                    "warning",
                    warnings=[
                        f"{field_name} is unavailable but explicitly marked as warning stub; "
                        "not confirmed inventory data"
                    ],
                )
            )
        else:
            results.append(_missing_check(field_name, value, rule_config, required_for_topic))

    if not _is_missing(value):
        for check_name in check_names:
            if check_name == "missing_check":
                continue
            check = CHECKS.get(check_name)
            if check is None:
                results.append(
                    _result(
                        "warning",
                        warnings=[f"{check_name} is not implemented in quality_checks v1"],
                    )
                )
                continue
            results.append(check(field_name, value, metadata, rule_config, context))

    status = aggregate_status(result["source_status"] for result in results)
    warnings = [warning for result in results for warning in result["warnings"]]
    errors = [error for result in results for error in result["errors"]]

    return {
        "field": field_name,
        "source_status": status,
        "warnings": warnings,
        "errors": errors,
    }


def aggregate_status(statuses: Any) -> str:
    """Aggregate check statuses using fail > warning > pass."""

    status_set = set(statuses)
    unknown = status_set - VALID_STATUSES
    if unknown:
        raise ValueError(f"Unknown quality status: {sorted(unknown)}")
    if "fail" in status_set:
        return "fail"
    if "warning" in status_set:
        return "warning"
    return "pass"


def missing_check(
    field_name: str,
    value: Any,
    rule_config: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Public wrapper for the missing-value rule."""

    return _missing_check(
        field_name,
        value,
        rule_config or {},
        _required_for_topic_set(context or {}),
    )


def stale_check(
    field_name: str,
    value: Any,
    metadata: dict[str, Any] | None,
    rule_config: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    rule_config = rule_config or {}
    context = context or {}
    frequency = rule_config.get("frequency")
    if frequency == "ad_hoc":
        return _result("pass")

    observed_date = _parse_date(
        metadata.get("data_date")
        or metadata.get("date")
        or metadata.get("publish_time")
        or metadata.get("update_time")
    )
    report_date = _parse_date(context.get("report_date")) or date.today()
    if observed_date is None:
        return _result("warning", warnings=[f"{field_name} has no data date for stale_check"])

    limit_days = STALE_LIMIT_DAYS.get(str(frequency), STALE_LIMIT_DAYS["daily"])
    age_days = (report_date - observed_date).days
    if age_days < 0:
        return _result("warning", warnings=[f"{field_name} data date is after report_date"])
    if age_days > limit_days:
        return _result(
            "warning",
            warnings=[f"{field_name} is stale: {age_days} days old, limit is {limit_days}"],
        )
    return _result("pass")


def range_check(
    field_name: str,
    value: Any,
    metadata: dict[str, Any] | None,
    rule_config: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    field_range = FIELD_RANGES.get(field_name)
    if field_range is None:
        return _result("pass")

    number = _to_float(value)
    if number is None:
        return _result("fail", errors=[f"{field_name} is not numeric for range_check"])

    lower = field_range["min"]
    upper = field_range["max"]
    if number < lower or number > upper:
        return _result(
            "fail",
            errors=[f"{field_name}={number} outside configured range [{lower}, {upper}]"],
        )
    return _result("pass")


def unit_check(
    field_name: str,
    value: Any,
    metadata: dict[str, Any] | None,
    rule_config: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    rule_config = rule_config or {}
    expected_unit = rule_config.get("unit")
    observed_unit = metadata.get("unit")

    if not expected_unit:
        return _result("pass")
    if not observed_unit:
        return _result("warning", warnings=[f"{field_name} has no observed unit"])
    if str(observed_unit) != str(expected_unit):
        return _result(
            "fail",
            errors=[f"{field_name} unit mismatch: expected {expected_unit}, got {observed_unit}"],
        )
    return _result("pass")


def timezone_check(
    field_name: str,
    value: Any,
    metadata: dict[str, Any] | None,
    rule_config: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    timezone = metadata.get("timezone") or metadata.get("time_zone")
    if timezone:
        return _result("pass")
    return _result("warning", warnings=[f"{field_name} has no timezone metadata"])


def spread_check(
    field_name: str,
    value: Any,
    metadata: dict[str, Any] | None,
    rule_config: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    aligned = metadata.get("dates_aligned")
    if aligned is False:
        return _result("warning", warnings=[f"{field_name} uses non-aligned dates"])
    if aligned is True:
        return _result("pass")

    sc_date = metadata.get("sc_date")
    external_date = metadata.get("external_date")
    fx_date = metadata.get("fx_date")
    dates = {d for d in (sc_date, external_date, fx_date) if d}
    if len(dates) > 1:
        return _result("warning", warnings=[f"{field_name} date inputs are not aligned"])
    return _result("pass")


def source_conflict_check(
    field_name: str,
    value: Any,
    metadata: dict[str, Any] | None,
    rule_config: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _result(
        "warning",
        warnings=[f"{field_name} source_conflict_check requires multi-source data; v1 placeholder"],
    )


def revision_check(
    field_name: str,
    value: Any,
    metadata: dict[str, Any] | None,
    rule_config: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _result(
        "warning",
        warnings=[f"{field_name} revision_check requires versioned source data; v1 placeholder"],
    )


def _missing_check(
    field_name: str,
    value: Any,
    rule_config: dict[str, Any],
    required_for_topic: set[str],
) -> dict[str, Any]:
    if not _is_missing(value):
        return _result("pass")

    if field_name in required_for_topic:
        return _result("fail", errors=[f"{field_name} is required for current topic"])

    required = bool(rule_config.get("required", False))
    fail_action = str(rule_config.get("fail_action", "")).strip()

    if required:
        if fail_action in WARNING_FAIL_ACTIONS:
            return _result(
                "warning",
                warnings=[f"{field_name} is missing; fail_action={fail_action}"],
            )
        return _result("fail", errors=[f"{field_name} is required but missing"])

    if fail_action in PASS_FAIL_ACTIONS:
        return _result("pass")
    if fail_action in WARNING_OPTIONAL_FAIL_ACTIONS or fail_action in WARNING_FAIL_ACTIONS:
        return _result(
            "warning",
            warnings=[f"{field_name} is optional but missing; fail_action={fail_action}"],
        )
    return _result("warning", warnings=[f"{field_name} is optional but missing"])


def _required_for_topic_set(context: dict[str, Any]) -> set[str]:
    raw = context.get("required_for_topic", [])
    if raw is None:
        return set()
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, (list, tuple, set)):
        return {str(item) for item in raw}
    return {str(raw)}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, (list, tuple, set, dict)) and not value:
        return True
    return False


def _is_explicit_warning_stub(field_name: str, value: Any, metadata: dict[str, Any]) -> bool:
    if field_name != "EIA_crude_inventory" or not _is_missing(value):
        return False
    return (
        metadata.get("eia_warning_stub") is True
        and metadata.get("fallback_used") is True
        and metadata.get("pending_manual_review") is True
        and metadata.get("source_status") == "warning"
    )


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d"):
            try:
                return datetime.strptime(text[:19], fmt).date()
            except ValueError:
                continue
    return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _result(
    source_status: str,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    if source_status not in VALID_STATUSES:
        raise ValueError(f"Invalid source_status: {source_status}")
    return {
        "source_status": source_status,
        "warnings": warnings or [],
        "errors": errors or [],
    }


CHECKS = {
    "stale_check": stale_check,
    "range_check": range_check,
    "unit_check": unit_check,
    "timezone_check": timezone_check,
    "spread_check": spread_check,
    "source_conflict_check": source_conflict_check,
    "revision_check": revision_check,
}
