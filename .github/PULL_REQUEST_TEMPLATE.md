## 变更说明 / What does this PR do

<!-- 一两句话说清改了什么、为什么改；关联 issue 请写 Fixes #N -->

## 自查清单 / Checklist

- [ ] 后端单测通过：`python -m pytest tests -q`（platform/backend，fake-db）
- [ ] 前端类型检查通过：`npx vue-tsc --noEmit`（platform/frontend）
- [ ] Lint 通过：`ruff check --select F platform/backend`
- [ ] 分层规约未破坏（路由层不内联 ORM、单次 HTTP 请求/执行编排/请求组装单点实现）
- [ ] 涉及 schema 变更时已补 Alembic 迁移，并确认全新库可初始化
- [ ] 文档已同步（README / platform/README / docs）

## 截图 / Screenshots（前端变更必填）
