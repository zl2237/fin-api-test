# 工程质量评分卡

> **文档版本**:v1.1
> **评分日期**:2026-10-10
> **基准提交**:`53ea862`(main,GitLab `dev-gitlab/main` 与之同步;GitHub 为镜像,滞后属正常由维护者自行同步)
> **评分对象**:fin-api-test 全仓库(测试平台前后端 + 根目录五层用例工程)
> **维护说明**:每次质量专项改进后追加一轮记录,评分依据须为可验证的客观证据(CI 结果、测试计数、扫描报告)。

---

## 1. 综合得分

**83 / 100**(百分制六维加权)

```
综合分 = Σ(维度得分 × 维度权重)
       = 85×0.20 + 72×0.15 + 95×0.15 + 82×0.20 + 85×0.20 + 78×0.10
       = 83.25 ≈ 83
```

## 2. 评分雷达图

![工程质量评分雷达图](scorecard_radar.svg)

## 3. 六维评分明细

| 维度 | 权重 | 得分 | 加权分 | 评分依据 |
|---|---|---|---|---|
| 测试保障 | 20% | 85 | 17.0 | 后端 pytest 759 通过(46 文件,较首轮 +25),前端 vitest 72 通过(7 文件,新增 ripple.test.ts 含 matchMedia mock);前端覆盖率已可量化(utils 行覆盖 86.8%/分支 83.6%),但 composables 11 个文件 0% 覆盖、后端仍无 pytest-cov 基线 |
| 类型安全 | 15% | 72 | 10.8 | vue-tsc --noEmit 零错误;但本地 mypy 回归至 28 错误/7 文件(首轮为 0,八批重构期间引入:validation.py 12、replay_service.py 4、dag_executor.py 4 等);GitHub 镜像的 mypy job 已飘红、GitLab 侧 `\|\| true` 完全吞掉信号,双平台均无强制卡点 |
| 依赖安全 | 15% | 95 | 14.25 | GitHub Dependabot 开放告警 0(API 实时核验);SQLAlchemy 2.0.52 兼容 Python 3.14;关键依赖全部钉版本 |
| CI/CD | 20% | 82 | 16.4 | 主 CI 为 GitLab 全链路(lint→build→deploy→企微通知)且与 main 同步(0 差异);GitHub 5 门禁 + Dependabot 作镜像侧护栏;扣分:mypy 双平台未 blocking(GitLab `\|\| true` 完全吞掉信号),后端 pytest 部署门禁本次刚补入 `backend-check` job(尚未经流水线验证,按未验证计) |
| 代码质量 | 20% | 85 | 17.0 | 八候选重构 6 批全部落地(详见第二轮记录):死代码 -327 行、DAG N+1 消除、25+ 路由补 response_model、巨型视图拆分、SQL 插入收敛;ruff(pyflakes F)零告警实测通过;169 文件/21,506 行,分层结构一致 |
| 文档完备 | 10% | 78 | 7.8 | SYSTEM_DESIGN.md(41KB)经巡检同步代码实况,CONTEXT.md 词条重写,OpenAPI 契约自动化(scripts/export_openapi.py → 前端 api.gen.ts 类型化客户端);仍缺独立 API 参考文档与部署运维手册(部署细节散在 .gitlab-ci.yml 头注释) |

## 4. 证据快照(2026-10-10)

| 指标 | 数值 | 来源 |
|---|---|---|
| 后端测试 | 759 passed(46 文件) | `pytest tests -q`(本地全量,3.45s) |
| 前端测试 | 72 passed / 7 files | `npm run test:coverage`(本地全量,1.98s) |
| 前端覆盖率(utils) | 行 86.82% / 分支 83.56% | vitest v8 provider |
| 前端覆盖率(计入 composables) | 行 29.27% | composables 11 文件全 0% |
| mypy 错误 | 28 errors / 7 files(64 源文件) | `mypy app`(本地,Python 3.14) |
| vue-tsc / 构建 | 0 错误 / 构建通过 | 远端 CI `Frontend Typecheck & Build` success |
| Dependabot 开放告警 | 0 | GitHub Dependabot alerts API 实时查询 |
| Python 规模 | 169 文件 / 21,506 行 | `git ls-files "*.py"` |
| 远端 CI | GitLab `dev-gitlab/main` = 本地 HEAD(0 差异);GitHub 镜像滞后 21 commit(维护者自行同步,非缺陷),其旧 HEAD(0fe3426)5 success + mypy failure | `git fetch dev-gitlab` + GitHub check-runs API |

## 5. 提升路线(下一轮目标 ≥ 88)

