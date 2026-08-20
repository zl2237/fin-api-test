"""用户管理：编辑用户接口（PUT /api/users/{id}）单测。

覆盖：
- 成功更新用户名/显示名/手机号/邮箱/角色
- 用户名过短 / 重复
- 手机号、邮箱格式错误
- 手机号、邮箱被其他用户占用
- 最后一个管理员降级保护
- User 模型 / UserOut schema 的 phone、email 字段
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models import User
from app.schemas import UserOut, UserInfoUpdate
from app.routers.users import update_user_info


def _make_user(uid=1, username="admin", name="管理员", role="admin", phone=None, email=None, department=None):
    return SimpleNamespace(
        id=uid,
        username=username,
        name=name,
        role=role,
        phone=phone,
        email=email,
        department=department,
        created_by=None,
        updated_by=None,
    )


def _make_admin():
    return _make_user(uid=9, username="boss", role="admin")


class FakeDb:
    """模拟 Session：first() 结果按调用顺序全局消费（跨 query 共享队列）。

    first_results 依次对应：按 id 查目标用户 / 用户名重复 / 手机号重复 / 邮箱重复，
    队列耗尽后 first() 返回 None（无重复）。
    """

    def __init__(self, first_results=(), admin_count=2):
        self._queue = list(first_results)
        self._admin_count = admin_count
        self.committed = False
        self.refreshed = False

    def query(self, *args, **kwargs):
        # 兼容 db.query(Model) 与 db.query(Model.id, Model.name, ...) 两种调用
        db = self

        class _Query:
            def filter(self, *args, **kwargs):
                return self

            def first(self):
                return db._queue.pop(0) if db._queue else None

            def count(self):
                return db._admin_count

            def all(self):
                return []

        return _Query()

    def add(self, _obj):
        pass

    def commit(self):
        self.committed = True

    def refresh(self, _obj):
        self.refreshed = True


# ==================== Schema / 模型层 ====================
class TestSchemaAndModel:
    def test_user_model_has_phone_email_columns(self):
        cols = [c.name for c in User.__table__.columns]
        assert "phone" in cols
        assert "email" in cols

    def test_userout_has_phone_email(self):
        fields = UserOut.model_fields
        assert "phone" in fields
        assert "email" in fields

    def test_user_info_update_schema(self):
        req = UserInfoUpdate(username="newname", name="新名", phone="13800138000", email="a@b.com", role="member")
        assert req.username == "newname"
        assert req.phone == "13800138000"


# ==================== 编辑用户接口 ====================
class TestUpdateUserInfo:
    def _data(self, **kw):
        base = dict(username="admin", name="管理员", phone=None, email=None, role="admin")
        base.update(kw)
        return UserInfoUpdate(**base)

    def test_success_updates_all_fields(self):
        user = _make_user()
        db = FakeDb()  # 第一次 first() 返回 target，之后全部 None（无重复）
        # 预置第一次 first() 返回 user 本身（按 id 查询）
        db = FakeDb(first_results=[user])

        result = update_user_info(1, self._data(
            username="newadmin", name="新管理员", phone="13800138000", email="boss@test.com",
        ), db, _make_admin())

        assert result is user
        assert user.username == "newadmin"
        assert user.name == "新管理员"
        assert user.phone == "13800138000"
        assert user.email == "boss@test.com"
        assert db.committed is True

    def test_success_keeps_role_when_unchanged(self):
        user = _make_user(role="member")
        db = FakeDb(first_results=[user])

        update_user_info(1, self._data(role="member"), db, _make_admin())

        assert user.role == "member"

    def test_role_downgrade_allowed_when_other_admins_exist(self):
        user = _make_user(role="admin")
        db = FakeDb(first_results=[user], admin_count=3)

        update_user_info(1, self._data(role="member"), db, _make_admin())

        assert user.role == "member"

    def test_last_admin_downgrade_raises_400(self):
        user = _make_user(role="admin")
        db = FakeDb(first_results=[user], admin_count=1)

        with pytest.raises(HTTPException) as exc:
            update_user_info(1, self._data(role="member"), db, _make_admin())
        assert exc.value.status_code == 400
        assert "至少保留一个管理员" in exc.value.detail
        assert db.committed is False

    def test_user_not_found_raises_404(self):
        db = FakeDb(first_results=[None])

        with pytest.raises(HTTPException) as exc:
            update_user_info(99, self._data(), db, _make_admin())
        assert exc.value.status_code == 404

    def test_invalid_role_raises_400(self):
        db = FakeDb(first_results=[_make_user()])

        with pytest.raises(HTTPException) as exc:
            update_user_info(1, self._data(role="superadmin"), db, _make_admin())
        assert exc.value.status_code == 400

    def test_short_username_raises_400(self):
        db = FakeDb(first_results=[_make_user()])

        with pytest.raises(HTTPException) as exc:
            # " a " 原始长度 3 通过 schema min_length，strip 后只剩 1 位，触发接口层兜底校验
            update_user_info(1, self._data(username=" a "), db, _make_admin())
        assert exc.value.status_code == 400

    def test_duplicate_username_raises_400(self):
        user = _make_user()
        other = _make_user(uid=2, username="taken")
        db = FakeDb(first_results=[user, other])  # 按 id 查到 user，用户名查到重复

        with pytest.raises(HTTPException) as exc:
            update_user_info(1, self._data(username="taken"), db, _make_admin())
        assert exc.value.status_code == 400
        assert "用户名已存在" in exc.value.detail
        assert db.committed is False

    def test_bad_phone_format_raises_400(self):
        db = FakeDb(first_results=[_make_user()])

        with pytest.raises(HTTPException) as exc:
            update_user_info(1, self._data(phone="12345"), db, _make_admin())
        assert exc.value.status_code == 400
        assert "手机号格式" in exc.value.detail

    def test_bad_email_format_raises_400(self):
        db = FakeDb(first_results=[_make_user()])

        with pytest.raises(HTTPException) as exc:
            update_user_info(1, self._data(email="not-an-email"), db, _make_admin())
        assert exc.value.status_code == 400
        assert "邮箱格式" in exc.value.detail

    def test_phone_used_by_other_raises_400(self):
        user = _make_user()
        other = _make_user(uid=2, username="someone", phone="13800138000")
        db = FakeDb(first_results=[user, None, other])  # user 本体 / 用户名无重复 / 手机号被占用

        with pytest.raises(HTTPException) as exc:
            update_user_info(1, self._data(phone="13800138000"), db, _make_admin())
        assert exc.value.status_code == 400
        assert "手机号" in exc.value.detail

    def test_email_used_by_other_raises_400(self):
        user = _make_user()
        other = _make_user(uid=2, username="someone", email="a@b.com")
        db = FakeDb(first_results=[user, None, other])  # user / 用户名无重复 / 邮箱被占用（phone 为空不查询）

        with pytest.raises(HTTPException) as exc:
            update_user_info(1, self._data(email="A@B.com"), db, _make_admin())
        assert exc.value.status_code == 400
        assert "邮箱" in exc.value.detail

    def test_email_normalized_to_lowercase(self):
        user = _make_user()
        db = FakeDb(first_results=[user])

        update_user_info(1, self._data(email="Mixed@Case.COM"), db, _make_admin())

        assert user.email == "mixed@case.com"

    def test_empty_strings_treated_as_none(self):
        user = _make_user(phone="13800138000", email="old@test.com")
        db = FakeDb(first_results=[user])

        update_user_info(1, self._data(name="", phone="", email=""), db, _make_admin())

        assert user.name is None
        assert user.phone is None
        assert user.email is None
