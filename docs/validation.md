# Validation Guide

本文件记录本地 MVP 日报流水线的验收方法。当前目标不是验证市场判断是否正确，而是验证系统在 `warning` 和 `fail` 数据质量状态下能否稳定执行、降级和留痕。

## 当前验收状态

```text
v0.4 本地完整日报流水线已通过核心验证
```

已验证：

- `warning` 场景：完整生成 `calculated_input`、`quality_report`、`data_snapshot`、`evidence_list`、Markdown 日报，并写入 `research_reports`。
- `fail` 场景：生成 `calculated_input`、`quality_report`、失败版 Markdown，并写入 `research_reports`；不写 `data_snapshot`，不生成 `evidence_list`。

暂未强制验证：

- `pass` 场景：当前正式数据字典包含 `source_conflict_check` / `revision_check` placeholder，示例文件会自然得到 `warning`。如需测试 `pass`，使用 test-only dictionary。

## Warning 验证

`data/manual/daily_input_example.json` 只是格式示例，不是真实市场数据，不能用于研究、交易或行情判断。

运行：

```bash
python src/pipeline/run_daily_pipeline.py \
  --input data/manual/daily_input_example.json \
  --calculated-input-output data/processed/calculated_input_example.json \
  --quality-report-output data/processed/quality_report_example.json \
  --evidence-list-output data/processed/evidence_list_example.json \
  --daily-report-output reports/daily/SC_daily_example.md \
  --report-id RPT-EXAMPLE-SC-DAILY \
  --replace \
  --init-db
```

预期输出要点：

```text
overall_status: warning
data_snapshot_id: SNAP-...
evidence_list_path: data/processed/evidence_list_example.json
daily_report_path: reports/daily/SC_daily_example.md
research_report_id: RPT-EXAMPLE-SC-DAILY
exit_code_meaning: success_quality_pass_or_warning
```

验证含义：

- `warning` 不是失败，表示数据可用于结构化日报，但结论需要降级和人工复核。
- 示例中的 warning 主要来自 `source_conflict_check` v1 placeholder 和额外实验字段。

## Fail 验证

创建 test-only 数据字典：

```bash
cat > /tmp/fail_dictionary.yaml <<'EOF'
SC_close:
  required: true
  unit: CNY/barrel
  frequency: daily
  quality_checks: [missing_check, unit_check]
  fail_action: report_as_missing
EOF
```

创建故意缺失 `SC_close` 的输入：

```bash
cat > /tmp/fail_input.json <<'EOF'
{
  "report_date": "2026-05-22",
  "fields": {}
}
EOF
```

运行：

```bash
python src/pipeline/run_daily_pipeline.py \
  --input /tmp/fail_input.json \
  --dictionary /tmp/fail_dictionary.yaml \
  --calculated-input-output /tmp/calculated_fail.json \
  --quality-report-output /tmp/quality_fail.json \
  --evidence-list-output /tmp/evidence_fail.json \
  --daily-report-output /tmp/SC_daily_fail.md \
  --report-id RPT-TEST-FAIL \
  --replace \
  --init-db
```

预期输出要点：

```text
overall_status: fail
data_snapshot_id:
evidence_list_path:
daily_report_path: /tmp/SC_daily_fail.md
research_report_id: RPT-TEST-FAIL
exit_code_meaning: quality_failed_no_snapshot_written
```

验证含义：

- `quality_report` 会生成。
- 失败版 Markdown 会生成。
- `research_reports` 会写入失败记录，便于复盘。
- `data_snapshot` 不写入。
- `evidence_list` 不生成，避免把失败字段包装成证据。

macOS 上 `/tmp` 可能显示为 `/private/tmp`，这是正常路径映射。

## Pass 验证说明

当前正式数据字典中，部分质量检查仍是 placeholder，因此正式 example 不追求 `pass`。如需测试 `pass`，使用只包含少量本地可验证字段的 test-only dictionary，例如只检查 `SC_close` 的 `missing_check` 和 `unit_check`。

后续当 `source_conflict_check` 和 `revision_check` 接入真实多来源/版本数据后，再把正式 `pass` 场景纳入验收。
