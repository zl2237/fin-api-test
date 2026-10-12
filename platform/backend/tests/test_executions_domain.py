"""executions 域函数单测（router 内联 ORM 收敛后的接缝）。

覆盖：
- create_execution：落 running 记录 + created_by 审计
- cleanup_old_records：按截止时间删除旧记录
- list_executions：offset/limit 翻页、case_name 联表模糊、status 过滤的查询管道
- execution_stats（router 内联）：近 N 天聚合口径与除零兜底
"""
from types import SimpleNamespace

from app import models
from app.crud import executions as exec_domain
from app.crud.legacy import count_executions, list_executions
from app.routers.executions import execution_stats


class FakeDb:
    def __init__(self, old_execs=()):
        self._old = list(old_execs)
        self.added = []
        self.deleted = []
        self.committed = 0

    def query(self, *_a, **_kw):
        db = self

        class _Q:
            def filter(self, *a, **kw):
                return self

            def all(self):
                return db._old

        return _Q()

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)

    def commit(self):
        self.committed += 1

    def refresh(self, _obj):
        pass


class TestCreateExecution:
    def test_creates_running_record_with_created_by(self):
        db = FakeDb()
        rec = exec_domain.create_execution(db, case_id=7, env_id=3, user_id=99)
        assert rec.case_id == 7
        assert rec.env_id == 3
        assert rec.status == "running"
        assert rec.created_by == 99
        assert db.added == [rec]
        assert db.committed == 1


class TestCleanupOldRecords:
    def test_deletes_only_old_records(self):
        old1 = SimpleNamespace(id=1)
        old2 = SimpleNamespace(id=2)
        db = FakeDb(old_execs=[old1, old2])
        count = exec_domain.cleanup_old_records(db, cutoff="2020-01-01")
        assert count == 2
        assert db.deleted == [old1, old2]
        assert db.committed == 1


class _ListQ:
    """捕获 list_executions 查询管道的链式 fake：filter/join/offset/limit/all"""

    def __init__(self, db):
        self.db = db

    def filter(self, *a):
        self.db.calls.setdefault("filters", []).append(a)
        return self

    def join(self, *a):
        self.db.calls.setdefault("joins", []).append(a)
        return self

    def order_by(self, *a):
        self.db.calls.setdefault("order_by", []).append(a)
        return self

    def offset(self, v):
        self.db.calls["offset"] = v
        return self

    def limit(self, v):
        self.db.calls["limit"] = v
        return self

    def all(self):
        return self.db.rows

    def count(self):
        self.db.calls["counted"] = True
        return len(self.db.rows)


class ListDb:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.calls = {}

    def query(self, *_a, **_kw):
        return _ListQ(self)


class TestListExecutionsParams:
    def test_offset_limit_passthrough(self):
        db = ListDb(rows=["r1"])
        out = list_executions(db, limit=20, offset=40)
        assert out == ["r1"]
        assert db.calls["offset"] == 40
        assert db.calls["limit"] == 20

    def test_case_name_triggers_join_and_like(self):
        db = ListDb()
        list_executions(db, case_name="运单")
        joins = db.calls.get("joins", [])
        assert len(joins) == 1, "case_name 应联表 TestCase"
        like_clauses = [str(a) for a in db.calls["filters"][0]]
        assert any("name LIKE" in s for s in like_clauses), like_clauses

    def test_no_case_name_no_project_no_join(self):
        db = ListDb()
        list_executions(db, case_id=5)
        assert db.calls.get("joins") in (None, [])

    def test_status_filter_appends_clause(self):
        db_no = ListDb()
        list_executions(db_no, case_id=5)
        db_yes = ListDb()
        list_executions(db_yes, case_id=5, status="success")
        assert len(db_yes.calls["filters"]) == len(db_no.calls["filters"]) + 1
        last = [str(a) for a in db_yes.calls["filters"][-1]]
        assert any("status" in s for s in last), last

    def test_time_range_appends_started_at_clauses(self):
        from datetime import datetime

        start = datetime(2026, 9, 1, 0, 0, 0)
        end = datetime(2026, 9, 2, 23, 59, 59)
        db = ListDb()
        list_executions(db, case_id=5, start_time=start, end_time=end)
        time_clauses = db.calls["filters"][-2:]
        flat = [str(a) for pair in time_clauses for a in pair]
        assert any("started_at" in s and ">=" in s for s in flat), flat
        assert any("started_at" in s and "<=" in s for s in flat), flat

    def test_sort_by_pushes_started_at_desc(self):
        db = ListDb(rows=["r1"])
        list_executions(db, sort_by="started_at", order="desc")
        flat = [str(a) for a in db.calls["order_by"][0]]
        assert any("started_at" in s and "DESC" in s.upper() for s in flat), flat

    def test_sort_asc_and_unknown_field_fallback(self):
        db = ListDb()
        list_executions(db, sort_by="id", order="asc")
        flat = [str(a) for a in db.calls["order_by"][0]]
        assert any("id" in s.lower() and "ASC" in s.upper() for s in flat), flat
        db2 = ListDb()
        list_executions(db2, sort_by="hacked; drop table")  # 白名单外 → 回落 id desc
        flat2 = [str(a) for a in db2.calls["order_by"][0]]
        assert any("id" in s.lower() and "DESC" in s.upper() for s in flat2), flat2


