"""Generate a non-Agent SC daily Markdown report from local structured files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


FORBIDDEN_TERMS = ["买入", "卖出", "必涨", "必跌", "稳赚"]


class DailyReportGenerationError(RuntimeError):
    """Raised when the daily report cannot be generated."""


def load_json(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    with json_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise DailyReportGenerationError(f"JSON file must be an object: {json_path}")
    return data


def build_default_output_path(report_date: str) -> Path:
    return PROJECT_ROOT / "reports" / "daily" / f"SC_daily_{report_date}.md"


def generate_daily_report(
    daily_input_path: str | Path,
    quality_report_path: str | Path,
    output_path: str | Path | None = None,
    data_snapshot_id: str | None = None,
) -> str:
    daily_input = load_json(daily_input_path)
    quality_report = load_json(quality_report_path)
    report_date = _report_date(daily_input, quality_report)
    output = Path(output_path) if output_path else build_default_output_path(report_date)

    markdown = render_daily_report(
        daily_input=daily_input,
        quality_report=quality_report,
        data_snapshot_id=data_snapshot_id or "未写入 data_snapshot",
    )
    _assert_no_forbidden_terms(markdown)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    return markdown


def render_daily_report(
    daily_input: dict[str, Any],
    quality_report: dict[str, Any],
    data_snapshot_id: str,
) -> str:
    report_date = _report_date(daily_input, quality_report)
    fields = daily_input.get("fields", {})
    if not isinstance(fields, dict):
        fields = {}

    status = str(quality_report.get("overall_status", "warning"))
    warnings = quality_report.get("warnings", [])
    errors = quality_report.get("errors", [])
    field_results = quality_report.get("field_results", [])
    if not isinstance(warnings, list):
        warnings = [str(warnings)]
    if not isinstance(errors, list):
        errors = [str(errors)]
    if not isinstance(field_results, list):
        field_results = []

    warning_fields = _fields_by_status(field_results, "warning")
    fail_fields = _fields_by_status(field_results, "fail")
    missing_fields = _missing_fields(field_results)
    confidence = "低" if status in {"warning", "fail"} else "中"
    conclusion = _conclusion_for_status(status)

    lines = [
        "# SC 中国原油期货日报",
        "",
        f"- 报告日期：{report_date}",
        "- 生成方式：非 Agent 本地模板生成器",
        "- 说明：本日报借鉴结构化 daily brief 思路，但当前不依赖 Agent、LLM 或外部 skill。",
        "",
        "## 1. 今日结论",
        f"- 日报状态：{status}",
        f"- 数据快照编号：{data_snapshot_id}",
        "- Prompt 版本：daily_report_prompt_v1",
        "- 计算规则版本：simple_fx_adjusted_v1",
        "- 代码版本：见 data_snapshot 或 Git commit",
        "- 对 SC 的影响：不输出方向性结论",
        "- 影响周期：待人工审核",
        f"- 置信度：{confidence}",
        f"- 一句话结论：{conclusion}",
        "- 口径提示：本报告当前使用 Brent / WTI 作为简化外盘参考，尚未接入 Oman / Dubai，因此 SC 内外盘强弱判断置信度下调。",
        "",
        "## 1.1 数据完整性提示",
        f"- 缺失字段：{_join_or_none(missing_fields)}",
        f"- warning 字段：{_join_or_none(warning_fields)}",
        f"- fail 字段：{_join_or_none(fail_fields)}",
        f"- 结论降级原因：{_downgrade_reason(status, warnings, errors)}",
        "",
        "## 2. 行情回顾",
        f"- SC 主力：{_field_value(fields, 'SC_close')}",
        f"- Brent：{_field_value(fields, 'Brent_close')}",
        f"- WTI：{_field_value(fields, 'WTI_close')}",
        f"- 人民币汇率：{_field_value(fields, 'USD_CNY')}",
        f"- 成交和持仓：成交量 {_field_value(fields, 'SC_volume')}；持仓量 {_field_value(fields, 'SC_open_interest')}",
        f"- 月差结构：{_field_value(fields, 'SC_calendar_spread')}",
        "",
        "## 3. 核心驱动因素",
    ]

    if status == "fail":
        lines.extend(
            [
                "1. 数据质量状态为 fail，本报告不进行行情归因。",
                "2. 请先修复 fail 字段或补充数据来源。",
                "3. 修复后重新运行质量检查和日报生成。",
            ]
        )
    else:
        lines.extend(
            [
                "1. 当前仅基于结构化输入进行描述性整理。",
                "2. 外盘、汇率、库存和新闻字段需结合人工审核解释。",
                "3. 若质量检查存在 warning，相关结论应保持保守。",
            ]
        )

    lines.extend(
        [
            "",
            "## 4. 国内基本面",
            "- 进口：未接入自动字段，等待后续 china_fundamental_data。",
            "- 炼厂开工：未接入自动字段，等待后续 china_fundamental_data。",
            "- 库存：未接入国内库存自动字段。",
            "- 成品油需求：未接入自动字段。",
            "- 炼油利润：未接入自动字段。",
            "",
            "## 5. 海外基本面",
            f"- OPEC+：{_field_value(fields, 'OPEC_monthly_summary')}",
            f"- 美国库存和产量：EIA 原油库存 {_field_value(fields, 'EIA_crude_inventory')}；汽油库存 {_field_value(fields, 'EIA_gasoline_inventory')}；馏分油库存 {_field_value(fields, 'EIA_distillate_inventory')}",
            "- 地缘政治：仅使用输入文件中的新闻或人工备注，不自动搜索。",
            f"- 全球需求：{_field_value(fields, 'IEA_monthly_summary')}",
            "",
            "## 6. 价差和结构",
            f"- SC-Brent：{_field_value(fields, 'SC_Brent_spread_simple')}",
            f"- SC-WTI：{_field_value(fields, 'SC_WTI_spread_simple')}",
            f"- SC 月差：{_field_value(fields, 'SC_calendar_spread')}",
            "- 内外盘强弱：仅作简化参考；Oman / Dubai 尚未接入，不能声称完成严格 SC 中东油锚定分析。",
            "",
            "## 7. 证据链",
            "- 正式 Evidence ID 尚未自动生成；以下为字段级数据依据占位。",
            f"- 行情字段：SC_close={_field_value(fields, 'SC_close')}；Brent_close={_field_value(fields, 'Brent_close')}；WTI_close={_field_value(fields, 'WTI_close')}",
            f"- 汇率字段：USD_CNY={_field_value(fields, 'USD_CNY')}",
            f"- 库存字段：EIA_crude_inventory={_field_value(fields, 'EIA_crude_inventory')}",
            f"- 新闻字段：important_oil_news={_field_value(fields, 'important_oil_news')}",
            "",
            "## 8. 风险与反例",
            "- Oman / Dubai 尚未接入，SC 中东油锚定分析不完整。",
            "- 免费数据源可能存在延迟、字段变化或口径不一致。",
            "- 本报告为非 Agent 模板生成，不进行自动搜索或深度推理。",
            "- 质量检查 warning 或 fail 字段需要人工复核。",
            "",
            "## 9. 下一交易日关注",
            "- 补充或校验 warning / fail 字段。",
            "- 关注外盘原油、人民币汇率、EIA 库存和交易所公告的时间戳。",
            "- 人工确认是否需要补充 Oman / Dubai 或国内基本面数据。",
            "",
            "## 10. 人工审核区",
            "- 是否接受结论：是 / 否",
            "- 错误类型：数据错误 / 口径错误 / 逻辑错误 / 归因过度 / 结论过强 / 遗漏变量",
            "- 严重程度：高 / 中 / 低",
            "- 错误点：",
            "- 需要补充的数据：",
            "- 是否需要修改数据源：是 / 否",
            "- 是否需要修改计算规则：是 / 否",
            "- 是否需要修改 Prompt：是 / 否",
            "- 研究员修正意见：",
            "",
        ]
    )

    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a non-Agent SC daily Markdown report.")
    parser.add_argument("--daily-input", required=True, help="Daily input JSON path.")
    parser.add_argument("--quality-report", required=True, help="Quality report JSON path.")
    parser.add_argument("--output", help="Markdown output path.")
    parser.add_argument("--data-snapshot-id", help="Optional data snapshot id.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        generate_daily_report(
            daily_input_path=args.daily_input,
            quality_report_path=args.quality_report,
            output_path=args.output,
            data_snapshot_id=args.data_snapshot_id,
        )
    except (DailyReportGenerationError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


def _report_date(daily_input: dict[str, Any], quality_report: dict[str, Any]) -> str:
    return str(quality_report.get("report_date") or daily_input.get("report_date") or "UNKNOWN_DATE")


def _field_value(fields: dict[str, Any], field_name: str) -> str:
    payload = fields.get(field_name, {})
    if not isinstance(payload, dict):
        return "未提供"
    value = payload.get("value")
    metadata = payload.get("metadata", {})
    unit = metadata.get("unit") if isinstance(metadata, dict) else None
    if value is None or str(value).strip() == "":
        return "未提供"
    if unit:
        return f"{value} {unit}"
    return str(value)


def _fields_by_status(field_results: list[Any], status: str) -> list[str]:
    fields = []
    for result in field_results:
        if isinstance(result, dict) and result.get("source_status") == status:
            fields.append(str(result.get("field", "unknown")))
    return fields


def _missing_fields(field_results: list[Any]) -> list[str]:
    missing = []
    for result in field_results:
        if not isinstance(result, dict):
            continue
        text = " ".join(str(item) for item in result.get("warnings", []) + result.get("errors", []))
        if "missing" in text or "缺失" in text:
            missing.append(str(result.get("field", "unknown")))
    return missing


def _join_or_none(items: list[str]) -> str:
    return "、".join(items) if items else "无"


def _downgrade_reason(status: str, warnings: list[Any], errors: list[Any]) -> str:
    if status == "pass" and not warnings and not errors:
        return "无"
    if status == "fail":
        return "数据质量检查为 fail，仅生成数据失败说明，不输出方向性结论。"
    reasons = [str(item) for item in warnings[:3]]
    if errors:
        reasons.extend(str(item) for item in errors[:3])
    return "；".join(reasons) if reasons else "存在质量检查 warning，结论自动降级。"


def _conclusion_for_status(status: str) -> str:
    if status == "fail":
        return "数据质量未通过，不能生成正常研究结论。"
    if status == "warning":
        return "数据可用于结构化日报，但存在 warning，结论需保持保守并等待人工审核。"
    return "数据质量状态为 pass，可生成描述性日报，仍需人工审核。"


def _assert_no_forbidden_terms(markdown: str) -> None:
    for term in FORBIDDEN_TERMS:
        if term in markdown:
            raise DailyReportGenerationError(f"Report contains forbidden term: {term}")


if __name__ == "__main__":
    raise SystemExit(main())
