"""suite_executor 单测：套件链串行驱动语义（测试套件周期）。

设计定案的关键行为逐条覆盖：
- 白名单快照注入：上游结束按名单快照，下游以 suite_vars 最高优先级注入
- 逐行配对：上游 N 行 → 下游第 i 次执行注入第 i 行快照，超出沿用最后有效快照
- 阻断：上游某行失败 → 下游对应行 blocked（不建执行记录）；上游整体失败 → 后续成员整体 blocked
- 嵌套校验 / 悬空引用 / 无成员兜底 / 成员记录回链套件主记录 / 通知抑制与套件级汇总
"""
from types import SimpleNamespace

import pytest

from app.services import suite_executor as se


def make_member(sort, case_id, env_id):
    return SimpleNamespace(id=sort, sort_order=sort, member_case_id=case_id, env_id=env_id)


class FakeQuery:
    def __init__(self, items):
        self._items = items

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def all(self):
        return self._items


class FakeDB:
    def __init__(self, members):
        self._members = members

    def query(self, model):
        return FakeQuery(self._members)

    def commit(self):
        pass

    def refresh(self, obj):
        pass


def make_record():
    return SimpleNamespace(id=999, status="running", env_id=None, summary={},
                           started_at=None, ended_at=None, created_by=5,
                           trigger_type="manual")


@pytest.fixture
def harness(monkeypatch):
    """桩掉 suite_executor 的全部外部依赖：crud / 数据集展开 / 执行记录 / DagExecutor / 通知"""
    cases = {
        11: SimpleNamespace(id=11, name="融资数据", case_type="normal"),
        33: SimpleNamespace(id=33, name="发起融资", case_type="normal"),
    }
    envs = {
        22: SimpleNamespace(id=22, name="物流环境"),
        44: SimpleNamespace(id=44, name="亿海融环境"),
    }
    created = []

    def fake_create(db, case_id, env_id, user_id=None, trigger_type=None,
                    dataset_id=None, dataset_row=None):
        rec = SimpleNamespace(id=100 + len(created), case_id=case_id, env_id=env_id,
                              status="running", summary={}, suite_execution_id=None,
                              started_at=None, ended_at=None)
        created.append(rec)
        return rec

    class FakeExecutor:
        """按脚本顺序产出 (status, extracted)；捕获构造入参供断言"""
        script: list = []
        instances: list = []

        def __init__(self, db, case, env, execution_record=None, row_vars=None,
                     row_origins=None, node_config_overrides=None, suite_vars=None,
                     suppress_notify=False):
            self.case, self.env, self.record = case, env, execution_record
            self.suite_vars = suite_vars
            self.suppress_notify = suppress_notify
            self.context = SimpleNamespace(extracted={})
            FakeExecutor.instances.append(self)

        def execute(self):
            status, extracted = FakeExecutor.script.pop(0)
            self.record.status = status
            self.context.extracted = dict(extracted)

    notif = []
    plans = {}

    monkeypatch.setattr(se, "DagExecutor", FakeExecutor)
    monkeypatch.setattr(se, "crud", SimpleNamespace(
        get_testcase=lambda db, cid: cases.get(cid),
        get_environment=lambda db, eid: envs.get(eid)))
    monkeypatch.setattr(se, "exec_domain", SimpleNamespace(create_execution=fake_create))
    monkeypatch.setattr(se, "send_suite_notify", lambda *a, **k: notif.append(a))
    monkeypatch.setattr(se, "dataset_service", SimpleNamespace(
        plan_case_expansion=lambda db, case, **kw: plans[case.id]))
    return SimpleNamespace(cases=cases, envs=envs, created=created,
                           FakeExecutor=FakeExecutor, notif=notif, plans=plans)


def _plain_plan():
    return [{"dataset_id": None, "row": None, "origins": None, "overrides": None}]


def _row_plan(*rows):
    """rows: (row_index, data) 序列 → 数据驱动展开项"""
    return [{"dataset_id": 7, "row": {"row_index": idx, "data": data, "label": ""},
             "origins": None, "overrides": None} for idx, data in rows]


class TestSnapshotVars:
    def test_whitelist_filters_pool(self):
        """只保留名单内且在池中的变量（名单外不外泄，池中缺失不报错）"""
        assert se._snapshot_vars(["bl_no", "absent"], {"bl_no": "BL1", "seq_no": "S9"}) == {"bl_no": "BL1"}

    def test_empty_whitelist_snapshots_nothing(self):
        assert se._snapshot_vars(None, {"bl_no": "BL1"}) == {}


