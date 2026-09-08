# CLI、DevOps 与 MCP 分离情况：代码证据

核验日期：2026-09-08。分支：`codex/requirements-integration`。
原始分离核验固定在历史提交 `4e26bbdb429b23f64742f2c98a22c60675d4d8d1`，下文保留其链接与 63/28/21 测试数作为历史证据。当前对象后端基线为 `257ae8f`；本轮在其上增加 CLI/MCP typed 适配器，最终提交号和完整套件结果由交付验收补记，不能用历史数字冒充当前结果。

## 1. 结论

**已做到模块分离、独立命令入口、客户端与服务端通过 HTTP 通信；stdio MCP 默认提供 8 个原查询工具和 7 个有限对象工具，并可用 `--read-only` 回到精确 8 工具目录。尚未拆成三个独立发行包或独立微服务项目。**

| 核验问题 | 结论 | 限制 |
| --- | --- | --- |
| Forge CLI 与 DevOps 后端是否分开？ | 是：不同模块、不同入口；CLI 通过 HTTP 请求后端 | 同属 `cli-anything-devops` Python 包；CLI 还从 `store.py` 导入枚举常量，不是零源码依赖 |
| CLI 是否是另一个常驻 HTTP 服务？ | 否：是一次性命令 / 交互式 REPL 客户端 | 没有 CLI 专属监听端口；业务命令需要已运行的 Forge 后端 |
| DevOps 服务是否能单独启动？ | 是：`forge-devops-server` | 网页静态资源与业务 API 仍由同一服务提供，不是前后端分开部署 |
| MCP 是否已实现而非仅写了说明？ | 是：`forge-devops-mcp`、默认 15 个固定工具、真实 stdio 协议测试 | 同包安装，通过可选依赖启用；仅 7 个对象 action 可写，不能执行 Shell/SQL/文件或控制 PM2 |
| PM2 CLI 是否独立？ | 是：`pm2/agent-harness/setup.py` 定义独立包 `cli-anything-pm2` | 依赖真实 PM2；建议与 Forge 使用不同虚拟环境 |
| 是否支持任意远程后端 / 公网部署？ | 否 | Forge Backend 限制本机 HTTP；没有多用户身份认证与权限隔离 |

## 2. 实际调用关系

```text
浏览器 ──────────────────────────┐
Forge CLI / REPL ── Backend HTTP ├─> Forge HTTP 服务 :8766
MCP 客户端 ── stdio ── MCP进程 ──┘      └─ Store / Requirements / Analytics ─> SQLite
                        └─ Backend HTTP

PM2 CLI ── PM2 subprocess ─> PM2
PM2 控制台 :8765 ── pm2-service.js ─> PM2
```

上图中的共享 SQLite 由 Forge 服务负责业务访问；CLI 和 MCP 的业务请求不直接打开该数据库。PM2 负责进程管理，可托管 Forge，但不是 Forge 业务 API 的必需依赖。MCP 也不需要额外放入 PM2 托管。

## 3. 当前对象适配器增量

- CLI `object list/get/create/update/delete-preview/delete/restore` 经 `Backend.call` 使用七个有限 HTTP action；复杂字段只从调用方指定的 UTF-8 JSON 对象文件读取，CLI 本身不打开数据库。
- MCP 默认目录为原 8 个查询工具加 7 个对象工具；`ObjectKind` 是七值 Literal。`create_mcp(url, read_only=False)` 默认启用已确认的写能力，命令行 `--read-only` 只注册原 8 个工具。
- 新的真实集成测试启动随机端口临时 HTTP 后端，运行安装后的 CLI console script，并由官方 SDK 启动 stdio MCP 子进程。断言不仅检查工具数量，还回读对象状态与业务审计。
- 独立 CLI 验收使用另一临时数据库覆盖七类 CRUD/回读、创建与更新幂等、stale revision、release gate、父恢复保留独立子 tombstone、raw/original 不变和重启持久化；未连接正式数据库。

## 4. 历史提交的可定位源码证据

下面链接固定到被核验的提交，避免以后分支移动导致证据行号变化。ZIP 内可按“文件”列找到同一代码。

