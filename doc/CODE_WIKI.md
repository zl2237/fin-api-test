# fin-api-test · Code Wiki

> 面向金融业务系统的 API 自动化测试平台。本文档从代码层面完整描述项目的整体架构、模块职责、关键类与函数、依赖关系及运行方式。

---

## 目录

- [一、项目概览](#一项目概览)
- [二、整体架构](#二整体架构)
- [三、目录结构](#三目录结构)
- [四、旧测试框架（命令行版）](#四旧测试框架命令行版)
- [五、平台后端（FastAPI）](#五平台后端fastapi)
- [六、平台前端（Vue3）](#六平台前端vue3)
- [七、依赖关系总览](#七依赖关系总览)
- [八、项目运行方式](#八项目运行方式)
- [九、速查附录](#九速查附录)

---

## 一、项目概览

### 1.1 项目定位

fin-api-test 是一个 **API 自动化测试平台**，面向金融业务系统（订单 / 费用链路）。项目内同时存在两套体系：

| 体系 | 位置 | 形态 | 用途 |
|------|------|------|------|
| **旧框架** | 根目录 `api/ flows/ steps/ testcases/ utils/ db/` | pytest 代码驱动 | 命令行回归测试 |
| **新平台** | `platform/` | FastAPI + Vue3 Web 平台 | 可视化 DAG 拖拽编排、结构化报告 |

实际部署上线的是新平台；旧框架保留为本地命令行工具。两套体系共享底层能力：新平台通过 `path_setup.py` 注入 `sys.path` 后复用旧框架的 `utils/` 与 `db/`。

### 1.2 技术栈

| 层 | 技术 |
|----|------|
| 旧框架 | Python 3.12 · pytest 9 · requests 2.33 · PyMySQL 1.1 · PyYAML 6 · pytest-html 4 |
| 平台后端 | Python 3.12 · FastAPI 0.115 · SQLAlchemy 2.0 · Pydantic V2 · Alembic · jsonpath-ng · PyMySQL |
| 平台前端 | Vue 3.5 (`<script setup>`) · TypeScript · Pinia · Vue Router · Element Plus · Vue Flow（DAG 画布）· Axios · Vite 6 |
| 部署 | nginx（反代 + SPA）· systemd · GitLab CI/CD |

### 1.3 核心能力

- 接口管理：支持 cURL / HAR / OpenAPI 三种导入方式
- 用例编排：DAG 可视化拖拽，多级分组
- 变量传递：`${变量名}` 表达式引擎，跨节点引用，DB 查询内联
- 断言体系：17 种断言类型（JSONPath / HTTP / DB / DB vs 响应交叉），DB 断言支持重试
- 执行引擎：线程池异步执行，失败即停止，结构化报告
- 项目版本：快照 / 对比 / 硬回滚
- 用户权限：JWT（HMAC-SHA256）鉴权，admin/member 角色，操作审计
- 企微通知：执行结果推送群机器人

---

## 二、整体架构

### 2.1 双体系分层

**旧框架分层（自上而下调用）：**

```
Test Cases (testcases/)      用例编排、断言、marker
     ↓
Order Flow (flows/)          链路编排、阶段幂等、DB 断言
     ↓
Business Steps (steps/)      原子步骤（API 调用 + code 断言）
     ↓
API Layer (api/)             HTTP 请求封装
     ↓
HTTP Client | MySQL Client   401 自动重登 | 落库校验
```

**新平台架构：**

```
┌─────────────────────────────────────────────┐
│      前端 Vue3 + Element Plus + Vue Flow       │
│  ApiManage · CaseDesigner · ReportDetail ...   │
└────────────────────┬────────────────────────┘
                     │ /api（nginx 反代）
┌────────────────────▼────────────────────────┐
│             后端 FastAPI                       │
│  projects · environments · apis · cases        │
│  executions · reports · users · logs           │
└────────────────────┬────────────────────────┘
                     │ 线程池异步执行
┌────────────────────▼────────────────────────┐
│             DAG 执行引擎                       │
│  拓扑排序 → 前置处理 → 请求 → 提取 → 断言       │
└────────────────────┬────────────────────────┘
         ┌───────────┴───────────┐
         ▼                       ▼
    HTTP Client              MySQL Client
    401 自动重登              落库数据校验
```

路由层与执行引擎解耦，公共逻辑抽到 `services/`（runtime / body_builder / spec_parser / notifier）供两层复用。

### 2.2 端到端执行流程（新平台）

从"点击执行"到"出报告"的完整链路：

```
阶段1 路由层触发：POST /api/testcases/{case_id}/execute
        → 创建 ExecutionRecord(status=running) → submit_execution() 非阻塞提交 → 立即返回 record
阶段2 后台线程：runner.run_execution_background（独立 SessionLocal）→ DagExecutor(db,case,env,record).execute()
阶段3 DagExecutor.execute()：build_http_client → build_db_client → login(注册401回调) → _topo_sort → 逐节点 _execute_node（失败即停止）
阶段4 单节点 6 步管线：组装请求体 → 发请求 → 后置提取 → 断言 → 落库 StepRecord → 落库 AssertionRecord
阶段5 报告查询：GET /api/reports/executions/{exec_id} → ExecutionRecord + steps + assertions
```

---

## 三、目录结构

```
fin-api-test/
├── api/                      旧框架：HTTP 接口定义层
│   ├── base_api.py             BaseApi 父类
│   ├── auth_api.py             AuthApi 鉴权接口
│   └── order/order_api.py      OrderApi 订单接口
├── steps/order/order_step.py 旧框架：原子步骤层（接口调用 + 硬断言）
├── flows/order/order_flow.py 旧框架：链路编排层（幂等控制 + DB 断言）
├── testcases/order/test_order.py 旧框架：测试用例
├── utils/                    旧框架工具层（被新平台复用）
│   ├── http_client.py          HttpClient（401 自动重登）
│   ├── api_factory.py          ApiFactory（懒加载工厂）
│   ├── db_factory.py           DbFactory
│   ├── exceptions.py           分层异常体系
│   ├── assert_util.py          断言函数库
│   ├── generator_util.py       测试数据生成器
│   ├── yaml_util.py            YAML 读写
│   ├── common_util.py          路径工具
│   ├── log_util.py             日志
│   └── wecom_util.py           企微机器人
├── db/                       旧框架数据访问层（被新平台复用）
│   ├── db_client.py            DBClient（懒连接 + ping 保活）
│   ├── base_db.py              BaseDB 父类
│   └── biz/order_db.py         OrderDB
├── config/env_demo.yaml      环境配置模板
├── data/                     测试数据（YAML 数据驱动）
├── conftest.py               旧框架会话级 Fixture 与 Token 自动刷新回调装配
├── run.py                    旧框架启动入口
├── platform/                 ★ 新平台（部署上线部分）
│   ├── backend/                后端 FastAPI
│   │   ├── app/
│   │   │   ├── main.py           应用入口
│   │   │   ├── database.py       数据库引擎与会话
│   │   │   ├── models.py         ORM 模型
│   │   │   ├── schemas.py        Pydantic 模型
│   │   │   ├── crud.py           CRUD 操作
│   │   │   ├── auth.py           认证授权
│   │   │   ├── path_setup.py     sys.path 注入（复用根目录模块）
│   │   │   ├── json_safe.py      大整数安全序列化
│   │   │   ├── engine/           ★ 执行引擎（核心）
│   │   │   ├── services/         服务层
│   │   │   └── routers/          路由层
│   │   ├── alembic/             数据库迁移
│   │   ├── tests/               单元测试
│   │   └── requirements.txt
│   └── frontend/                前端 Vue3
│       └── src/
│           ├── views/            页面
│           ├── components/       组件
│           ├── api/index.ts      API 封装
│           ├── stores/           Pinia 状态
│           ├── router/           路由
│           ├── composables/      组合式函数
│           ├── utils/            工具函数
│           └── layouts/          布局
├── .gitlab-ci.yml            CI/CD 配置
├── fin-api-test.service      systemd 服务
└── fin-api-test.nginx.conf   nginx 配置
```

---

## 四、旧测试框架（命令行版）

### 4.1 utils/ 工具层

#### 4.1.1 `utils/exceptions.py` — 分层异常体系

所有自定义异常继承自 `Exception`，是 HttpClient / DBClient 的异常统一出口。

| 异常类 | 触发场景 | 构造签名 |
|--------|----------|----------|
| `HttpStatusError` | HTTP 状态码非 200 | `(status_code: int, url: str, resp_text: str)` |
| `HttpTimeoutError` | 请求超时 | `(url: str, timeout: int)` |
| `AuthError` | 鉴权失效（401 / code=405） | `(url: str, resp_text: str)` |
| `JsonParseError` | 响应 JSON 解析失败 | `(url: str, resp_text: str)` |
| `BusinessError` | HTTP 200 但业务 code 非成功 | `(code: int, msg: str, url: str, resp_text: str)` |
| `DBQueryError` | 数据库执行异常 | `(sql: str, args: tuple, error_msg: str)` |

#### 4.1.2 `utils/http_client.py` — `HttpClient`（核心）

封装 `requests.Session`，内置 401 自动重登回调与统一异常分层。

```python
class HttpClient:
    def __init__(self, base_url: str = "")
    def set_header(self, key: str, value: str)
    def clear_headers(self)
    def set_token_refresh_callback(self, callback: Callable[[], None])   # 注册 401 回调
    def get(self, url, params=None, timeout=10) -> Dict
    def post(self, url, json=None, timeout=10) -> Dict
    def post_multipart(self, url, data=None, files=None, timeout=20) -> Dict
    def _request(self, method, url, params=None, json=None, data=None,
                 files=None, timeout=20, retry_401: bool = True) -> Dict  # 核心统一请求
```

**`_request` 关键设计**：鉴权失效判定（`status_code==401` 或 `resp_json.code==405`）→ 若已注册回调则调用回调刷新 token，并以 `retry_401=False` 递归重试一次（防无限递归）。状态码 / JSON 解析 / 业务码分别映射为对应异常。日志中对 `Authorization` 脱敏为 `******`。

#### 4.1.3 `utils/api_factory.py` — `ApiFactory`（懒加载工厂）

```python
T = TypeVar("T", bound=BaseApi)
class ApiFactory:
    def __init__(self, base_url: str, base_headers: Dict = None)
    def set_global_token_refresh_callback(self, callback)        # 全局 token 回调注入
    def get_api(self, api_cls: Type[T]) -> T                     # 按类类型缓存单例
    def update_global_header(self, key: str, value: str)         # 同步刷新所有已缓存实例的 header
```

设计模式：工厂 + 懒加载缓存（按类类型缓存）；回调注入（token 刷新回调从工厂注入到每个 HttpClient）。

#### 4.1.4 `utils/db_factory.py` — `DbFactory`

与 ApiFactory 对称的 DB 侧懒加载工厂。

```python
class DbFactory:
    def __init__(self, db_config: Dict)
    def get_db(self, db_cls: Type[BaseDB]) -> BaseDB             # 按类类型缓存单例
```

#### 4.1.5 其他 utils 模块

| 文件 | 关键内容 |
|------|----------|
| `assert_util.py` | 纯函数断言库：`equal / not_equal / is_not_empty / greater / less / contains / in_list / key_exists` 等 18 个，统一中文提示 |
| `generator_util.py` | `generate_bl_no(prefix="BL")`、`generate_invoice_number()`、`generate_unique_id()`（uuid4）、`get_random_str(length)` |
| `yaml_util.py` | `read_yaml(path)`（FileNotFoundError）、`write_yaml(path, data)`（保持键序与中文） |
| `common_util.py` | 常量 `PROJECT_ROOT/LOG_DIR/REPORT_DIR`，`get_project_root()`、`init_project_dir()`（import 时自动建目录） |
| `log_util.py` | `init_logger(log_file_name, level)`（控制台+文件双输出）、`get_logger()`（全局 `api_auto`） |
| `wecom_util.py` | `WeComRobot(webhook).send_markdown(title, content)` |

### 4.2 db/ 数据访问层

#### `db/db_client.py` — `DBClient`（懒连接 + ping 保活）

```python
class DBClient:
    def __init__(self, host, port, user, password, database)
    def _ping_alive(self) -> bool            # ping(reconnect=False) 探测
    def connect(self)                        # 失效自动重建
    def query(self, sql, args=None) -> list  # list[dict]
    def query_one(self, sql, args=None) -> dict | None
    def execute(self, sql, args=None)        # 返回影响行数
    def close(self)
    def __enter__(self) / __exit__(...)      # 支持 with
```

关键设计：每次操作前 `connect()`，通过 `_ping_alive` 探测失效自动重建，规避 MySQL 长空闲断连。使用 `DictCursor + autocommit=True`。

#### `db/base_db.py` — `BaseDB`

```python
class BaseDB:
    def __init__(self, db_client: DBClient)
    # 业务子类通过 self.db.query/query_one/execute 访问
```

#### `db/biz/order_db.py` — `OrderDB(BaseDB)`

- `query_by_bl_no(bl_no: str) -> dict | None`：查 `sys_order`
- `query_fee_by_order_id(order_id: int) -> list`：查 `sys_order_fee_real`

### 4.3 api/ 接口定义层

```python
class BaseApi:
    def __init__(self, http_client: HttpClient)   # self.http = http_client

class AuthApi(BaseApi):
    def login(self, req_body: dict) -> dict       # POST /api/home/login/userLogin

class OrderApi(BaseApi):
    def create_order(self, req_body) -> dict        # POST /api/order/orderEntrust/orderAdd
    def distribute_order(self, req_body) -> dict    # 同上 URL（请求体区分语义）
    def stash_order(self, req_body) -> dict         # POST /api/order/order/orderAdd
    def submit_order(self, req_body) -> dict        # 同上 URL
    def generate_sub_order(self, req_body) -> dict  # POST /api/order/order/generateOrderSub
    def fee_add(self, req_body) -> dict             # POST /api/order/orderFee/bookRealAmountEdit
```

### 4.4 steps/ 步骤层（带硬断言的原子操作）

```python
class OrderStep:
    def __init__(self, order_api: OrderApi)
    # 6 个方法，每个封装一个接口调用 + 内置硬断言 equal(resp["code"], 200, ...)
    # create_order / distribute_order / stash_order / submit_order / generate_sub_order / fee_add
```

### 4.5 flows/ 流程编排层（核心：幂等链路编排）

`flows/order/order_flow.py` — `OrderFlow`：封装 创建→分发→暂存→提交→生成子订单→录入费用 完整链路。

```python
class OrderFlow:
    def __init__(self, api_factory, db_factory, env_config: dict)
    def _load_yaml(self, filename: str) -> dict   # 读 data/{env}/order/{filename}，深拷贝模板
    def create(self) -> dict            # 阶段1：生成 bl_no → 调用 → DB 校验落库
    def distribute(self) -> dict        # 阶段2：自动前置 create()，注入 order_id
    def stash(self) -> dict             # 阶段3：自动前置 distribute()
    def submit(self) -> dict            # 阶段4：DB 断言 status/effective_time/business_time
    def generate_sub_order(self) -> dict# 阶段5：断言 is_traverse==1
    def fee_add(self) -> dict           # 阶段6：遍历费用行生成 unique_id 关联，断言共 16 条费用
```

**关键设计模式**：
- **阶段幂等控制**：6 个布尔标记 `_xxx_done`，重复调用直接返回 `{}`。
- **链式前置自动执行**：每阶段首行调用上一阶段，用例只需调任一阶段，前置自动复用。
- **数据驱动 + 深拷贝模板**：yaml 经 `_load_yaml` 深拷贝后注入运行时 id，避免污染模板。

### 4.6 testcases/ 测试用例层

`testcases/order/test_order.py`：6 个测试函数，各自构造 `OrderFlow` 调用单一阶段方法（前置链路由 Flow 自动完成），各带独立 marker（`create/distribute/stash/submit/generate_sub_order/fee_add`）。

### 4.7 配置与 Fixture 装配

**`conftest.py`**（关键装配点，会话级 Fixture + Token 自动刷新回调链）：

```python
def pytest_configure(config)            # 读 TEST_ENV，加载 config/env_{env}.yaml
@pytest.fixture(scope="session")
def env_config()                         # 返回环境配置
def api_factory(env_config)             # ApiFactory(base_url, headers)
def login_token(api_factory, env_config) # ★ 会话登录 + 注册 refresh_token_func 闭包到工厂
def auto_login(login_token)             # autouse=True 自动触发
def db_factory(env_config)              # DbFactory(mysql)，yield 后关闭所有连接
```

**401 自动重登回调链装配**：闭包 `refresh_token_func`（`threading.Lock` 保证串行）→ `api_factory.set_global_token_refresh_callback` → 工厂 `get_api` 时注入每个 HttpClient → `_request` 检测 401/code=405 时回调并重试一次。

**`pytest.ini`**：`testpaths=testcases`、6 个 markers、HTML 报告配置。
**`run.py`**：`main(marker, loop_count)` 解析参数并循环调 `pytest.main`。

### 4.8 数据文件

| 文件 | 内容 |
|------|------|
| `config/env_demo.yaml` | `env_name/base_url/common_headers/mysql` |
| `data/test/auth/auth_data.yaml` | `login_admin/login_fin/login_operate` 三账号模板 |
| `data/test/order/*.yaml` | create / distribute / stash / submit / fee 请求体模板 |

---

## 五、平台后端（FastAPI）

代码位于 `platform/backend/app/`。

### 5.1 应用入口 `main.py`

```python
app = FastAPI(title="fin-api-test 平台", default_response_class=BigintSafeJSONResponse)
```

- `_check_secret_key()`：启动前校验 `JWT_SECRET_KEY`，缺失则 `RuntimeError` 中断启动
- `on_startup()`：`_check_secret_key()` → `init_db()` → `_ensure_default_admin()`（admin/admin123）→ `_cleanup_old_executions(30)`
- 注册 16 个路由器对象

### 5.2 数据库 `database.py`

```python
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
class Base(DeclarativeBase): ...
def get_db()                # FastAPI 依赖：yield 会话，请求结束自动关闭
def init_db()               # 智能迁移：旧库 stamp head / 新库与已迁移库 upgrade head
def _build_mysql_url()      # 密码用 quote_plus 编码
```

### 5.3 ORM 模型 `models.py`（18 个模型）

```
User
Project ─┬─ Environment(base_url, db_config, login_config, notify_config, variables, common_headers)
         ├─ ApiGroup(parent_id 自引用多级)
         ├─ ApiDefinition(method, path, request_template) ─ ApiField(key, field_type, default_value)
         ├─ CaseGroup(parent_id 自引用多级)
         ├─ TestCase(dag_config JSON) ─ CaseNodeConfig(pre_process, post_extract, assertions, wait_after_ms)
         ├─ ProjectVersion(snapshot JSON)
         ├─ FieldDictionary(key, label)
         ├─ FileCategory(parent_id) ─ TestFile(sha256, storage_path, ref_count)
         ├─ FileTag
         └─ FileTagRelation(多对多)
TestCase ─ ExecutionRecord(status, summary) ─ StepRecord ─ AssertionRecord
OperationLog
```

| 模型 | 关键字段 |
|------|----------|
| `TestCase` | `dag_config`(JSON，存节点和连线) |
| `CaseNodeConfig` | `api_id`, `pre_process`, `post_extract`, `assertions`, `wait_after_ms` |
| `ApiDefinition` | `method`, `path`, `request_template`, `headers_template` |
| `Environment` | `base_url`, `db_config`, `login_config`, `notify_config`, `variables`, `common_headers` |
| `ExecutionRecord` | `status`(running/success/failed), `summary` |

### 5.4 Pydantic 模型 `schemas.py`

`ORMBase(BaseModel)` 配置 `from_attributes=True`。按业务域分 Create / Update / Out 三组：User/Auth、Project、Environment、ApiGroup/ApiField/ApiDefinition、CaseGroup/NodeConfig/TestCase、ProjectVersion、Execution、FieldDictionary、File。

### 5.5 认证授权 `auth.py`（零第三方依赖，标准库实现）

```python
def hash_password(password: str) -> str            # pbkdf2_hmac(sha256) 10万轮 + 随机 salt
def verify_password(password: str, stored: str) -> bool  # hmac.compare_digest 防时序攻击
def validate_password_strength(password: str) -> tuple[bool, str]  # 8-64位，含字母+数字
def create_token(user_id, username, role) -> str   # base64(payload).base64(hmac_sha256)，有效期 7 天
def decode_token(token: str) -> Optional[dict]     # 验签 + 验过期
def get_current_user(cred, db) -> models.User      # FastAPI 依赖：解析 Bearer token
def get_optional_user(cred, db) -> Optional[models.User]
```

> 虽名为 `JWT_SECRET_KEY`，实际是自实现 HMAC-SHA256 签名 Token（规避 Python 3.14 下 passlib/bcrypt wheel 问题）。

### 5.6 CRUD 层 `crud.py`

**审计字段填充（避免 N+1）**：
- `get_user_name_map(db, user_ids) -> dict`、`fill_audit_names(db, obj)`、`fill_audit_names_batch(db, objs)`、`fill_exec_names(db, objs)`

**操作日志**：
```python
def log_operation(db, user, action, target_type, target_id=None, target_name=None, detail=None)
```
失败静默回滚不影响主业务。

**各实体 CRUD**：签名模式一致 `create_xxx(db, data, user_id)` / `get_xxx` / `list_xxx` / `update_xxx` / `delete_xxx` / `reorder_xxx` / `copy_xxx` / `batch_move_xxx`。删除策略：非空阻止删除（分组）、被用例引用阻止删除（接口）、ref_count-1 归零删物理文件。

**项目版本快照/回滚**：
- `build_project_snapshot(db, project_id) -> dict`：构建完整快照
- `create_project_version(db, project_id, name, description, user_id)`：version_no 自增
- `diff_project_versions(base, target) -> dict`：对比返回 added/removed/modified
- `rollback_project_version(db, project, version, user_id)`：**硬回滚**（回滚前自动快照留痕 → 分离执行记录 → 删除重建分组/接口/用例 → 重新关联执行记录，全程同一事务）

### 5.7 引擎层 `engine/`（核心）

#### 5.7.1 `dag_executor.py` — `DagExecutor`

```python
class DagExecutor:
    def __init__(self, db, case, env, execution_record=None)
    @staticmethod
    def _topo_sort(dag) -> Tuple[List[str], List[str]]  # Kahn 算法，返回(order, leftover)
    def execute(self) -> models.ExecutionRecord          # 全流程编排
    def _execute_node(self, execution_id, node_id, node) -> Tuple[bool, int]  # 单节点 6 步
    def _send_request(self, api, body, headers, file_fields=None) -> Tuple[int, Any, Optional[str]]
    def _build_multipart_files(self, file_fields) -> list
    def _close_multipart_files(self, files_payload) -> None
```

**`execute()` 流程**：build_http_client → build_db_client → login（注册 401 回调）→ `_topo_sort` → 逐节点 `_execute_node`（失败即停止）→ 更新 record.status/summary → finally 关闭 db_client/http_session → send_notify。

**`_execute_node` 6 步管线**：
1. 准备请求体/请求头（`build_request_body` → 表达式求值 → 前置处理 → `coerce_json_strings` → `apply_field_types` → `pop_file_fields_from_body`）
2. 发送请求 `_send_request`
3. 后置提取 `Extractor.extract` → `context.update_extracted`
4. 断言 `AssertionEngine.evaluate_all`
5. 落库 StepRecord
6. 落库 AssertionRecord

返回 `(是否通过, wait_after_ms)`；step_passed 判定 = 请求无异常 AND 所有断言通过。

#### 5.7.2 `runner.py` — 执行入口与线程池

```python
_get_executor() -> ThreadPoolExecutor            # 全局懒加载线程池 max_workers=4
run_execution(db, case_id, env_id)               # 同步执行（兼容旧调用）
run_execution_background(execution_id, ...)       # 后台线程，独立 SessionLocal，异常兜底标记 failed
submit_execution(case_id, env_id, execution_id)  # 非阻塞提交到线程池
submit_batch_execution(execution_ids, case_ids, env_id)  # 批量串行执行
```

#### 5.7.3 `context.py` — `ExecutionContext`（统一变量池）

```python
class ExecutionContext:
    def __init__(self, env_vars=None, global_vars=None)
    # env_vars（环境变量副本） / extracted（=环境变量+后置提取，统一池） / global_vars
    def update_extracted(self, data)
    def set_global(self, key, value)
    def to_dict() -> Dict   # {"env":..., "extracted":..., "global":...}
```

#### 5.7.4 `expression.py` — `ExpressionEngine`（表达式引擎）

```python
class ExpressionEngine:
    def __init__(self, context: Dict, db_client=None)
    def evaluate(self, expr: Any) -> Any   # 递归求值 str/dict/list
```

**支持语法**：`${name}`、`${context.name}`、`${env.xxx}`、`${global.xxx}`，内置 14 个函数：`generate_bl_no / generate_unique_id / generate_invoice_number / now / timestamp / random_int / random_string / uuid / upper / lower / md5 / date_add`，以及 DB 函数 `db.query_one / db.query_value / db.query`。

**两种替换模式**：整串就是 `${...}` → 返回原生类型；字符串内嵌多个 `${...}` → 字符串替换。**未定义变量保留 `${}` 占位符**（支持多次求值）。

模块级公共函数 `inject_sql_vars(sql, extracted)`：把 SQL 中 `${xxx}` 替换为变量值（字符串加引号防注入），被三处共用。

#### 5.7.5 `extractor.py` — `Extractor`（后置提取器）

```python
class Extractor:
    def __init__(self, db_client=None)
    def extract(self, response, rules: List[Dict]) -> Dict[str, Any]   # response 用 jsonpath，db 执行 SQL
    def set_extracted_vars(self, vars)                                  # 注入已提取变量供 SQL 引用
```

实时更新 `_vars`，同节点后续规则能引用前面刚提取的变量。

#### 5.7.6 `assertion_engine.py` — `AssertionEngine`（17 种断言）

```python
class AssertionEngine:
    def __init__(self, context: Dict, db_client=None)
    def evaluate_all(self, response_body, status_code, response_time_ms, rules) -> List[Dict]
```

| 类别 | 断言类型 |
|------|----------|
| JSON Path | `json_path_equals / not_equals / contains / exists / not_empty / match_regex / type_equals` |
| HTTP | `response_status_equals / response_time_less_than` |
| DB 查询 | `db_query_equals / not_equals / not_empty / count_equals / count_greater_than / count_less_than` |
| DB vs 响应 | `db_vs_jsonpath_equals / not_equals` |

DB 断言支持 `retry_count` / `retry_interval`（应对异步落库）。`expected` 支持表达式求值；`_loose_equals` 松散相等（int 3 与 "3" 判等）。

#### 5.7.7 `preprocessor.py` — `PreProcessor`（4 种动作）

```python
class PreProcessor:
    def __init__(self, context: Dict, db_client=None)
    def process(self, body, actions: List[Dict], extracted=None) -> Any
```

动作类型：`set_field` / `add_field`（含嵌套路径，求值后同步写入 extracted）、`delete_field`、`sleep`、`iterate_set`（遍历列表赋值，用于 unique_id 关联）。辅助函数 `get_nested_value / set_nested_value / delete_nested_value`。

#### 5.7.8 `type_coercer.py` — 类型强转

```python
coerce_json_strings(obj) -> Any      # "[123]" → [123]
apply_field_types(body, api) -> Any  # 按 ApiField.field_type 强转标量
coerce_scalar(val, field_type) -> Any
infer_array_elem_type(default_value) -> Optional[str]
```

#### 5.7.9 接口导入解析器

| 文件 | 函数 | 说明 |
|------|------|------|
| `curl_parser.py` | `parse_curl_to_previews(text) -> (previews, errors)` | shlex 词法拆分，支持 -X/-H/-d/-k/-L 及 `$'...'` ANSI-C quoting |
| `har_parser.py` | `parse_har_to_previews(har_data) -> previews` | 跳过静态资源、非业务方法、同 method+path 去重 |
| `har_parser.py` | `previews_to_api_create(previews, project_id, group_id, existing_codes) -> (to_create, skipped)` | HAR/cURL 共用落库 |

字段类型推断：bool→bool，int→int，**float→string**（金额避免精度问题），list→array，dict→object。

### 5.8 服务层 `services/`

| 文件 | 关键函数 | 职责 |
|------|----------|------|
| `runtime_service.py` | `build_http_client(env)`、`login(client, env)`、`build_db_client(env)` | 运行时构建 HTTP/DB 客户端，登录注册 401 回调 |
| `body_builder.py` | `build_request_body(api)`、`parse_field_value(raw, field_type)`、`set_nested(target, path, value)`、`extract_file_fields(api)`、`pop_file_fields_from_body(body, api)` | 请求体组装 |
| `spec_parser.py` | `extract_fields_from_spec(info, spec, is_v3)`、`path_to_code`、`resolve_ref`、`swagger_type_to_field_type` | OpenAPI/Swagger 解析 |
| `notifier.py` | `send_notify(env, case, record, executor_name="")` | 企微通知（按 enable_on_success/failure 开关） |
| `file_helpers.py` | `build_storage_path(sha256)`、`resolve_physical_path(storage_path)`、`is_previewable(content_type)` | 文件存储路径 |

### 5.9 路由层 `routers/`（12 个文件）

| 路由文件 | 前缀 | 核心端点 |
|----------|------|----------|
| `auth.py` | `/api/auth` | login / register / me / change-password / avatar CRUD |
| `users.py` | `/api/users` | 用户 CRUD（仅 admin）+ `/simple` 轻量列表 |
| `projects.py` | `/api/projects` | 项目 CRUD + reorder |
| `environments.py` | `/api/environments` | 环境 CRUD + copy + test-db + test-login |
| `apis.py` | `/api/apis` + `/api/api-groups` | 接口 CRUD + 分组 + 导入(cURL/HAR/Swagger) + debug |
| `testcases.py` | `/api/testcases` + `/api/case-groups` | 用例 CRUD + 分组 |
| `executions.py` | `/api` | execute / batch-execute / executions 列表 / 详情 |
| `reports.py` | `/api/reports` | 完整执行报告（含 steps+assertions） |
| `versions.py` | 无统一前缀 | 版本快照 / list / diff / rollback / delete |
| `field_dictionaries.py` | `/api/field-dictionaries` | 字段字典 + `/map` + batch |
| `files.py` | `/api/files` + `/api/file-categories` + `/api/file-tags` | 文件中心（sha256 去重上传/预览/下载） |
| `operation_logs.py` | `/api/operation-logs` | 日志查询 + cleanup（仅 admin） |

### 5.10 辅助模块

- `path_setup.py`：将项目根目录（`parents[3]`）和 backend 目录（`parents[1]`）加入 `sys.path`，使平台复用 `utils/`、`db/`。
- `json_safe.py`：`BigintSafeJSONResponse`（`render()` 前递归 `sanitize_bigints`，把超 2^53-1 的大整数转字符串，防前端精度丢失）。

---

## 六、平台前端（Vue3）

代码位于 `platform/frontend/src/`。

### 6.1 入口与配置

- **`package.json`**：依赖 vue 3.5 / vue-router 4 / pinia 2 / element-plus / axios / `@vue-flow/core` + background/controls/minimap / vue-json-pretty / sortablejs + vuedraggable；scripts：`dev`/`build`(`vue-tsc -b && vite build`)/`preview`
- **`vite.config.ts`**：别名 `@`→`./src`，dev port 5173，代理 `/api/`（带尾斜杠避免误匹配前端路由）→ `http://127.0.0.1:8000`
- **`main.ts`**：注册 Pinia / router / ElementPlus，全量引入 element-plus 与 vue-flow 样式，挂载后调 `setupRipple()`
- **`App.vue`**：渲染 `<RequestProgressBar />` + `<router-view />`，setup 调 `store.initTheme()`
- **`style.css`**：设计令牌体系（圆角/表面/边框/文字层级/主色 `#0071e3`/状态色/阴影），双主题（`:root` 亮 / `html.dark` 暗），全局美化 el 组件

### 6.2 路由 `router/index.ts`

`createWebHistory`。独立路由：`/login`（public）、`/change-password`；主布局子路由 `/`→MainLayout 下 13 个页面。

**全局守卫 `beforeEach`（4 道关卡）**：
1. `meta.public` 放行；2. 无 token 跳 `/login`；3. 首次异步 `loadUser`，`must_change_password` 强制跳改密页；4. `requireAdmin` 且非 admin 跳 `/apis`。

### 6.3 状态管理 `stores/`

**`stores/index.ts`（`useAppStore`）**

| state | 说明 |
|-------|------|
| `projects` / `currentProjectId` | 项目列表与当前项目 |
| `environments` / `currentEnvId` | 环境列表与当前环境（自动持久化） |
| `user` | 当前登录用户 |
| `fieldDictMap` | 当前项目字段中英文映射 |
| `coreCapVisible` / `coreCapTab` | 核心能力弹窗（跨组件共享） |
| `theme` | light/dark/auto |

关键 actions：`loadProjects`（恢复记忆项目→localStorage）、`loadEnvironments`、`loadFieldDict`（防竞态）、`setProject(id)`（持久化项目、清环境、触发加载）、主题三件套（`initTheme/applyTheme/toggleTheme`）。

**数据流核心**：`setProject` 改变 `currentProjectId` → 各业务页 `watch` 自动刷新数据 → `fieldDictMap` 驱动字段中文标签。

**`stores/tabs.ts`（`useTabStore`）**：多标签页管理，配合 keep-alive。`addTab` / `removeTab` / `removeOthers` / `removeAll` / `reset`。

### 6.4 API 封装 `api/index.ts`

Axios 实例 `baseURL: '/api'`、`timeout: 60000`，扩展 `AxiosRequestConfig.silent?`（轮询跳过进度条）。

**拦截器**：请求注入 `Authorization: Bearer <token>` + 启动进度条；响应成功/失败结束进度条，**401 清 token 跳 /login**，错误统一提取 `detail`。

Token 管理：`getToken/setToken/clearToken`（localStorage `fin_api_test_token`）。

业务 API 模块（均基于 `http`）：`authApi` / `userApi` / `logApi` / `projectApi` / `envApi`（testDb/testLogin）/ `apiGroupApi` / `apiApi`（importSpec/previewHar/importHar/previewCurl/importCurl/importFields/debug）/ `caseGroupApi` / `caseApi`（execute/batchExecute）/ `projectVersionApi`（diff/rollback）/ `execApi` / `dictApi` / `fileApi`（fetchBlob）/ `fileCategoryApi` / `fileTagApi`。

### 6.5 组合式函数 `composables/`

| Hook | 职责 |
|------|------|
| `useFaviconStatus` | 执行状态动态切换 favicon（SVG data URI，running/success/failed，success/failed 3 秒恢复），模块级单例 |
| `useFieldDict` | `resolveLabel(key, existingLabel?)` / `dictLabel(key)`（嵌套路径智能匹配） |
| `useGroupMemory` | 分组展开/折叠记忆，按 `scope + projectId` 持久化 localStorage |
| `useGroupTree` | 多级分组树形工具：`buildGroupTree` / `flattenTreeVisible` / `useGroupTree()`（封装视图模型，含 treeSelectData、展开记忆） |

### 6.6 组件 `components/`

| 组件 | props / emits | 职责 |
|------|---------------|------|
| `AssertionTable` | modelValue / update:modelValue | 17 种断言规则表，按类型动态显隐列 |
| `CommandPalette` | 暴露 open/close | 全局命令面板（Ctrl+K），fuzzy + 拼音首字母搜索 |
| `DagCanvas` | nodes, edges / update:nodes, update:edges, node-open, nodes-pasted | VueFlow DAG 画布，拖拽连线/快捷键/自动布局/复制粘贴 |
| `EmptyState` | description, imageSize | 空状态占位（内置 SVG 插图） |
| `FieldTable` | modelValue / update:modelValue | 接口字段配置表（支持嵌套路径、字典提示） |
| `FilePicker` | modelValue, modelFileId / update:modelValue, select | 文件选择器弹窗 |
| `KeyValueTable` | modelValue, valueType / update:modelValue | 键值对配置表 |
| `NodeConfigDrawer` | visible, config, apis / update:visible, save | 节点配置抽屉（4 Tab：基础/前置/后置/断言） |
| `PostExtractTable` | modelValue / update:modelValue | 后置变量提取表 |
| `PreProcessTable` | modelValue, fields / update:modelValue | 前置处理表（set_field/delete_field/iterate_set） |
| `ProjectVersionHistory` | modelValue, projectId / update:modelValue, rollback | 项目版本管理（快照/diff/回滚，含 LCS 行级 diff） |
| `RequestProgressBar` | 无 | 顶部进度条（订阅 progressState） |

**`DagCanvas` 快捷键**：`Esc` 退出连线、`Delete` 删节点、`Enter` 打开配置、`Ctrl+C/V` 复制粘贴（新 id + 偏移 40,40 + 克隆 config）。

### 6.7 页面 `views/`

| 页面 | 路径 | 核心功能 |
|------|------|----------|
| Login | `/login` | 登录/注册双 Tab，品牌区鼠标视差 |
| ChangePassword | `/change-password` | 强制改密 |
| ProjectManage | `/projects` | 项目管理（拖拽排序） |
| EnvManage | `/envs` | 环境列表（拖拽、复制、测试连接/登录） |
| EnvEdit | `/envs/edit/:id?` | 环境编辑（base_url/db/login/notify/variables/headers） |
| ApiManage | `/apis` | 接口管理（多级分组、导入、批量操作） |
| ApiEdit | `/apis/edit/:id?` | 接口编辑（字段管理、调试、导入覆盖字段） |
| CaseList | `/cases` | 用例列表（批量执行） |
| **CaseDesigner** | `/cases/designer/:id?` | ★ 用例 DAG 编排（三栏布局） |
| Execution | `/executions` | 执行记录（自动刷新、清理） |
| ReportDetail | `/reports/:id` | 执行报告（SVG 趋势图、重跑、导出 CSV/HTML） |
| DictManage | `/dictionary` | 字段字典（批量导入） |
| FileCenter | `/files` | 文件中心（分类树+标签云） |
| UserManage | `/users` | 用户管理（admin） |
| OperationLog | `/operation-logs` | 操作日志（admin） |

**CaseDesigner 三栏**：左侧接口列表（分组树，点击 addNode）+ 中央 DagCanvas（v-model:nodes/edges）+ 右侧 NodeConfigDrawer。执行时 `useFaviconStatus` 切图标 + 递归 setTimeout(poll, 2000) 轮询（maxPolls=150，silent 模式）。

### 6.8 布局 `layouts/MainLayout.vue`

包裹除 login/change-password 外所有页面。

- **侧边栏**：品牌 logo + `el-menu` 导航（admin 额外用户管理/操作日志）+ 开发者头像
- **顶栏**：折叠按钮、面包屑、命令面板触发器（Ctrl+K）、项目选择器、版本按钮、环境选择器、使用说明、主题下拉（View Transitions API 圆形扩散）、用户下拉
- **标签页栏**：渲染 tabStore.tabs（点击跳转/中键关闭/关闭其他/关闭全部）
- **main**：`<router-view>` + `<transition>` + `<keep-alive :max="15">`
- **内置弹窗**：使用说明、核心能力详情（表达式引擎 + 17 断言规则，与后端对齐）、头像上传（canvas 压缩 256×256 base64）

### 6.9 工具 `utils/`

| 文件 | 职责 |
|------|------|
| `fuzzy.ts` | `fuzzyMatch(query, target)`（借鉴 VS Code，连续匹配加分、词首加分） |
| `pinyin.ts` | `toPinyinInitials(str)`（内置约 500 常用汉字，避免引入 pinyin 依赖） |
| `reportFilename.ts` | `generateReportFilename({caseName, envName, status, ext})` |
| `requestProgress.ts` | 响应式 `progressState` + `startProgress()/doneProgress()`（并发计数，不引入 NProgress） |
| `ripple.ts` | `setupRipple()`（点击 `.el-button` 扩散水波纹，尊重 prefers-reduced-motion） |

---

## 七、依赖关系总览

### 7.1 旧框架运行时装配链

```
conftest.py
  ├─ config/env_{env}.yaml → env_config
  ├─ ApiFactory(base_url, headers) ── set_global_token_refresh_callback(refresh_token_func)
  │     └─ get_api(OrderApi) → OrderApi(HttpClient[注入401回调])
  ├─ DbFactory(mysql) ── get_db(OrderDB) → OrderDB(DBClient[ping保活])
  └─ test_order.py → OrderFlow(api_factory, db_factory, env_config)
        ├─ OrderApi / OrderDB / OrderStep(order_api)
        └─ _load_yaml → data/{env}/order/*.yaml
```

### 7.2 平台后端依赖关系

```
main.py
 ├── database (init_db, SessionLocal, Base)
 ├── auth (get_current_user 依赖)
 ├── json_safe (BigintSafeJSONResponse)
 └── routers/* (16 个路由器)

DagExecutor（核心编排者）
 ├── ExecutionContext（变量池）
 ├── runtime_service (build_http_client, login, build_db_client)
 ├── body_builder (build_request_body, pop_file_fields_from_body)
 ├── PreProcessor → ExpressionEngine（表达式求值）
 ├── Extractor → inject_sql_vars, jsonpath_ng（后置提取）
 ├── AssertionEngine → ExpressionEngine, inject_sql_vars, jsonpath_ng（断言）
 ├── type_coercer → preprocessor (get/set_nested_value)
 └── notifier (send_notify)

runner.py ── ThreadPoolExecutor(max_workers=4) ──→ DagExecutor（异步驱动）
```

### 7.3 新旧复用关系

新平台通过 `platform/backend/app/path_setup.py` 注入 `sys.path`，复用旧框架的：
- `utils/http_client.HttpClient`（请求 + 401 自动重登 + 业务码校验 + 日志脱敏）
- `db/db_client.DBClient`（MySQL 查询）
- `utils/generator_util`（通过表达式引擎调用）

### 7.4 继承关系

```
旧框架：
  Exception → HttpStatusError / HttpTimeoutError / AuthError / JsonParseError / BusinessError / DBQueryError
  BaseDB → OrderDB
  BaseApi → AuthApi / OrderApi

平台后端：
  Base(DeclarativeBase) → 18 个 ORM 模型
  ORMBase(BaseModel) → 各 Create/Out Schema
```

---

## 八、项目运行方式

### 8.1 旧框架（命令行）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境（复制模板并编辑 base_url / mysql）
cp config/env_demo.yaml config/env_test.yaml

# 3. 运行（环境由 TEST_ENV 环境变量控制，默认 test）
python run.py              # 跑全部用例 1 轮
python run.py fee_add      # 只跑 fee_add 用例
python run.py fee_add 5    # 只跑 fee_add 用例 5 轮
pytest -m create           # 按 marker 过滤
```

报告输出到 `report/report.html`，日志输出到 `logs/`。

### 8.2 平台本地开发

**后端：**

```bash
cd platform/backend
cp .env.example .env          # 填写 DB_PASSWORD 与 JWT_SECRET_KEY
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000   # 自动迁移建表 + 创建 admin 账号
```

**前端：**

```bash
cd platform/frontend
npm install
npm run dev                  # http://localhost:5173
```

默认账号 `admin` / `admin123`（首登强制改密）。Swagger 文档 http://127.0.0.1:8000/docs。

**测试与 Lint：**

```bash
cd platform/backend
python -m pytest tests/ -v                     # 单元测试
python -m ruff check --select F platform/backend  # Lint（pyflakes）
```

### 8.3 数据库迁移

```bash
cd platform/backend
alembic revision --autogenerate -m "描述"
alembic upgrade head
```

> `init_db()` 智能迁移：旧库（有表无 alembic_version）→ `stamp head`；全新库 / 已迁移库 → `upgrade head`。

### 8.4 部署架构

```
浏览器 http://192.168.22.106:8088
  ↓
nginx（监听 8088）
  ├─ location /          → 前端静态文件（Vue dist，SPA try_files 回退）
  ├─ location /api/      → 反代后端 http://127.0.0.1:8001
  └─ 静态资源 30d 缓存
  ↓
后端 FastAPI（uvicorn :8001，systemd 管理）
  ├─ .env 环境变量（CI 注入）
  └─ MySQL（业务+平台库）
```

**systemd 服务**（`fin-api-test.service`）：`ExecStart=.../venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001`，`Restart=always`。

### 8.5 CI/CD 流水线

`.gitlab-ci.yml` 四阶段：`lint → build → deploy → notify`

- **lint**（并行）：`backend-lint`（ruff check --select F）、`frontend-lint`（vue-tsc --noEmit）
- **build**：`frontend-build`（npm run build → dist）
- **deploy**：SSH 拉代码 → 写 .env → pip install + alembic upgrade → 上传 dist → systemctl restart
- **notify**（always）：curl POST 企微 webhook

GitLab Variables：`SSH_PRIVATE_KEY` / `WECOM_WEBHOOK` / `JWT_SECRET_KEY` / `DB_PASSWORD` / `DB_HOST` / `DB_USER` / `DB_NAME`。

---

## 九、速查附录

### 9.1 关键文件速查

| 需求 | 文件 |
|------|------|
| 旧框架启动 | run.py |
| 旧框架 Fixture 装配 | conftest.py |
| HTTP 客户端（401 自动重登） | utils/http_client.py |
| API 工厂 | utils/api_factory.py |
| 链路编排（幂等） | flows/order/order_flow.py |
| 平台后端入口 | platform/backend/app/main.py |
| 数据库连接/迁移 | platform/backend/app/database.py |
| 表结构 | platform/backend/app/models.py |
| 认证授权 | platform/backend/app/auth.py |
| 执行核心 | platform/backend/app/engine/dag_executor.py |
| 表达式引擎 | platform/backend/app/engine/expression.py |
| 断言引擎 | platform/backend/app/engine/assertion_engine.py |
| 前端路由 | platform/frontend/src/router/index.ts |
| 前端状态 | platform/frontend/src/stores/index.ts |
| 前端 API 封装 | platform/frontend/src/api/index.ts |
| DAG 画布 | platform/frontend/src/components/DagCanvas.vue |
| 用例编排 | platform/frontend/src/views/CaseDesigner.vue |

### 9.2 表达式速查

| 表达式 | 说明 |
|--------|------|
| `${order_id}` | 引用已提取变量 |
| `${context.order_id}` | 同上（兼容写法） |
| `${env.base_url}` | 引用环境变量 |
| `${now(format='%Y-%m-%d')}` | 当前时间 |
| `${random_int(min=1, max=100)}` | 随机整数 |
| `${generate_bl_no(prefix='smoke')}` | 生成提单号 |
| `${md5(s='abc')}` | MD5 哈希 |
| `${db.query_value(sql, field='xxx')}` | DB 查询单值 |

### 9.3 断言类型速查（17 种）

JSON Path：`json_path_equals / not_equals / contains / exists / not_empty / match_regex / type_equals`
HTTP：`response_status_equals / response_time_less_than`
DB 查询：`db_query_equals / not_equals / not_empty / count_equals / count_greater_than / count_less_than`
DB vs 响应：`db_vs_jsonpath_equals / not_equals`

### 9.4 设计模式汇总

1. **工厂 + 懒加载缓存**（ApiFactory / DbFactory）：按类类型缓存实例
2. **401 自动重登回调链**（旧框架 + 平台共用）：闭包注入 → 工厂 → HttpClient → `_request` 检测 401/code=405 回调重试，`threading.Lock` 保证串行
3. **阶段幂等控制**（OrderFlow）：6 个布尔标记 + 链式前置自动执行
4. **懒连接 + ping 保活**（DBClient）：每次操作前 connect，失效自动重建
5. **数据驱动 + 深拷贝模板**（OrderFlow `_load_yaml`）：注入运行时 id 不污染模板
6. **分层异常体系**（HttpClient）：状态码/JSON/鉴权/业务码分别映射异常
7. **未定义变量保留占位符**（ExpressionEngine）：支持 body 多次求值
8. **松散相等比较**（AssertionEngine）：int 与字符串判等，DB 断言支持重试
9. **统一变量池**（ExecutionContext）：环境变量 + 各节点后置提取统一存放，贯穿用例生命周期
10. **大整数安全序列化**（BigintSafeJSONResponse）：防前端精度丢失

---

> 本文档基于源码逐行梳理生成，所有方法签名、模型字段、路由路径均与代码一致。若代码更新，请同步修订本文档。
