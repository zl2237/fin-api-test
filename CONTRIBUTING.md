# 贡献指南 / Contributing

感谢关注 fin-api-test！欢迎通过 Issue、Discussion 与 Pull Request 参与共建。

## 开发环境

```bash
git clone https://github.com/zl2237/fin-api-test.git
cd fin-api-test

# 后端（Python 3.12+）
python -m venv .venv && .venv\Scripts\activate      # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt -r platform/backend/requirements.txt pytest ruff
cd platform/backend
cp .env.example .env        # 填写本机 MySQL 与 JWT_SECRET_KEY
python -m uvicorn app.main:app --port 8000

# 前端（Node 20+）
cd ../frontend
npm install && npm run dev   # http://localhost:5173
```

## 提交前自查（与 CI 同口径）

```bash
# platform/backend 下
python -m pytest tests -q                 # 全量 fake-db 单测
python -m ruff check --select F platform/backend

# platform/frontend 下
npx vue-tsc --noEmit
```

## 架构约定（由测试守卫，提交前请确认未破坏）

- 分层：`routers`（薄）→ `crud`（域模块）→ `services`（业务编排）→ `engine`（DAG 执行引擎）
- 单点实现：HTTP 请求发送（`services/request_sender.py`）、执行编排（`services/execution_launcher.py`）、
  请求组装（`engine/prepare_request.py`）、拓扑排序（`engine/topo.py`）各只有一份实现
- 引擎不反向 import 路由层；`StepResult` 事件经 `ExecutionSink` 落库，引擎可脱离 DB 测试
- 涉及数据库结构变更：新增 Alembic 迁移，并保证全新库可直接初始化

## 提交规范

使用 Conventional Commits（类型 + 中文描述均可）：

```
feat: 测试套件串行执行与共享变量白名单
fix(frontend): 数据集行编辑对象字段显示 [object Object]
docs: README 同步数据驱动能力
```

## PR 流程

1. Fork 或建分支，完成开发与自查
2. 提交 PR 并填写模板中的 Checklist
3. CI（后端单测 / ruff / vue-tsc / 前端构建）全部通过后合并

## 报告问题

- 可复现 Bug：[Issue](https://github.com/zl2237/fin-api-test/issues/new?template=bug_report.md)
- 安全漏洞：见 [SECURITY.md](SECURITY.md)
- 使用问题与想法：[Discussions](https://github.com/zl2237/fin-api-test/discussions)
