"""auth 域函数单测（router 内联 ORM 收敛后的接缝）。

已知事实独立复述自 auth.py 路由现行为：
- 锁定账号登录 → 403 提示剩余分钟
- 连续失败 5 次 → 锁定 15 分钟并 403
- 用户名或密码错误 → 401
- 登录成功 → 清零 failed_count / locked_until
- 注册：重名 400；首个用户 admin，其余 member
- 改密：与当前密码相同 400；成功清除 must_change_password
- 头像：非法格式 400；超过 200KB 400
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.auth import hash_password
from app.crud import auth as auth_domain

PWD = "abc12345"


class FakeDb:
    def __init__(self, first_results=(), count=0):
        self._queue = list(first_results)
        self._count = count
        self.added = []
        self.committed = 0

    def query(self, *_a, **_kw):
        db = self

        class _Q:
            def filter(self, *a, **kw):
                return self

            def first(self):
                return db._queue.pop(0) if db._queue else None

            def count(self):
                return db._count

        return _Q()

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed += 1

    def refresh(self, _obj):
        pass


def _user(**over):
    base = dict(id=1, username="u1", password_hash=hash_password(PWD),
                role="member", failed_count=0, locked_until=None,
                must_change_password=False, avatar=None, name="U1")
    base.update(over)
    return SimpleNamespace(**base)


class TestAuthenticateUser:
    def test_locked_account_raises_403_with_remaining_minutes(self):
        u = _user(locked_until=datetime.now() + timedelta(minutes=10))
        db = FakeDb(first_results=[u])
        with pytest.raises(HTTPException) as e:
            auth_domain.authenticate_user(db, "u1", PWD)
        assert e.value.status_code == 403
        assert "锁定" in e.value.detail

    def test_wrong_password_401_and_increments_fail_count(self):
        u = _user(failed_count=2)
        db = FakeDb(first_results=[u])
        with pytest.raises(HTTPException) as e:
            auth_domain.authenticate_user(db, "u1", "wrong-password")
        assert e.value.status_code == 401
        assert u.failed_count == 3

    def test_fifth_failure_locks_account(self):
        u = _user(failed_count=4)
        db = FakeDb(first_results=[u])
        with pytest.raises(HTTPException) as e:
            auth_domain.authenticate_user(db, "u1", "wrong-password")
        assert e.value.status_code == 403
        assert u.locked_until is not None and u.locked_until > datetime.now()

    def test_unknown_user_401_without_commit(self):
        db = FakeDb(first_results=[None])
        with pytest.raises(HTTPException) as e:
            auth_domain.authenticate_user(db, "ghost", PWD)
        assert e.value.status_code == 401

    def test_success_resets_counters(self):
        u = _user(failed_count=3, locked_until=datetime.now() - timedelta(minutes=1))
        db = FakeDb(first_results=[u])
        got = auth_domain.authenticate_user(db, "u1", PWD)
        assert got is u
        assert u.failed_count == 0 and u.locked_until is None


class TestRegisterUser:
    def test_duplicate_username_400(self):
        db = FakeDb(first_results=[_user()])
        req = SimpleNamespace(username="u1", password=PWD, name=None)
        with pytest.raises(HTTPException) as e:
            auth_domain.register_user(db, req)
        assert e.value.status_code == 400

    def test_first_user_becomes_admin(self):
        db = FakeDb(first_results=[None], count=0)
        req = SimpleNamespace(username="root", password=PWD, name=None)
        u = auth_domain.register_user(db, req)
        assert u.role == "admin"

    def test_later_user_becomes_member(self):
        db = FakeDb(first_results=[None], count=3)
        req = SimpleNamespace(username="u2", password=PWD, name=None)
        u = auth_domain.register_user(db, req)
        assert u.role == "member"


class TestChangePassword:
    def test_same_as_current_400(self):
        u = _user()
        with pytest.raises(HTTPException) as e:
            auth_domain.change_password(FakeDb(), u, PWD)
        assert e.value.status_code == 400
        assert "相同" in e.value.detail

    def test_success_updates_hash_and_flag(self):
        u = _user(must_change_password=True)
        db = FakeDb()
        auth_domain.change_password(db, u, "xyz67890")
        assert u.must_change_password is False
        assert u.password_hash != hash_password(PWD)
        assert db.committed >= 1


class TestAvatar:
    def test_invalid_format_400(self):
        with pytest.raises(HTTPException) as e:
            auth_domain.validate_avatar("data:image/gif;base64,AAAA")
        assert e.value.status_code == 400

    def test_oversize_400(self):
        big = "data:image/png;base64," + "A" * (300 * 1024)
        with pytest.raises(HTTPException) as e:
            auth_domain.validate_avatar(big)
        assert e.value.status_code == 400

    def test_valid_avatar_passes(self):
        auth_domain.validate_avatar("data:image/png;base64,iVBORw0KGgo=")
