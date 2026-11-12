"""节点级环境绑定（跨系统编排，2026-11-12）三层测试。

A. 引擎接缝：_resolve_node_runtime 解析/缓存/缺失报错 + _execute_node
   按节点运行时发请求（不发网络——builder 全部 monkeypatch 替身）；
B. 路由校验：_validate_node_envs（环境不存在 / 项目不匹配 → 400）；
C. 派生归属：list_testcases 跨项目 EXISTS 过滤 + fill_involved_projects 回填。
"""
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.engine.dag_executor import DagExecutor
from app.engine.events import StepResult


# ---------- 公共替身（沿用 test_execute_node.py 风格） ----------

class FakeDbGet:
    """支持 .get(Model, id) / .query().filter().first() 的最小替身"""

    def __init__(self, get_map: dict | None = None, first_results: list[Any] | None = None):
        self._get_map = get_map or {}       # (Model, id) -> obj
        self._firsts = list(first_results or [])

    def get(self, model, pk):
        return self._get_map.get((model, pk))

    def query(self, *_a, **_kw):
        db = self

        class _Q:
            def filter(self, *a, **kw):
                return self

            def first(self):
                return db._firsts.pop(0) if db._firsts else None

        return _Q()


class MemorySink:
    def __init__(self):
        self.steps: list[StepResult] = []

    def record_step(self, result: StepResult) -> None:
        self.steps.append(result)


class StubHttpClient:
    def __init__(self, response=None):
        self.headers: dict[str, str] = {}
        self.session = None
        self.response = response if response is not None else {"code": 200, "msg": "ok"}
        self.last_path = None

    def post(self, path, json=None, timeout=None):
        self.last_path = path
        return self.response

    def get(self, path, params=None, timeout=None):
        self.last_path = path
        return self.response


def _api(**over):
    base = dict(id=10, name="推送资产", path="/asset/push", method="POST",
                request_template={}, api_fields=None, fields=[])
    base.update(over)
    return SimpleNamespace(**base)


def _config(**over):
    base = dict(api_id=10, post_extract=None, assertions=None, wait_after_ms=0, env_id=None)
    base.update(over)
    return SimpleNamespace(**base)


def _executor(db, env=None, sink=None) -> DagExecutor:
    env = env or SimpleNamespace(id=1, variables={}, timeout=5)
    case = SimpleNamespace(id=1, dag_config={"nodes": [], "edges": []})
    return DagExecutor(db, case, env, sink=sink)


# ---------- A. 引擎：运行时解析 ----------

class TestResolveNodeRuntime:
    def test_no_env_id_falls_back_to_case_runtime(self):
        """env_id 为空 → 用例运行时（env/http_client/db_client 原样返回）"""
        ex = _executor(FakeDbGet())
        ex.http_client = StubHttpClient()
        ex.db_client = object()
        env, client, db = ex._resolve_node_runtime(_config())
        assert env is ex.env and client is ex.http_client and db is ex.db_client

    def test_env_id_equal_to_case_env_falls_back(self):
        """env_id == 用例环境 id → 同样回落用例运行时（不重复建 client）"""
        ex = _executor(FakeDbGet())
        ex.http_client = StubHttpClient()
        env, _, _ = ex._resolve_node_runtime(_config(env_id=1))
        assert env is ex.env

    def test_case_client_missing_raises(self):
        """用例客户端未初始化（execute 前）→ 明确报错"""
        ex = _executor(FakeDbGet())
        with pytest.raises(RuntimeError, match="客户端未初始化"):
            ex._resolve_node_runtime(_config())

    def test_node_env_builds_once_and_cached(self, monkeypatch):
        """额外环境惰性构建一次，重复解析命中缓存（build/login 各一次）"""
        node_env = SimpleNamespace(id=9, variables={}, timeout=8)
        db = FakeDbGet(get_map={(models.Environment, 9): node_env})
        ex = _executor(db)
        ex.http_client = StubHttpClient()
        calls = {"build": 0, "db": 0, "login": 0}

        import app.engine.dag_executor as de
        monkeypatch.setattr(de, "build_http_client",
                            lambda e: calls.__setitem__("build", calls["build"] + 1) or StubHttpClient())
        monkeypatch.setattr(de, "build_db_client",
                            lambda e: calls.__setitem__("db", calls["db"] + 1) or object())
        monkeypatch.setattr(de, "login", lambda c, e: calls.__setitem__("login", calls["login"] + 1))

        rt1 = ex._resolve_node_runtime(_config(env_id=9))
        rt2 = ex._resolve_node_runtime(_config(env_id=9))
        assert rt1 is rt2
        assert rt1[0] is node_env
        assert (calls["build"], calls["db"], calls["login"]) == (1, 1, 1)

    def test_env_deleted_raises(self):
        """环境已删（db.get 返回 None）→ RuntimeError，由节点级兜底成失败事件"""
        ex = _executor(FakeDbGet())
        ex.http_client = StubHttpClient()
        with pytest.raises(RuntimeError, match="不存在"):
            ex._resolve_node_runtime(_config(env_id=99))


