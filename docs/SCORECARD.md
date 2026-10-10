# 工程质量评分卡

> **文档版本**:v1.2
> **评分日期**:2026-10-10
> **基准提交**:`07b4cf3`(main,GitLab 流水线 #126)
> **评分对象**:fin-api-test 全仓库(测试平台前后端 + 根目录五层用例工程)
> **维护说明**:每次质量专项改进后追加一轮记录,评分依据须为可验证的客观证据(CI 结果、测试计数、扫描报告)。

---

## 1. 综合得分

**90 / 100**(百分制六维加权)

```
综合分 = Σ(维度得分 × 维度权重)
       = 93×0.20 + 90×0.15 + 95×0.15 + 90×0.20 + 85×0.20 + 88×0.10
       = 90.15 ≈ 90
```

## 2. 评分雷达图

![工程质量评分雷达图](scorecard_radar.svg)

## 3. 六维评分明细

| 维度 | 权重 | 得分 | 加权分 | 评分依据 |
|---|---|---|---|---|
| 测试保障 | 20% | 93 | 18.6 | 后端 pytest 759 通过 + pytest-cov 基线建立(总体行覆盖 62%,engine 核心 76-100%);前端 vitest 137 通过(72→137,补齐 11 个零覆盖文件),统计范围行覆盖 29.3%→97.7%(composables 98.5%);双平台 CI 均执行测试并输出覆盖率。遗留:routers/legacy CRUD 覆盖 0-31%,为下一轮空间 |
| 类型安全 | 15% | 90 | 13.5 | mypy 0 错误(64 源文件,28 错清零)且**双平台转 blocking**(GitHub 移除 `continue-on-error`、GitLab 去掉 `\|\| true`),类型回归从此被 CI 拦截;vue-tsc --noEmit 零错误。未到 95+:Basic 档(非 strict) |
| 依赖安全 | 15% | 95 | 14.25 | GitHub Dependabot 开放告警 0;SQLAlchemy 2.0.52;关键依赖全部钉版本 |
| CI/CD | 20% | 90 | 18.0 | GitLab `backend-check`(mypy blocking + pytest 全量 blocking + 覆盖率)上线并经**流水线 #126 实测 success(500s)**,部署从此被 759 条测试与类型检查双门禁守护;原子部署 + 企微通知保留;GitHub 5 门禁 + Dependabot(镜像侧,mypy 同步转 blocking)。遗留:GitHub 镜像因网络未同步(维护者自管,非缺陷) |
| 代码质量 | 20% | 85 | 17.0 | 八候选重构 6 批落地(死代码/N+1/契约/巨型视图拆分);ruff(pyflakes F)零告警;169 文件/21,506 行分层一致 |
| 文档完备 | 10% | 88 | 8.8 | **API.md**(16 路由模块 ~100 端点速查)与 **DEPLOYMENT.md**(拓扑/CI 变量/原子部署/运维/故障排查/回滚)补齐;OpenAPI 契约自动化(gen:api → api.gen.ts);SYSTEM_DESIGN/CONTEXT 经巡检与代码同步。遗留:无用户使用手册 |

## 4. 证据快照(2026-10-10,`07b4cf3`)

| 指标 | 数值 | 来源 |
|---|---|---|
| 后端测试 | 759 passed(46 文件)+ 行覆盖 62% | `pytest tests -q --cov=app`(本地)+ GitLab `backend-check` |
| 前端测试 | 137 passed / 18 files(72→137) | `npm run test:coverage` |
| 前端覆盖率(统计范围) | 行 97.69% / 语句 94.84% | vitest v8 provider(utils + composables) |
| 前端 composables 覆盖 | 行 98.51%(原 11 文件全 0%) | vitest v8 provider |
| mypy 错误 | 0(64 源文件,上轮 28) | `mypy app` 本地 + 双平台 CI blocking |
| vue-tsc / 构建 | 0 错误 / 8.5s 构建成功 | `npm run build`(含 vue-tsc -b) |
| GitLab 流水线 #126 | backend-lint 12s ✓,**backend-check 500s ✓**(新门禁首验),frontend/deploy 串行执行中 | gitlab-rails 实查 |
| Dependabot 开放告警 | 0 | GitHub Dependabot alerts API |
| Python 规模 | 169 文件 / 21,506 行 | `git ls-files "*.py"` |

## 5. 提升路线(下一轮目标 ≥ 93)

1. **后端覆盖薄弱区补测**:`crud/legacy.py`(31%)、`routers/*`(0-19%)、`services/replay_service.py`(15%)、`engine/runner.py`(20%)——routers 多为薄委托,补 API 级测试即可显著拉升(测试保障 93 → 96)。
2. **mypy 升 strict 档**:对 engine/ 新代码启用 `disallow_untyped_defs`,渐进收紧(类型安全 90 → 94)。
3. **覆盖率门禁阈值**:基线稳定后(62%/97.7%)加 `--cov-fail-under` 硬阈值防回退(CI/CD 90 → 92)。
4. **用户使用手册**:面向测试工程师的用例编排/执行/报告操作指引(文档完备 88 → 92)。

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

## 7. 第二轮记录(2026-10-10 上午,架构改进 8 候选)

**基准提交**:`0c17c3c`(dev/main)。八候选分 6 批落地(死代码/术语收口、DAG N+1 消除与 25+ 路由契约、_execute_node 收深、replay 出路由、前端 SQL 收敛、巨型视图拆分),每批独立 commit + 全量护栏;另含 53ea862 文档巡检同步。

## 8. 第三轮记录(2026-10-10,按约重评,84 → 83)

**基准提交**:`53ea862`。八批重构期间 mypy 从 0 回归至 28 错(advisory 漏网),类型安全 80→72;CI/CD 85→82(含漂移误判后修正为 82);代码质量 80→85、文档完备 75→78。综合 83。

## 9. 第四轮记录(2026-10-10,提升路线全量兑现,83 → 90)

**基准提交**:`07b4cf3`(dev 5 个质量提交 ff 至 main,GitLab 流水线 #126)。五个提交:

| commit | 内容 |
|---|---|
| `4e7ace6` | fix(backend):清零 28 个 mypy 错误(非收窄三元/可空 FK 守卫/重复注解,行为保持,759 测试全过) |
| (test) | test(frontend):11 个零覆盖文件补测 72→137,统计范围行覆盖 29.3%→97.7%(jsdom 无 localStorage,测试内 stubGlobal 内存实现) |
| (ci) | ci:mypy 双平台转 blocking;pytest 挂入 GitLab backend-check 复用依赖安装(fake-db 759 条对 job 增量极小);双平台接入 --cov;.coveragerc 入库(修复 .coverage* 误伤) |
| (docs) | docs:API.md + DEPLOYMENT.md 补齐 |
| `07b4cf3` | docs(scorecard):第三轮漂移误扣修正 |

| 维度 | 三轮 | 本轮 | 变化原因 |
|---|---|---|---|
| 测试保障 | 85 | **93 ↑** | 前端 11 个零覆盖文件补齐 + 双端覆盖率基线量化(62% / 97.7%)并接入 CI |
| 类型安全 | 72 | **90 ↑** | 28 错清零 + 双平台 blocking(路线预估 90 达成) |
| 依赖安全 | 95 | 95 | 无依赖变更,告警持续 0 |
| CI/CD | 82 | **90 ↑** | backend-check 部署门禁上线并经 #126 实测 success;"未经流水线验证"项关闭 |
| 代码质量 | 85 | 85 | 本轮无架构变更(mypy 修复计入类型安全维) |
| 文档完备 | 78 | **88 ↑** | API 参考 + 部署运维手册补齐,OpenAPI 契约自动化在列 |

**结论**:第三轮暴露的全部短板(覆盖率空洞/类型回归/门禁缺失/文档缺口)一轮兑现,综合 83 → 90.15 ≈ 90,越过 ≥ 88 目标。剩余提升空间集中在后端薄弱区覆盖与 strict 档收紧(见第 5 节)。
