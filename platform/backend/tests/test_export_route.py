"""export 路由单测：勾选导出（case_ids）只导勾选的用例 + 非法参数拒绝。

真 SQLite 内存库走真 ORM（同 test_api_keys 的直调路由模式，不启 TestClient）。
"""
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.routers import testcases as tc


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
def user(db):
    u = models.User(username="admin", password_hash="x", name="管理员", role="admin")
    db.add(u)
    db.commit()
    return u


@pytest.fixture()
def project(db):
    p = models.Project(name="业务前台")
    db.add(p)
    db.commit()
    return p


def _case(db, project_id, name):
    c = models.TestCase(project_id=project_id, name=name, dag_config={"nodes": [], "edges": []})
    db.add(c)
    db.commit()
    return c


def test_export_selected_case_ids(db, user, project):
    """勾选 1 个：JSON 包 items 只含该用例，count=1"""
    keep = _case(db, project.id, "保留用例")
    _case(db, project.id, "排除用例A")
    _case(db, project.id, "排除用例B")
    resp = tc.export_list(
        project_id=project.id, format="json",
        case_ids=f"{keep.id}", db=db, user=user,
    )
    data = json.loads(resp.body)
    assert data["count"] == 1
    assert [c["name"] for c in data["items"]] == ["保留用例"]


def test_export_selected_multi_ids_dedup(db, user, project):
    """多选 + 重复/空段逗号：过滤正确且不炸"""
    c1 = _case(db, project.id, "用例一")
    c2 = _case(db, project.id, "用例二")
    _case(db, project.id, "用例三")
    resp = tc.export_list(
        project_id=project.id, format="json",
        case_ids=f"{c1.id},,{c2.id},{c1.id}", db=db, user=user,
    )
    data = json.loads(resp.body)
    assert data["count"] == 2
    assert {c["name"] for c in data["items"]} == {"用例一", "用例二"}


def test_export_without_case_ids_keeps_all(db, user, project):
    """不传 case_ids：维持原语义（按筛选范围全量）"""
    _case(db, project.id, "用例一")
    _case(db, project.id, "用例二")
    resp = tc.export_list(project_id=project.id, format="json", db=db, user=user)
    assert json.loads(resp.body)["count"] == 2


def test_export_selected_no_match_rejected(db, user, project):
    """勾选 id 不在项目内：400 且报「勾选」语义"""
    _case(db, project.id, "用例一")
    with pytest.raises(HTTPException) as ei:
        tc.export_list(project_id=project.id, format="json", case_ids="99999", db=db, user=user)
    assert ei.value.status_code == 400
    assert "勾选" in ei.value.detail


def test_export_bad_case_ids_rejected(db, user, project):
    """case_ids 非数字：400 明确格式非法"""
    with pytest.raises(HTTPException) as ei:
        tc.export_list(project_id=project.id, format="json", case_ids="1,a,3", db=db, user=user)
    assert ei.value.status_code == 400
    assert "case_ids" in ei.value.detail
