"""执行方案单测：validate_plan_items 保存校验 + run_plan 两阶段编排 + chain 串行链驱动。

与 test_execution_launcher 同风格：SimpleNamespace 替身 + monkeypatch，
不碰真库；build/commit 打桩验证透传语义，_run_chain 直调验证链语义。
"""
from types import SimpleNamespace

import pytest

from app.services import plan_executor
from app.services.plan_executor import run_plan, validate_plan_items

# 普通用例替身（各绑环境）
CASE = SimpleNamespace(id=11, name="提单用例", env_id=5)
CASE2 = SimpleNamespace(id=12, name="融资用例", env_id=23)


def _item(**kw):
    base = dict(case_id=11, dataset_id=None, run_count=1, pass_vars=None, sort_order=0)
    base.update(kw)
    return SimpleNamespace(**base)


class TestValidatePlanItems:

    @pytest.fixture
    def stubbed(self, monkeypatch):
        """crud.get_testcase → CASE；validate_binding 打桩（记录调用，dataset_id=999 时抛错）"""
        calls = []

        def fake_binding(db, case, dataset_id):
            calls.append((case.id, dataset_id))
            if dataset_id == 999:
                raise ValueError("数据集不属于该用例（数据集按用例隔离）")

        monkeypatch.setattr(plan_executor.crud, "get_testcase",
                            lambda db, cid: {11: CASE, 12: CASE2}.get(cid))
        monkeypatch.setattr(plan_executor.dataset_service,
                            "validate_binding", fake_binding)
        return SimpleNamespace(calls=calls)

    def test_ok_without_override(self, stubbed):
        """无换绑成员合法，且不触发数据集绑定校验"""
        validate_plan_items(object(), [_item()])
        assert stubbed.calls == []

    def test_case_missing_rejected(self, stubbed):
        with pytest.raises(ValueError, match="用例不存在"):
            validate_plan_items(object(), [_item(case_id=404)])

    def test_dataset_of_other_case_rejected(self, stubbed):
        """换绑数据集不属于成员用例：复用执行面板换绑同口径校验拒绝"""
        with pytest.raises(ValueError, match="不属于该用例"):
            validate_plan_items(object(), [_item(dataset_id=999)])
        assert stubbed.calls == [(11, 999)]

    def test_run_count_out_of_range(self, stubbed):
        with pytest.raises(ValueError, match="执行次数"):
            validate_plan_items(object(), [_item(run_count=0)])
        with pytest.raises(ValueError, match="执行次数"):
            validate_plan_items(object(), [_item(run_count=10000)])
        validate_plan_items(object(), [_item(run_count=9999)])  # 边界合法


DB = lambda: SimpleNamespace(commit=lambda: None)  # db 替身：run_plan 收尾 commit


