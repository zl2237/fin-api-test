# -*- coding: utf-8 -*-
"""断点续跑执行器测试：start_node 跳过前缀 / context_seed 注入 / 旧记录清理 / resumed 标记。

接缝沿用 test_execute_node.py（sink=MemorySink + http 替身），db 用按查询模型
路由的 RoutingFakeDb（execute 内部有多种查询：节点配置/接口/旧步骤/终止标记）。
"""
from types import SimpleNamespace

import pytest

import app.engine.dag_executor as de
from app.engine.dag_executor import DagExecutor
from app.models import ExecutionRecord, StepRecord
from tests.test_execute_node import MemorySink, StubHttpClient, _api, _config

import app.models as models


class RoutingFakeDb:
    """按 query(model) 路由到不同桶的 Session 替身。

    - CaseNodeConfig → configs 桶（first 逐个弹）
    - ApiDefinition → apis 桶（first 逐个弹）
    - StepRecord → steps 桶（all 一次性返回，供 _prune_stale_steps）
    - 其他（ExecutionRecord / 列查询）→ scalar None（未终止）
    """

    def __init__(self, configs=None, apis=None, steps=None):
        self._configs = list(configs or [])
        self._apis = list(apis or [])
        self._steps = list(steps or [])
        self.deleted: list = []
        self.commits = 0

    def query(self, model, *a, **kw):
        db = self
        cls = getattr(model, "class_", None) or model

        class _Q:
            def filter(self, *a, **kw):
                return self

            def order_by(self, *a, **kw):
                return self

            def first(self):
                if cls is models.CaseNodeConfig:
                    return db._configs.pop(0) if db._configs else None
                if cls is models.ApiDefinition:
                    return db._apis.pop(0) if db._apis else None
                return None

            def all(self):
                if cls is models.StepRecord:
                    steps, db._steps = db._steps, []
                    return steps
                return []

            def scalar(self):
                return None

        return _Q()

    def add(self, obj):
        pass

    def delete(self, obj):
        self.deleted.append(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass

    def merge(self, obj):
        return obj

    def __contains__(self, obj):
        return False


DAG = {"nodes": [{"id": "n1"}, {"id": "n2"}, {"id": "n3"}],
       "edges": [{"source": "n1", "target": "n2"}, {"source": "n2", "target": "n3"}]}


def _env():
    return SimpleNamespace(id=2, timeout=5, node_retry_count=0, node_retry_interval=1)


def _case():
    return SimpleNamespace(id=1, dag_config=DAG, project_id=None)


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch):
    monkeypatch.setattr(de, "login", lambda *a, **kw: None)
    # http 替身挂在 env 上（execute 会用 build 结果覆盖 self.http_client）
    monkeypatch.setattr(de, "build_http_client", lambda env: getattr(env, "_stub_client", None))
    monkeypatch.setattr(de, "build_db_client", lambda env: None)
    monkeypatch.setattr(de, "send_notify", lambda *a, **kw: None)


def _resume_executor(start_node, context_seed=None, steps=None):
    """构造续跑执行器：n2/n3 可执行（config+api），n1 被跳过不查询"""
    db = RoutingFakeDb(
        configs=[_config(api_id=10), _config(api_id=10)],  # n2, n3
        apis=[_api(), _api()],
        steps=steps or [],
    )
    record = ExecutionRecord(case_id=1, env_id=2, status="failed")
    sink = MemorySink()
    env = _env()
    env._stub_client = StubHttpClient(response={"code": 200, "data": {"id": 1}})
    ex = DagExecutor(db, _case(), env, execution_record=record, sink=sink,
                     start_node=start_node, context_seed=context_seed,
                     suppress_notify=True)
    return ex, record, sink, db


class TestResumeExecutor:
    def test_resume_skips_prefix_and_finishes_success(self):
        """从 n2 续跑：n1 不发请求；前缀计入 passed；跑完 status=success"""
        ex, record, sink, db = _resume_executor("n2")

        record = ex.execute()

        # 续跑段只产出 n2/n3 两步（n1 前缀跳过，不落新步骤）
        assert [s.node_id for s in sink.steps] == ["n2", "n3"]
        assert record.status == "success"
        assert record.summary["total"] == 3
        assert record.summary["passed"] == 3
        assert record.summary["failed"] == 0

    def test_context_seed_injected_into_pool(self):
        """报告虚拟上下文注入 ${} 统一池，后续节点可引用"""
        ex, record, sink, db = _resume_executor("n2", context_seed={"seed_var": 42})

        ex.execute()

        assert ex.context.extracted["seed_var"] == 42

    def test_resumed_steps_marked(self):
        """续跑段产出的步骤全部带 resumed=True"""
        ex, record, sink, db = _resume_executor("n2")

        ex.execute()

        assert len(sink.steps) == 2
        assert all(s.resumed for s in sink.steps)

    def test_stale_failed_steps_pruned(self):
        """续跑前清理旧失败记录：成功步骤保留，非成功步骤删除"""
        stale_ok = StepRecord(execution_id=1, node_id="n1", status="success")
        stale_fail = StepRecord(execution_id=1, node_id="n2", status="failed")
        ex, record, sink, db = _resume_executor("n2", steps=[stale_ok, stale_fail])

        ex.execute()

        assert db.deleted == [stale_fail]

    def test_fingerprint_written_on_execute(self):
        """执行时写入结构指纹（空绑定也有确定值）"""
        ex, record, sink, db = _resume_executor("n2")

        ex.execute()

        assert record.orchestration_fingerprint is not None
        assert len(record.orchestration_fingerprint) == 32

    def test_normal_execute_not_resumed(self):
        """普通执行（无 start_node）：步骤 resumed=False，行为不变"""
        db = RoutingFakeDb(configs=[_config(api_id=10)], apis=[_api()])
        record = ExecutionRecord(case_id=1, env_id=2, status="running")
        sink = MemorySink()
        single = {"nodes": [{"id": "n1"}], "edges": []}
        env = _env()
        env._stub_client = StubHttpClient(response={"code": 200})
        ex = DagExecutor(db, SimpleNamespace(id=1, dag_config=single, project_id=None),
                         env, execution_record=record, sink=sink)

        ex.execute()

        assert record.status == "success"
        assert all(not s.resumed for s in sink.steps)
