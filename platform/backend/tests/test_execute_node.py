"""DagExecutor 执行主链路测试（通过事件接缝）。

接缝：DagExecutor(sink=...) + _execute_node —— 执行产出 StepResult 事件写入 sink，
不接触真实 DB/HTTP。断言只看事件内容与上下文状态，不看落库副作用。

fake db 沿用项目现有测试风格（见 test_file_update.py）。
"""
from types import SimpleNamespace
from typing import Any

from app.engine.dag_executor import DagExecutor
from app.engine.events import StepResult


class FakeDb:
    """最小 Session 替身：支持 query().filter().first() 链式调用"""

    def __init__(self, first_results: list[Any] | None = None):
        # first_results 按查询顺序依次弹出；空则返回 None
        self._firsts = list(first_results or [])
        self.added: list[Any] = []
        self.commits = 0

    def query(self, *_a, **_kw):
        db = self

        class _Q:
            def filter(self, *a, **kw):
                return self

            def first(self):
                return db._firsts.pop(0) if db._firsts else None

        return _Q()

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, _obj):
        pass


class MemorySink:
    """内存 sink：收集事件，供断言"""

    def __init__(self):
        self.steps: list[StepResult] = []

    def record_step(self, result: StepResult) -> None:
        self.steps.append(result)


def _executor(db, env=None, sink=None) -> DagExecutor:
    """构造不触发网络/DB 的 DagExecutor"""
    env = env or SimpleNamespace(variables={}, timeout=5)
    case = SimpleNamespace(id=1, dag_config={"nodes": [], "edges": []})
    return DagExecutor(db, case, env, sink=sink)


class StubHttpClient:
    """不发网络的 http client 替身：post 返回固定响应，记录收到的 body"""

    def __init__(self, response=None):
        self.headers: dict[str, str] = {}
        self.response = response if response is not None else {"code": 200, "msg": "ok"}
        self.last_json_body = None
        self.last_path = None

    def post(self, path, json=None, timeout=None):
        self.last_path = path
        self.last_json_body = json
        return self.response

    def get(self, path, params=None, timeout=None):
        self.last_path = path
        self.last_json_body = params
        return self.response


def _api(**over):
    base = dict(id=10, name="下单", path="/order/create", method="POST",
                request_template={}, api_fields=None, fields=[])
    base.update(over)
    return SimpleNamespace(**base)


def _config(**over):
    base = dict(api_id=10, pre_process=None, post_extract=None, assertions=None, wait_after_ms=0)
    base.update(over)
    return SimpleNamespace(**base)


class TestExecuteNodeSuccess:
    def test_success_emits_success_event_with_request_response(self):
        """绑定接口 + 请求成功 + 无断言 → success 事件，请求/响应原样入事件"""
        config = _config(api_id=10)
        api = _api()
        db = FakeDb(first_results=[config, api])  # 两次查询：CaseNodeConfig → ApiDefinition
        sink = MemorySink()
        ex = _executor(db, sink=sink)
        ex.http_client = StubHttpClient(response={"code": 200, "data": {"id": 1}})

        passed, wait_ms = ex._execute_node(100, "n1", {"id": "n1"})

        assert passed is True
        assert wait_ms == 0
        ev = sink.steps[0]
        assert ev.status == "success"
        assert ev.api_name == "下单"
        assert ev.api_path == "/order/create"
        assert ev.response_status == 200
        assert ev.response_body == {"code": 200, "data": {"id": 1}}
        assert ev.request_body is not None


class TestExecuteNodeAssertionFail:
    def test_failed_assertion_emits_failed_event_with_assertion_results(self):
        """断言不通过 → 事件 status=failed，assertions 列表携带每条断言的 pass/actual/expected"""
        config = _config(api_id=10, assertions=[
            {"type": "json_path_equals", "path": "$.code", "expected": 500},
        ])
        api = _api()
        db = FakeDb(first_results=[config, api])
        sink = MemorySink()
        ex = _executor(db, sink=sink)
        ex.http_client = StubHttpClient(response={"code": 200, "data": {"id": 1}})

        passed, _ = ex._execute_node(100, "n1", {"id": "n1"})

        assert passed is False
        ev = sink.steps[0]
        assert ev.status == "failed"
        assert len(ev.assertions) == 1
        ar = ev.assertions[0]
        assert ar.type == "json_path_equals"
        assert ar.passed is False
        assert ar.actual == 200
        assert ar.expected == 500


class TestExecuteNodePostExtract:
    def test_post_extract_updates_context(self):
        """post_extract 从响应提取变量 → 写入执行上下文，后续节点可用"""
        config = _config(api_id=10, post_extract=[
            {"name": "order_id", "json_path": "$.data.id"},
        ])
        api = _api()
        db = FakeDb(first_results=[config, api])
        sink = MemorySink()
        ex = _executor(db, sink=sink)
        ex.http_client = StubHttpClient(response={"code": 200, "data": {"id": 42}})

        passed, _ = ex._execute_node(100, "n1", {"id": "n1"})

        assert passed is True
        # 变量已入上下文统一池（供后续节点 ${order_id} 引用）
        assert ex.context.extracted["order_id"] == 42


class TestExecuteNodeUnboundApi:
    def test_unbound_node_emits_failed_step_event(self):
        """节点未绑定接口 → 产出 status=failed 的 StepResult，error 信息入 response_body"""
        db = FakeDb(first_results=[None])  # CaseNodeConfig 查询 → None
        sink = MemorySink()
        ex = _executor(db, sink=sink)

        passed, wait_ms = ex._execute_node(100, "n1", {"id": "n1"})

        assert passed is False
        assert wait_ms == 0
        assert len(sink.steps) == 1
        ev = sink.steps[0]
        assert ev.status == "failed"
        assert ev.node_id == "n1"
        assert ev.response_status == 0
        assert "未绑定接口" in str(ev.response_body)
        assert ev.assertions == []


class TestEngineLayering:
    def test_engine_does_not_import_routers(self):
        """分层约束：engine 不得依赖 routers 层（持久化接缝的一部分）"""
        import inspect

        import app.engine.dag_executor as de

        src = inspect.getsource(de)
        assert "from ..routers" not in src, "engine 反向依赖 routers，应改走 services 层"
