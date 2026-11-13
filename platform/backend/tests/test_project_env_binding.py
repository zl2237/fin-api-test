# -*- coding: utf-8 -*-
"""跨系统用例按项目环境绑定（2026-11-13）三层测试。

背景：环境绑定原来只有用例级单值（原生项目维度），跨系统用例的非原生项目
节点靠节点级 env_id 隐藏生效——该项目视角下看不到也切不了。本组测试钉住：
- 引擎解析链：节点显式 env > 项目绑定 > 项目默认环境 > 用例环境（原生节点）；
  跨项目无任何环境 → 报错（不静默打到用例环境域名）
- crud：绑定行写/改/删（幂等）+ 串写防护（env 不属该项目 / 原生项目 / 不可见）
- 列表/端点：按项目视角回填生效环境（env_source 标注 binding/default）
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models, schemas
from app.engine.dag_executor import DagExecutor


# ---------- 真 SQLite 夹具（沿用 test_cross_group_view 风格） ----------

@pytest.fixture()
def db():
    engine = create_engine("sqlite://",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed(db):
    """双项目 + 双项目环境（B 有默认/非默认两个）+ 跨系统用例（原生 A，引用 B 接口）"""
    pa = models.Project(name="物流")
    pb = models.Project(name="亿海融")
    db.add_all([pa, pb])
    db.commit()
    env_a = models.Environment(project_id=pa.id, name="A-测试", base_url="http://a", is_default=True)
    env_b1 = models.Environment(project_id=pb.id, name="B-测试", base_url="http://b1", is_default=True)
    env_b2 = models.Environment(project_id=pb.id, name="B-预发", base_url="http://b2")
    db.add_all([env_a, env_b1, env_b2])
    db.commit()
    api_a = models.ApiDefinition(project_id=pa.id, name="物流下单", code="a1",
                                 method="POST", path="/a/order", request_template={}, headers_template={})
    api_b = models.ApiDefinition(project_id=pb.id, name="推送资产", code="b1",
                                 method="POST", path="/b/asset", request_template={}, headers_template={})
    db.add_all([api_a, api_b])
    db.commit()
    cross = models.TestCase(project_id=pa.id, name="跨系统-推送", env_id=env_a.id,
                            dag_config={"nodes": [{"id": "n1"}, {"id": "n2"}], "edges": []})
    db.add(cross)
    db.commit()
    db.add_all([
        models.CaseNodeConfig(case_id=cross.id, node_id="n1", api_id=api_a.id),
        models.CaseNodeConfig(case_id=cross.id, node_id="n2", api_id=api_b.id),
    ])
    db.commit()
    return SimpleNamespace(pa=pa, pb=pb, env_a=env_a, env_b1=env_b1, env_b2=env_b2,
                           api_a=api_a, api_b=api_b, cross=cross)


# ---------- A. crud：绑定写/删与串写防护 ----------

class TestSetProjectEnvBinding:
    def test_write_update_delete_idempotent(self, db):
        s = _seed(db)
        crud.set_project_env_binding(db, s.cross, s.pb.id, s.env_b2.id)
        row = db.query(models.CaseProjectEnv).filter_by(case_id=s.cross.id).one()
        assert row.env_id == s.env_b2.id and row.project_id == s.pb.id
        crud.set_project_env_binding(db, s.cross, s.pb.id, s.env_b1.id)  # 改绑
        assert db.query(models.CaseProjectEnv).filter_by(case_id=s.cross.id).one().env_id == s.env_b1.id
        crud.set_project_env_binding(db, s.cross, s.pb.id, None)         # 清除回退默认
        assert db.query(models.CaseProjectEnv).filter_by(case_id=s.cross.id).count() == 0
        crud.set_project_env_binding(db, s.cross, s.pb.id, None)         # 幂等
        assert db.query(models.CaseProjectEnv).count() == 0

    def test_foreign_env_rejected(self, db):
        """env 不属于该项目（拿 A 的环境绑 B 视角）→ 拒"""
        s = _seed(db)
        with pytest.raises(ValueError, match="不属于当前项目"):
            crud.set_project_env_binding(db, s.cross, s.pb.id, s.env_a.id)

    def test_native_project_rejected(self, db):
        """原生项目走用例 env_id 编辑，不走本接口"""
        s = _seed(db)
        with pytest.raises(ValueError, match="原生项目"):
            crud.set_project_env_binding(db, s.cross, s.pa.id, s.env_a.id)

    def test_invisible_project_rejected(self, db):
        """项目未参与该用例（未引用其接口）→ 拒"""
        s = _seed(db)
        pc = models.Project(name="局外人")
        db.add(pc)
        db.commit()
        with pytest.raises(ValueError, match="不可见"):
            crud.set_project_env_binding(db, s.cross, pc.id, None)


# ---------- B. 引擎：解析链 ----------

class FakeDb:
    """支持 .get / .query(CaseProjectEnv列).filter().all() / .query(Environment).filter().order_by().all()"""

    def __init__(self, envs=None, bindings=None, case_id=1):
        self.envs = envs or {}                 # id -> env obj
        self.env_list = list(envs.values()) if envs else []
        self.bindings = bindings or {}         # project_id -> env_id
        self.case_id = case_id

    def get(self, model, pk):
        return self.envs.get(pk)

    def query(self, *target):
        db = self

        class _Q:
            def filter(self, *a, **k):
                return self

            def order_by(self, *a, **k):
                return self

            def all(self):
                if any(t is models.CaseProjectEnv.case_id for t in target):
                    return [(db.case_id, p, e) for p, e in db.bindings.items()]
                if target and target[0] is models.Environment:
                    return db.env_list
                return []

        return _Q()


def _exec(db, case_project=1):
    env = SimpleNamespace(id=1, variables={}, timeout=5)
    case = SimpleNamespace(id=1, project_id=case_project, dag_config={"nodes": [], "edges": []})
    ex = DagExecutor(db, case, env, sink=None)
    ex.http_client = object()
    ex.db_client = object()
    return ex


def _env(i, project_id, is_default=False):
    return SimpleNamespace(id=i, project_id=project_id, is_default=is_default,
                           variables={}, timeout=5)


class TestEngineResolution:
    def _patch_builders(self, monkeypatch):
        import app.engine.dag_executor as de
        built = {"envs": []}
        monkeypatch.setattr(de, "build_http_client", lambda e: built["envs"].append(e) or object())
        monkeypatch.setattr(de, "build_db_client", lambda e: object())
        monkeypatch.setattr(de, "login", lambda c, e: None)
        return built

    def test_binding_env_used_for_cross_node(self, monkeypatch):
        """跨项目节点无显式 env、有项目绑定 → 用绑定环境"""
        built = self._patch_builders(monkeypatch)
        env_b = _env(23, project_id=3)
        db = FakeDb(envs={23: env_b}, bindings={3: 23})
        ex = _exec(db, case_project=1)
        rt = ex._resolve_node_runtime(SimpleNamespace(env_id=None), SimpleNamespace(project_id=3))
        assert rt[0] is env_b and built["envs"] == [env_b]

    def test_default_env_used_when_no_binding(self, monkeypatch):
        """无绑定 → 项目默认环境（is_default）"""
        self._patch_builders(monkeypatch)
        e1 = _env(31, project_id=3)
        e2 = _env(32, project_id=3, is_default=True)
        db = FakeDb(envs={31: e1, 32: e2})
        ex = _exec(db, case_project=1)
        rt = ex._resolve_node_runtime(SimpleNamespace(env_id=None), SimpleNamespace(project_id=3))
        assert rt[0] is e2

    def test_project_without_env_raises(self):
        """项目一个环境都没有 → 明确报错（不能静默落到用例环境域名打偏请求）"""
        db = FakeDb()
        ex = _exec(db, case_project=1)
        with pytest.raises(RuntimeError, match="未配置任何环境"):
            ex._resolve_node_runtime(SimpleNamespace(env_id=None), SimpleNamespace(project_id=3))

    def test_explicit_node_env_wins_over_binding(self, monkeypatch):
        """节点显式 env 优先于项目绑定（显式例外语义）"""
        built = self._patch_builders(monkeypatch)
        e_bind = _env(23, project_id=3)
        e_explicit = _env(24, project_id=3)
        db = FakeDb(envs={23: e_bind, 24: e_explicit}, bindings={3: 23})
        ex = _exec(db, case_project=1)
        rt = ex._resolve_node_runtime(SimpleNamespace(env_id=24), SimpleNamespace(project_id=3))
        assert rt[0] is e_explicit and built["envs"] == [e_explicit]

    def test_native_node_falls_back_to_case_runtime(self):
        """原生项目节点无显式 env → 用例运行时（不查绑定）"""
        db = FakeDb()
        ex = _exec(db, case_project=1)
        env, client, dbcl = ex._resolve_node_runtime(SimpleNamespace(env_id=None), SimpleNamespace(project_id=1))
        assert env is ex.env and client is ex.http_client and dbcl is ex.db_client


# ---------- C. 列表视角回填 + 端点 ----------

class TestListViewEnvResolution:
    def test_default_env_shown_without_binding(self, db):
        """无绑定：B 视角显示项目默认环境（env_source=default），A 视角保持原生"""
        from app.routers import testcases as tc_router
        s = _seed(db)
        outs_b = tc_router.list_all(project_id=s.pb.id, db=db, user=None)
        cb = next(o for o in outs_b if o.id == s.cross.id)
        assert (cb.env_id, cb.env_name, cb.env_source) == (s.env_b1.id, "B-测试", "default")
        outs_a = tc_router.list_all(project_id=s.pa.id, db=db, user=None)
        ca = next(o for o in outs_a if o.id == s.cross.id)
        assert (ca.env_id, ca.env_source) == (s.env_a.id, None)

    def test_binding_env_shown_after_set(self, db):
        """有绑定：B 视角显示绑定环境（env_source=binding）"""
        from app.routers import testcases as tc_router
        s = _seed(db)
        crud.set_project_env_binding(db, s.cross, s.pb.id, s.env_b2.id)
        outs_b = tc_router.list_all(project_id=s.pb.id, db=db, user=None)
        cb = next(o for o in outs_b if o.id == s.cross.id)
        assert (cb.env_id, cb.env_name, cb.env_source) == (s.env_b2.id, "B-预发", "binding")


class TestProjectEnvEndpoint:
    def test_endpoint_returns_view_patched_out(self, db):
        """端点返回按发起视角回填的生效环境（前端直接同步行内显示）"""
        from app.routers import testcases as tc_router
        s = _seed(db)
        u = SimpleNamespace(id=1, username="tester")
        out = tc_router.set_project_env(
            case_id=s.cross.id, data=schemas.CaseProjectEnvIn(project_id=s.pb.id, env_id=s.env_b2.id),
            db=db, user=u)
        assert (out.env_id, out.env_name, out.env_source) == (s.env_b2.id, "B-预发", "binding")
        # 清除后回默认
        out = tc_router.set_project_env(
            case_id=s.cross.id, data=schemas.CaseProjectEnvIn(project_id=s.pb.id, env_id=None),
            db=db, user=u)
        assert (out.env_id, out.env_source) == (s.env_b1.id, "default")

    def test_endpoint_rejects_foreign_env(self, db):
        from fastapi import HTTPException
        from app.routers import testcases as tc_router
        s = _seed(db)
        u = SimpleNamespace(id=1, username="tester")
        with pytest.raises(HTTPException) as ei:
            tc_router.set_project_env(
                case_id=s.cross.id, data=schemas.CaseProjectEnvIn(project_id=s.pb.id, env_id=s.env_a.id),
                db=db, user=u)
        assert ei.value.status_code == 400


class TestDetailBindings:
    def test_detail_fills_project_env_bindings(self, db):
        """详情回填 project_env_bindings（设计器提示各项目生效环境）"""
        s = _seed(db)
        crud.set_project_env_binding(db, s.cross, s.pb.id, s.env_b2.id)
        crud.fill_project_env_bindings(db, [s.cross])
        assert s.cross.project_env_bindings == [{"project_id": s.pb.id, "env_id": s.env_b2.id}]