class TestCountExecutions:
    def test_count_same_filters_as_list(self):
        db_list = ListDb()
        db_count = ListDb()
        list_executions(db_list, case_id=5, status="success")
        count_executions(db_count, case_id=5, status="success")
        # 过滤口径一致：filter 子句字符串形式逐条相同（BinaryExpression 不可直接 ==）
        str_filters = lambda db: [[str(a) for a in pair] for pair in db.calls["filters"]]
        assert str_filters(db_count) == str_filters(db_list)
        assert db_count.calls["counted"] is True
        assert "offset" not in db_count.calls and "limit" not in db_count.calls


class StatsDb:
    """execution_stats 查询链 fake：query→filter→[join→filter]→with_entities→group_by→all"""

    def __init__(self, statuses=()):
        self._st = list(statuses)

    def query(self, *_a, **_kw):
        return self

    def filter(self, *a):
        return self

    def join(self, *a):
        return self

    def with_entities(self, *a):
        return self

    def group_by(self, *a):
        return self

    def all(self):
        # 模拟数据库端聚合：[(status, count), ...]
        from collections import Counter
        return list(Counter(self._st).items())


class TestExecutionStats:
    def test_aggregates_count_passed_rate(self):
        out = execution_stats(days=7, db=StatsDb(["success", "success", "failed"]),
                              user=SimpleNamespace())
        assert out["count"] == 3
        assert out["passed"] == 2
        assert out["rate"] == 67

    def test_empty_returns_none_rate(self):
        out = execution_stats(days=7, db=StatsDb([]), user=SimpleNamespace())
        assert out["count"] == 0
        assert out["passed"] == 0
        assert out["rate"] is None


class TouchDb:
    """touch_case_last_exec 的 update 链 fake：query→filter→update"""

    def __init__(self):
        self.updates: list[dict] = []
        self.commits = 0

    def query(self, *_a, **_kw):
        db = self

        class _UQ:
            def filter(self, *_f):
                return self

            def update(self, vals, **_kw):
                db.updates.append(vals)
                return 1

        return _UQ()

    def commit(self):
        self.commits += 1


class TestTouchCaseLastExec:
    def test_terminal_status_writes_started_at_and_status(self):
        from datetime import datetime

        db = TouchDb()
        started = datetime(2026, 10, 12, 16, 0, 0)
        rec = SimpleNamespace(status="failed", case_id=7, started_at=started)
        exec_domain.touch_case_last_exec(db, rec)
        assert db.updates and db.updates[0] == {
            models.TestCase.last_exec_at: started,
            models.TestCase.last_exec_status: "failed",
        }
        assert db.commits == 1

    def test_running_record_is_noop(self):
        db = TouchDb()
        rec = SimpleNamespace(status="running", case_id=7, started_at=None)
        exec_domain.touch_case_last_exec(db, rec)
        assert db.updates == []
        assert db.commits == 0

    def test_db_error_swallowed(self):
        class BoomDb(TouchDb):
            def query(self, *_a, **_kw):
                raise RuntimeError("db down")

        exec_domain.touch_case_last_exec(  # 不得抛出：统计列不在关键路径
            BoomDb(), SimpleNamespace(status="failed", case_id=7, started_at=None))
