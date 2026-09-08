# Forge DevOps · 研发工作台

参考 Jira 的项目、待办池、看板、迭代与版本工作流，提供可以通过 Codex 对话操作的本地应用。

## 已实现

- 项目：独立编号空间，按项目切换与隔离。
- 工作项：故事/任务/缺陷/史诗，描述、负责人、优先级、故事点、标签、截止日期、迭代分配。
- 五列拖拽看板、列表、搜索与类型/优先级/迭代筛选。
- 工作项详情、编辑、评论、来源标记和变更审计；版本检查阻止覆盖并发修改。
- 迭代：创建/开始/完成。同项目最多一个活动迭代；未完成工作自动回到待办池。
- 版本：创建时至少关联一个工作项，未发布版本支持编辑名称、说明与关联项；计划/验证/已发布，关联项全部完成后才能标记发布，已发布版本不可改写。
- CLI-Anything：真实 HTTP 后端、JSON 输出、REPL、可安装命令、可发现的 Codex Skill。
- 统一对象协议：项目、工作项、需求、场景、迭代、版本、评论均可通过带 request ID 与 revision 的 CLI/MCP 创建和修改；删除为可恢复 tombstone，并要求先预览影响。
- 管理分析：项目/活动迭代/指定迭代切换，12 个核心指标卡，风险筛选与任务直达、工作流分布、负责人工作量、数据完整性、项目级版本门禁；工作看板另有 6 项项目管理摘要。
- SQLite 数据持久化；没有模型 API Key 依赖。

## 启动

在仓库根目录：

```sh
python3 -m venv "$HOME/.local/share/forge-devops/venv"
"$HOME/.local/share/forge-devops/venv/bin/pip" install -e 'devops/agent-harness[dev]'
"$HOME/.local/share/forge-devops/venv/bin/forge-devops-server" --port 8766
```

打开 http://127.0.0.1:8766 。默认数据库位于 `~/.local/share/forge-devops/data.sqlite3`，支持 `--db PATH` 或 `FORGE_DEVOPS_DB`。程序没有自动重置/覆盖现有数据的功能。

可选 PM2 托管（在端口空闲时启动）：

```sh
"$HOME/.local/share/forge-devops/venv/bin/python" devops/agent-harness/manage.py start
"$HOME/.local/share/forge-devops/venv/bin/python" devops/agent-harness/manage.py status
```

启动工具会清理传给 PM2 子进程的环境，只保留必要运行变量。不会调用 `pm2 save`、配置开机启动或修改其他托管进程。

## CLI 与 Codex

安装后将虚拟环境的 `bin` 目录加入 PATH，或激活该虚拟环境后使用 CLI。

```sh
cli-anything-devops --json health
cli-anything-devops --json project list
cli-anything-devops --json issue create --project APP --title '修复登录超时' --type bug --priority high
cli-anything-devops --json issue move APP-1 in_progress
cli-anything-devops --json report --project APP
cli-anything-devops --json analytics --project APP --scope active
cli-anything-devops --json analytics --project APP --scope project
cli-anything-devops --json analytics --project APP --scope sprint:1
cli-anything-devops --json object create project --fields-file /absolute/path/project.json --request-id create-app-1
cli-anything-devops --json object get project APP
cli-anything-devops
```

`--json`、`--url`、`--actor` 位于子命令前。单次执行和 REPL 调用相同 HTTP API；没有直接写数据库的 CLI 捷径。对象命令的复杂字段放入 UTF-8 JSON 对象文件，写入必须提供调用方生成的唯一 `--request-id`；更新和恢复还要使用刚读取的 opaque `revision`。错误以 JSON 输出到 stderr，退出码非零。完整七类字段、删除/恢复流程见 [对象写入协议](../../docs/OBJECT-WRITES.md)。

规范 Skill：`skills/cli-anything-devops/SKILL.md`（仓库根目录）；安装包同时包含兼容副本。需要在 Codex 中启用时，可将该技能安装到个人技能目录；也可以在对话中指定仓库内的技能路径并执行 CLI。

示例对话：“在 APP 项目创建一个高优先级缺陷：登录超时，指派给 Sushi。” Codex 查询项目、调用 CLI 创建、回读并回复真实工作项编号。网页约 5 秒内同步。

## API

管理分析页面可直接打开 `http://127.0.0.1:8766/?project=DEMO&view=analytics&scope=active`。页面每约 5 秒读取真实数据；不修改项目、任务或迭代。`report.analytics` 与 CLI `analytics` 使用同一计算函数，`scope=all` 返回全部可选范围。

统计口径：工作项/故事点完成率只看当前状态，空分母为 `null`（网页显示 —）；未完成工作项才参与逾期、近期到期、高优、未分配、0 SP 和久未更新统计。3 天内到期含今天至今天 +3 天；久未更新为 ≥7 个服务器本地日历日没有字段修改，评论不改变该时间。覆盖率分母是所选范围全部工作项。未完成平均存续时间从创建日起算，不是周期时间。版本门禁始终为整个项目，且不是外部部署状态。已完成迭代也只统计当前仍关联的工作项，不是冻结的承诺基线。

缺少可靠采集数据的燃尽图、迭代速率、周期时间、阻塞率、产能利用率、DORA 显示不可计算原因；不会用零代替未知或把故事点当作工时。

- `GET /api/health`：服务健康。
- `GET /api/state?project=APP`：网页所需的项目、工作项、迭代、版本、报告和近期活动。
- `POST /api/call`：`{"action":"issue.create","data":{"project":"APP","title":"修复错误"}}`。
- 有限对象 action：`object.list/get/create/update/delete.preview/delete/restore`；只接受七类业务对象，不是通用 action、SQL 或 Shell 代理。
- 写请求需 `Content-Type: application/json`、`X-Forge-Client: 1`；可选 URL 编码的 `X-Forge-Actor`。
- action 见 `store.py` 的显式映射；所有语义验证与事务集中于 Store。
- 仅绑定 IPv4 回环；严格检查 Host、Origin，拒绝大请求与任意 Shell 执行。

## 验证与演示

```sh
PATH="$HOME/.local/share/forge-devops/venv/bin:$PATH" CLI_ANYTHING_FORCE_INSTALLED=1 \
  "$HOME/.local/share/forge-devops/venv/bin/python" -m pytest devops/agent-harness/cli_anything/devops/tests/ -v
node --test devops/agent-harness/cli_anything/devops/tests/test_web_refresh.cjs
PATH="$HOME/.local/share/forge-devops/venv/bin:$PATH" \
  "$HOME/.local/share/forge-devops/venv/bin/python" devops/agent-harness/seed_demo.py
```

演示脚本通过已安装 CLI 创建明确标记的 DEMO 项目；若同名项目已存在则保留不变。测试使用临时数据库和随机端口，与日常数据分离。依赖 Node.js 仅用于可选 PM2；服务本身是 Python。

## 当前边界

本版本为本机单用户应用，不是 Jira 的服务连接器或完整替代品。工作类型 epic 为分类，尚无父子工作项树。发布状态是记录和完成度门禁，不会运行外部 CI/CD 或真实部署。Actor、request ID 与删除 confirmation 都不是身份认证。没有多用户权限、远程公开访问、内嵌聊天模型或自动开机启动。Codex 对话发生在 Codex 应用中。MCP 默认注册 8 个原查询工具与 7 个对象工具；需要兼容只读部署时使用 `forge-devops-mcp --read-only`，详见 [MCP 接入](../../docs/MCP.md)。

参考：https://www.atlassian.com/software/jira/features · https://www.atlassian.com/software/jira/features/scrum-boards
