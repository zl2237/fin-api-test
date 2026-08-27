# WF-01 功能交付自测循环

> 一批功能交付前必跑的质量闸门。白盒 + 接口层由 agent 全自动执行，
> UI 层生成勾选文档交人工走查，汇总以 brief 形式回到对话。

## 触发（Trigger）

- **事件**：任何一批功能开发完成、即将交付/提交前。agent 在认为"开发完成"的节点**主动**发起，不等用户喊。
- 触发时 agent 自动确定"本批改动范围"（`git diff` + 新增文件），动态生成重点测试面；下方"接口层重点清单"以最近一批为默认内容，每次触发时按实际改动重算。

## 三阶段（顺序执行，push right——全部自动化做完才打扰人）

### 阶段 1：白盒（单测落库 + 存量全量回归）

1. **新单测落库**：为本批新增/改动的核心服务补 pytest 单测，并入 `platform/backend/tests/`。落库标准：
   - 覆盖每个公开函数的正常路径 + 关键边界（拒绝条件、空输入、超长截断、回滚路径）
   - 写法遵循 `tests/` 现有模式（看 `test_notifier.py` / `test_dag_executor_topo.py` 的 fixture 风格）
   - 最近一批的落库清单：
     - `tests/test_case_combine.py`：combine（顺序/前缀/串接边/配置复制/跨项目拒/重复拒）、scan_split_boundary（outgoing/incoming/`${uuid()}` 与 `context.x` 排除）、split（分流/跨界边丢弃/位置归零/全量拒/非法拒/失败回滚）
     - `tests/test_export_service.py`：四导出函数（Excel 头行、JSON 结构、节点配置合并、`_fmt` None/datetime/dict）
     - 扩充 `tests/test_notifier.py`：字节预算截断、`_request_error_text` 提取、断言消息回退、leftover/error 行
2. **存量全量回归**：`pytest`（backend 目录）26+ 存量文件全跑，要求 100% 通过；失败按"阻断即修"处理。
3. **复杂场景一次性脚本**：需真实 DB 的闭环（组合→拆分→导出→执行→通知）用 `.tmp_` 前缀脚本验证后即删，不入库。

### 阶段 2：接口层（分层：重点全打 + 其余冒烟）

**数据隔离**：先建 `__自测__` 专用项目（含专用接口/用例/分组/环境引用），全部写操作落此项目；跑完全量删除。绝不写项目 #1。

**重点面全打**（正常 + 异常分支，按当批改动重算；最近一批默认）：

| 模块 | 覆盖点 |
|---|---|
| 导出 | `GET /apis/export`、`/testcases/export`：excel/json 二格式、非法 format 400、空数据 400、审计日志两条分支都落 |
| 组合 | `POST /testcases/combine`：正常（节点数=和/串接边/前缀/配置对齐）、<2 拒、重复 id 拒、跨项目拒、不存在 404 |
| 拆分 | `/scan-split`（outgoing/incoming）、`/split`：正常分流、全量拒、非法 node_ids 拒且不留空用例、新用例位置归零 |
| 执行链路 | 用例失败执行 → steps 落 `{"error": ...}`、summary.error/leftover 正确 |
| 并行批量 | `batch-execute` ≥4 用例：并发上限 4、同秒起跑、零 401/407 互踢 |
| 通知 | 失败通知内容含失败接口/断言消息/请求异常；极端长度 ≤4096 字节带截断标记 |

**其余模块冒烟**（每路由 ≥1 条 happy path）：auth(login/me) / projects / environments(list/copy) / users(simple) / api-groups / apis(crud/copy/debug) / case-groups / testcases(crud/execute) / executions(list/get) / reports(get/export csv+html) / schedules(list/create/run) / files+categories+tags / field-dictionaries / operation-logs / versions(list/create/diff)。
破坏性接口（cleanup/rollback/批量删除）只验权限与参数校验，不真正执行。

### 阶段 3：UI 人工走查（Checkpoint）

1. agent 生成勾选文档 `docs/self-test/UI-CHECKLIST.md`（每轮覆盖重写，不归档历史）：
   - 按页面分组，每条含 **编号 / 前置条件 / 操作步骤 / 预期结果**，编号规则 `UI-<模块缩写>-<序号>`
   - 当批改动页面列全量用例；其余页面列代表性冒烟条目
2. 用户在文档中勾选/批注 → agent 读文档收结果。
3. brief 中同步给出"自动化部分已通过/已修复"结论，用户只需关注 UI 部分。

### Brief（对话内输出，不落文件）

跑完阶段 1+2 后立即发一轮（不等 UI）：
- 总通过率（白盒 N/N、接口 M/M）
- 失败分级清单：🔴 阻断（已修复，列修复摘要）/ 🟡 建议（待用户决策）
- 附件路径：UI-CHECKLIST.md
UI 结果回收后再发终轮（含修复项与全绿确认）。

## 失败处置

- **🔴 阻断**（功能不可用/报错/数据损坏/测试不过）：立即修复并回归，brief 中列修复摘要。
- **🟡 非阻断**（体验/风格/文案）：只记录，brief 汇总由用户决策，不擅自动手。

## 边界

- 仅本地 dev（127.0.0.1:8000 / vite 端口）；部署环境验证交给 CI 流水线。
- 自测发现的临时脚本/截图一律 `.tmp_` 前缀（.gitignore 已覆盖），不进仓库。
