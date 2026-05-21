# SC Oil Agent

个人创作者版 SC 中国原油期货研究自动化项目。

## 目录

- `docs/`：系统设计文档分册
- `config/data_dictionary.yaml`：MVP 字段数据字典
- `templates/`：日报、周报、事件点评模板
- `prompts/`：Agent 系统提示词
- `src/`：后续 Python 模块目录
- `db/`：SQLite 数据库位置
- `reports/`：生成的研究报告

## MVP 顺序

1. 建工程骨架和数据字典
2. 半自动日报 + 极简 SQLite
3. 补齐 7 张正式表
4. Evidence ID 自动化
5. 接入 Agent 生成解释
6. 连续 10 个交易日试运行
