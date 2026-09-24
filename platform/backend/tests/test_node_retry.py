# -*- coding: utf-8 -*-
"""环境级节点失败重试测试（请求层失败自动重发）。

接缝沿用 test_execute_node.py：DagExecutor(sink=MemorySink) + _execute_node，
http_client 用前 N 次抛 HttpStatusError(406)、之后成功的替身，
sleep 打桩避免真实等待。验证：
- 重试后成功：retry_count 入事件、请求体逐次原样重发
- 重试耗尽仍失败：失败收尾、尝试次数 = 重试次数 + 1
- 未配置重试（count=0）：只发一次
- 断言失败不触发重试（掩盖断言问题 + 写接口重复提交风险）
"""
from types import SimpleNamespace

import pytest

import app.engine.dag_executor as de
from tests.test_execute_node import FakeDb, MemorySink, _api, _config, _executor

from utils.exceptions import HttpStatusError


class FlakyHttpClient:
    """前 fail_times 次请求抛 406，之后返回成功响应；记录每次请求的 body"""

    def __init__(self, fail_times: int, response=None):
        self.headers: dict[str, str] = {}
        self.fail_times = fail_times
        self.response = response if response is not None else {"code": 200, "msg": "ok"}
        self.calls: list = []  # 每次 post 收到的 json body

    def post(self, path, json=None, timeout=None):
        self.calls.append(json)
        if len(self.calls) <= self.fail_times:
            raise HttpStatusError(406, path, '{"msg":"费用数据未同步"}')
        return self.response

    def get(self, path, params=None, timeout=None):
        return self.post(path, params, timeout)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """重试间隔打桩：不真实等待"""
    monkeypatch.setattr(de.time, "sleep", lambda s: None)


def _retry_executor(retry_count: int, interval: int = 1):
    env = SimpleNamespace(variables={}, timeout=5,
                          node_retry_count=retry_count, node_retry_interval=interval)
    sink = MemorySink()
    ex = _executor(FakeDb(first_results=[_config(api_id=10), _api()]),
                   env=env, sink=sink)
    return ex, sink


class TestNodeRetry:
    def test_retry_then_success_records_retry_count(self):
        """前 2 次 406、第 3 次成功：节点通过，事件携带 retry_count=2，请求体原样重发"""
        ex, sink = _retry_executor(retry_count=2)
        ex.http_client = FlakyHttpClient(fail_times=2, response={"code": 200, "data": {"id": 1}})

        passed, _ = ex._execute_node(100, "n1", {"id": "n1"})

        assert passed is True
        assert len(ex.http_client.calls) == 3
        ev = sink.steps[0]
        assert ev.status == "success"
        assert ev.retry_count == 2
        assert ev.response_status == 200
        # 三次请求体完全一致（与报告页手工重放同语义）
        assert ex.http_client.calls[0] == ex.http_client.calls[1] == ex.http_client.calls[2]

    def test_retry_exhausted_fails_with_retry_count(self):
        """配置重试 2 次但始终 406：共尝试 3 次后失败，事件携带 retry_count=2"""
        ex, sink = _retry_executor(retry_count=2)
        ex.http_client = FlakyHttpClient(fail_times=99)

        passed, _ = ex._execute_node(100, "n1", {"id": "n1"})

        assert passed is False
        assert len(ex.http_client.calls) == 3
        ev = sink.steps[0]
        assert ev.status == "failed"
        assert ev.retry_count == 2
        assert ev.response_status == 406
        assert "406" in str(ev.response_body)

    def test_no_retry_configured_sends_once(self):
        """环境未开重试（count=0）：失败只发一次，retry_count=0"""
        ex, sink = _retry_executor(retry_count=0)
        ex.http_client = FlakyHttpClient(fail_times=1)

        passed, _ = ex._execute_node(100, "n1", {"id": "n1"})

        assert passed is False
        assert len(ex.http_client.calls) == 1
        assert sink.steps[0].retry_count == 0

    def test_assertion_failure_does_not_retry(self):
        """断言失败不触发重试：请求成功但断言不过 → 只发一次"""
        config = _config(api_id=10, assertions=[
            {"type": "json_path_equals", "path": "$.code", "expected": 500},
        ])
        env = SimpleNamespace(variables={}, timeout=5,
                              node_retry_count=3, node_retry_interval=1)
        sink = MemorySink()
        ex = _executor(FakeDb(first_results=[config, _api()]), env=env, sink=sink)
        ex.http_client = FlakyHttpClient(fail_times=0, response={"code": 200})

        passed, _ = ex._execute_node(100, "n1", {"id": "n1"})

        assert passed is False
        assert len(ex.http_client.calls) == 1
        assert sink.steps[0].retry_count == 0
