# Fin API Test

> 面向金融业务系统的 API 自动化测试框架 · pytest 驱动 · 多环境 · 数据库校验 · 企微通知

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![pytest](https://img.shields.io/badge/pytest-9.0.3-green.svg)](https://pytest.org/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)

金融业务接口链路长、状态流转复杂、强依赖落库校验。本项目把"登录鉴权 → 接口调用 → 业务编排 → 数据校验 → 结果通知"串联成一套开箱即用的骨架，让用例代码只关心业务本身。

> 可视化平台版本（DAG 拖拽编排 + 结构化报告）位于 [`platform/`](./platform/README.md)，与命令行版本共享底层能力。

## 特性

- **分层架构** — `Test → Step → API → HTTP/DB`，职责清晰
- **多环境** — `config/env_*.yaml` 一键切换 test / pre / prod
- **Token 自动刷新** — 401 自动重登并刷新全局 Authorization
- **数据库校验** — 直接 MySQL 查询，校验落库状态
- **YAML 数据驱动** — 请求模板与测试数据分离
- **30+ 断言方法** — 自带期望值与实际值对比
- **企微通知** — 执行结束自动推送结果
- **HTML 报告** — 自包含单文件，可邮件直接发送

## 快速开始

```bash
# 安装依赖（推荐清华镜像）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 配置环境
cp config/env_demo.yaml config/env_test.yaml
# 编辑 env_test.yaml，填写 base_url / mysql / wecom_webhook

# 运行
python run.py              # 单轮
python run.py 5            # 循环 5 轮（稳定性回归）
pytest -m create           # 按 marker 过滤
```

报告输出到 `report/report.html`。

## 分层架构

```
Test Cases (testcases/)      用例编排、断言、marker
     ↓
Business Steps (steps/)      业务流程编排
     ↓
API Layer (api/)             HTTP 请求封装
     ↓
HTTP Client | MySQL Client   401 自动重登 | 落库校验
```

| 层级 | 路径 | 职责 |
|------|------|------|
| Test | `testcases/` | 用例编排、断言、pytest marker |
| Step | `steps/` | 业务流程编排 |
| API | `api/` | HTTP 请求封装 |
| DB | `db/` | MySQL 查询、数据校验 |
| Utils | `utils/` | HTTP 客户端、断言、日志、通知 |

## 使用示例

```python
# api/order/order_api.py
from api.base_api import BaseApi

class OrderApi(BaseApi):
    def create_order(self, body: dict):
        return self.http.post("/api/order/orderEntrust/orderAdd", json=body)
```

```python
# testcases/order/test_order.py
@pytest.mark.create
def test_create(api_factory, db_factory):
    order_api = api_factory.get_api(OrderApi)
    order_db = db_factory.get_db(OrderDB)
    step = OrderStep(order_api)

    body = read_yaml("data/test/order/create.yaml")
    resp = step.create_order(body)

    record = order_db.query_by_bl_no(body["bl_no"])
    is_not_empty(record, "订单未落库")
    equal(record["entrust_status"], 1, "分发状态不一致")
```

## 目录结构

```
fin-api-test/
├── api/             # 接口层（base_api + 业务接口）
├── steps/           # 业务流程层
├── db/              # 数据库层（连接池 + 业务查询）
├── testcases/       # 测试用例
├── data/            # 测试数据（按环境分目录）
├── utils/           # 工具层（http_client / assert / log / wecom）
├── config/          # 环境配置
├── platform/        # 可视化测试平台（前后端分离）
├── conftest.py      # pytest 全局 fixture
├── run.py           # 启动入口
└── pytest.ini
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 测试框架 | [pytest](https://pytest.org/) 9.0.3 |
| HTTP | [requests](https://docs.python-requests.org/) 2.33.0 |
| 数据库 | [PyMySQL](https://pymysql.readthedocs.io/) 1.1.1 |
| 数据格式 | [PyYAML](https://pyyaml.org/) 6.0.1 |
| 报告 | [pytest-html](https://pytest-html.readthedocs.io/) 4.0.2 |

## 可视化平台

本项目同时提供一套 Web 测试平台，位于 [`platform/`](./platform/README.md)：

- **后端**：FastAPI + SQLAlchemy + MySQL
- **前端**：Vue3 + Element Plus + Vue Flow
- **核心**：DAG 拖拽编排、字段级接口配置、结构化报告、用户权限、并发执行

## License

[MIT](LICENSE)
