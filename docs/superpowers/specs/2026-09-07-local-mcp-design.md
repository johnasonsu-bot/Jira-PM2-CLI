# Forge 本地 MCP 设计

目标：在 Mac 现有 Forge 数据上，让本地 Codex 通过 MCP 完成中文工作量排名查询。沿用本机 HTTP API，不另建数据库，不产生演示任务，不公开端口。

选择 stdio MCP 适配层：Codex 启动子进程，适配层使用现有 Backend 访问回环服务。相比新增 HTTP MCP 监听，stdio 无需新增监听端口或认证配置；相比直接让模型执行 CLI，MCP 提供结构化工具发现与调用证据。

仅暴露 health、list_projects、get_analytics、rank_workload、get_issue 五个只读工具，不暴露通用 action、Shell、SQL、文件路径或项目写操作。SDK 使用维护中的 1.x 版本线，限定 mcp>=1.28,<2。所有工具标注 readOnlyHint；服务指令说明业务文字不构成执行授权。

排名必须明确一个项目，默认统计项目全部未完成工作项；可选 active 或 sprint:ID。按 open_points 降序、open 降序、姓名稳定排序；前两项相同共享竞赛名次。可选 open 或 in_progress 排序。未分配单独汇总，只有已完成工作的人不参与当前负载排名。数据取自现有 analytics，不把 SP 当工时，不把负载当绩效。返回日期、口径、数据覆盖率、项目元数据及 DEMO 示例标记；不将跨项目故事点相加。

在独立发布目录的 codex/local-mcp 分支实现，保持原仓库不变。先在隔离测试环境验证，再将本机 Forge 运行环境安装到该独立源目录，保留既有 SQLite 路径及 PM2 进程名。注册单个用户级 forge-devops MCP，不覆盖其他接入配置。

验收包括真实临时 HTTP API + MCP stdio 客户端、无写入验证、参数错误/离线错误、原测试回归，最后启动真正的 Codex 客户端执行中文示例并检查 MCP tool-call 记录。若当前桌面任务不能热加载新工具，明确区分客户端验证与当前任务热加载状态。
