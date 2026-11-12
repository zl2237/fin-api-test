"""API 密钥（外部触发）单测：生成/哈希、认证双通道、路由 CRUD 与权限。

真实 SQLite 内存库（含 api_keys 表）；get_current_user 直接函数调用
（不启 TestClient）——X-API-Key 头与 Bearer fin_* 凭据手工构造注入。
"""
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth, models, schemas
from app.routers import api_keys as api_keys_router


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture()
def admin(db):
    u = models.User(username="admin", password_hash="x", name="管理员", role="admin")
    db.add(u)
    db.commit()
    return u


@pytest.fixture()
def member(db):
    u = models.User(username="ci_user", password_hash="x", name="CI账号", role="member")
    db.add(u)
    db.commit()
    return u


@pytest.fixture()
def project(db):
    p = models.Project(name="业务前台")
    db.add(p)
    db.commit()
    return p


def _make_key(db, user, project_id, name="jenkins-nightly"):
    """走真路由创建密钥，返回 (路由响应, 明文)。"""
    resp = api_keys_router.create_key(
        data=schemas.ApiKeyCreate(project_id=project_id, name=name),
        db=db,
        user=user,
    )
    return resp


# ============ 生成与哈希 ============

class TestGenerateAndHash:
    def test_generate_has_prefix_and_length(self):
        raw = auth.generate_api_key()
        assert raw.startswith("fin_")
        assert len(raw) > 40  # fin_ + 43 位 urlsafe

    def test_generate_unique(self):
        assert auth.generate_api_key() != auth.generate_api_key()

    def test_hash_is_sha256_hex(self):
        h = auth.hash_api_key("fin_abc")
        assert len(h) == 64 and int(h, 16) >= 0

    def test_hash_deterministic(self):
        assert auth.hash_api_key("fin_x") == auth.hash_api_key("fin_x")


# ============ resolve_api_key_user ============

class TestResolveApiKeyUser:
    def test_valid_key_resolves_creator(self, db, member, project):
        resp = _make_key(db, member, project.id)
        resolved = auth.resolve_api_key_user(db, resp.api_key)
        assert resolved is not None
        user, key = resolved
        assert user.id == member.id
        assert key.id == resp.id
        assert key.last_used_at is not None  # 命中回写

    def test_wrong_key_returns_none(self, db, member, project):
        _make_key(db, member, project.id)
        assert auth.resolve_api_key_user(db, "fin_not-the-key") is None

    def test_non_prefixed_returns_none(self, db, member, project):
        _make_key(db, member, project.id)
        assert auth.resolve_api_key_user(db, "random-garbage") is None
        assert auth.resolve_api_key_user(db, "") is None

    def test_deleted_key_returns_none(self, db, member, project):
        resp = _make_key(db, member, project.id)
        api_keys_router.delete_key(resp.id, db=db, user=member)
        assert auth.resolve_api_key_user(db, resp.api_key) is None

    def test_creator_deleted_returns_none(self, db, member, project):
        resp = _make_key(db, member, project.id)
        db.delete(member)
        db.commit()
        assert auth.resolve_api_key_user(db, resp.api_key) is None


# ============ get_current_user 双通道 ============

class TestGetCurrentUserChannels:
    def test_x_api_key_header(self, db, member, project):
        resp = _make_key(db, member, project.id)
        user = auth.get_current_user(cred=None, x_api_key=resp.api_key, db=db)
        assert user.id == member.id

    def test_bearer_fin_prefix(self, db, member, project):
        resp = _make_key(db, member, project.id)
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=resp.api_key)
        user = auth.get_current_user(cred=cred, x_api_key=None, db=db)
        assert user.id == member.id

    def test_bearer_jwt_still_works(self, db, member):
        """回归：普通 JWT 路径不受影响（fin_ 前缀才分流）。"""
        token = auth.create_token(member.id, member.username, member.role)
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user = auth.get_current_user(cred=cred, x_api_key=None, db=db)
        assert user.id == member.id

    def test_invalid_key_401(self, db, member, project):
        _make_key(db, member, project.id)
        with pytest.raises(HTTPException) as e:
            auth.get_current_user(cred=None, x_api_key="fin_wrong", db=db)
        assert e.value.status_code == 401
        assert "密钥" in e.value.detail

    def test_no_credentials_401(self, db):
        with pytest.raises(HTTPException) as e:
            auth.get_current_user(cred=None, x_api_key=None, db=db)
        assert e.value.status_code == 401

    def test_x_api_key_wins_over_jwt(self, db, member, project):
        """显式密钥头优先：密钥无效时不静默回落 JWT。"""
        token = auth.create_token(member.id, member.username, member.role)
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        with pytest.raises(HTTPException):
            auth.get_current_user(cred=cred, x_api_key="fin_wrong", db=db)


