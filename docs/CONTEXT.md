# CONTEXT.md · 领域词汇表

架构评审（improve-codebase-architecture）与日常开发共用的领域语言。新概念入册后，评审与代码讨论统一用这些词。

## 执行编排（execution launcher）

- **execution_launcher**（`services/execution_launcher.py`）：执行编排的深模块——数据驱动展开 → 建记录 → 批量提交 → 聚合通知的唯一入口。调用方只有 executions 路由与 scheduler 两类；新触发来源调它即接入全部语义。
- **ExecutionSpec**（`engine/runner.py`）：单条执行的提交规格（record id、用例 id、行变量、列快照、节点配置快照、抑制通知标志）。`submit_batch_execution` 的接口，取代旧的 5 个平行数组。
- **LaunchPlan**：一个用例（× 执行次数轮）的发射计划；多个 plan 可平铺进一个批次专用线程池一次 `commit_launch`。
- **AggregateGroup**（聚合组）：一次数据驱动多行展开的失败聚合通知组——全部终态后只发一条汇总，组内每条抑制逐条通知。
- **批次专用池**：每次批量执行新建 `ThreadPoolExecutor(max_workers=concurrency)`，提交完即回收；与内部后台任务池（聚合通知等零散提交）互不复用。

## 请求组装（prepare_request）

- **prepare_request**（`engine/prepare_request.py`）：请求组装的深模块——三级取值优先级（数据集行值 > 编排 set_field 字面量 > 接口默认值）的唯一调用点，编排顺序（组装→行值覆盖→求值→pre_process→再求值→coerce→apply_field_types→pop_file_fields→headers 求值）成为直接可测单元。调用方仅 dag_executor。
- **RequestParts**：组装产物 dataclass（body / headers / file_fields），取代此前散落的三个平行返回值。

## 引擎原语（engine）

- **topo_order**（`engine/topo.py`）：DAG 拓扑序的唯一实现（Kahn + 节点 id 字典序入队），返回 (拓扑序, 环/断链未入序节点)。执行顺序（dag_executor）与收集口径（dataset_service 同名异值列取源头节点值）共用——入队稳定性改变两边同时生效，不允许再出现平行第二份。
- **set_nested_value**（`engine/preprocessor.py`）：点号路径嵌套设值的唯一实现（数字段索引已存在列表）。body_builder 组装请求体与编排 set_field / 类型强转共用，不再有 dict-only 的平行版本。

## 数据驱动（dataset）

- **snapshot_node_configs**（`services/dataset_service.py`）：用例当前编排 → 数据集节点配置快照的唯一口径（只快照 dag 中存在的节点）；生成/resync/自动同步/drift 四处共用。
- **sync_case_datasets**（`services/dataset_service.py`）：保存用例即同步——用例 update 提交 node_configs/dag_config 时，把该用例绑定的全部数据集 node_configs 一次性重快照（列/行不动，各数据集独立深拷贝）。手动 `resync_node_configs` 降级为兜底入口，drift 检测降级为异常兜底（自动同步失败时不影响用例保存）。

## crud 域拆分

- **crud/versions**（`crud/versions.py`）：项目版本域——快照（snapshot）/对比（diff）/回滚（rollback）整族自 legacy.py 迁出。回滚是高风险机制（删当前全部接口/用例/分组后按快照重建，执行记录分离再重关联），一文件自洽；对外经 crud 包显式 re-export，`crud.rollback_project_version` 等旧引用不变。

## 通知（notifier）

- **notifier**（`services/notifier.py`）：企微通知的深模块——取数（执行人/项目名、环境/数据集名）与门控（webhook 存在性 + enable_on_success/enable_on_failure 开关及默认值）都只在模块内部定义，调用方只交对象与 id，不替通知查表。窄接口两个：`send_notify(db, env, case, record)`（单条）、`send_batch_notify(db, env_id, dataset_id, records, case_name)`（数据驱动聚合）。
- **_send_wecom**：门控 + 发送单点，单条与聚合通知共用；改通知开关语义只改这里。
- **_wait_and_notify**（`engine/runner.py`）：聚合通知的等待侧——只剩"轮询批次到终态 + 调用 send_batch_notify"，不再持有门控副本。

