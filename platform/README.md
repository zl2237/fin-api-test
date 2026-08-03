# Fin API Test Platform

> API 测试平台 · DAG 可视化编排 · 结构化执行报告 · 用户权限 · 并发执行

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.6-009688.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883.svg)](https://vuejs.org/)
[![Element Plus](https://img.shields.io/badge/Element_Plus-2.9-409EFF.svg)](https://element-plus.org/)
[![Vue Flow](https://img.shields.io/badge/Vue_Flow-DAG-ff6b6b.svg)](https://vueflow.dev/)

把"写代码 → 跑用例 → 看报告"升级为"拖拽编排 → 一键执行 → 可视化报告"。用例不再是一段 Python 代码，而是一张可复用、可 diff 的 DAG 图。

## 特性

- **DAG 可视化编排** — 拖拽节点 + 连线描述接口执行顺序
- **字段级接口配置** — 字段表维护请求体（key、类型、默认值、必填），告别手写 JSON
- **Swagger/OpenAPI 导入** — 一键导入 OpenAPI 3.0 / Swagger 2.0，自动生成接口与字段
- **断言引擎** — 17 种类型（HTTP 状态码、JSONPath、响应耗时、数据库查询、DB 与响应交叉校验等）
- **表达式引擎** — 12 个内置函数（now / random_int / uuid / md5 / date_add ...）+ 变量引用 + DB 查询
- **异步并发执行** — 线程池（max_workers=4）后台执行，前端轮询状态，不阻塞 UI
- **用户权限** — JWT 鉴权 + admin/member 双角色 + 操作审计日志
- **密码安全** — 强度校验（≥8 位 + 字母数字）+ 连续失败 5 次锁定 15 分钟
- **多数据库** — SQLite（默认零配置）或 MySQL（生产推荐），支持数据迁移
- **结构化报告** — 每步请求/响应/断言全量落库，支持导出 PDF + 性能趋势图
- **执行记录清理** — 启动自动清理 30 天前记录，管理员可手动清理

## 快速开始

### 1. 配置环境变量

```bash
cd platform/backend
cp .env.example .env
# 编辑 .env，填写 JWT_SECRET_KEY 和 MySQL 配置（或使用默认 SQLite）
```

```ini
# .env 示例
JWT_SECRET_KEY=your-random-secret-key    # 必填，python -c "import secrets; print(secrets.token_hex(32))"
DB_TYPE=mysql                            # sqlite 或 mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=123456
DB_NAME=fin_api_test
```

### 2. 启动后端

```bash
cd platform/backend
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
python -m uvicorn app.main:app --port 8000
```

- API：http://127.0.0.1:8000
- Swagger：http://127.0.0.1:8000/docs
- 默认账号：`admin` / `admin123`（首次启动自动创建）

### 3. 启动前端

```bash
cd platform/frontend
npm install
npm run dev
```

访问 http://localhost:5173 （已配置代理转发 `/api/` → 8000）。

### 4. 从 SQLite 迁移到 MySQL（可选）

```bash
# 先创建 MySQL 数据库
mysql -u root -p -e "CREATE DATABASE fin_api_test DEFAULT CHARSET utf8mb4"

# 修改 .env 中 DB_TYPE=mysql，启动后端自动建表

# 迁移存量数据
python platform/migrate_sqlite_to_mysql.py
```

## 架构

```
┌──────────────────────────────────────────┐
│            前端（Vue3）                    │
│  ApiManage · CaseDesigner · Report ...    │
└─────────────────┬────────────────────────┘
                  │ /api
                  ▼
┌──────────────────────────────────────────┐
│            后端（FastAPI）                 │
│  projects · environments · apis · cases  │
│  executions · reports · users · logs     │
└─────────────────┬────────────────────────┘
                  │ 线程池异步执行
                  ▼
┌──────────────────────────────────────────┐
│            DAG 执行引擎                    │
│  拓扑排序 → 前置处理 → 请求 → 提取 → 断言   │
└─────────────────┬────────────────────────┘
                  │ 复用
        ┌─────────┴─────────┐
        ▼                   ▼
   HTTP Client          MySQL Client
   401 自动重登          落库数据校验
```

### 执行引擎

| 模块 | 文件 | 职责 |
|------|------|------|
| DAG 执行器 | `engine/dag_executor.py` | 拓扑排序、节点执行、登录、token 刷新 |
| 前置处理 | `engine/preprocessor.py` | set_field / delete_field / 表达式求值 |
| 后置提取 | `engine/extractor.py` | JSONPath 提取变量到上下文 |
| 断言引擎 | `engine/assertion_engine.py` | 16 种断言类型 |
| 表达式引擎 | `engine/expression.py` | 变量引用 + 内置函数 |
| 异步执行 | `engine/runner.py` | 线程池 + 状态轮询 |

## 目录结构

```
platform/
├── backend/
│   ├── app/
│   │   ├── engine/          # 执行引擎（DAG / 断言 / 提取 / 表达式）
│   │   ├── routers/         # API 路由（auth / users / projects / apis / cases / executions）
│   │   ├── auth.py          # 密码哈希 + JWT + 鉴权 + 密码强度校验
│   │   ├── models.py        # ORM 模型（User / Project / Environment / Api / TestCase ...）
│   │   ├── schemas.py       # Pydantic 模型
│   │   ├── database.py      # SQLAlchemy 初始化（SQLite/MySQL 双模式）
│   │   └── main.py          # FastAPI 入口（.env 加载 + 自动迁移 + 启动清理）
│   ├── .env.example         # 环境变量模板
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/             # axios 封装 + 类型定义
│   │   ├── components/      # DAG 画布 / 字段表 / 断言配置 ...
│   │   ├── views/           # 登录 / 接口管理 / 用例编排 / 报告 / 用户管理 ...
│   │   ├── router/          # 路由 + 守卫
│   │   └── stores/          # Pinia 状态管理
│   └── package.json
├── migrate_sqlite_to_mysql.py
└── README.md
```

## 鉴权头值模板

环境配置支持自定义鉴权头值，通过占位符组合：

| 场景 | 模板 | 注入结果 |
|------|------|----------|
| 直接注入（默认） | `${token}` | `Authorization: abc123` |
| Bearer 前缀 | `Bearer ${token}` | `Authorization: Bearer abc123` |
| 时间戳组合 | `${token}_${timestamp}` | `Authorization: abc123_1698765432` |

## 表达式引擎

可在字段默认值、预处理 `set_field` 的 `value`、断言的 `expected` 中使用。整串是 `${...}` 时返回原生类型，字符串内嵌时做替换。

### 变量引用

| 语法 | 说明 |
|------|------|
| `${context.order_id}` | 引用上下文中已提取的变量（post_extract 提取的结果） |
| `${env.base_url}` | 引用当前环境配置的字段 |
| `${global.xxx}` | 引用全局变量（保留扩展） |
| `${bl_no}` | SQL 内简写，等价于 `${context.bl_no}`，自动做字符串转义防注入 |

### 内置函数（12 个）

| 函数 | 参数 | 示例 | 说明 |
|------|------|------|------|
| `now` | `format?` | `${now(format='%Y-%m-%d')}` | 当前时间，无参返回 ISO 字符串 |
| `timestamp` | — | `${timestamp()}` | 当前时间戳（秒，整数） |
| `random_int` | `min`, `max` | `${random_int(min=1, max=100)}` | 区间内随机整数 |
| `random_string` | `length` | `${random_string(length=8)}` | 随机字符串（大小写字母+数字） |
| `uuid` | — | `${uuid()}` | UUID v4 字符串 |
| `upper` | `s` | `${upper(s='abc')}` | 转大写 |
| `lower` | `s` | `${lower(s='ABC')}` | 转小写 |
| `md5` | `s` | `${md5(s='abc')}` | MD5 哈希 |
| `date_add` | `days`, `format` | `${date_add(days=1, format='%Y-%m-%d')}` | 当前日期加 N 天 |
| `generate_bl_no` | `prefix` | `${generate_bl_no(prefix='smoke')}` | 业务编号生成（订单 bl_no） |
| `generate_unique_id` | — | `${generate_unique_id()}` | 业务唯一 ID |
| `generate_invoice_number` | — | `${generate_invoice_number()}` | 发票号生成 |

### DB 查询函数（3 个）

可在表达式或 SQL 注入中使用，直接查业务库。

| 函数 | 返回 | 示例 |
|------|------|------|
| `db.query(sql)` | 行列表 `[{...}]` | `${db.query('SELECT * FROM sys_order WHERE bl_no=${bl_no}')}` |
| `db.query_one(sql)` | 第一行 dict 或 None | `${db.query_one('SELECT order_id FROM sys_order WHERE bl_no=${bl_no}')}` |
| `db.query_value(sql, field)` | 标量值 | `${db.query_value('SELECT status FROM sys_order WHERE bl_no=${bl_no}', field='status')}` |

> 注：SQL 内的 `${bl_no}` 会被自动注入上下文变量，字符串值自动加单引号并转义，无需手写引号。

## 断言引擎

共 17 种断言类型，分响应断言与 DB 断言两组。所有 DB 断言支持 `retry_count` / `retry_interval` 参数，应对异步落库场景。

### 响应断言（9 种）

| 类型 | 必填字段 | 说明 |
|------|----------|------|
| `json_path_equals` | `path`, `expected` | JSONPath 取值等于期望 |
| `json_path_not_equals` | `path`, `expected` | JSONPath 取值不等于期望 |
| `json_path_contains` | `path`, `expected` | JSONPath 取值包含期望（字符串/列表） |
| `json_path_exists` | `path` | JSONPath 路径存在（值非 null） |
| `json_path_not_empty` | `path` | JSONPath 取值非空 |
| `json_path_match_regex` | `path`, `expected` | JSONPath 取值匹配正则 |
| `json_path_type_equals` | `path`, `expected` | 类型校验：`string` / `int` / `bool` / `array` / `object` / `null` / `number` |
| `response_status_equals` | `expected` | HTTP 状态码等于期望 |
| `response_time_less_than` | `expected` | 响应时间小于期望（毫秒） |

### DB 断言（8 种）

| 类型 | 必填字段 | 说明 |
|------|----------|------|
| `db_query_equals` | `sql`, `field?`, `expected` | DB 查询指定字段等于期望（未指定 field 取第一列） |
| `db_query_not_equals` | `sql`, `field?`, `expected` | DB 查询指定字段不等于期望 |
| `db_query_not_empty` | `sql` | DB 查询结果非空 |
| `db_query_count_equals` | `sql`, `expected` | 查询行数等于期望 |
| `db_query_count_greater_than` | `sql`, `expected` | 查询行数大于期望 |
| `db_query_count_less_than` | `sql`, `expected` | 查询行数小于期望 |
| `db_vs_jsonpath_equals` | `sql`, `field?`, `path` | DB 值 等于 响应 JSONPath 取值（交叉校验） |
| `db_vs_jsonpath_not_equals` | `sql`, `field?`, `path` | DB 值 不等于 响应 JSONPath 取值 |

> `retry_count` 默认 0（不重试），`retry_interval` 默认 2 秒。异步落库场景可配置 `retry_count=3, retry_interval=2`。

### 字段含义速查

| 字段 | 适用断言 | 说明 |
|------|----------|------|
| `type` | 全部 | 断言类型，见上表 |
| `path` | 响应断言 / DB vs JSONPath | JSONPath 表达式，如 `$.data.status` |
| `sql` | DB 断言 | SQL 语句，支持 `${var}` 注入上下文变量 |
| `field` | db_query_equals / db_vs_jsonpath_* | 从查询结果第一行取的字段名，缺省取第一列 |
| `expected` | 大部分 | 期望值，支持 `${...}` 表达式 |
| `pattern` | json_path_match_regex | 正则表达式（与 expected 同义，前端用 expected 字段） |
| `message` | 全部 | 失败时显示的提示信息（可选） |
| `retry_count` | DB 断言 | 重试次数，默认 0 |
| `retry_interval` | DB 断言 | 重试间隔秒数，默认 2 |

## API 接口

后端启动后访问 Swagger UI：http://127.0.0.1:8000/docs

主要接口前缀：`/api/auth`（公开）· `/api/users`（仅 admin）· `/api/projects` · `/api/environments` · `/api/apis` · `/api/testcases` · `/api/executions` · `/api/operation-logs`（仅 admin）

## 技术栈

**后端**：FastAPI 0.115.6 · SQLAlchemy 2.0.36 · Pydantic 2.11 · jsonpath-ng 1.6.1 · PyMySQL · python-dotenv

**前端**：Vue 3.5 · Element Plus 2.9 · Vue Flow 1.42 · Vue Router 4.5 · Pinia 2.3 · axios 1.7 · Vite 6.0

## 常见问题

**Q: Python 3.14 安装依赖卡住？** 改用 Python 3.12，或升级 pydantic≥2.11、uvicorn 至最新版。

**Q: 连续执行多个用例后请求超时？** HTTP session 已在 finally 块关闭，自研执行器请检查 `session.close()`。

**Q: JWT_SECRET_KEY 未设置启动失败？** 这是预期行为。在 `.env` 文件中配置 `JWT_SECRET_KEY` 后重启。

## License

[MIT](../LICENSE)
