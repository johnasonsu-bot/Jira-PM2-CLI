# 服务、DevOps、CLI-Anything 与 MCP：交付代码证据

> 归档说明：这是源码提交 `cbe8ecd` 对应的三件套交付证据。下文“本次”指该次打包，不是后续本机构建；文件名称、固定链接和测试结果按当时记录保留。后续构建步骤见 [本地构建说明](LOCAL-BUILD.md)。

核验日期：2026-09-08。源码分支：`codex/requirements-integration`。

固定源码提交：`cbe8ecdb8f4c8d0650fba057d001425252b1f841`。本次仅重新组织交付文件，不修改业务代码、不重启服务、不操作正式业务数据。

## 一、结论与三个文件的区别

已经实现独立命令入口和 HTTP 客户端/服务端边界；Forge CLI、DevOps 服务、MCP 仍属于同一个 Python 发行包，不能将单独 ZIP 误认为已拆成三个独立微服务。

| 文件 | 用途 | 内容边界 |
| --- | --- | --- |
| `01_Forge完整系统源码_含DevOps服务和MCP_cbe8ecd.zip` | 完整系统交付 | 当前提交全部源码、DevOps 网页/API、Forge CLI、MCP、PM2 CLI 与控制台、测试、原文档，并附本文 |
| `02_服务与DevOps及MCP_代码证据_cbe8ecd.md` | 独立审阅证据 | 当前提交的代码定位、服务入口、MCP 协议/工具、安装方式和核验范围；同一份文件也放入两个 ZIP 根目录 |
| `03_CLI-Anything代码包_ForgeCLI与PM2CLI_cbe8ecd.zip` | CLI 代码专项交付 | Forge agent-harness、PM2 Python CLI、安装描述、技能、测试、相关文档和脚本；不含独立 PM2 网页控制台 |

两个 ZIP 均不含 `.git`、虚拟环境、日志、数据库、业务数据备份或完整导入快照。拿到代码不会自动获得本机已导入的需求数据。旧 ZIP 不覆盖、不删除。

CLI 专项包保留 Forge harness 的共享服务模块和包内网页资源，原因是原 `setup.py` 同时声明 CLI、HTTP server、MCP 入口及资源，且 CLI 从 `store.py` 导入枚举。它是可用于安装原有包的源码子集，不是本轮新拆出的“零后端依赖纯客户端包”。PM2 CLI 则已有自己的独立 `setup.py`。

## 二、调用与数据边界

```text
浏览器 ──────────────────────────────────┐
Forge CLI / REPL ── Backend HTTP ────────┼─> Forge DevOps HTTP :8766
MCP 客户端 ── stdio ── MCP ── Backend ──┘       └─ 业务规则 / SQLite

PM2 CLI ── subprocess ── PM2
PM2 网页控制台 :8765 ── PM2（仅完整系统 ZIP 提供控制台）
```

Forge CLI 和 MCP 的业务操作通过同一个 HTTP API，未维护另一份数据库。CLI 是一次性命令或交互式 REPL，不是另一个常驻 HTTP 服务。MCP 使用标准输入输出，没有自己的 HTTP 监听端口；8766 是 DevOps 网页/API 地址，不是 MCP URL。

## 三、当前提交的可定位源码证据

以下链接固定到本次打包提交，而不是会移动的分支头。表中路径也可在 ZIP 内直接查找。