# ============ 路由 CRUD 与权限 ============

class TestRouterCrud:
    def test_create_returns_plaintext_once(self, db, member, project):
        resp = _make_key(db, member, project.id)
        assert resp.api_key.startswith("fin_")
        # 库里只有哈希与前缀，明文不落库
        rec = db.query(models.ApiKey).filter(models.ApiKey.id == resp.id).first()
        assert rec.key_hash == auth.hash_api_key(resp.api_key)
        assert rec.key_hash != resp.api_key
        assert rec.key_prefix == resp.api_key[:12]
        assert rec.created_by == member.id

    def test_list_never_exposes_material(self, db, member, project):
        created = _make_key(db, member, project.id)
        items = api_keys_router.list_keys(project_id=project.id, db=db, user=member)
        assert len(items) == 1
        assert items[0].key_prefix == created.key_prefix
        assert items[0].created_by_name == member.name  # fill_audit_names 生效
        # 线上真实出参（response_model 序列化口径）：无任何密钥材料字段
        out = schemas.ApiKeyOut.model_validate(items[0]).model_dump()
        assert "api_key" not in out and "key_hash" not in out

    def test_list_filter_by_project(self, db, member, project):
        other = models.Project(name="另一个项目")
        db.add(other)
        db.commit()
        _make_key(db, member, project.id)
        _make_key(db, member, other.id, name="other-ci")
        assert len(api_keys_router.list_keys(project_id=project.id, db=db, user=member)) == 1
        assert len(api_keys_router.list_keys(db=db, user=member)) == 2

    def test_create_missing_project_404(self, db, member):
        with pytest.raises(HTTPException) as e:
            _make_key(db, member, 9999)
        assert e.value.status_code == 404

    def test_member_can_create(self, db, member, project):
        """外部触发不限于管理员：member 建的密钥以 member 身份生效。"""
        resp = _make_key(db, member, project.id)
        user = auth.get_current_user(cred=None, x_api_key=resp.api_key, db=db)
        assert user.role == "member"

    def test_delete_by_creator(self, db, member, project):
        resp = _make_key(db, member, project.id)
        out = api_keys_router.delete_key(resp.id, db=db, user=member)
        assert out["message"] == "已吊销"
        assert db.query(models.ApiKey).count() == 0

    def test_delete_by_other_member_403(self, db, member, project):
        resp = _make_key(db, member, project.id)
        other = models.User(username="other", password_hash="x", role="member")
        db.add(other)
        db.commit()
        with pytest.raises(HTTPException) as e:
            api_keys_router.delete_key(resp.id, db=db, user=other)
        assert e.value.status_code == 403
        assert db.query(models.ApiKey).count() == 1  # 未被误删

    def test_delete_by_admin_allowed(self, db, member, admin, project):
        resp = _make_key(db, member, project.id)
        api_keys_router.delete_key(resp.id, db=db, user=admin)
        assert db.query(models.ApiKey).count() == 0

    def test_delete_missing_404(self, db, member):
        with pytest.raises(HTTPException) as e:
            api_keys_router.delete_key(999, db=db, user=member)
        assert e.value.status_code == 404

    def test_revoked_key_rejected_at_auth(self, db, member, project):
        """吊销闭环：删除后再用同一明文认证 → 401。"""
        resp = _make_key(db, member, project.id)
        api_keys_router.delete_key(resp.id, db=db, user=member)
        with pytest.raises(HTTPException) as e:
            auth.get_current_user(cred=None, x_api_key=resp.api_key, db=db)
        assert e.value.status_code == 401
