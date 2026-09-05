# Fin API Test

> 面向金融业务系统的 API 自动化测试框架 · pytest 驱动 · 多环境 · 数据库校验 · 链路编排

[![CI](https://github.com/zl2237/fin-api-test/actions/workflows/ci.yml/badge.svg)](https://github.com/zl2237/fin-api-test/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![pytest](https://img.shields.io/badge/pytest-9.0.3-green.svg)](https://pytest.org/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)

金融业务接口链路长、状态流转复杂、强依赖落库校验。本项目把"登录鉴权 → 接口调用 → 业务编排 → 数据校验"串联成一套开箱即用的骨架，让用例代码只关心业务本身。

> 可视化 Web 平台版本见 [`platform/`](./platform/README.md)。

## Features

- **分层架构** — `Test → Flow → Step → API → HTTP/DB`，职责清晰
- **链路编排** — `OrderFlow` 封装完整业务链路，用例 3 行代码跑通全流程
- **多环境** — `config/env_*.yaml` 一键切换 test / pre / prod
- **Token 自动刷新** — 401 自动重登并刷新全局 Authorization
- **数据库校验** — 直接 MySQL 查询，校验落库状态
- **YAML 数据驱动** — 请求模板与测试数据分离

## Quick Start

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境
cp config/env_demo.yaml config/env_test.yaml   # 编辑 base_url / mysql

# 运行
python run.py              # 跑全部用例 1 轮
python run.py fee_add      # 只跑 fee_add 用例
python run.py fee_add 5    # 只跑 fee_add 用例 5 轮
pytest -m create           # 按 marker 过滤
```

报告输出到 `report/report.html`。

## Architecture

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

## Example

```python
# api/order/order_api.py
from api.base_api import BaseApi

class OrderApi(BaseApi):
    def create_order(self, body: dict):
        return self.http.post("/api/order/orderEntrust/orderAdd", json=body)
```

```python
# testcases/order/test_order.py
@pytest.mark.fee_add
def test_fee_add(api_factory, db_factory, env_config):
    """创建→分发→暂存→提交→生成子订单→录入费用"""
    flow = OrderFlow(api_factory, db_factory, env_config)
    flow.fee_add()   # 自动执行前置链路，幂等控制
```

## Tech Stack

[pytest](https://pytest.org/) 9 · [requests](https://docs.python-requests.org/) 2.33 · [PyMySQL](https://pymysql.readthedocs.io/) 1.1 · [PyYAML](https://pyyaml.org/) 6 · [pytest-html](https://pytest-html.readthedocs.io/) 4

## Visual Platform

同时提供一套 Web 测试平台（FastAPI + Vue3），与命令行版本共享底层能力：

- 平台说明与快速上手：[platform/README.md](./platform/README.md)
- 深模块词汇表（单一实现约定）：[docs/CONTEXT.md](./docs/CONTEXT.md)
- 后端 730 个 fake-db 单测 + 前端 vue-tsc 全量类型检查，CI 与 pre-commit 同口径

## License

[MIT](LICENSE)