class TestRunPlan:

    @pytest.fixture
    def stubbed(self, monkeypatch):
        """全发射链路打桩：build 记录 kwargs 返回假 plan，commit 记录 (plans, concurrency)"""
        built, committed = [], []

        def fake_build(db, case, user_id, **kw):
            rec = SimpleNamespace(id=100 + len(built), case_id=case.id)
            built.append({"case_id": case.id, "user_id": user_id, **kw})
            return SimpleNamespace(records=[rec], specs=[SimpleNamespace()])

        def fake_commit(plans, concurrency):
            committed.append((list(plans), concurrency))

        monkeypatch.setattr(plan_executor, "build_launch_plan", fake_build)
        monkeypatch.setattr(plan_executor, "commit_launch", fake_commit)
        return SimpleNamespace(built=built, committed=committed)

    @pytest.fixture
    def plan(self):
        return SimpleNamespace(id=3, mode="combo", concurrency=6, last_run_at=None, items=[
            _item(case_id=11, dataset_id=7, run_count=1, sort_order=0),
            _item(case_id=12, run_count=2, sort_order=1),  # 第二成员 ×2 轮
        ])

    def _stub_env(self, monkeypatch):
        """crud.get_testcase/get_environment 与数据集展开试算打桩（单套语义无行参）"""
        monkeypatch.setattr(plan_executor.crud, "get_testcase",
                            lambda db, cid: {11: CASE, 12: CASE2}.get(cid))
        monkeypatch.setattr(plan_executor.crud, "get_environment",
                            lambda db, eid: SimpleNamespace(id=eid))
        monkeypatch.setattr(plan_executor.dataset_service, "plan_case_expansion",
                            lambda db, case, **kw: [{"dataset_id": 7, "row": None}])

    def test_members_launch_with_override_and_plan_id(self, stubbed, plan, monkeypatch):
        """成员级换绑 + run_count + plan_id/trigger_type 正确透传；concurrency 取方案配置"""
        self._stub_env(monkeypatch)

        records = run_plan(DB(), plan, 22)

        assert [(b["case_id"], b["dataset_id"], b["run_count"]) for b in stubbed.built] \
            == [(11, 7, 1), (12, None, 2)]
        assert all(b["plan_id"] == 3 and b["user_id"] == 22 for b in stubbed.built)
        assert all(b["trigger_type"] == "plan" for b in stubbed.built)
        specs, concurrency = stubbed.committed[0]
        assert concurrency == 6 and len(specs) == 2  # 一次合并提交
        assert len(records) == 2  # 返回平铺记录（假 build 每 plan 1 条）
        assert plan.last_run_at is not None  # 回写最近执行时间

    def test_trigger_type_plan_schedule(self, stubbed, plan, monkeypatch):
        self._stub_env(monkeypatch)
        run_plan(DB(), plan, 22, trigger_type="plan_schedule")
        assert all(b["trigger_type"] == "plan_schedule" for b in stubbed.built)

    def test_empty_plan_rejected(self, stubbed, monkeypatch):
        with pytest.raises(ValueError, match="未配置成员"):
            run_plan(DB(), SimpleNamespace(id=3, mode="combo", concurrency=4,
                                           last_run_at=None, items=[]), 22)
        assert stubbed.built == []  # 零发射

    def test_precheck_failure_zero_records(self, stubbed, plan, monkeypatch):
        """预检（环境/数据集展开试算）失败：零记录零提交，ValueError 上抛"""
        self._stub_env(monkeypatch)

        def boom(db, case, **kw):
            raise ValueError("数据集无数据行，请先在数据集页完成入参配置")

        monkeypatch.setattr(plan_executor.dataset_service, "plan_case_expansion", boom)
        with pytest.raises(ValueError, match="无数据行"):
            run_plan(DB(), plan, 22)
        assert stubbed.built == [] and stubbed.committed == []

    def test_precheck_env_missing(self, stubbed, plan, monkeypatch):
        """成员绑定环境已删：预检即拒（不进 build）"""
        monkeypatch.setattr(plan_executor.crud, "get_testcase",
                            lambda db, cid: {11: CASE, 12: CASE2}.get(cid))
        monkeypatch.setattr(plan_executor.crud, "get_environment", lambda db, eid: None)
        with pytest.raises(ValueError, match="环境已不存在"):
            run_plan(DB(), plan, 22)
        assert stubbed.built == []

    def test_member_case_deleted_precheck_rejects(self, stubbed, plan, monkeypatch):
        monkeypatch.setattr(plan_executor.crud, "get_testcase", lambda db, cid: None)
        with pytest.raises(ValueError, match="已不存在"):
            run_plan(DB(), plan, 22)
        assert stubbed.built == []


