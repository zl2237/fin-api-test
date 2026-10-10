<p align="center">
  <img src="banner.svg" alt="Fin API Test Platform" width="100%" />
</p>

# Fin API Test Platform

> 把用例从"一段代码"变成"一张可复用、可 diff 的 DAG 图"。

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.6-009688.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883.svg)](https://vuejs.org/)
[![Element Plus](https://img.shields.io/badge/Element_Plus-2.9-409EFF.svg)](https://element-plus.org/)
[![Vue Flow](https://img.shields.io/badge/Vue_Flow-DAG-ff6b6b.svg)](https://vueflow.dev/)
[![Tests](https://img.shields.io/badge/pytest-759_passed-brightgreen.svg)](#testing)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](../LICENSE)

## Features

- **DAG 可视化编排** — 拖拽节点 + 连线描述执行顺序，自动布局 / 新节点防重叠 / minimap
- **字段级接口配置** — 字段表维护请求体（key、类型、默认值、必填），告别手写 JSON
- **多格式导入** — cURL / HAR / Swagger 2.0 / OpenAPI 3.0 一键导入接口与字段
- **参数四来源模型** — 每个入参单选取值来源：常量（容器内嵌来源递归解析）/ 内置函数（12 个注册表函数，入参可引用上游变量）/ 上游引用（结构化 `node_id + var_path`）/ 参数级标量 SQL（`{{节点.变量}}` 占位）；保存时静态校验悬空引用并定位到参数，运行期引用失败即节点失败
- **测试套件** — 跨系统用例链：`case_type='suite'` 串行执行多个成员用例（可跨项目、逐成员绑环境），共享变量白名单把上游产出按 `__suite__` 命名空间注入下游，逐行配对 / 上游失败下游阻断 / 套件级汇总通知与专属报告
- **数据集行入参** — 数据集行承载各节点入参配置（`{"nodes": {...}}`），多行即多场景；支持粘贴 JSON 预览导入（引用型参数不覆盖）；复用靠复制数据集
- **17 种断言** — JSONPath / 状态码 / 耗时 / DB 查询 / DB 与响应交叉校验，DB 断言支持重试应对异步落库
- **结构化报告** — 每步请求/响应/断言全量落库，响应体 JSON 可展开收起；支持编辑节点请求参数后按原环境重放（纯调试口径不写回报告）；后端导出 CSV（Excel 兼容）/ HTML（可打印 PDF）+ 耗时趋势图
- **文件中心** — 分类树 + 标签 + multipart 上传，`file` 字段直接引用文件中心资源
- **工程化** — JWT 鉴权 + admin/member 角色 + 操作审计 + Alembic 迁移 + 亮暗主题 + 标签页 + 命令面板（Ctrl+K）

## Quick Start

```bash
# 1. 建库
mysql -u root -p -e "CREATE DATABASE fin_api_test DEFAULT CHARSET utf8mb4"

# 2. 配置后端
cd platform/backend
cp .env.example .env   # 填写 DB_PASSWORD 与 JWT_SECRET_KEY
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000   # 自动迁移建表 + 创建 admin 账号

# 3. 启动前端
cd platform/frontend
npm install && npm run dev
```

访问 http://localhost:5173 · 默认账号 `admin` / `admin123`（首登强制改密）· Swagger http://127.0.0.1:8000/docs

## Architecture

```
┌─────────────────────────────────────────────────┐
│        前端 Vue3 + Element Plus + Vue Flow        │
│  views (20 页) ← composables                      │
│  useGroupedTable / useGroupMasterDetail           │
│  useExecutionRunner / useGroupTree                │
│       │                    ↑ 复用分组/拖拽/轮询    │
│       │ api/index.ts ← types/api.gen.ts (OpenAPI) │
└──────────────────────────┬──────────────────────┘
                           │ /api
┌──────────────────────────▼──────────────────────┐
│                 路由层 routers/                   │
│  HTTP 语义 + 鉴权 + 审计日志（薄层，无业务逻辑）      │
├─────────────────────────────────────────────────┤
│       数据访问层 crud/（按域拆分，显式 re-export）   │
│  users · auth · executions · datasets            │
│  versions · legacy（兼容期）                      │
├─────────────────────────────────────────────────┤
│                 服务层 services/                   │
│  execution_launcher · runtime · request_sender   │
│  body_builder · dataset_service · scheduler      │
│  suite_executor · spec_parser · report_export    │
│  replay_service · notifier · files               │
└──────────────────────────┬──────────────────────┘
                           │ 线程池异步执行
┌──────────────────────────▼──────────────────────┐
│              DAG 执行引擎 engine/                  │
│  topo_order 唯一实现 → prepare_request 统一组装    │
│  → 前置处理 → 请求 → 提取 → 断言                   │
│  events.py: StepResult → ExecutionSink 接缝       │
│  （事件产出与落库解耦，主链路可脱离 DB 测试）          │
└──────────────────────────┬──────────────────────┘
                ┌─────────┴─────────┐
                ▼                   ▼
          HTTP Client          MySQL Client
          401 自动重登          落库数据校验
```

**分层规约**（由测试守卫）：

- 路由层不内联 ORM，业务不变量下沉 `crud/` 域模块（如登录锁定策略在 `crud/auth.py`）
- 单次 HTTP 请求（GET/POST/multipart + 异常四分类）只有一份实现 `services/request_sender.py`，
  执行引擎与单接口调试共用
- 执行编排（数据集展开→建记录→提交→聚合通知）只有一份实现 `services/execution_launcher.py`，
  单次/批量/定时三入口共用；`runner.submit_batch_execution` 收 `list[ExecutionSpec]`
- 请求组装四来源参数模型（constant/func/ref/sql 单选，按 order_params 拓扑序解析，
  结果按节点命名空间注册，引用失败即失败）单点 `engine/prepare_request.py`；
  参数解析唯一定义点 `engine/param_resolver.py`；
  Kahn 拓扑排序单点 `engine/topo.py`（执行序与数据集列序共用）；企微通知门控单点 `services/notifier.py`
- 执行引擎产出 `StepResult` 事件经 `ExecutionSink` 落库（`DbSink`），
  引擎不反向 import 路由层 —— `test_engine_does_not_import_routers` 守卫
- 报告导出为后端纯函数 `services/report_export.py`，`GET /reports/executions/{id}/export?format=csv|html`

## 前后端类型单一事实来源

后端 Pydantic schema → `npm run gen:api` 生成 `src/types/api.gen.ts` 供前端消费，字段漂移在 vue-tsc 编译期暴露。
审计字段由 `schemas.AuditMixin` 单一声明，7 个 Out schema 继承；生成物退化为 unknown 的嵌套结构仍手写，原因见 `api/index.ts` 类型段头注释。
错误契约显式化：拦截器把一切失败规整为 `ApiError`（message 必为后端 detail），视图 catch 只读 `e.message`。

## Testing

```bash
cd platform/backend
python -m pytest tests/ -q          # 759 passed
python -m ruff check --select F platform/backend   # 与 CI backend-lint 同口径
cd ../frontend && npx vue-tsc --noEmit             # 与 CI frontend-lint 同口径
```

测试布局（fake-db 单测，不依赖真实 MySQL）：

| 域 | 文件 | 覆盖 |
|---|---|---|
| 执行编排 | `test_execution_launcher.py` | 展开→提交→聚合编排 + ExecutionSpec 组装 |
| 执行引擎 | `test_execute_node.py` | 单节点管线 + 分层守卫 |
| 请求组装 | `test_prepare_request.py` | 骨架/四来源解析/SQL 参数注册/通配与类型强转/file 剥离与 headers 组装 |
| 请求发送 | `test_request_sender.py` | 分发/multipart/异常分类 + 防平行实现守卫 |
| 通知 | `test_notifier.py` | 门控开关/单条与聚合通知/环境查无 |
| 拓扑排序 | `test_dag_executor_topo.py` | Kahn 排序唯一实现（执行/数据集共用） |
| 测试套件 | `test_suite_executor.py` | 白名单注入/逐行配对/行与整体阻断/嵌套与悬空（10 用例） |
| 参数解析 | `test_param_resolver.py` | 四来源取值（constant 容器/ref 跨节点/func 引用入参/SQL 列选取与注册）+ `{{}}` 占位渲染转义 |
| 变量注册表 | `test_variables.py` | 命名空间隔离/引用取不到即失败/旧语法不匹配/order_params 参数拓扑与环检测 |
| 保存校验 | `test_validation.py` | 悬空引用/未知节点与函数/依赖环/旧语法残留拒绝保存并定位参数 |
| 续跑与重放 | `test_{resume_executor,orchestration_fingerprint,report_context}.py` | 结构指纹锁定/续跑起点定位/报告虚拟上下文 seed 还原 |
| crud 域 | `test_{users,auth,executions}_domain.py` | 登录锁定/首管理员/最后管理员保护等 |
| 数据驱动 | `test_{dataset_copy_merge,dataset_service,param_semantics,execution_expand}.py` | 复制与覆盖合并/单套语义/参数语义/行展开 |
| 报告导出 | `test_report_export.py` | CSV/HTML 契约 |
| schema | `test_audit_mixin.py` | 审计字段继承 + Out 契约 |

## Tech Stack

FastAPI · SQLAlchemy 2.0 · Pydantic 2 · Alembic · PyMySQL ｜ Vue 3.5 · Element Plus · Vue Flow · Pinia · Vite · openapi-typescript

## FAQ

- **uvicorn 无 access log** — `alembic/env.py` 的 `fileConfig()` 需设 `disable_existing_loggers=False`
- **路由切换后页面空白** — 顶层 `<router-view>` 不可加 `:key="route.path"`，会触发 MainLayout 重挂载丢状态

## License

[MIT](../LICENSE)
