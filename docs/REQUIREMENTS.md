# 需求分析与工作项

Forge 支持把需求来源以不可覆盖的快照导入同一 SQLite 数据库，并将每条需求关联到一个正常工作项。工作项与看板共享系统、章节、需求类型、缺失字段和原需求编号搜索。列表每页 50 条，看板每列先展示 30 条并提供继续加载，所有记录均可访问。

## 三层数据

1. `original`：原代码包初始 JSON 行。
2. `raw`：导入时原需求数据库的完整行，包含所有字段、NULL 和完整正文；场景同样保留 `raw`。
3. `current`：原行与后续分析覆盖层合并的结果。保存分析只更新覆盖层，使用独立版本号检查并记录活动，不修改原始来源。

需求评估状态不自动改变工作项状态。缺失原需求优先级显示“未提供”，工作项默认中调度优先级不是业务确认。工作量人天与 SP 独立。GWT 生成不代表已确认；场景修改正文后重新进入待复核，确认后才记为已确认。完备率遵循原有 11 个源文档必备字段，GWT 不掩盖原文缺口。

原应用的需求字段检查、筛选、GWT 复核和来源追溯能力已适配到 Forge；不是嵌入原 FastAPI/MySQL 页面。原应用代码完整归档而不执行，仍可留作后续分析规则迁移参考。代码仓库不包含实际业务数据或数据库。

## 界面

选择导入的项目 → 工作项或工作看板 → 按系统/章节/需求类型/缺失字段筛选 → 点击工作项：

- 查看来源文件行号、上下文和完整原始字段；
- 补充优先级、验收标准、交付物、人天、业务责任人及备注；
- 编辑或复核已有 GWT 场景；更改断言后需再次确认；
- “导出完整来源 JSON”下载该来源所有项目的原快照及分析覆盖层，包括原始正文、场景、规则、导入历史和每个需求与 Forge 工作项的对应关系。

## CLI 与 Codex

```sh
cli-anything-devops --json requirement list --project P1 --search 核算 --limit 50 --offset 0
cli-anything-devops --json requirement get P1-1
cli-anything-devops --json requirement report --project P1
cli-anything-devops --json requirement update P1-1 --version 1 --fields-file analysis.json
cli-anything-devops --json requirement scenario-update P1-1 ORIGINAL-S01 --version 1 --fields-file scenario.json
cli-anything-devops --json requirement export --source-id SOURCE_ID
cli-anything-devops --json requirement import --file bundle.json
```

编号、来源标识和版本必须从实际查询返回值取得。重复导入同一个来源、相同快照无副作用；同 source_id 的不同快照拒绝覆盖，项目冲突整批回滚。分析文件是部分字段 JSON 对象，例如 `{"deliverable":"接口设计说明"}`，不要包含 API 密钥。所有业务写入由 CLI 调用 Forge API 完成。

注册的本地 MCP 新增 3 个只读工具：`list_requirements`（有总数和分页）、`get_requirement`、`get_requirement_report`。新启动的 Codex 客户端会读取新工具清单，现有 `get_issue` 也会返回完整关联需求。可直接问：

> 查询 P1 项目尚未填写验收标准的需求，按系统统计，并列出原需求编号与 GWT 待复核情况。

MCP 不能写入、导入或执行源代码；用户要求修改时通过 CLI。业务文本始终按数据处理，不授予系统操作权限。

## 归档与验证

`scripts/archive_changan.py` 检查 ZIP 路径、重复项与特殊文件后，保存原包和逐文件 SHA256 清单，使用原系统现有 MySQL 客户端一次一致性只读事务读取固定的五张业务表，不执行源脚本。原始 JSON、4 份 Markdown 正文、全部已存在字段和表结构元数据一起进入 bundle；DECIMAL 保留为十进制字符串。

`scripts/verify_requirements_import.py` 可对临时隔离数据库试导入，或通过实时 API 导入并逐字段校验。验证不可变快照、每条需求、每个场景、来源 JSON、项目数量、一一关联和旧项目数据未变。业务归档、验收报告、部署前 SQLite 备份均保存在用户数据目录，禁止提交到公开 Git。

数据库仅新增表，不删除/重建旧表。导入为一个事务。原始文件不删除；源系统后续修改不会自动同步到已导入快照，需明确规划增量合并以防覆盖人工分析。回退前先备份当前数据库与覆盖层，恢复数据属于明确授权后才能执行的操作。