class TestLaunchChain:
    """chain 建记录编排：轮主序预建 rounds×成员 + rounds×成员 上限 + 驱动提交。"""

    @pytest.fixture
    def chain_plan(self):
        return SimpleNamespace(id=7, mode="chain", rounds=2, concurrency=3,
                               last_run_at=None, items=[
            _item(case_id=11, sort_order=0),
            _item(case_id=12, sort_order=1),
        ])

    def _stub(self, monkeypatch, chain_plan):
        """环境/展开/建记录/提交全打桩；返回捕获容器"""
        created, submitted = [], []
        monkeypatch.setattr(plan_executor.crud, "get_testcase",
                            lambda db, cid: {11: CASE, 12: CASE2}.get(cid))
        monkeypatch.setattr(plan_executor.crud, "get_environment",
                            lambda db, eid: SimpleNamespace(id=eid))
        monkeypatch.setattr(plan_executor.dataset_service, "plan_case_expansion",
                            lambda db, case, **kw: [{"dataset_id": 7, "row": {"data": {"k": case.id}}}])
        import app.crud.executions as exec_domain
        seq = iter(range(500, 600))

        def fake_create(db, **kw):
            rec = SimpleNamespace(id=next(seq), **kw)
            created.append(rec)
            return rec

        monkeypatch.setattr(exec_domain, "create_execution", fake_create)
        monkeypatch.setattr(plan_executor.crud, "fill_audit_names", lambda db, rec: None)
        monkeypatch.setattr(plan_executor.crud, "fill_exec_names", lambda db, rec: None)

        def fake_submit(plan, rounds, members):
            submitted.append({"rounds": rounds, "members": [
                {k: m[k] for k in ("case_id", "env_id", "pass_vars")}
                | {"record_ids": list(m["record_ids"]), "n_expansion": len(m["expansion"])}
                for m in members]})

        monkeypatch.setattr(plan_executor, "_submit_chain", fake_submit)
        return created, submitted

    def test_round_major_records_and_submit(self, chain_plan, monkeypatch):
        """2 轮×2 成员=4 条记录，轮主序（第 1 轮全员→第 2 轮全员），驱动收纯数据"""
        created, submitted = self._stub(monkeypatch, chain_plan)
        records = run_plan(DB(), chain_plan, 22)
        assert [r.case_id for r in records] == [11, 12, 11, 12]  # 轮主序
        assert all(r.plan_id == 7 and r.trigger_type == "plan" for r in records)
        sub = submitted[0]
        assert sub["rounds"] == 2
        assert [m["case_id"] for m in sub["members"]] == [11, 12]
        assert all(m["record_ids"] and m["n_expansion"] == 1 for m in sub["members"])
        assert chain_plan.last_run_at is not None

    def test_rounds_cap_rejected(self, chain_plan, monkeypatch):
        """整链轮数×成员数超上限：预建零记录、ValueError 上抛"""
        created, submitted = self._stub(monkeypatch, chain_plan)
        chain_plan.rounds = 9999  # 9999×2 > MAX_RUN_COUNT
        with pytest.raises(ValueError, match="整链轮数×成员数超过"):
            run_plan(DB(), chain_plan, 22)
        assert created == [] and submitted == []


