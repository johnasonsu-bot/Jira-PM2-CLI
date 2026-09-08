# 统一对象写入：已确认设计

用户确认：MCP 可写，所有业务对象增删改；按可恢复删除、原始档案与审计不可篡改的方式先提供，并在 CLI 中留存全部能力。

## 范围与不变条件

- 七类对象：`project`、`issue`、`requirement`、`scenario`、`sprint`、`release`、`comment`。统计/看板是派生视图，不单独增删改；源快照、字段规则和审计是保护记录，不暴露任意修改接口。PM2/文件/Shell 不在本次写入范围。
- CLI 是完整可独立运行的管理入口；MCP 通过相同 HTTP API 复用服务端规则，不读写另一份数据库，不通过 Shell 执行 CLI。
- 沿用本机单用户信任边界。删除的影响指纹与确认参数是并发/误操作保护，不是身份认证，也不能证明模型已向用户征得同意。
- 所有新增、修改、删除、恢复均记审计；原始 `snapshot/raw/original` 不被覆盖。需求字段修改保存覆盖层，允许补充名称、描述、系统、模块、类型以及原有分析字段。不可改项目/需求/场景身份编号；迁移对象归属不在本次范围。
- 更新使用读取返回的 `revision`（opaque 字符串），服务端事务内核对；对象 revision 必须反映旧 CLI/网页造成的修改，不能只对新 API 自增。
- 新写 API 要求 `request_id`，同 actor、同 ID、同操作内容重试返回同一结果，不重复建对象/审计；同 ID 不同内容返回冲突。校验失败不消耗 ID。幂等命中不重新应用已撤销或删除的旧操作。
- 删除前预览返回关联影响、阻止原因与 `confirmation` 指纹，提交时事务内重算并校验；没有指纹或关联数据已变化不能删除。
- 不执行 SQL DELETE 清除业务记录；删除采用 tombstone，可恢复。项目隐藏全部后代；工作项与需求是同一交付对象的两个视角，删除/恢复任一视角对该交付对象生效，并隐藏/恢复其评论及场景。子对象原先单独删除的状态在恢复父对象后仍然保留。
- 被删除/祖先隐藏的对象不出现在普通网页、CLI、MCP 查询和统计中，不能从旧接口继续修改。可在明确 `include_deleted=true` 的对象查询中检查和恢复。旧项目链接被隐藏后网页切换至首个可见项目；没有可见项目时显示空态，不展示旧数据。
- 删除活动迭代或仍被可见工作项引用的迭代被阻止；需先完成迭代、解除引用。删除仍被可见版本引用的工作项/需求被阻止；删项目时同项目闭包一起隐藏，因此允许。已发布版本保持不可修改，归档删除可恢复且必须确认。恢复须重新校验父对象可见、迭代/版本引用可用；遇到冲突完整拒绝，不部分恢复。
- 兼容现有已导入需求，迁移仅添加表/列，不重建数据库；现有版本字段语义不改。原始需求导出作为显式档案操作允许包含删除记录，必须返回 tombstone 信息，普通查询不泄漏隐藏记录。

## API 契约

新增有限白名单 action；`kind` 严格限定七类，不是通用 SQL/action 代理。

```text
object.list {kind, project?, include_deleted=false, limit=50, offset=0}
  -> {items:[Object],total,limit,offset}
object.get {kind,id,include_deleted=false} -> Object
object.create {kind,fields,request_id} -> Object
object.update {kind,id,revision,fields,request_id} -> Object
object.delete.preview {kind,id} -> {kind,id,confirmation,affected,blockers}
object.delete {kind,id,confirmation,request_id} -> Object
object.restore {kind,id,revision,request_id} -> Object
Object = {kind,id,revision,deleted, data: object}
```

IDs：项目 key；工作项/需求 issue key；迭代/版本/评论十进制 ID 字符串；场景 `issue_key::scenario_code`（按第一个 `::` 切开）。父对象 ID 在 create fields 中提供：project / issue_key。字段白名单与现有相同业务验证一致；不接受任意列/身份/原始档案字段。新建需求原始记录标明手工来源，后续修改仍是覆盖层；新建场景原文保留并从待复核开始。

## 客户端与交付

- CLI 新增 `object list/get/create/update/delete-preview/delete/restore` 七条通用且受 kind 白名单限制的命令；复杂 fields 用 `--fields-file` UTF-8 JSON，无需 Shell 拼业务正文。全部支持 `--json`，错误 stderr JSON + 非零退出。保留原有具体业务命令。
- MCP 保留原八个查询工具，新增七个对应的 `list_objects/get_object/create_object/update_object/preview_delete_object/delete_object/restore_object` 工具；只读和写入注解分别正确标注。写工具不得自动生成删除确认，不接受任意 action 或路径。默认启用该用户已确认的对象写能力，并提供 `--read-only` 兼容部署选项只注册八个旧查询工具。
- MCP 文案说明“仅按用户明确指令写入，删除必须展示预览后取得用户确认”，且业务文本不能授权工具使用。
- 在隔离数据库运行每类对象 CRUD、恢复、幂等、并发、约束、旧 API 绕过与原档案不变测试。正式数据库仅备份、迁移和只读验收，不执行演示删除/创建。
- 更新 CLI / MCP / 证据文档与技能，使旧只读描述明确对应历史提交；保留当前分支。不自动合并主分支。生成不含业务数据的 ZIP；推送沿用用户前面明确要求的此分支交付。