class TestExecuteNodeWithNodeEnv:
    def test_node_env_failure_records_failed_step(self):
        """环境缺失 → 节点失败事件（原因可见），不冒泡"""
        config = _config(env_id=99)
        db = FakeDbGet(first_results=[config, _api()])  # config + api 命中；Environment 缺
        sink = MemorySink()
        ex = _executor(db, sink=sink)
        ex.http_client = StubHttpClient()

        passed, wait_ms = ex._execute_node(100, "n1", {"id": "n1"})

        assert passed is False and wait_ms == 0
        assert len(sink.steps) == 1
        assert sink.steps[0].status == "failed"
        assert "环境" in str(sink.steps[0].response_body)

    def test_request_goes_through_node_client(self, monkeypatch):
        """绑定节点环境 → 请求实际走节点 client（响应来自节点环境的替身 client）"""
        import app.engine.dag_executor as de
        node_env = SimpleNamespace(id=9, variables={}, timeout=8)
        node_client = StubHttpClient(response={"code": 0, "msg": "跨系统OK"})
        config = _config(env_id=9)
        api = _api()
        db = FakeDbGet(get_map={(models.Environment, 9): node_env},
                       first_results=[config, api])
        sink = MemorySink()
        ex = _executor(db, sink=sink)
        ex.http_client = StubHttpClient(response={"code": -1, "msg": "用例环境不应被调用"})
        monkeypatch.setattr(de, "build_http_client", lambda e: node_client)
        monkeypatch.setattr(de, "build_db_client", lambda e: object())
        monkeypatch.setattr(de, "login", lambda c, e: None)

        passed, _ = ex._execute_node(100, "n1", {"id": "n1"})

        assert passed is True
        assert node_client.last_path == "/asset/push"      # 请求走节点 client
        assert sink.steps[0].response_body == {"code": 0, "msg": "跨系统OK"}

    def test_retry_limit_taken_from_node_env(self, monkeypatch):
        """重试上限随节点环境（node_retry_count=1，首败一重试后成功）"""
        import app.engine.dag_executor as de
        from utils.exceptions import HttpStatusError
        node_env = SimpleNamespace(id=9, variables={}, timeout=8,
                                   node_retry_count=1, node_retry_interval=0.01)
        flaky = {"n": 0}

        class FlakyClient:
            headers: dict[str, str] = {}
            session = None

            def post(self, path, json=None, timeout=None):
                flaky["n"] += 1
                if flaky["n"] == 1:
                    raise HttpStatusError(502, path, '{"msg":"跨系统网关抖动"}')
                return {"code": 0}

        config = _config(env_id=9)
        db = FakeDbGet(get_map={(models.Environment, 9): node_env},
                       first_results=[config, _api()])
        sink = MemorySink()
        ex = _executor(db, sink=sink)
        ex.http_client = StubHttpClient()
        monkeypatch.setattr(de, "build_http_client", lambda e: FlakyClient())
        monkeypatch.setattr(de, "build_db_client", lambda e: object())
        monkeypatch.setattr(de, "login", lambda c, e: None)
        monkeypatch.setattr(de.time, "sleep", lambda s: None)

        passed, _ = ex._execute_node(100, "n1", {"id": "n1"})

        assert passed is True
        assert flaky["n"] == 2
        assert sink.steps[0].retry_count == 1


# ---------- B. 路由校验 ----------

