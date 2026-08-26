# 数据驱动测试 · 开发方案定案

> 状态：**已定案 · 概念重构版**（首轮六轮 grilling 2026-08-24 定案 + 复审重构 2026-08-25，本期实现以本版为准）
> 前置调查结论：平台现状为"单实例流程驱动"——字段默认值支持 `${...}` 表达式、环境变量、节点间提取/注入（post_extract / set_field）。本方案在其上补"一组数据 × N 次执行"乘积层。

## 一、概念定案（2026-08-25 重构，推翻首轮"项目级共享"）

**数据集 = 用例私有的"场景包"**：行数据（变量组）+ 按节点的编排配置快照（前置处理 / 后置提取 / 断言 / 等待 / api_id）。

| # | 分叉 | 定案 | 否决项及原因 |
|---|---|---|---|
| 1 | 归属模型 | **用例级 1:N**：`data_sets.case_id NOT NULL`，一个用例名下多个数据集，不同用例的可选数据集**互相隔离** | 项目级共享（概念误解来源：跨用例复用导致配置语义混乱，数据集与用例编排强耦合无法独立理解） |
| 2 | 跨用例复用 | **彻底放弃共享，复用靠复制**：全量深拷贝（列/行/节点配置快照），默认名"原名-副本"，连续复制递增编号（副本2、副本3…） | 共享引用（A 用例改数据影响 B 用例） |
| 3 | 节点配置存储 | 编排用例时，当前配置的前置/后置提取/断言**按节点存进数据集**（`node_configs` JSON，只读快照） | 只存行数据（同一用例不同场景需不同断言强度，纯数据表表达不了） |
| 4 | 执行语义 | **快照优先、整块替换、缺失回落**：执行时快照按 node_id 命中则整块替换该节点配置（SimpleNamespace 替身），未命中节点回落用例当前 CaseNodeConfig | 逐字段合并（语义模糊，配置来源不可追溯） |
| 5 | 快照更新策略 | **只读 + 手动重新同步**：`POST /{id}/resync` 用用例当前编排整块替换快照（列/行不动）；用例编排变更后不自动跟随 | 自动同步（快照失去"场景固化"意义）/ 双向编辑（复杂度爆炸） |
| 6 | 列中文名 | **纯引用项目字段字典**（FieldDictionary key→label），列定义只存 `{key, type}`，label 字段废除；字典缺失显 key | 列内嵌 label（字典改一处数据集要逐个改，实时引用零维护） |
| 7 | 执行选择 | 用例保留**默认绑定 + 执行时可换**（仅本用例名下数据集） | 仅执行时选（定时任务拿不到） |
| 8 | 存量迁移 | 绑定的归绑定用例；名字前缀匹配（`{用例名}-参数集` / 截断后缀回溯）归源用例；**归不上的直接删**（含行，清悬空绑定） | 保留无主数据集（违背隔离模型） |
| 9 | 管理页维度 | **用例维度**：左侧用例列表（含数据集计数），右侧该用例数据集切换条 + 行编辑 + 快照只读面板 | 项目平铺列表（跨用例混排，隔离概念不可见） |
| 10 | 执行模型 | **每行一条执行记录**（复用 batch 并发上限 4） | 一条记录 N 轮（改动面大） |
| 11 | 注入机制 | **列名即变量名**：行值进变量池优先于同名环境变量；同名写死参数自动覆盖（body 顶层 / set_field path） | 用例侧映射表 |
| 12 | 失败通知 | 数据驱动批量执行失败**一条汇总**（失败行号列表）；单行手动保持逐条 | 逐行各发刷屏 |

## 二、数据层设计

```
data_sets        数据集（用例私有场景包）
  id, project_id,                 # project_id 冗余，归属以 case_id 为准
  case_id        INT NOT NULL FK test_cases  # 1:N 归属（隔离边界）
  name, description,
  columns        JSON  # [{key, type}] —— 中文名实时引用字段字典，不存 label
  node_configs   JSON  # [{node_id, api_id, pre_process, post_extract,
                       #   assertions, wait_after_ms}] 编排配置快照（只读，resync 更新）
  created_by/updated_by/created_at/updated_at

data_set_rows    数据行
  id, dataset_id, row_index,      # row_index 维护行序（1 起）
  data          JSON              # {"bl_no": "BL001", "put_amount": 100}

test_cases         dataset_id  INT NULL   # 默认绑定，NULL = 普通用例
execution_records  dataset_id  INT NULL   # 执行时实际使用的数据集
                   dataset_row JSON NULL  # 该次执行对应数据行快照（不回写）
```

- 删除数据集级联删行；被用例绑定时拒绝（提示先解绑）。
- 迁移 `d3e4f5a6b7c8`：加列 → 存量归属（绑定映射 + 名字回溯）→ 删无主 → case_id 收紧 NOT NULL → columns 剥离 label。

## 三、执行链路

### 请求体参数三级取值优先级（引擎定案）

优先级：数据集行值(1) > 用例编排 set_field(2) > 接口字段默认值(3，兜底)。
动态绑定例外：数据集 = 除动态绑定（值为 `${}` 表达式）外的所有字段集合。