| 对象 | 文件与固定定位 | 证据含义 |
| --- | --- | --- |
| Forge 发行包和三个入口 | [devops/agent-harness/setup.py:4](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/devops/agent-harness/setup.py#L4) | 包名 `cli-anything-devops`；三个 console scripts；MCP 为可选依赖 |
| Forge CLI | [devops_cli.py:8](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/devops/agent-harness/cli_anything/devops/devops_cli.py#L8)；[object 命令组:80](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/devops/agent-harness/cli_anything/devops/devops_cli.py#L80) | 共享枚举仍有源码依赖；命令经 Backend 执行；统一对象增删改、恢复和查询 |
| HTTP 客户端 | [backend.py:11](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/devops/agent-harness/cli_anything/devops/backend.py#L11) | 只接受本机 HTTP，禁用代理和重定向；普通调用走 `/api/call` |
| DevOps 服务 | [server.py:13](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/devops/agent-harness/cli_anything/devops/server.py#L13)；[绑定地址:120](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/devops/agent-harness/cli_anything/devops/server.py#L120) | 同一服务提供网页和 API，绑定 `127.0.0.1` |
| 数据与事务 | [store.py:86](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/devops/agent-harness/cli_anything/devops/store.py#L86)；[事务:117](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/devops/agent-harness/cli_anything/devops/store.py#L117) | SQLite 连接、业务处理函数白名单及 `BEGIN IMMEDIATE` 事务 |
| 写入与恢复规则 | [objects.py:10](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/devops/agent-harness/cli_anything/devops/objects.py#L10)；[辅助表:16](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/devops/agent-harness/cli_anything/devops/object_lifecycle.py#L16) | 七类对象、request ID 幂等、revision 校验、删除预览和可恢复 tombstone |
| MCP 实现 | [mcp_server.py:31](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/devops/agent-harness/cli_anything/devops/mcp_server.py#L31)；[对象工具:114](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/devops/agent-harness/cli_anything/devops/mcp_server.py#L114)；[stdio 入口:183](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/devops/agent-harness/cli_anything/devops/mcp_server.py#L183) | 真实 FastMCP 服务、有限工具注册及 stdio 运行，不只是接入说明 |
| 独立 PM2 CLI 包 | [pm2/agent-harness/setup.py:6](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/pm2/agent-harness/setup.py#L6)；[PM2 backend:65](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/pm2/agent-harness/cli_anything/pm2/utils/pm2_backend.py#L65) | 独立 `cli-anything-pm2` 包和入口，调用真实 PM2；不属于 Forge MCP 工具 |
| 客户端协议测试 | [test_object_clients.py:105](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/devops/agent-harness/cli_anything/devops/tests/test_object_clients.py#L105)；[MCP:202](https://github.com/johnasonsu-bot/Jira-PM2-CLI/blob/cbe8ecdb8f4c8d0650fba057d001425252b1f841/devops/agent-harness/cli_anything/devops/tests/test_object_clients.py#L202) | 实际 CLI 子进程、SDK stdio、写入回读及审计、只读模式拒绝写工具 |

## 四、服务与 MCP 信息

| 项目 | 已实现值 |
| --- | --- |
| Forge HTTP 服务命令 | `forge-devops-server --port 8766` |
| Forge CLI | `cli-anything-devops`，支持 `--json` 和 REPL |
| MCP 服务名 | `Forge DevOps` |
| MCP 命令 | `forge-devops-mcp --url http://127.0.0.1:8766` |
| MCP 传输 | `stdio`，由客户端启动子进程；无额外 HTTP MCP 端口 |
| 本机已安装 MCP 命令路径 | `/Users/sushi/.local/share/forge-devops/venv/bin/forge-devops-mcp`；其他机器需替换 |
| Python / SDK 声明 | Python ≥3.10；可选 `mcp>=1.28,<2` |
| 默认目录 | 15 个工具：原 8 个查询 + 7 个对象工具 |
| 兼容只读模式 | 加 `--read-only`，仅注册原 8 个查询工具 |
| 信任边界 | 可信本机单用户；无多用户认证；Actor、revision、request ID、confirmation 都不是认证凭据 |

原 8 个查询工具：`health`、`list_projects`、`get_analytics`、`rank_workload`、`get_issue`、`list_requirements`、`get_requirement`、`get_requirement_report`。

新增 7 个对象工具：

```text
list_objects(kind, project?, include_deleted=false, limit=50, offset=0)
get_object(kind, id, include_deleted=false)
create_object(kind, fields, request_id)
update_object(kind, id, revision, fields, request_id)
preview_delete_object(kind, id)
delete_object(kind, id, confirmation, request_id)
restore_object(kind, id, revision, request_id)
```

`kind` 限定为项目、工作项、需求、场景、迭代、版本、评论。7 个对象工具中，list/get/preview 是只读，create/update/delete/restore 才是写入；不存在任意 action、SQL、Shell、文件或 PM2 工具。

删除前必须展示预览影响并取得用户确认；confirmation 仅校验影响是否变化，不证明用户授权。原始需求快照、raw/original 和审计不开放任意覆盖。已连接的 Codex 会话可能缓存工具目录，本报告不宣称当前会话热加载，也不将本地 MCP 等同于离线模型。

## 五、解压后如何使用

在任一 ZIP 的解压根目录，用新的虚拟环境安装 Forge：

```sh
python3 -m venv .venv-forge
source .venv-forge/bin/activate
pip install -e 'devops/agent-harness[dev,mcp]'
cli-anything-devops object --help
forge-devops-mcp --help
```

业务操作需要已运行的 Forge 服务。只有确认没有现有实例、目标端口空闲时，才运行 `forge-devops-server --port 8766`，不要对现有数据进行重置或重复导入。

```sh
cli-anything-devops --url http://127.0.0.1:8766 --json health
cli-anything-devops --json object list project
```

复杂创建/修改字段使用 `--fields-file` 指向 UTF-8 JSON 对象文件；更新需当前 revision，写入需 request ID。完整用法见包内 `docs/OBJECT-WRITES.md`；MCP 接入信息见 `docs/MCP.md`。

PM2 CLI 建议使用另一个虚拟环境：

```sh
python3 -m venv .venv-pm2
source .venv-pm2/bin/activate
pip install -e 'pm2/agent-harness[dev]'
cli-anything-pm2 --help
```

PM2 CLI 的实际管理命令需要机器上已有 Node.js/PM2；`--help` 不等于真实进程管理验收。CLI 专项包没有独立 PM2 dashboard，不能从该包启动 PM2 网页控制台。

## 六、验证证据及限制

本次重新运行 `test_object_clients.py`：**4 passed in 10.16s**。覆盖七类对象的 CLI 生命周期、无效字段/过期 revision、默认 MCP 15 工具及写入回读、只读模式 8 工具及拒绝写入。使用临时数据库和随机端口，不修改正式业务库。

此前同一版本已完成 Forge 109 项、PM2 模拟单元 28 项、Node 21 项回归及正式库迁移前后逐表一致性验证，详见包内 `docs/OBJECT-WRITES.md`；本次不把此前完整测试冒称为全部重新运行。

两个 ZIP 交付前验证 CRC、文件清单及源码字节与固定 Git 提交一致；本文与 CLI 专项 README 是本次新增的交付说明。包内另有 `SOURCE_MANIFEST.json`，记录来源提交、源码文件及新增交付文件的 SHA-256。CLI 专项包另外从实际解压目录检查导入路径、运行命令和隔离生命周期验收。

这些证据证明代码及客户端协议，不等于另行启动 Codex 模型完成自然语言任务的证据，也不是公网/多用户生产安全认证。
