# CONTEXT.md · 领域词汇表

架构评审（improve-codebase-architecture）与日常开发共用的领域语言。新概念入册后，评审与代码讨论统一用这些词。

## 执行编排（execution launcher）

- **execution_launcher**（`services/execution_launcher.py`）：执行编排的深模块——数据驱动展开 → 建记录 → 批量提交 → 聚合通知的唯一入口。调用方只有 executions 路由与 scheduler 两类；新触发来源调它即接入全部语义。
- **ExecutionSpec**（`engine/runner.py`）：单条执行的提交规格（record id、用例 id、行变量、列快照、节点配置快照、抑制通知标志）。`submit_batch_execution` 的接口，取代旧的 5 个平行数组。
- **LaunchPlan**：一个用例（× 执行次数轮）的发射计划；多个 plan 可平铺进一个批次专用线程池一次 `commit_launch`。
- **AggregateGroup**（聚合组）：一次数据驱动多行展开的失败聚合通知组——全部终态后只发一条汇总，组内每条抑制逐条通知。
- **批次专用池**：每次批量执行新建 `ThreadPoolExecutor(max_workers=concurrency)`，提交完即回收；与内部后台任务池（聚合通知等零散提交）互不复用。

## 前端（待 F2 落地后补充）

- `useExecutionRunner`：执行轮询的深模块候选（runOnce / pollUntilDone / refreshWhileRunning），统一 5 处轮询实现。