class TestRunSuite:

    def test_no_members(self, harness):
        """无成员：直接 failed + 引导文案，不建任何成员记录"""
        record = make_record()
        se.run_suite(FakeDB([]), SimpleNamespace(id=77, shared_vars=None), record)

        assert record.status == "failed"
        assert "未配置成员" in record.summary["error"]
        assert harness.created == []
        assert harness.notif == []

    def test_two_members_shared_var_inject(self, harness):
        """跨系统两成员：白名单快照注入下游、成员通知抑制、记录回链、环境对齐、汇总通知"""
        harness.plans.update({11: _plain_plan(), 33: _plain_plan()})
        harness.FakeExecutor.script = [
            ("success", {"bl_no": "BL001", "seq_no": "S9"}),  # 上游：名单外的 seq_no 不外泄
            ("success", {"bl_no": "BL002"}),
        ]
        record = make_record()
        suite = SimpleNamespace(id=77, shared_vars=["bl_no"])
        se.run_suite(FakeDB([make_member(0, 11, 22), make_member(1, 33, 44)]), suite, record)

        assert record.status == "success"
        assert record.env_id == 22  # 主记录环境对齐首成员
        assert harness.FakeExecutor.instances[0].suite_vars is None  # 首成员无上游注入
        assert harness.FakeExecutor.instances[1].suite_vars == {"bl_no": "BL001"}
        assert all(i.suppress_notify for i in harness.FakeExecutor.instances)
        assert all(r.suite_execution_id == record.id for r in harness.created)
        s = record.summary
        assert s["suite"] is True and s["total"] == 2 and s["passed"] == 2
        assert s["shared_vars"] == {"bl_no": "BL002"}  # 终值=最后一个有效快照
        assert len(harness.notif) == 1  # 套件级一条汇总通知

    def test_row_pairing_and_carry_over(self, harness):
        """逐行配对：上游 2 行 → 下游 3 行（第 3 行沿用最后有效快照）"""
        harness.plans.update({
            11: _row_plan((1, {"x": 1}), (2, {"x": 2})),
            33: _row_plan((1, {}), (2, {}), (3, {})),
        })
        harness.FakeExecutor.script = [
            ("success", {"bl_no": "BL1"}), ("success", {"bl_no": "BL2"}),
            ("success", {}), ("success", {}), ("success", {}),
        ]
        record = make_record()
        se.run_suite(FakeDB([make_member(0, 11, 22), make_member(1, 33, 44)]),
                     SimpleNamespace(id=77, shared_vars=["bl_no"]), record)

        injects = [i.suite_vars for i in harness.FakeExecutor.instances[2:]]
        assert injects == [{"bl_no": "BL1"}, {"bl_no": "BL2"}, {"bl_no": "BL2"}]
        assert record.status == "success"

    def test_upstream_row_failure_blocks_paired_downstream_row(self, harness):
        """上游行失败：下游仅对应行阻断（不建记录），其余行照常执行"""
        harness.plans.update({
            11: _row_plan((1, {}), (2, {})),
            33: _row_plan((1, {}), (2, {})),
        })
        harness.FakeExecutor.script = [
            ("success", {"bl_no": "BL1"}), ("failed", {}),
            ("success", {}),  # 下游仅第 1 行真正执行
        ]
        record = make_record()
        se.run_suite(FakeDB([make_member(0, 11, 22), make_member(1, 33, 44)]),
                     SimpleNamespace(id=77, shared_vars=["bl_no"]), record)

        assert len(harness.created) == 3  # 上游 2 条 + 下游 1 条（阻断行不建记录）
        downstream = record.summary["members"][1]
        assert downstream["status"] == "failed"  # 1 成功 + 1 阻断 → 成员整体 failed
        assert [r["status"] for r in downstream["rows"]] == ["success", "blocked"]
        assert "execution_id" not in downstream["rows"][1]
        assert record.status == "failed"
        # 成员计数口径：两成员都含非成功行 → 各计 1 个 failed（行级明细见 members[].rows）
        assert record.summary["failed"] == 2 and record.summary["passed"] == 0

    def test_upstream_total_failure_blocks_following_members(self, harness):
        """上游整体失败：后续成员整体 blocked，不建任何执行记录"""
        harness.plans.update({11: _plain_plan(), 33: _plain_plan()})
        harness.FakeExecutor.script = [("failed", {})]
        record = make_record()
        se.run_suite(FakeDB([make_member(0, 11, 22), make_member(1, 33, 44)]),
                     SimpleNamespace(id=77, shared_vars=["bl_no"]), record)

        assert len(harness.created) == 1  # 仅上游那条
        downstream = record.summary["members"][1]
        assert downstream["status"] == "blocked"
        assert downstream["rows"] == []
        assert record.summary["blocked"] == 1 and record.summary["failed"] == 1
        assert record.status == "failed"

    def test_nested_suite_member_rejected(self, harness):
        """成员是套件：拒绝嵌套，链在此阻断"""
        harness.cases[55] = SimpleNamespace(id=55, name="嵌套套件", case_type="suite")
        harness.plans.update({11: _plain_plan()})
        harness.FakeExecutor.script = [("success", {"bl_no": "BL1"})]
        record = make_record()
        se.run_suite(FakeDB([make_member(0, 11, 22), make_member(1, 55, 44)]),
                     SimpleNamespace(id=77, shared_vars=["bl_no"]), record)

        downstream = record.summary["members"][1]
        assert downstream["status"] == "failed"
        assert "嵌套" in downstream["error"]
        assert record.status == "failed"

    def test_dangling_member_reference(self, harness):
        """成员用例已被删除：该成员 failed，后续成员阻断"""
        harness.plans.update({11: _plain_plan()})
        harness.FakeExecutor.script = [("success", {"bl_no": "BL1"})]
        record = make_record()
        se.run_suite(FakeDB([make_member(0, 11, 22), make_member(1, 999, 44)]),
                     SimpleNamespace(id=77, shared_vars=["bl_no"]), record)

        downstream = record.summary["members"][1]
        assert downstream["status"] == "failed"
        assert "不存在" in downstream["error"]
        assert record.status == "failed"