class TestPlanChain:
    """chain 串行链（依赖/传参的组织方式）+ 批量策略正交：
    轮内按序串行 + 成员级 pass_vars 相邻定向传参 + 上游失败阻断本轮下游；
    轮间按 rounds×concurrency 并行，轮与轮互不影响。"""

    @staticmethod
    def _record(rid):
        return SimpleNamespace(id=rid, status="running", summary={},
                               case_id=None, ended_at=None)

    @staticmethod
    def _registry(vars_):
        return SimpleNamespace(to_dict=lambda: {"n1": vars_})

    def _run(self, monkeypatch, members_spec, rounds=1, concurrency=1):
        """members_spec: (case, env, pass_vars, rows, [per-round 行为], [record 按轮序])
        → 驱动并返回 (injects, dataset_rows)：按执行器构造序记录。"""
        return self._drive(monkeypatch, members_spec, rounds, concurrency)

    def _drive(self, monkeypatch, members_spec, rounds=1, concurrency=1):
        records: dict = {}
        injects: list = []
        dataset_rows: list = []

        class FakeExecutor:
            def __init__(self, db, case, env, execution_record=None, dataset_row=None,
                         prev_vars=None, **kw):
                self.record = execution_record
                self.context = SimpleNamespace(registry=TestPlanChain._registry({}))
                injects.append(prev_vars)
                dataset_rows.append(dataset_row)
                self._spec = next(m for m in members_spec if m[0].id == case.id)

            def execute(self):
                beh = self._spec[4].pop(0)
                self.record.status = beh["status"]
                if beh.get("vars"):
                    self.context = SimpleNamespace(
                        registry=TestPlanChain._registry(beh["vars"]))

        import app.engine.dag_executor as de
        monkeypatch.setattr(de, "DagExecutor", FakeExecutor)
        import app.crud.executions as exec_domain
        monkeypatch.setattr(exec_domain, "touch_case_last_exec", lambda db, rec: None)

        class FakeQuery:
            def get(self, rid):
                return records.get(rid)

        db = SimpleNamespace(query=lambda m: FakeQuery(), refresh=lambda o: None,
                             commit=lambda: None, close=lambda: None)
        case_map = {m[0].id: m[0] for m in members_spec}
        env_map = {m[1].env_id: m[1] for m in members_spec}
        monkeypatch.setattr(plan_executor.crud, "get_testcase",
                            lambda d, cid: case_map.get(cid))
        monkeypatch.setattr(plan_executor.crud, "get_environment",
                            lambda d, eid: env_map.get(eid))
        # members_spec: (case, env, pass_vars, rows, [行为...], [record...按轮序])
        members = []
        for m in members_spec:
            case, env, pass_vars, rows, behs, recs = m
            for r in recs:
                records[r.id] = r
            members.append({"case_id": case.id, "env_id": env.env_id,
                            "pass_vars": pass_vars, "rows": rows,
                            "record_ids": [r.id for r in recs]})
        plan_executor._run_chain(lambda: db, {
            "plan_id": 1, "rounds": rounds, "concurrency": concurrency,
            "members": members})
        return injects, dataset_rows

    def _run(self, monkeypatch, members_spec, rounds=1, concurrency=1):
        return self._drive(monkeypatch, members_spec, rounds, concurrency)

    def test_adjacent_pass_vars_whitelist(self, monkeypatch):
        """上一棒成功：按其 pass_vars 名单注入下一棒；名单外变量不外泄"""
        c1 = SimpleNamespace(id=11, env_id=5)
        c2 = SimpleNamespace(id=12, env_id=23)
        r1, r2 = self._record(101), self._record(102)
        injects, _ = self._run(monkeypatch, [
            (c1, SimpleNamespace(env_id=5), ["bl_no"], [{"bl_no": "BL1"}],
             [{"status": "success", "vars": {"bl_no": "BL9", "order_id": 7}}], [r1]),
            (c2, SimpleNamespace(env_id=23), [], [{}],
             [{"status": "success"}], [r2]),
        ])
        assert r1.status == "success" and r2.status == "success"
        assert injects == [None, {"bl_no": "BL9"}]  # 首棒无注入；下一棒只拿名单内变量

    def test_empty_pass_vars_snapshot_allows_downstream(self, monkeypatch):
        """pass_vars 空名单：上一棒成功快照为空 dict（非 None），下一棒照常执行"""
        c1 = SimpleNamespace(id=11, env_id=5)
        c2 = SimpleNamespace(id=12, env_id=23)
        r1, r2 = self._record(101), self._record(102)
        injects, _ = self._run(monkeypatch, [
            (c1, SimpleNamespace(env_id=5), [], [{}],
             [{"status": "success", "vars": {"x": 1}}], [r1]),
            (c2, SimpleNamespace(env_id=23), [], [{}],
             [{"status": "success"}], [r2]),
        ])
        assert r1.status == "success" and r2.status == "success"
        assert injects == [None, {}]  # 空快照注入 ≠ 失败阻断

    def test_per_edge_different_vars(self, monkeypatch):
        """相邻定向：棒1→棒2 传 a，棒2→棒3 传 b（各边名单独立）"""
        c1 = SimpleNamespace(id=11, env_id=5)
        c2 = SimpleNamespace(id=12, env_id=23)
        c3 = SimpleNamespace(id=13, env_id=9)
        r1, r2, r3 = self._record(101), self._record(102), self._record(103)
        injects, _ = self._run(monkeypatch, [
            (c1, SimpleNamespace(env_id=5), ["a"], [{}],
             [{"status": "success", "vars": {"a": 1, "x": "丢弃"}}], [r1]),
            (c2, SimpleNamespace(env_id=23), ["b"], [{}],
             [{"status": "success", "vars": {"b": 2, "a": "不透传"}}], [r2]),
            (c3, SimpleNamespace(env_id=9), [], [{}],
             [{"status": "success"}], [r3]),
        ])
        assert injects == [None, {"a": 1}, {"b": 2}]

    def test_upstream_failure_blocks_round_downstream(self, monkeypatch):
        """上游失败：本轮下游预建记录置 failed 并注明阻断（执行器不构造）"""
        c1 = SimpleNamespace(id=11, env_id=5)
        c2 = SimpleNamespace(id=12, env_id=23)
        r1, r2 = self._record(101), self._record(102)
        injects, _ = self._run(monkeypatch, [
            (c1, SimpleNamespace(env_id=5), ["bl_no"], [{}],
             [{"status": "failed"}], [r1]),
            (c2, SimpleNamespace(env_id=23), [], [{}],
             [{"status": "success"}], [r2]),  # 不应被执行
        ])
        assert r1.status == "failed"
        assert r2.status == "failed" and "本轮阻断" in r2.summary["error"]
        assert len(injects) == 1  # 下游未实例化执行器

    def test_terminated_record_skipped(self, monkeypatch):
        """记录已被手动终止（级联置 terminated）：保留终态不再执行"""
        c1 = SimpleNamespace(id=11, env_id=5)
        r1 = self._record(101)
        r1.status = "terminated"
        injects, _ = self._run(monkeypatch, [
            (c1, SimpleNamespace(env_id=5), ["bl_no"], [{}],
             [{"status": "success"}], [r1]),
        ])
        assert r1.status == "terminated"
        assert injects == []

    def test_rounds_independent_and_row_pickup(self, monkeypatch):
        """多轮正交批量：第 1 轮上游失败只阻断第 1 轮下游，第 2 轮照常；
        各轮按 round 索引取数据集行（超出沿用最后一套）"""
        c1 = SimpleNamespace(id=11, env_id=5)
        c2 = SimpleNamespace(id=12, env_id=23)
        r1a, r1b = self._record(101), self._record(102)  # 第 1 轮（上游失败）
        r2a, r2b = self._record(103), self._record(104)  # 第 2 轮（全成功）
        rows = [{"bl_no": "A"}, {"bl_no": "B"}]
        injects, dataset_rows = self._run(monkeypatch, [
            (c1, SimpleNamespace(env_id=5), ["bl_no"], rows,
             [{"status": "failed"}, {"status": "success", "vars": {"bl_no": "B2"}}],
             [r1a, r2a]),
            (c2, SimpleNamespace(env_id=23), [], rows,
             [{"status": "success"}, {"status": "success"}],
             [r1b, r2b]),
        ], rounds=2, concurrency=1)
        assert r1a.status == "failed"
        assert r1b.status == "failed" and "本轮阻断" in r1b.summary["error"]
        assert r2a.status == "success" and r2b.status == "success"
        # 构造序：轮0首棒、轮1首棒（无注入）、轮1次棒（拿轮1首棒快照）；轮0次棒被阻断未构造
        assert injects == [None, None, {"bl_no": "B2"}]
        assert dataset_rows == [{"bl_no": "A"}, {"bl_no": "B"}, {"bl_no": "B"}]  # 按轮取行

    def test_rounds_overflow_reuses_last_row(self, monkeypatch):
        """轮数超出数据集行数：沿用最后一套值"""
        c1 = SimpleNamespace(id=11, env_id=5)
        r1, r2, r3 = self._record(101), self._record(102), self._record(103)
        _, dataset_rows = self._run(monkeypatch, [
            (c1, SimpleNamespace(env_id=5), [], [{"bl_no": "A"}, {"bl_no": "B"}],
             [{"status": "success"}] * 3, [r1, r2, r3]),
        ], rounds=3)
        assert dataset_rows == [{"bl_no": "A"}, {"bl_no": "B"}, {"bl_no": "B"}]

    def test_parallel_rounds_both_complete(self, monkeypatch):
        """轮间并行路径（concurrency=2）：各轮独立跑完"""
        c1 = SimpleNamespace(id=11, env_id=5)
        r1, r2 = self._record(101), self._record(102)
        self._run(monkeypatch, [
            (c1, SimpleNamespace(env_id=5), [], [{}],
             [{"status": "success"}, {"status": "success"}], [r1, r2]),
        ], rounds=2, concurrency=2)
        assert r1.status == "success" and r2.status == "success"