1. **mypy 清零并转 blocking**:修复 28 个错误(集中于 engine/validation.py 的 `_check_ref` 参数类型),随后移除 GitHub `continue-on-error` 与 GitLab `|| true`,让类型检查成为强制卡点(类型安全 72 → 90)。
2. **composables 补测**:11 个 0% 覆盖的 composables(useRefGroups/useSqlInsert/useGroupTree 等)按第二批拆分补挂载级测试;后端接入 pytest-cov 并在 services/engine 层建立行覆盖率基线(测试保障 85 → 92)。
3. ~~**GitLab 部署链路补后端测试门禁**~~:已落地——`backend-mypy` 改造为 `backend-check`(mypy 保持 advisory + pytest 全量 blocking,复用依赖安装实测仅 +4s,详见 `.gitlab-ci.yml`);待下次 push 后流水线验证通过,CI/CD 可升至 86+。
4. ~~**消除 CI 漂移**~~:经核实 GitLab `dev-gitlab/main` 与本地 HEAD 一致(0 差异),无漂移;GitHub 镜像滞后由维护者按需自行同步,不作为扣分项。
5. **顺手项**:OpenAPI schema 导出为 API 参考文档补进 docs/(`platform/frontend/coverage/` 已于本轮加入 .gitignore)。

---

## 6. 首轮记录(2026-09-06,综合 84)

**基准提交**:`c9d0e56`(main)。

| 维度 | 得分 | 当时依据摘要 |
|---|---|---|
| 测试保障 | 85 | 后端 734 通过(37 文件),前端 72 通过(7 文件) |
| 类型安全 | 80 | mypy 0 错误(58 源文件),vue-tsc 零错误;CI mypy 为 advisory |
| 依赖安全 | 95 | Dependabot 0;SQLAlchemy 2.0.52 |
| CI/CD | 85 | GitHub 5 job 全绿,GitLab 同步,pre-commit 钩子齐全 |
| 代码质量 | 80 | ruff F 零告警;19,018 行/143 文件分层清晰 |
| 文档完备 | 75 | SYSTEM_DESIGN + CONTEXT + README;缺 API 文档 |

综合 = 85×0.20 + 80×0.15 + 95×0.15 + 85×0.20 + 80×0.20 + 75×0.10 = 83.75 ≈ 84

## 7. 第二轮记录(2026-10-10,架构改进 8 候选)

**基准提交**:`0c17c3c`(dev/main)。八候选分 6 批落地,每批独立 commit + 全量护栏:

| 批 | commit | 内容 |
|---|---|---|
| 1 死代码+术语 | `bb1e94d` | 删 engine/expression.py(327 行)等死代码;preprocessor.py→nested_path.py、row_vars→dataset_row 术语收口;CONTEXT.md 词条重写 |
| 2 性能+契约 | `f92cf2c` | dag_executor 节点/接口缓存预载消除 N+1;DbSink flush 收口;422 折叠;25+ 路由补 response_model;stats 改 SQL 聚合 |
| 3 _execute_node 收深 | `612f855` | _step_event/_extract_and_assert/_assertion_events 样板收口;report_context 公开 iter_body_paths/iter_replay_paths |
| 4 replay 出路由 | `92a99de` | 新建 services/replay_service.py,executions 两路由瘦成 2 行委托 |
| 5 前端 SQL 收敛 | `e1c6b4c` | 新建 useSqlInsert + SqlCell,三处复制的 SQL 插入逻辑收敛 |
| 6 巨型视图拆分 | `0c17c3c` | 新建 useRefGroups/ImportJsonDialog/ReplayDialog/clipboard,DatasetManage 1083→约 880 行、ReportDetail 1390→约 1240 行 |

## 8. 第三轮记录(2026-10-10,按约重评,84 → 83)

**基准提交**:`53ea862`。兑现第二轮"下一轮按新证据取数"的约定,全量重跑证据(见第 4 节)。

| 维度 | 首轮 | 本轮 | 变化原因 |
|---|---|---|---|
| 测试保障 | 85 | 85 | 测试数 734→759,覆盖率首次可量化(加分);但暴露 composables 0% 空洞、后端无 cov 基线(减分),两相抵消 |
| 类型安全 | 80 | **72 ↓** | 八批重构期间 mypy 从 0 回归至 28 错,远端 CI mypy job 飘红未被 advisory 模式拦截 |
| 依赖安全 | 95 | 95 | Dependabot 持续 0 告警 |
| CI/CD | 85 | **82 ↓** | GitLab 部署链路此前缺后端测试门禁(本轮已补 `backend-check`);mypy 双平台无强制卡点;~~21 commit 漂移~~ 经核实为误判——GitLab 与本地同步,GitHub 为镜像滞后正常 |
| 代码质量 | 80 | **85 ↑** | 八批重构落地:死代码清除、N+1 消除、契约补齐、巨型视图拆分,ruff F 零告警 |
| 文档完备 | 75 | **78 ↑** | SYSTEM_DESIGN 巡检同步实况、CONTEXT 重写、OpenAPI 契约自动化 |

**结论**:架构与文档实质改善(+1.3 加权),被类型回归(-1.2)与 CI 门禁缺口(-0.6)抵消,综合 84 → 83。修正记录:初评误将 GitHub 镜像滞后计入 CI 漂移扣分(CI/CD 曾计 80),经维护者澄清并核实 GitLab 同步后撤回,CI/CD 修正为 82,综合 83.25 仍为 83。下一轮优先兑现第 5 节路线 1-3,可回升至 88+。