- 接口字段默认值（3）：`build_request_body` 组装进 body，作为兜底。
- 用例编排（2）：节点拓扑排序、动态参数提取/注入（`${}` 求值）、断言、字面量 set_field。
- 数据集（1）：`apply_row_overrides` 覆盖 body 顶层同名列（只覆盖不新增，`${}` 字段除外）；
  `PreProcessor(row_vars=...)` 使字面量 set_field 同名 path 让位行值、嵌套字面量子路径跳过（防盖回整对象行值）。
- 动态绑定：值为 `${}` 的字段（上游提取注入/生成函数）不在数据集覆盖范围，表达式照常求值，行值同名列不压制。
- 变量池初始值 = env.variables 被行值覆盖同名项；`${列名}` 全链路可用（默认值/前置/断言/headers）。
- 嵌套/跨字段：用 `${列名}` 表达式（既有机制）。

### 节点配置快照（本期新增核心）

- 生成/重新同步时 `snapshot_node_configs(case, cfgs)`：按用例 dag_config 的 nodes 过滤 node_id，深拷贝 pre_process / post_extract / assertions / wait_after_ms / api_id。
- 执行展开 `plan_case_expansion`：归属校验（`ds.case_id != case.id` → 400）+ 构造 `overrides = {node_id: snap}` 附在每条执行项。
- `DagExecutor(node_config_overrides=...)`：`_resolve_node_config(node_id)` 快照命中返回 SimpleNamespace 替身（整块替换），未命中查 CaseNodeConfig（回落）；定时任务同路径。

### 从用例生成数据集

- `collect_case_params`：顶层 key、非 file、非空、不含 `${}`；同 key 跨节点同值合并、异值跳过（stats.conflicts 提示）；全部不可提取 → 400。
- 生成 = 列 + 1 行原值快照 + **节点配置快照** + case_id 归属，默认名 `{用例名}-参数集`。

### 执行展开与通知

- N 行 → N 条执行记录（复用 batch，并发 4，共享 token）；0 行拒绝；未绑定行为不变。
- 批量失败一条汇总（用例名 + 数据集名 + 失败行号 + 首因）；单行手动逐条。

## 四、API 设计

```
/api/datasets                     GET 列表（?case_id 用例维度过滤 / ?project_id）
                                  POST 建数据集（{project_id, case_id, name, columns}，校验用例存在且同项目）
/api/datasets/generate            POST 从用例生成（{case_id, name?} → {dataset, stats}）
/api/datasets/{id}/copy           POST 复制（深拷贝列/行/快照，同用例，名"原名-副本"递增）
/api/datasets/{id}/resync         POST 重新同步节点配置快照（用例当前编排整块替换，列/行不动）
/api/datasets/{id}                GET / PUT（改名改列）/ DELETE（被绑定拒 400）
/api/datasets/{id}/rows…          行 CRUD / 批量保存 / 全清 / Excel/CSV 导入（preview 可选）
/api/testcases/{id}               PUT 扩展 dataset_id；绑定校验：他用例数据集 → 400"复用请复制"
```

## 五、UI 设计

1. **数据集管理页（用例维度）**：左侧用例列表（数据集计数）；右侧该用例数据集切换 chip 条 + 行表格（单元格编辑/增删/导入）+ **节点配置快照只读面板**（折叠：节点/API/前置/后置/断言/等待计数 + 查看明细 JSON + 重新同步按钮）。新建数据集必须先选用例；「复制」按钮在数据集操作区。
2. **列中文名**：行表头、执行选行表头、列定义编辑器均 `fieldDictMap[key] || key` 实时引用字典，字典缺失旁注原始 key。
3. **用例绑定**（CaseList）：下拉仅列本用例名下数据集（`?case_id=` 过滤），提示隔离语义。
4. **执行确认**：N 行执行 N 次弹窗可临时换数据集（本用例名下）/选行。
5. **执行记录**：数据行列（行号 + 首列值），详情含 dataset_row 快照。

## 六、边界与拒绝条件

- 绑定他用例数据集 → 400（"数据集按用例隔离，复用请复制"）
- 执行展开时数据集归属校验同上（手动改库防呆）
- 跨项目、0 行执行、导入空文件 → 400
- dataset_row / node_configs 快照不回写（历史可溯源）
- 删除被绑定数据集 → 拒绝

## 七、自测（WF-01 循环）

- **白盒单测**：快照生成（结构/过滤/深拷贝）、copy（递增编号/missing 拒/深拷贝走 create）、resync（整块替换/列行动）、归属校验、overrides 附着、执行器回落、变量优先级、导入解析、通知聚合
- **接口层**：datasets CRUD/copy/resync/generate、按 case_id 过滤、绑定拒绝路径、批量展开
- **UI checklist**：UI-DD-01~13 + 复制/重新同步/快照面板/字典列名/用例维度切换（见 docs/self-test/UI-CHECKLIST.md）
- **存量迁移**：35 → 34（绑定归绑定用例 5、名字归源 29、删无主 1），无悬空绑定/孤儿行，label 全剥离

## 八、范围外（本期不做）

- 数据行级断言差异对比（期望/实际矩阵报告）
- 数据集版本管理 / 快照双向往返编辑
- 从 DB 查询动态生成数据行
- 组合场景数据集绑定继承
