# Jira · PM2 · CLI — Forge DevOps

参考 Jira 工作流的本地研发管理系统，附带 PM2 进程控制台和 CLI-Anything 命令行接口，可由 Codex 通过对话操作。

当前 Forge 版本：**0.1.0**。这是代码发布，不包含本机业务数据，也不是已部署的公网服务。

## 功能

- 项目、工作项、五列看板、评论与变更审计。
- 迭代和版本管理，版本发布前检查关联工作项是否全部完成。
- 项目 / 当前迭代 / 指定迭代分析：12 项核心指标、数据完整性、风险清单、负责人工作量、版本门禁。
- PM2 进程状态页面和受限命令输入；独立 PM2 CLI。
- Forge HTTP CLI、JSON 输出、交互式 REPL 与 Codex Skill。

## 快速启动 Forge

需要 Python 3.10+；可选 PM2 功能还需要 Node.js 与已安装的 PM2。

```sh
git clone git@github.com:johnasonsu-bot/Jira-PM2-CLI.git
cd Jira-PM2-CLI
python3 -m venv .venv
source .venv/bin/activate
pip install -e 'devops/agent-harness[dev]'
forge-devops-server --port 8766
```

打开 [Forge 工作台](http://127.0.0.1:8766/)。默认数据库位于 `~/.local/share/forge-devops/data.sqlite3`；如需独立数据，请使用 `--db /path/to/data.sqlite3`。不要启动第二个实例占用已使用的端口。

在另一个已激活虚拟环境的终端中：

```sh
cli-anything-devops --json health
cli-anything-devops --json project list
```

可选演示数据：`python devops/agent-harness/seed_demo.py`。脚本创建明确标注的 DEMO 项目，同名项目已存在时保留不变。管理分析入口为 [当前迭代分析](http://127.0.0.1:8766/?project=DEMO&view=analytics&scope=active)。

## PM2 托管和进程控制台

PM2 安装后，Forge 可由 `python devops/agent-harness/manage.py start` 托管；查询使用 `python devops/agent-harness/manage.py status`。仅在没有手动启动 Forge、且端口空闲时使用托管启动。

在仓库根目录启动可选进程控制台：

```sh
PM2_BIN="$(command -v pm2)" node pm2/agent-harness/dashboard/server.js
```

显式指定 `PM2_BIN` 可以覆盖原型中的本机默认路径。打开 [PM2 控制台](http://127.0.0.1:8765/)。支持进程列表、指标、日志，以及指定进程的停止和重启；停止与重启会影响真实进程。

独立 PM2 CLI 的安装和命令见 [PM2 文档](pm2/agent-harness/cli_anything/pm2/README.md)。建议安装到单独的虚拟环境，与 Forge 环境隔离。

## Codex 对话操作

本地 MCP 提供八个只读工具，支持结构化工作量排名和导入需求的原文、GWT 场景及完备率查询。安装额外依赖 `pip install -e 'devops/agent-harness[dev,mcp]'`，并按 [MCP 接入指南](docs/MCP.md) 注册到 Codex。MCP 按需启动，无额外监听端口。

工作项与看板已支持来源需求编号、系统/章节/需求类型筛选、完整原文追溯、带版本保护的分析补充和 GWT 复核。原始档案不覆盖，业务数据不进入本仓库，详见[需求整合说明](docs/REQUIREMENTS.md)。

向 Codex 指定 [Forge Skill](skills/cli-anything-devops/SKILL.md)，并确保 `cli-anything-devops` 在 PATH 中。例如：“列出项目，分析 Forge 当前迭代的逾期和高优先级工作项”。对话发生在 Codex 中，网页没有内嵌聊天模型，也不需要模型 API Key。

## 验证

```sh
pip install -e 'devops/agent-harness[dev,mcp]'
CLI_ANYTHING_FORCE_INSTALLED=1 python -m pytest devops/agent-harness/cli_anything/devops/tests/ -q
PYTHONPATH=pm2/agent-harness python -m pytest pm2/agent-harness/cli_anything/pm2/tests/test_core.py -q
node --test devops/agent-harness/cli_anything/devops/tests/test_web*.cjs pm2/agent-harness/dashboard/test/*.test.js
```

Forge 测试使用临时数据库和随机端口。上述 PM2 单元测试使用模拟调用，不修改真实进程；未包含会操作真实 PM2 的端到端测试。

## 使用边界

仅供可信本机、单用户使用。不要将 Forge 或 PM2 控制台端口转发到公网；PM2 原型控制台没有登录和完整的跨站请求防护。Actor 是来源标签，不是身份认证。版本发布是管理记录，不会执行 CI/CD。缺少真实历史采集的燃尽、速率、容量和 DORA 指标不会伪造。

详细说明见 [Forge 文档](devops/agent-harness/README.md)。上游来源与许可证见 [第三方声明](THIRD_PARTY_NOTICES.md) 和 [LICENSE](LICENSE)。
