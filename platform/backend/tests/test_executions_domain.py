"""executions 域函数单测（router 内联 ORM 收敛后的接缝）。

覆盖：
- create_execution：落 running 记录 + created_by 审计
- cleanup_old_records：按截止时间删除旧记录
"""
from types import SimpleNamespace

from app.crud import executions as exec_domain


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