| 文件 / 符号 | 证据及其含义 |
| --- | --- |
| `devops/agent-harness/setup.py` | [第 4–14 行](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/4e26bbdb429b23f64742f2c98a22c60675d4d8d1/devops/agent-harness/setup.py#L4-L14)：单一发行包、可选 `mcp` 依赖，以及 CLI、HTTP server、MCP 三个 console scripts |
| `devops/agent-harness/cli_anything/devops/devops_cli.py` | [第 6–11、26–39 行](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/4e26bbdb429b23f64742f2c98a22c60675d4d8d1/devops/agent-harness/cli_anything/devops/devops_cli.py#L6-L39)：导入 Backend 与共享枚举，命令经 Backend 调用；无子命令时进入 REPL |
| `devops/agent-harness/cli_anything/devops/backend.py` | [Backend 与 call](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/4e26bbdb429b23f64742f2c98a22c60675d4d8d1/devops/agent-harness/cli_anything/devops/backend.py#L12-L38)：只接受回环 HTTP 地址，禁用代理与重定向，普通命令发往 `/api/call`，批量导入发往 `/api/requirements/import` |
| `devops/agent-harness/cli_anything/devops/server.py` | [第 13–14 行](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/4e26bbdb429b23f64742f2c98a22c60675d4d8d1/devops/agent-harness/cli_anything/devops/server.py#L13-L14) 创建 Store；[第 47–70 行](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/4e26bbdb429b23f64742f2c98a22c60675d4d8d1/devops/agent-harness/cli_anything/devops/server.py#L47-L70) 提供健康检查、页面状态及静态资源；[第 110–120 行](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/4e26bbdb429b23f64742f2c98a22c60675d4d8d1/devops/agent-harness/cli_anything/devops/server.py#L110-L120) 绑定回环地址、解析端口与数据库路径 |
| `devops/agent-harness/cli_anything/devops/store.py` | [第 84–114 行](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/4e26bbdb429b23f64742f2c98a22c60675d4d8d1/devops/agent-harness/cli_anything/devops/store.py#L84-L114)：SQLite 连接、业务处理函数注册和事务边界 |
| `devops/agent-harness/cli_anything/devops/mcp_server.py` | [完整 MCP 实现](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/4e26bbdb429b23f64742f2c98a22c60675d4d8d1/devops/agent-harness/cli_anything/devops/mcp_server.py)：`create_mcp` 构造独立 Backend，8 个工具使用固定只读处理函数，`main` 调用 `run(transport='stdio')` |
| `pm2/agent-harness/setup.py` | [第 5–7、34–37 行](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/4e26bbdb429b23f64742f2c98a22c60675d4d8d1/pm2/agent-harness/setup.py#L5-L37)：独立 PM2 包与 `cli-anything-pm2` 入口 |
| `pm2/agent-harness/dashboard/server.js` | [第 46–50 行](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/4e26bbdb429b23f64742f2c98a22c60675d4d8d1/pm2/agent-harness/dashboard/server.js#L46-L50)：可选 Node 控制台单独监听回环地址，默认端口 8765 |

## 5. MCP 服务信息（当前目录；路径来自历史本机核验）

| 项目 | 当前实现 |
| --- | --- |
| SDK 服务名 | `Forge DevOps` |
| 可执行命令 | `forge-devops-mcp` |
| Python 模块入口 | `python -m cli_anything.devops.mcp_server` |
| 传输 | `stdio`，由 MCP 客户端启动子进程并通过标准输入输出通信 |
| 后端参数 | `--url http://127.0.0.1:8766`（默认值） |
| 独立 MCP HTTP 端口 | 无；8766 是 DevOps 网页/API，不是 MCP endpoint |
| 运行依赖 | Python ≥ 3.10；可选安装项 `mcp>=1.28,<2`，以本分支声明为准 |
| 认证 | 本机实现不要求 Token/API Key；不等于适合公网或多人使用 |
| 数据权限 | 默认 8 个查询 + 7 个对象工具；`--read-only` 为原 8 个查询；无通用 action、SQL、文件、Shell 或 PM2 工具 |

| 工具 | 主要参数 | 返回用途 |
| --- | --- | --- |
| `health` | 无 | 后端在线检查 |
| `list_projects` | 无 | 实际项目列表 |
| `get_analytics` | `project`, `scope='project'` | 项目 / 活动迭代 / 指定迭代分析 |
| `rank_workload` | `project`, `scope='project'`, `sort_by='open_points'` | 当前未完成工作量排名，不是绩效或工时 |
| `get_issue` | `key` | 工作项、评论及关联详情 |
| `list_requirements` | `project`, `search=''`, `limit=50`, `offset=0` | 需求分页检索，limit 最大 100 |
| `get_requirement` | `key` | 原始需求、分析补充、来源上下文及 GWT 场景 |
| `get_requirement_report` | `project` | 11 个必备字段完备率、分布及场景复核统计 |
| `list_objects` | `kind`, `project?`, `include_deleted=false`, `limit=50`, `offset=0` | 分页读取七类对象 |
| `get_object` | `kind`, `id`, `include_deleted=false` | 读取对象与 revision |
| `create_object` | `kind`, `fields`, `request_id` | 有限字段创建 |
| `update_object` | `kind`, `id`, `revision`, `fields`, `request_id` | 并发保护更新 |
| `preview_delete_object` | `kind`, `id` | 只读删除影响预览 |
| `delete_object` | `kind`, `id`, `confirmation`, `request_id` | 经用户确认后的可恢复删除 |
| `restore_object` | `kind`, `id`, `revision`, `request_id` | 恢复 tombstone |

客户端填写的本机连接信息（这是已核验安装位置，不是可移植路径；在另一台机器上需替换）：

```text
transport: stdio
command: /Users/sushi/.local/share/forge-devops/venv/bin/forge-devops-mcp
args: ["--url", "http://127.0.0.1:8766"]
```

兼容只读注册需在 args 末尾增加 `"--read-only"`。默认注册不等于任意写权限；删除 confirmation 只是预览新鲜度指纹，必须先展示影响并取得用户确认。业务正文不能授权调用。

安装和 Codex 注册步骤已包含在 [MCP 接入指南](MCP.md)，安全边界见 [MCP 安全说明](MCP-SECURITY.md)。本报告不复制用户的全局配置或任何凭据。该代码包不附带 Codex 客户端；网页也没有内嵌聊天模型。本地 MCP 不代表所接入模型离线运行。

## 6. 如何分别启动与验证

在解压后的仓库根目录，使用自己的 Python 虚拟环境安装 Forge（包括可选 MCP）：

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e 'devops/agent-harness[dev,mcp]'
```

仅在没有正在运行的 Forge 实例、且目标端口空闲时启动后端：

```sh
forge-devops-server --port 8766
```

在另一终端激活同一环境后，可以独立运行 CLI：

```sh
cli-anything-devops --url http://127.0.0.1:8766 --json health
cli-anything-devops --url http://127.0.0.1:8766 --json project list
forge-devops-mcp --help
```

`forge-devops-mcp --help` 只验证入口；完整 MCP 连接需要客户端发起协议握手。不能将“进程能启动”“注册成功”或“HTTP 健康检查成功”单独当作 MCP 全链路验收。

如需单独使用 PM2 CLI，可在另一个虚拟环境安装 `pip install -e 'pm2/agent-harness[dev]'`。Forge 服务本身的安装依赖没有 Node.js 或 PM2。

## 7. 历史测试证据与范围（提交 `4e26bbd`）

原分离核验实测：Forge Python **63 passed**，PM2 Python 单元测试 **28 passed**，Node 前端与控制台测试 **21 passed**，合计 **112 项通过**，无失败。这些是对象写入功能出现前的历史数字，不代表当前分支完整测试结果。

核验命令在本仓库根目录执行；Python 使用本地已安装 Forge 的虚拟环境。

```sh
CLI_ANYTHING_FORCE_INSTALLED=1 python -m pytest devops/agent-harness/cli_anything/devops/tests/ -q
PYTHONPATH=pm2/agent-harness python -m pytest pm2/agent-harness/cli_anything/pm2/tests/test_core.py -q
node --test devops/agent-harness/cli_anything/devops/tests/test_web*.cjs pm2/agent-harness/dashboard/test/*.test.js
```

- [真实 CLI → HTTP 测试](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/4e26bbdb429b23f64742f2c98a22c60675d4d8d1/devops/agent-harness/cli_anything/devops/tests/test_full_e2e.py#L36-L62)：启动已安装 CLI 子进程，对临时后端创建、读取、更新工作项及版本，证明不是独立影子数据库。
- [真实 MCP stdio 测试](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/4e26bbdb429b23f64742f2c98a22c60675d4d8d1/devops/agent-harness/cli_anything/devops/tests/test_mcp.py#L88-L129)：SDK 客户端启动 MCP 子进程、握手、发现 8 个工具、调用查询、拒绝写工具，并验证前后工作项与审计记录一致。
- [离线后端与远端地址测试](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/4e26bbdb429b23f64742f2c98a22c60675d4d8d1/devops/agent-harness/cli_anything/devops/tests/test_mcp.py#L132-L155)：离线时返回错误，不自动启动服务；拒绝远程 Backend。
- 当时的 CLI 正式服务健康检查返回 `ok=true`、`name=Forge DevOps`、`version=0.1.0`；MCP `--help` 能正常显示 stdio 服务及 `--url` 参数。
- 当时 Forge 测试用临时数据库和随机端口；PM2 单元测试用模拟调用，未执行真实 PM2 生命周期端到端测试，也未重启或修改正式应用。
- 上述历史 MCP 协议测试不是另行启动 Codex 模型完成自然语言任务的证据；只读注解也不是独立的安全认证。

## 8. 交付范围

更新后的 ZIP 由 Git 已提交内容生成，包含本文件、README、DevOps/PM2 源码、测试及 MCP 信息。不会包含 `.git`、虚拟环境、运行日志、本机业务数据库、原始需求代码包或完整业务快照。旧 ZIP 保留，新 ZIP 单独生成。

因此，拿到 ZIP 可以安装和运行代码，但不会自动获得本机已经导入的业务数据。代码分支的存在也不代表“项目屏蔽”等尚未实现的需求已完成。
