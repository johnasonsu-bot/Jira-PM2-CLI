# 长安需求与 Forge 工作项整合设计

用户已批准执行。范围：将所提供代码包及同目录原系统的完整业务数据整合到现有 Forge 工作项和工作看板，为后续需求分析保留可追溯证据。

## 数据与边界

- 压缩包：1,472 条初始需求，4 份解析正文和原应用代码。原本地 MySQL：4 个项目、1,472 条当前需求、6,689 个 GWT 场景、16 条字段规则、1 条导入记录。读取采用一致性只读事务，不执行原脚本或建表 SQL。
- 保留完整压缩包、所有原表字段、NULL、长正文、原始 JSON、文档正文、原场景和导入批次。业务内容保存在本机用户数据目录与 Forge SQLite，不进入公开 Git 仓库。
- 新建 P1/P2/P3/P4 四个 Forge 项目，分别映射原实施包。一条需求对应一个工作项，原 req_code 为外部标识；现有 DEMO/APP 不变。项目编号已被无关项目占用时整批拒绝，不合并覆盖。
- 原始快照不可编辑；可编辑分析字段和 GWT 场景以覆盖层保存，带版本冲突保护和审计。全量导出包含原始快照及分析覆盖层，重复相同导入无副作用；不同快照同 source_id 拒绝覆盖。
- 需求评估状态与研发工作项状态分离。所有当前原需求“待评估”导入待办池；不虚构负责人、迭代、工时或完成情况。人天与 SP 分开。缺失原优先级明确标注，工作项调度优先级默认中不作为需求确认依据。

## 实现

在同一个 SQLite 增加 imports、requirement_links、requirement_scenarios 表，原 issues 表保持兼容。新 requirements.py 实现导入、概要、详情、分析更新、场景更新、完整导出。Store.call 统一事务入口；HTTP 增加仅本机同源的大包导入入口，普通操作仍限制 64 KiB。CLI 使用同一 API；MCP 添加只读需求查询与报告，不暴露导入或任意执行。

工作项与看板共用需求筛选：系统、章节、需求类型、缺失字段、关键词。卡片和列表可见原需求编号和系统；需求详情显示完整原文、来源上下文、11 个源文档必备字段检查、GWT 列表、补充分析和导出。工作项分页、看板每列分段加载，不静默截断；数量与筛选范围一致。

## API 合同（供界面使用）

- issue.list、/api/state 的每项可有 requirement：{req_code,system_name,chapter,module_path,req_type,priority,status,workload_md,is_common,missing:[字段键],filled,need:11,scenario_count,confirmed_scenario_count}；普通项无该字段。
- issue.get 的 requirement 替换为详情：{source_id,req_code,raw:原数据库行,original:压缩包行或null,current:合并分析字段后需求行,version,missing,filled,need:11,scenarios:[{scenario_code,raw,current,version}],source:{file,line,excerpt},...概要字段}。
- requirement.update {key,version,fields:{priority,acceptance_criteria,deliverable,workload_md,related_systems,biz_owner,owner_side,status,remark}} → requirement 详情；所有 fields 可部分更新，workload_md 为非负数或 null，priority 为 P0/P1/P2 或 null，status 为待评估/已确认/开发中/已验收/已否决。工作项状态不自动改变。
- requirement.scenario.update {key,scenario_code,version,fields:{title,given_text,when_text,then_text,scenario_type,status,remark}} → 更新后的 scenario；status 为待复核/已确认/已废弃，确认时 derived=0，改正文重新待复核 derived=1。原场景始终保留。
- requirement.report {project} → {total,scenario_count,confirmed_scenario_count,common_count,fields:[{key,label,filled,total,rate}],by_system:[{name,count}],by_type:[{name,count}],methodology}。
- requirement.export {source_id} → {snapshot:原导入包,requirements:[{key,req_code,fields,version}],scenarios:[{key,scenario_code,fields,version}]}。
- requirement.import {bundle} → {source_id,digest,projects,requirements,scenarios,reused}，仅通过 /api/requirements/import 接收大型请求。

## 验收

自动测试覆盖原文 >10,000 字、未知字段、NULL、来源、场景、幂等导入、失败事务回滚、编号冲突、乐观锁、XSS 转义、普通工作项兼容和 CLI/MCP 真实连接。部署前备份现有 SQLite；部署后用公开 API 全量导出逐字段比较源快照，核对每个需求与工作项一一对应。浏览器检查实际工作项与看板、筛选、详情和分页；不修改真实需求来做验收测试。
