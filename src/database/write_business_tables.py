"""Write calculated daily data into formal business tables."""

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

from src.database.write_snapshot import DEFAULT_DB_PATH  # noqa: E402


VALID_STATUSES = {"pass", "warning", "fail"}
CORE_TABLES = ("market_prices", "fx_rates", "spread_table")


class BusinessTableWriteError(RuntimeError):
    """Raised when business table writes cannot be completed safely."""


def write_business_tables(
    calculated_input_path: str | Path,
    quality_report_path: str | Path,
    evidence_list_path: str | Path | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    data_snapshot_id: str | None = None,
    research_report_id: str | None = None,
    summary_output_path: str | Path | None = None,
    write_core_tables: bool = True,
    write_evidence_database: bool = True,
    allow_fail_write: bool = False,
) -> dict[str, Any]:
    """Write core business tables and Evidence DB rows, returning a stable summary."""

    calculated_input = _load_json(calculated_input_path)
    quality_report = _load_json(quality_report_path)
    final_db_path = Path(db_path).expanduser().resolve()
    if not final_db_path.exists():
        raise BusinessTableWriteError("Database not found. Run python src/database/init_db.py first.")

    warnings: list[str] = []
    errors: list[str] = []
    overall_status = str(quality_report.get("overall_status") or "warning")
    effective_core_write = bool(write_core_tables)
    if overall_status == "fail" and write_core_tables and not allow_fail_write:
        effective_core_write = False
        warnings.append("quality_report.overall_status=fail; core business table write skipped")

    evidence_report = None
    effective_evidence_write = bool(write_evidence_database)
    if write_evidence_database:
        if evidence_list_path and Path(evidence_list_path).exists():
            evidence_report = _load_json(evidence_list_path)
        else:
            effective_evidence_write = False
            warnings.append("evidence_database write skipped because evidence_list is absent")

    final_snapshot_id = data_snapshot_id

    summary = _empty_summary(
        core_tables_written=effective_core_write,
        evidence_database_written=effective_evidence_write,
        research_report_id=research_report_id,
        data_snapshot_id=final_snapshot_id,
        warnings=warnings,
        errors=errors,
    )

    if not effective_core_write and not effective_evidence_write:
        _write_summary_if_requested(summary, summary_output_path)
        return summary

    with sqlite3.connect(final_db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        if effective_evidence_write:
            _validate_foreign_key_readiness(
                conn=conn,
                research_report_id=research_report_id,
                data_snapshot_id=final_snapshot_id,
            )

        if effective_core_write:
            status_by_field = _status_by_field(quality_report)
            fields = calculated_input.get("fields", {})
            if not isinstance(fields, dict):
                raise BusinessTableWriteError("calculated input must include a fields object")
            report_date = str(quality_report.get("report_date") or calculated_input.get("report_date") or "")
            summary["market_prices_written"] = _write_market_prices(
                conn,
                fields,
                status_by_field,
                report_date,
                warnings,
            )
            summary["fx_rates_written"] = _write_fx_rates(
                conn,
                fields,
                status_by_field,
                report_date,
                warnings,
            )
            summary["spreads_written"] = _write_spreads(
                conn,
                fields,
                status_by_field,
                report_date,
                warnings,
            )

        if effective_evidence_write and isinstance(evidence_report, dict):
            summary["evidence_written"] = _write_evidence_database(
                conn=conn,
                evidence_report=evidence_report,
                research_report_id=research_report_id,
                data_snapshot_id=final_snapshot_id,
            )
        conn.commit()

    _write_summary_if_requested(summary, summary_output_path)
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write calculated daily data into business tables.")
    parser.add_argument("--calculated-input", required=True, help="Calculated input JSON path.")
    parser.add_argument("--quality-report", required=True, help="Quality report JSON path.")
    parser.add_argument("--evidence-list", help="Evidence List JSON path.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--data-snapshot-id", help="Existing data_snapshot id for Evidence DB rows.")
    parser.add_argument(
        "--research-report-id",
        "--report-id",
        dest="research_report_id",
        help="Existing research_reports report_id.",
    )
    parser.add_argument("--no-core-tables", action="store_false", dest="write_core_tables", help="Skip core tables.")
    parser.add_argument(
        "--no-evidence-database",
        action="store_false",
        dest="write_evidence_database",
        help="Skip evidence_database.",
    )
    parser.add_argument(
        "--allow-fail-write",
        action="store_true",
        help="Allow core table writes when quality_report.overall_status is fail.",
    )
    parser.add_argument("--summary-output", help="Optional JSON summary output path.")
    parser.set_defaults(write_core_tables=True, write_evidence_database=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = write_business_tables(
            calculated_input_path=args.calculated_input,
            quality_report_path=args.quality_report,
            evidence_list_path=args.evidence_list,
            db_path=args.db,
            data_snapshot_id=args.data_snapshot_id,
            research_report_id=args.research_report_id,
            write_core_tables=args.write_core_tables,
            write_evidence_database=args.write_evidence_database,
            allow_fail_write=args.allow_fail_write,
            summary_output_path=args.summary_output,
        )
    except (BusinessTableWriteError, OSError, json.JSONDecodeError, sqlite3.Error, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _load_json(path: str | Path) -> dict[str, Any]:
    json_path = Path(path).expanduser().resolve()
    with json_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise BusinessTableWriteError(f"JSON file must be an object: {json_path}")
    return data


def _empty_summary(
    core_tables_written: bool,
    evidence_database_written: bool,
    research_report_id: str | None,
    data_snapshot_id: str | None,
    warnings: list[str],
    errors: list[str],
) -> dict[str, Any]:
    return {
        "market_prices_written": 0,
        "fx_rates_written": 0,
        "spreads_written": 0,
        "evidence_written": 0,
        "core_tables_written": core_tables_written,
        "evidence_database_written": evidence_database_written,
        "research_report_id": research_report_id,
        "data_snapshot_id": data_snapshot_id,
        "warnings": warnings,
        "errors": errors,
    }


def _write_summary_if_requested(summary: dict[str, Any], output_path: str | Path | None) -> None:
    if not output_path:
        return
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _validate_foreign_key_readiness(
    conn: sqlite3.Connection,
    research_report_id: str | None,
    data_snapshot_id: str | None,
) -> None:
    if research_report_id:
        row = conn.execute(
            "SELECT 1 FROM research_reports WHERE report_id = ? LIMIT 1;",
            (research_report_id,),
        ).fetchone()
        if row is None:
            raise BusinessTableWriteError(
                f"foreign-key readiness failed: research_report_id {research_report_id} not found in research_reports"
            )
    if data_snapshot_id:
        row = conn.execute(
            "SELECT 1 FROM data_snapshot WHERE data_snapshot_id = ? LIMIT 1;",
            (data_snapshot_id,),
        ).fetchone()
        if row is None:
            raise BusinessTableWriteError(
                f"foreign-key readiness failed: data_snapshot_id {data_snapshot_id} not found in data_snapshot"
            )


def _status_by_field(quality_report: dict[str, Any]) -> dict[str, str]:
    field_results = quality_report.get("field_results", [])
    if not isinstance(field_results, list):
        return {}
    result: dict[str, str] = {}
    for item in field_results:
        if not isinstance(item, dict) or not item.get("field"):
            continue
        status = str(item.get("source_status") or "warning")
        result[str(item["field"])] = status if status in VALID_STATUSES else "warning"
    return result


def _write_market_prices(
    conn: sqlite3.Connection,
    fields: dict[str, Any],
    status_by_field: dict[str, str],
    report_date: str,
    warnings: list[str],
) -> int:
    rows = []
    seen_keys: set[tuple[str, str, str, str]] = set()
    sc_close = _field_number(fields, "SC_close")
    if sc_close is not None:
        metadata = _metadata(fields, "SC_close")
        unit = metadata.get("unit") or "CNY/barrel"
        row = {
            "date": _field_date(metadata, report_date),
            "symbol": "SC",
            "contract": _contract(metadata, "SC_MAIN_UNKNOWN"),
            "open": None,
            "high": None,
            "low": None,
            "close": sc_close,
            "settlement": _field_number(fields, "SC_settlement"),
            "volume": _field_number(fields, "SC_volume"),
            "open_interest": _field_number(fields, "SC_open_interest"),
            "currency": _currency_for_unit(unit),
            "unit": unit,
            "source": _source(metadata),
            "source_status": _field_status("SC_close", fields, status_by_field),
            "update_time": _update_time(metadata),
        }
        rows.append(row)
        seen_keys.add(_market_row_key(row))
    else:
        warnings.append("SC_close missing; market_prices main SC row skipped")

    for field_name, default_contract in (
        ("SC_near_price", "SC_NEAR_UNKNOWN"),
        ("SC_next_price", "SC_NEXT_UNKNOWN"),
    ):
        value = _field_number(fields, field_name)
        if value is None:
            warnings.append(f"{field_name} missing; market_prices row skipped")
            continue
        metadata = _metadata(fields, field_name)
        unit = metadata.get("unit") or "CNY/barrel"
        row = {
            "date": _field_date(metadata, report_date),
            "symbol": "SC",
            "contract": _contract(metadata, default_contract),
            "open": None,
            "high": None,
            "low": None,
            "close": value,
            "settlement": None,
            "volume": None,
            "open_interest": None,
            "currency": _currency_for_unit(unit),
            "unit": unit,
            "source": _source(metadata),
            "source_status": _field_status(field_name, fields, status_by_field),
            "update_time": _update_time(metadata),
        }
        row_key = _market_row_key(row)
        if row_key in seen_keys:
            warnings.append(f"{field_name} shares an existing market_prices key; duplicate row skipped")
            continue
        rows.append(row)
        seen_keys.add(row_key)
    count = 0
    for row in rows:
        conn.execute(
            """
            INSERT INTO market_prices (
                date, symbol, contract, open, high, low, close, settlement,
                volume, open_interest, currency, unit, source, source_status, update_time
            )
            VALUES (
                :date, :symbol, :contract, :open, :high, :low, :close, :settlement,
                :volume, :open_interest, :currency, :unit, :source, :source_status, :update_time
            )
            ON CONFLICT(date, symbol, contract, source) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                settlement = excluded.settlement,
                volume = excluded.volume,
                open_interest = excluded.open_interest,
                currency = excluded.currency,
                unit = excluded.unit,
                source_status = excluded.source_status,
                update_time = excluded.update_time;
            """,
            row,
        )
        count += 1
    return count


def _write_fx_rates(
    conn: sqlite3.Connection,
    fields: dict[str, Any],
    status_by_field: dict[str, str],
    report_date: str,
    warnings: list[str],
) -> int:
    usd_cny = _field_number(fields, "USD_CNY")
    if usd_cny is None:
        warnings.append("USD_CNY missing; fx_rates row skipped")
        return 0
    metadata = _metadata(fields, "USD_CNY")
    conn.execute(
        """
        INSERT INTO fx_rates (
            date, pair, mid_price, close, intraday_price, source, source_status, update_time
        )
        VALUES (
            :date, :pair, :mid_price, :close, :intraday_price, :source, :source_status, :update_time
        )
        ON CONFLICT(date, pair, source) DO UPDATE SET
            mid_price = excluded.mid_price,
            close = excluded.close,
            intraday_price = excluded.intraday_price,
            source_status = excluded.source_status,
            update_time = excluded.update_time;
        """,
        {
            "date": _field_date(metadata, report_date),
            "pair": "USD/CNY",
            "mid_price": None,
            "close": usd_cny,
            "intraday_price": None,
            "source": _source(metadata),
            "source_status": _field_status("USD_CNY", fields, status_by_field),
            "update_time": _update_time(metadata),
        },
    )
    return 1


def _write_spreads(
    conn: sqlite3.Connection,
    fields: dict[str, Any],
    status_by_field: dict[str, str],
    report_date: str,
    warnings: list[str],
) -> int:
    source_fields = (
        "SC_close",
        "Brent_close",
        "WTI_close",
        "USD_CNY",
        "SC_calendar_spread",
        "SC_Brent_spread_simple",
        "SC_WTI_spread_simple",
        "SC_near_price",
        "SC_next_price",
    )
    if all(_field_number(fields, field_name) is None for field_name in source_fields):
        warnings.append("spread_table row skipped because no spread source fields were available")
        return 0
    for field_name, column_name in (
        ("Brent_close", "brent_price"),
        ("WTI_close", "wti_price"),
    ):
        if _field_number(fields, field_name) is None:
            warnings.append(f"{field_name} missing; spread_table.{column_name} left NULL")
    metadata = _metadata(fields, "SC_Brent_spread_simple") or _metadata(fields, "SC_calendar_spread")
    calendar_spread = _field_number(fields, "SC_calendar_spread")
    row = {
        "date": str(report_date)[:10],
        "sc_contract": _contract(_metadata(fields, "SC_close"), "SC_MAIN_UNKNOWN"),
        "sc_close": _field_number(fields, "SC_close"),
        "brent_price": _field_number(fields, "Brent_close"),
        "wti_price": _field_number(fields, "WTI_close"),
        "oman_price": None,
        "dubai_price": None,
        "usd_cny": _field_number(fields, "USD_CNY"),
        "sc_brent_spread": _field_number(fields, "SC_Brent_spread_simple"),
        "sc_wti_spread": _field_number(fields, "SC_WTI_spread_simple"),
        "sc_oman_spread": None,
        "sc_dubai_spread": None,
        "near_contract": _contract_or_none(_metadata(fields, "SC_near_price")),
        "far_contract": _contract_or_none(_metadata(fields, "SC_next_price")),
        "calendar_spread": calendar_spread,
        "structure_type": _structure_type(calendar_spread),
        "calculation_method": str(metadata.get("calculation_method") or "simple_fx_adjusted_v1"),
        "data_alignment_note": _data_alignment_note(fields),
        "source": "Python calculation",
        "source_status": _worst_status(
            [_field_status(field_name, fields, status_by_field) for field_name in source_fields]
        ),
    }
    conn.execute(
        """
        INSERT INTO spread_table (
            date, sc_contract, sc_close, brent_price, wti_price, oman_price, dubai_price,
            usd_cny, sc_brent_spread, sc_wti_spread, sc_oman_spread, sc_dubai_spread,
            near_contract, far_contract, calendar_spread, structure_type, calculation_method,
            data_alignment_note, source, source_status
        )
        VALUES (
            :date, :sc_contract, :sc_close, :brent_price, :wti_price, :oman_price, :dubai_price,
            :usd_cny, :sc_brent_spread, :sc_wti_spread, :sc_oman_spread, :sc_dubai_spread,
            :near_contract, :far_contract, :calendar_spread, :structure_type, :calculation_method,
            :data_alignment_note, :source, :source_status
        )
        ON CONFLICT(date, sc_contract, calculation_method, source) DO UPDATE SET
            sc_close = excluded.sc_close,
            brent_price = excluded.brent_price,
            wti_price = excluded.wti_price,
            oman_price = excluded.oman_price,
            dubai_price = excluded.dubai_price,
            usd_cny = excluded.usd_cny,
            sc_brent_spread = excluded.sc_brent_spread,
            sc_wti_spread = excluded.sc_wti_spread,
            sc_oman_spread = excluded.sc_oman_spread,
            sc_dubai_spread = excluded.sc_dubai_spread,
            near_contract = excluded.near_contract,
            far_contract = excluded.far_contract,
            calendar_spread = excluded.calendar_spread,
            structure_type = excluded.structure_type,
            data_alignment_note = excluded.data_alignment_note,
            source_status = excluded.source_status;
        """,
        row,
    )
    return 1


def _write_evidence_database(
    conn: sqlite3.Connection,
    evidence_report: dict[str, Any],
    research_report_id: str | None,
    data_snapshot_id: str | None,
) -> int:
    evidence_items = evidence_report.get("evidence_list", [])
    if not isinstance(evidence_items, list):
        return 0
    count = 0
    for item in evidence_items:
        if not isinstance(item, dict) or not item.get("evidence_id"):
            continue
        row = {
            "evidence_id": str(item["evidence_id"]),
            "report_id": research_report_id,
            "data_snapshot_id": data_snapshot_id,
            "source_name": str(item.get("source_name") or item.get("field") or "daily_input_field"),
            "source_level": item.get("source_level"),
            "evidence_type": item.get("evidence_type"),
            "publish_time": item.get("publish_time"),
            "data_time": item.get("data_time"),
            "extracted_fact": _safe_extracted_fact(item),
            "raw_value": _json_text(item.get("raw_value")),
            "normalized_value": _to_float(item.get("normalized_value")),
            "unit": item.get("unit"),
            "related_variable": item.get("related_variable") or item.get("field"),
            "conclusion_impact": item.get("conclusion_impact"),
            "confidence": item.get("confidence") or _item_metadata(item).get("confidence"),
            "url_or_reference": item.get("url_or_reference"),
            "source_status": _valid_status(item.get("source_status")),
        }
        conn.execute(
            """
            INSERT INTO evidence_database (
                evidence_id, report_id, data_snapshot_id, source_name, source_level,
                evidence_type, publish_time, data_time, extracted_fact, raw_value,
                normalized_value, unit, related_variable, conclusion_impact, confidence,
                url_or_reference, source_status
            )
            VALUES (
                :evidence_id, :report_id, :data_snapshot_id, :source_name, :source_level,
                :evidence_type, :publish_time, :data_time, :extracted_fact, :raw_value,
                :normalized_value, :unit, :related_variable, :conclusion_impact, :confidence,
                :url_or_reference, :source_status
            )
            ON CONFLICT(evidence_id) DO UPDATE SET
                report_id = excluded.report_id,
                data_snapshot_id = excluded.data_snapshot_id,
                source_name = excluded.source_name,
                source_level = excluded.source_level,
                evidence_type = excluded.evidence_type,
                publish_time = excluded.publish_time,
                data_time = excluded.data_time,
                extracted_fact = excluded.extracted_fact,
                raw_value = excluded.raw_value,
                normalized_value = excluded.normalized_value,
                unit = excluded.unit,
                related_variable = excluded.related_variable,
                conclusion_impact = excluded.conclusion_impact,
                confidence = excluded.confidence,
                url_or_reference = excluded.url_or_reference,
                source_status = excluded.source_status;
            """,
            row,
        )
        count += 1
    return count


def _field_number(fields: dict[str, Any], field_name: str) -> float | None:
    payload = fields.get(field_name)
    if not isinstance(payload, dict):
        return None
    return _to_float(payload.get("value"))


def _metadata(fields: dict[str, Any], field_name: str) -> dict[str, Any]:
    payload = fields.get(field_name)
    if not isinstance(payload, dict):
        return {}
    metadata = payload.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _field_date(metadata: dict[str, Any], fallback: str) -> str:
    value = metadata.get("date") or metadata.get("data_time") or metadata.get("sc_date") or fallback
    return str(value)[:10]


def _source(metadata: dict[str, Any]) -> str:
    return str(metadata.get("source_name") or metadata.get("source") or "unknown")


def _contract(metadata: dict[str, Any], fallback: str) -> str:
    return str(metadata.get("contract") or metadata.get("symbol") or metadata.get("source_field") or fallback)


def _contract_or_none(metadata: dict[str, Any]) -> str | None:
    value = metadata.get("contract") or metadata.get("symbol") or metadata.get("source_field")
    return str(value) if value is not None else None


def _market_row_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (str(row["date"]), str(row["symbol"]), str(row["contract"]), str(row["source"]))


def _currency_for_unit(unit: Any) -> str | None:
    return "CNY" if str(unit) == "CNY/barrel" else None


def _update_time(metadata: dict[str, Any]) -> str | None:
    value = metadata.get("fetched_at") or metadata.get("update_time") or metadata.get("publish_time") or metadata.get("data_time")
    return str(value) if value is not None else None


def _field_status(field_name: str, fields: dict[str, Any], status_by_field: dict[str, str]) -> str:
    metadata_status = _metadata(fields, field_name).get("source_status")
    if metadata_status is not None:
        return _valid_status(metadata_status)
    if field_name in status_by_field:
        return _valid_status(status_by_field[field_name])
    return _valid_status(metadata_status)


def _valid_status(value: Any) -> str:
    text = str(value or "warning")
    return text if text in VALID_STATUSES else "warning"


def _worst_status(statuses: list[str]) -> str:
    if "fail" in statuses:
        return "fail"
    if "warning" in statuses:
        return "warning"
    return "pass"


def _structure_type(calendar_spread: float | None) -> str | None:
    if calendar_spread is None:
        return None
    if calendar_spread > 0:
        return "Backwardation"
    if calendar_spread < 0:
        return "Contango"
    return "Flat"


def _data_alignment_note(fields: dict[str, Any]) -> str | None:
    notes = []
    for field_name in ("USD_CNY", "Brent_close", "WTI_close", "SC_Brent_spread_simple", "SC_WTI_spread_simple"):
        note = _metadata(fields, field_name).get("data_alignment_note")
        if note is not None:
            notes.append(f"{field_name}: {note}")
    return "; ".join(notes) if notes else None


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _item_metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _safe_extracted_fact(item: dict[str, Any]) -> str:
    if item.get("extracted_fact"):
        return str(item["extracted_fact"])
    field_name = str(item.get("field") or item.get("related_variable") or "unknown")
    value = item.get("raw_value")
    if value is None:
        value = item.get("normalized_value")
    return f"Field {field_name} validated with value {value}"


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
