"""2c 首次登录强制改密：单测。

覆盖：
- UserOut / ChangePasswordRequest schema 字段
- change_password 接口核心逻辑（成功改密/强度校验/新旧不同/标记清空）
- User 模型 must_change_password 字段默认值
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import auth
from app.models import User
from app.routers.auth import change_password
from app.schemas import ChangePasswordRequest, UserOut


class FakeDb:
    """模拟 Session：记录 commit 调用"""

    def __init__(self):
        self.committed = False

    def commit(self):
        self.committed = True


def _make_user(password="admin123", must_change=True):
    """构造带真实密码哈希的 fake user"""
    return SimpleNamespace(
        id=1,
        username="admin",
        password_hash=auth.hash_password(password),
        name="管理员",
        role="admin",
        must_change_password=must_change,
    )


# ==================== Schema 层 ====================
class TestSchemaFields:
    def test_userout_has_must_change_password(self):
        fields = UserOut.model_fields
        assert "must_change_password" in fields

    def test_userout_must_change_password_defaults_false(self):
        """UserOut 的 must_change_password 默认 False（兼容旧用户）"""
        schema = UserOut(id=1, username="x")
        assert schema.must_change_password is False

    def test_change_password_request_accepts_new_password(self):
        req = ChangePasswordRequest(new_password="newPass123")
        assert req.new_password == "newPass123"


# ==================== 模型层 ====================
class TestUserModel:
    def test_must_change_password_column_exists(self):
        cols = [c.name for c in User.__table__.columns]
        assert "must_change_password" in cols

    def test_must_change_password_default_false(self):
        """模型层默认值 False（仅默认 admin 创建时显式设 True）"""
        col = User.__table__.c.must_change_password
        # default=False 用于 ORM 层，server_default 在迁移里设为 0
        assert col.default is not None
        # default.arg 可能是 False 或 callable
        if callable(col.default.arg):
            assert col.default.arg(None) is False
        else:
            assert col.default.arg is False


# ==================== change_password 接口 ====================
class TestChangePassword:
    def test_success_updates_password_and_clears_flag(self):
        user = _make_user(password="admin123", must_change=True)
        db = FakeDb()
        data = ChangePasswordRequest(new_password="newSecure123")

        result = change_password(data, user, db)

        assert result == {"message": "密码修改成功"}
        assert db.committed is True
        assert user.must_change_password is False
        # 新密码能验证通过
        assert auth.verify_password("newSecure123", user.password_hash) is True
        # 旧密码不再有效
        assert auth.verify_password("admin123", user.password_hash) is False

    def test_weak_password_raises_400(self):
        user = _make_user(must_change=True)
        db = FakeDb()
        data = ChangePasswordRequest(new_password="123")  # 太短

        with pytest.raises(HTTPException) as exc:
            change_password(data, user, db)
        assert exc.value.status_code == 400
        assert user.must_change_password is True  # 未改
        assert db.committed is False

    def test_password_no_letters_raises_400(self):
        user = _make_user(must_change=True)
        db = FakeDb()
        data = ChangePasswordRequest(new_password="12345678")  # 无字母

        with pytest.raises(HTTPException) as exc:
            change_password(data, user, db)
        assert exc.value.status_code == 400

    def test_password_no_digits_raises_400(self):
        user = _make_user(must_change=True)
        db = FakeDb()
        data = ChangePasswordRequest(new_password="abcdefgh")  # 无数字

        with pytest.raises(HTTPException) as exc:
            change_password(data, user, db)
        assert exc.value.status_code == 400

    def test_same_as_current_password_raises_400(self):
        user = _make_user(password="samePass123", must_change=True)
        db = FakeDb()
        data = ChangePasswordRequest(new_password="samePass123")

        with pytest.raises(HTTPException) as exc:
            change_password(data, user, db)
        assert exc.value.status_code == 400
        assert "相同" in exc.value.detail
        assert user.must_change_password is True
        assert db.committed is False

    def test_change_password_then_can_login_with_new(self):
        """改密后用新密码能验证通过，标记清空"""
        user = _make_user(password="oldPass123", must_change=True)
        db = FakeDb()
        data = ChangePasswordRequest(new_password="brandNew456")

        change_password(data, user, db)

        assert auth.verify_password("brandNew456", user.password_hash) is True
        assert user.must_change_password is False

    def test_non_default_admin_not_required_to_change(self):
        """非默认 admin 用户 must_change_password=False 时也能正常改密"""
        user = _make_user(password="userPass1", must_change=False)
        db = FakeDb()
        data = ChangePasswordRequest(new_password="newUserPass2")

        result = change_password(data, user, db)

        assert result == {"message": "密码修改成功"}
        assert user.must_change_password is False  # 本来就是 False
        assert auth.verify_password("newUserPass2", user.password_hash) is True