## 前端

- **useGroupMasterDetail**（`composables/useGroupMasterDetail.ts`）：分组管理骨架的 master-detail 状态机——左导航选中态（分组消失回「全部」）、子树聚合视图判定、右侧详情取数/分页、el-table 实例登记（互斥勾选 clearOthers 注入点）、SortableJS 组内行拖拽绑定（含卸载清理）。挂在 useGroupedTable 之上，ApiManage / CaseList 共用；视图只注入取数与拖拽落点持久化。
- **GroupManageDialog**（`components/GroupManageDialog.vue`）：分组管理弹窗——新增/重命名/删除/拖拽层级保存收敛在组件内，CRUD API 经 props 注入（apiGroupApi / caseGroupApi），变更后 emit('changed', kind) 由父视图重载。
- **BatchMoveDialog**（`components/BatchMoveDialog.vue`）：批量移动弹窗——目标选择（id=0 = 未分组→null）、loading 与报错自持，移动逻辑经 props.move 注入（成功 resolve 自关，失败 throw 保持打开）。
- **expandStorageKey**（`composables/useGroupTree.ts`）：展开记忆持久化 key 的唯一约定点；视图自定义虚拟节点（如 DatasetManage 的未分组 -1）复用同一存储，不再各自拼 key。
- **ScheduleDialog**（`components/ScheduleDialog.vue`）：定时任务自治弹窗——列表展示、CRUD 六操作（新增/编辑/启停/立即执行/删除）与表单状态全在组件内走 scheduleApi，变更后 emit('changed') 由父视图重载列表；父视图只持"当前用例 + 开合态"和列表数据。
- **DataDrivenRunDialog**（`components/DataDrivenRunDialog.vue`）：数据驱动执行弹窗——数据集选择、行勾选（打开时全选）、漂移检测（drift/resync）与字典渲染自治；确认时 emit('confirm', { datasetId, rowIds })，执行编排（runner/favicon/router）留在父视图。
- **BatchRunDialog**（`components/BatchRunDialog.vue`）：批量执行配置弹窗——每用例次数/并发数配置与打开时重置（全 1 / 4）自治，纯 UI 无 API；确认时 emit('confirm', { caseIds, counts, concurrency })，提交与轮询编排在父视图。
- **ApiError**（`api/index.ts`）：API 错误契约——axios 拦截器把一切失败（HTTP 错误/blob 响应/网络错误）规整为 ApiError，message 必为后端 detail；调用方 catch 只读 `e.message`，禁止再写 `e?.response?.data?.detail` 对冲解析（含 blob 手动 text()+JSON.parse 的重复实现）。
- **响应类型别名**（`api/index.ts`）：User/Project/ApiGroup/CaseGroup/OperationLog/FieldDictionary/FileCategory/TestFile 等直接取 `components['schemas'][...]`（OpenAPI 生成物，后端 Pydantic 单一事实源）；Environment/ApiDef/TestCase/记录族/DataSet 族等仍手写，因生成物嵌套退化为 unknown 或手写 union 承载领域约束，待后端模型细化后分批换。

- **useExecutionRunner**（`composables/useExecutionRunner.ts`）：执行轮询的深模块——定时器注册表、卸载清理、间隔/超时策略、favicon 三态、结果提示单点管理。窄接口三个：`runWithFeedback`（单用例完整体验）、`pollUntilDone`（纯轮询到终态）、`refreshWhileRunning`（running 态自刷新）。取代此前 5 份平行实现（CaseList runCase/pollOne、CaseDesigner onRun、ReportDetail、Execution），2s/3s 与 150/300 魔法数不再漂移。
- **execStatusType / execStatusText**（`utils/format.ts`）：执行状态 → 标签色/中文文案的唯一映射，各视图以 `as statusType/statusText` 别名引入。
