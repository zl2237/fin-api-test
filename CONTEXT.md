# CONTEXT.md · 领域词汇表

架构评审（improve-codebase-architecture）与日常开发共用的领域语言。新概念入册后，评审与代码讨论统一用这些词。

## 执行编排（execution launcher）

- **execution_launcher**（`services/execution_launcher.py`）：执行编排的深模块——数据驱动展开 → 建记录 → 批量提交 → 聚合通知的唯一入口。调用方只有 executions 路由与 scheduler 两类；新触发来源调它即接入全部语义。
- **ExecutionSpec**（`engine/runner.py`）：单条执行的提交规格（record id、用例 id、行变量、列快照、节点配置快照、抑制通知标志）。`submit_batch_execution` 的接口，取代旧的 5 个平行数组。
- **LaunchPlan**：一个用例（× 执行次数轮）的发射计划；多个 plan 可平铺进一个批次专用线程池一次 `commit_launch`。
- **AggregateGroup**（聚合组）：一次数据驱动多行展开的失败聚合通知组——全部终态后只发一条汇总，组内每条抑制逐条通知。
- **批次专用池**：每次批量执行新建 `ThreadPoolExecutor(max_workers=concurrency)`，提交完即回收；与内部后台任务池（聚合通知等零散提交）互不复用。

## 前端

- **useExecutionRunner**（`composables/useExecutionRunner.ts`）：执行轮询的深模块——定时器注册表、卸载清理、间隔/超时策略、favicon 三态、结果提示单点管理。窄接口三个：`runWithFeedback`（单用例完整体验）、`pollUntilDone`（纯轮询到终态）、`refreshWhileRunning`（running 态自刷新）。取代此前 5 份平行实现（CaseList runCase/pollOne、CaseDesigner onRun、ReportDetail、Execution），2s/3s 与 150/300 魔法数不再漂移。
- **execStatusType / execStatusText**（`utils/format.ts`）：执行状态 → 标签色/中文文案的唯一映射，各视图以 `as statusType/statusText` 别名引入。