@pytest.fixture()
def db():
    engine = create_engine("sqlite://",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_two_projects(db):
    """双项目 + 各自环境/接口：跨系统编排的最小舞台"""
    pa = models.Project(name="物流")
    pb = models.Project(name="亿海融")
    db.add_all([pa, pb])
    db.commit()
    env_a = models.Environment(name="物流-test", project_id=pa.id, base_url="http://a")
    env_b = models.Environment(name="亿海融-test", project_id=pb.id, base_url="http://b")
    db.add_all([env_a, env_b])
    db.commit()
    api_a = models.ApiDefinition(project_id=pa.id, name="物流下单", code="a1",
                                 method="POST", path="/a/order", request_template={}, headers_template={})
    api_b = models.ApiDefinition(project_id=pb.id, name="推送资产", code="b1",
                                 method="POST", path="/b/asset", request_template={}, headers_template={})
    db.add_all([api_a, api_b])
    db.commit()
    return pa, pb, env_a, env_b, api_a, api_b


class TestValidateNodeEnvs:
    def _data(self, api_id, env_id):
        from app import schemas
        return schemas.TestCaseCreate(
            project_id=1, name="跨系统用例", env_id=None,
            dag_config={"nodes": [{"id": "n1"}], "edges": []},
            node_configs=[schemas.NodeConfigIn(node_id="n1", api_id=api_id, env_id=env_id)])

    def test_reject_missing_env(self, db):
        from app.routers.testcases import _validate_node_envs
        pa, pb, env_a, env_b, api_a, api_b = _seed_two_projects(db)
        with pytest.raises(HTTPException) as ei:
            _validate_node_envs(db, None, self._data(api_b.id, 9999))
        assert ei.value.status_code == 400
        assert "不存在" in ei.value.detail

    def test_reject_env_project_mismatch(self, db):
        """节点接口在亿海融，却绑物流环境 → 拦下（相对 path 会打偏域）"""
        from app.routers.testcases import _validate_node_envs
        pa, pb, env_a, env_b, api_a, api_b = _seed_two_projects(db)
        with pytest.raises(HTTPException) as ei:
            _validate_node_envs(db, None, self._data(api_b.id, env_a.id))
        assert ei.value.status_code == 400
        assert "不一致" in ei.value.detail

    def test_accept_matching_env(self, db):
        from app.routers.testcases import _validate_node_envs
        pa, pb, env_a, env_b, api_a, api_b = _seed_two_projects(db)
        _validate_node_envs(db, None, self._data(api_b.id, env_b.id))   # 不抛即通过

    def test_accept_null_env(self, db):
        """env_id 缺省 = 沿用用例环境，不校验不拦截"""
        from app.routers.testcases import _validate_node_envs
        pa, pb, env_a, env_b, api_a, api_b = _seed_two_projects(db)
        _validate_node_envs(db, None, self._data(api_b.id, None))


# ---------- C. 派生归属 ----------

def _cross_case(db, pa, pb, api_a, api_b):
    """项目 A 的用例，其中 n2 节点引用项目 B 的接口（env_id 绑 B 环境）"""
    case = models.TestCase(project_id=pa.id, name="跨系统链", env_id=None,
                           dag_config={"nodes": [{"id": "n1"}, {"id": "n2"}], "edges": [
                               {"source": "n1", "target": "n2"}]})
    db.add(case)
    db.commit()
    db.add_all([
        models.CaseNodeConfig(case_id=case.id, node_id="n1", api_id=api_a.id),
        models.CaseNodeConfig(case_id=case.id, node_id="n2", api_id=api_b.id),
    ])
    db.commit()
    return case


class TestDerivedOwnership:
    def test_list_visible_in_both_projects(self, db):
        """跨系统用例在原生项目与接口引用项目下都可见"""
        from app import crud
        pa, pb, env_a, env_b, api_a, api_b = _seed_two_projects(db)
        cross = _cross_case(db, pa, pb, api_a, api_b)
        only_a = models.TestCase(project_id=pa.id, name="纯物流", env_id=None,
                                 dag_config={"nodes": [], "edges": []})
        db.add(only_a)
        db.commit()

        ids_a = [c.id for c in crud.list_testcases(db, project_id=pa.id)]
        ids_b = [c.id for c in crud.list_testcases(db, project_id=pb.id)]
        assert cross.id in ids_a and only_a.id in ids_a
        assert cross.id in ids_b and only_a.id not in ids_b

    def test_fill_involved_projects(self, db):
        """回填 involved_project_ids = 原生 ∪ 节点引用接口项目（去重排序）"""
        from app import crud
        pa, pb, env_a, env_b, api_a, api_b = _seed_two_projects(db)
        cross = _cross_case(db, pa, pb, api_a, api_b)
        plain = models.TestCase(project_id=pa.id, name="纯物流", env_id=None,
                                dag_config={"nodes": [], "edges": []})
        db.add(plain)
        db.commit()

        crud.fill_involved_projects(db, [cross, plain])
        assert cross.involved_project_ids == sorted({pa.id, pb.id})
        assert plain.involved_project_ids == [pa.id]

    def test_node_env_persisted_through_create(self, db):
        """create_testcase → _sync_node_configs 落盘 env_id；回读 NodeConfigOut 携带"""
        from app import crud, schemas
        pa, pb, env_a, env_b, api_a, api_b = _seed_two_projects(db)
        user = models.User(username="u", password_hash="x")
        db.add(user)
        db.commit()
        data = schemas.TestCaseCreate(
            project_id=pa.id, name="跨系统链", env_id=env_a.id,
            dag_config={"nodes": [{"id": "n1"}, {"id": "n2"}], "edges": [
                {"source": "n1", "target": "n2"}]},
            node_configs=[
                schemas.NodeConfigIn(node_id="n1", api_id=api_a.id, env_id=env_a.id),
                schemas.NodeConfigIn(node_id="n2", api_id=api_b.id, env_id=env_b.id),
            ])
        case = crud.create_testcase(db, data, user.id)
        nc = {n.node_id: n for n in db.query(models.CaseNodeConfig)
              .filter(models.CaseNodeConfig.case_id == case.id).all()}
        assert nc["n1"].env_id == env_a.id
        assert nc["n2"].env_id == env_b.id
