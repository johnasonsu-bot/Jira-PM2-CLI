# 本地构建与复核

Forge 的网页是随 Python 包发布的静态资源，不需要额外 npm 打包。源码存在两个 Python 发行包：`cli-anything-devops`（包括 CLI、HTTP 服务、MCP）和 `cli-anything-pm2`。构建 Wheel 不代表这三个 Forge 入口已拆为独立发行包。

## 构建产物

先固定待构建提交，并从 Git 导出到新的临时目录，在导出副本内构建，避免构建产生的 `build/`、egg-info 等文件干扰正在运行的源码目录。保留已有构建结果，不覆盖旧目录。

在导出副本根目录，用已经装有 `pip`、`setuptools`、`wheel` 的构建 Python 环境执行：

```sh
python -m pip wheel --no-index --no-deps --no-build-isolation --no-cache-dir \
  --wheel-dir /absolute/path/to/new-build-output \
  ./devops/agent-harness ./pm2/agent-harness
```

`--no-index` 禁止构建期间访问软件索引，`--no-deps` 不更新现有运行依赖。若构建工具尚未安装，应先准备单独的构建环境，不要为了生成 Wheel 改动正在提供服务的环境。

预期产物：

- `cli_anything_devops-0.1.0-py3-none-any.whl`：Forge CLI、HTTP 服务、MCP、包内网页资源。
- `cli_anything_pm2-1.0.0-py3-none-any.whl`：独立 PM2 Python CLI；独立 Node PM2 dashboard 不属于此 Wheel。

这两个 Wheel 不捆绑全部第三方依赖，也不包含业务数据库。安装到新环境时，仍需按包元数据准备依赖；MCP 是 Forge 的可选依赖。

## 验证与启动

1. 检查 Wheel 的 ZIP CRC、包内模块/资源、METADATA、entry_points.txt 和 SHA-256。
2. 从实际构建产物加载模块，确认导入路径不是原源码目录，检查 CLI/MCP 帮助和隔离业务验收。
3. 重新执行项目回归测试，命令见根目录 README；真实 PM2 进程生命周期测试不属于日常安全回归。
4. 本机已有安装为 editable 形式时，核对其源码位置确实是本仓库；无需为同一份代码强制卸载/重装现有环境。Wheel 保留为可分发的构建结果。
5. 若需要更新运行服务，先对正式 SQLite 做在线备份，记录原表的行数和内容摘要；核实 PM2 中唯一的 `forge-devops` 进程及其入口，只重启该进程，不使用 `--update-env`。
6. 复核 HTTP 健康、CLI 对象查询、真实 MCP stdio 发现和查询、数据库完整性及更新前后表内容一致。写入验收只在临时数据库执行。

不要重置或重复导入数据，也不要自动启动第二个实例占用 8766。既有服务未启用公网认证；构建和启动不改变本机单用户安全边界。

## 三件套交付的留存记录

此前 `cbe8ecd` 三件套的完整文件名、服务代码定位、MCP 信息、CLI 专项包依赖说明与测试边界见 [交付代码证据](DELIVERY-CODE-EVIDENCE.md)。当时两个 ZIP 各自包含独立证据 Markdown 和源码摘要清单，CLI 包排除了独立 PM2 dashboard，但保留 Forge 发行包的共享服务依赖。

旧包使用其原始提交号命名；后续仅补充文档，不应把旧 ZIP 改名成新的提交号。新的本机构建应标注本次实际源码提交，并在仓库外保存产物和验证记录。
