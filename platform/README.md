# Fin API Test Platform

> 把用例从"一段代码"变成"一张可复用、可 diff 的 DAG 图"。

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.6-009688.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883.svg)](https://vuejs.org/)
[![Element Plus](https://img.shields.io/badge/Element_Plus-2.9-409EFF.svg)](https://element-plus.org/)
[![Vue Flow](https://img.shields.io/badge/Vue_Flow-DAG-ff6b6b.svg)](https://vueflow.dev/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](../LICENSE)

## Features

- **DAG 可视化编排** — 拖拽节点 + 连线描述执行顺序，自动布局 / 新节点防重叠 / minimap
- **字段级接口配置** — 字段表维护请求体（key、类型、默认值、必填），告别手写 JSON
- **多格式导入** — cURL / HAR/ Swagger 2.0 / OpenAPI 3.0 一键导入接口与字段
- **表达式引擎** — `${now()}` `${random_int()}` `${uuid()}` 等 12 个内置函数 + `${context.xxx}` 变量引用 + `db.query()` 内联 SQL 查询
- **17 种断言** — JSONPath / 状态码 / 耗时 / DB 查询 / DB 与响应交叉校验，DB 断言支持重试应对异步落库
- **结构化报告** — 每步请求/响应/断言全量落库，HTML 导出（可打印 PDF）+ 耗时趋势图
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
┌───────────────────────────────────────────┐
│      前端 Vue3 + Element Plus + Vue Flow     │
│  ApiManage · CaseDesigner · ReportDetail    │
└──────────────────┬────────────────────────┘
                   │ /api
┌──────────────────▼────────────────────────┐
│             后端 FastAPI                    │
│  projects · environments · apis · cases    │
│  executions · reports · users · logs       │
└──────────────────┬────────────────────────┘
                   │ 线程池异步执行
┌──────────────────▼────────────────────────┐
│             DAG 执行引擎                    │
│  拓扑排序 → 前置处理 → 请求 → 提取 → 断言    │
└──────────────────┬────────────────────────┘
         ┌─────────┴─────────┐
         ▼                   ▼
    HTTP Client          MySQL Client
    401 自动重登          落库数据校验
```

路由层与执行引擎解耦，公共逻辑抽到 `services/`（runtime / body_builder / spec_parser / notifier）供两层复用。

## Expression & Assertion

```yaml
# 字段默认值、set_field、断言 expected 均可用表达式
order_id: ${random_int(min=1, max=999999)}
bl_no: ${generate_bl_no(prefix='smoke')}
sign: ${md5(s='${context.token}_${timestamp()}')}

# 断言示例：DB 值 = 响应 JSONPath 取值（交叉校验，支持重试）
- type: db_vs_jsonpath_equals
  sql: "SELECT status FROM sys_order WHERE bl_no=${bl_no}"
  path: $.data.status
  retry_count: 3
  retry_interval: 2
```

完整 12 函数清单与 17 断言类型详见 [Swagger 文档](http://127.0.0.1:8000/docs) 与 `app/engine/`。

## Tech Stack

**后端** · FastAPI · SQLAlchemy 2.0 · Pydantic 2 · Alembic · jsonpath-ng · PyMySQL

**前端** · Vue 3.5 · Element Plus · Vue Flow · Vue Router · Pinia · Vite

## FAQ

- **uvicorn 无 access log** — `alembic/env.py` 的 `fileConfig()` 需设 `disable_existing_loggers=False`
- **admin 被强制跳转改密页** — 预期行为，迁移标记旧库 admin `must_change_password=True`，改密即恢复
- **路由切换后页面空白** — 顶层 `<router-view>` 不可加 `:key="route.path"`，会触发 MainLayout 重挂载丢状态

## License

[MIT](../LICENSE)
