"""users 域函数单测（router→crud 收敛后的新接缝）。

接缝：app.crud.users 模块的域函数（create_user / update_user_info / delete_user）。
router 保留 HTTP 语义（状态码/权限），不变量（唯一性/最后管理员保护/审计）全部收进域函数。
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.crud import users as users_domain


class FakeDb:
    """first() 按队列消费；all() 返回空列表；count() 返回 admin_count"""

    def __init__(self, first_results=(), admin_count=2):
        self._queue = list(first_results)
        self.admin_count = admin_count
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
                return db.admin_count

            def all(self):
                return []

            def in_(self, *a):
                return self

        return _Q()

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed += 1

    def refresh(self, _obj):
        pass


def _admin():
    return SimpleNamespace(id=9, username="boss", role="admin")


def _make_user(uid=1, username="u1", role="member"):
    return SimpleNamespace(
        id=uid, username=username, name=username, role=role,
        phone=None, email=None, created_by=None, updated_by=None,
    )


class TestCreateUser:
    def test_duplicate_username_raises_400(self):
        db = FakeDb(first_results=[_make_user(username="taken")])
        req = SimpleNamespace(username="taken", password="abc12345", name="", role="member")
        with pytest.raises(HTTPException) as e:
            users_domain.create_user(db, req, operator=_admin())
        assert e.value.status_code == 400
        assert "已存在" in e.value.detail

    def test_create_hashes_password_and_defaults_role(self):
        db = FakeDb(first_results=[None])
        req = SimpleNamespace(username="newbie", password="abc12345", name="", role="hacker")
        user = users_domain.create_user(db, req, operator=_admin())
        assert user.username == "newbie"
        # 密码哈希而非明文
        assert user.password_hash != "abc12345"
        # 非法角色回退 member
        assert user.role == "member"
        assert db.added and db.committed >= 1


class TestUpdateUserInfo:
    def test_last_admin_demote_raises_400(self):
        """目标用户是唯一 admin 且要降级 → 400（username/phone/email 查重先通过）"""
        user = _make_user(uid=9, username="boss", role="admin")
        # first() 队列：username 查重 → None（无重复）；phone/email 为空跳过查重；count=1 触发保护
        db = FakeDb(first_results=[None], admin_count=1)
        req = SimpleNamespace(username="boss", name="b", phone="", email="", role="member")
        with pytest.raises(HTTPException) as e:
            users_domain.update_user_info(db, user, req, operator=_admin())
        assert e.value.status_code == 400
        assert "管理员" in e.value.detail

    def test_success_applies_fields_and_returns_changes(self):
        user = _make_user(uid=2, username="old", role="member")
        db = FakeDb(first_results=[None, None, None], admin_count=2)
        req = SimpleNamespace(username="new", name="新名", phone="13800138000", email="a@b.com", role="member")
        users_domain.update_user_info(db, user, req, operator=_admin())
        assert user.username == "new"
        assert user.phone == "13800138000"
        assert user.email == "a@b.com"
        assert db.committed >= 1


class TestDeleteUser:
    def test_cannot_delete_self(self):
        admin = _admin()
        db = FakeDb(first_results=[admin])
        with pytest.raises(HTTPException) as e:
            users_domain.delete_user(db, admin, operator=admin)
        assert e.value.status_code == 400

    def test_last_admin_delete_raises_400(self):
        user = _make_user(uid=5, username="last", role="admin")
        db = FakeDb(first_results=[user], admin_count=1)
        with pytest.raises(HTTPException) as e:
            users_domain.delete_user(db, user, operator=_admin())
        assert e.value.status_code == 400
        assert "管理员" in e.value.detail
