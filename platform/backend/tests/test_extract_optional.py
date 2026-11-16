# -*- coding: utf-8 -*-
"""可选提取（rule.optional）语义：未取到不判节点失败，改标 __miss__。

必选规则（缺省）维持硬失败语义（test_extractor_fail.py 锁定）；本文件锁软化
边界：仅 optional 规则软化、成功值与必选错误原样、DB 提取同口径。
"""
from types import SimpleNamespace

from app.engine.dag_executor import DagExecutor
from app.engine.extractor import (
    Extractor, is_extract_error, is_extract_miss, soften_optional_extracts,
)
from app.engine.variables import VariableRegistry


def _rule(name="v1", optional=None, **kw):
    base = {"name": name, "source": "response", "json_path": "$.data.id"}
    if optional is not None:
        base["optional"] = optional
    base.update(kw)
    return base


class TestSoftenOptionalExtracts:
    def test_optional_miss_softened(self):
        extracted = {"v1": {"__error__": "jsonpath 未命中：$.data.id"}}
        out = soften_optional_extracts(extracted, [_rule(optional=True)])
        assert is_extract_miss(out["v1"])
        assert out["v1"]["__miss__"] == "jsonpath 未命中：$.data.id"
        assert out["v1"]["optional"] is True
        assert not is_extract_error(out["v1"])  # 不再判失败的关键

    def test_required_miss_untouched(self):
        extracted = {"v1": {"__error__": "jsonpath 未命中：$.data.id"}}
        out = soften_optional_extracts(extracted, [_rule()])
        assert is_extract_error(out["v1"]) and not is_extract_miss(out["v1"])

    def test_success_value_untouched(self):
        extracted = {"v1": 42, "v2": {"__error__": "x"}}
        rules = [_rule(optional=True), _rule(name="v2", optional=True)]
        out = soften_optional_extracts(extracted, rules)
        assert out["v1"] == 42  # 命中的可选提取就是普通值
        assert is_extract_miss(out["v2"])

    def test_no_optional_rules_is_noop(self):
        extracted = {"v1": {"__error__": "x"}}
        assert soften_optional_extracts(extracted, [_rule()]) == extracted
        assert soften_optional_extracts(extracted, None) == extracted

    def test_db_extract_same_semantics(self):
        """DB 提取同口径：查询无结果 + optional → __miss__（不被重查语义混淆）"""
        reg = VariableRegistry()
        rules = [{"name": "audit_id", "source": "db", "sql": "SELECT 1", "optional": True}]

        class _EmptyDb:
            def query(self, sql):
                return []

        out = Extractor(db_client=_EmptyDb()).extract({}, rules, reg, "n1")
        out = soften_optional_extracts(out, rules)
        assert is_extract_miss(out["audit_id"])
        assert reg.read("n1", "audit_id") is None  # 注册表口径：无值（下游引用同旧语义）


class TestNodeVerdict:
    """节点判定：可选未取到不进 extract_failed（tail_passed 仅由断言决定）"""

    def _tail(self, post_extract, response, assertions=None):
        """直调 DagExecutor._extract_and_assert（不发请求，收尾纯逻辑）"""
        exe = DagExecutor.__new__(DagExecutor)  # 只用收尾逻辑，不初始化客户端
        exe.context = SimpleNamespace(registry=VariableRegistry())
        exe.db_client = None
        exe.extractor = Extractor()
        config = SimpleNamespace(post_extract=post_extract,
                                 assertions=assertions or [])
        return exe._extract_and_assert("n1", config, response, 200, 10)

    def test_optional_miss_node_passes(self):
        rules = [_rule(optional=True)]
        extracted, _, tail = self._tail(rules, {"data": {}})
        assert tail is True
        assert is_extract_miss(extracted["v1"])

    def test_optional_miss_plus_assertion_fail_blocks(self):
        """仅断言阻塞：可选未取到 + 断言失败 → 节点失败"""
        rules = [_rule(optional=True)]
        assertions = [{"type": "json_path_equals", "path": "$.code", "expected": 0}]
        extracted, results, tail = self._tail(rules, {"data": {}, "code": 1}, assertions)
        assert tail is False
        assert results[0]["pass"] is False

    def test_required_miss_still_fails(self):
        extracted, _, tail = self._tail([_rule()], {"data": {}})
        assert tail is False
        assert is_extract_error(extracted["v1"])

    def test_optional_hit_records_plain_value(self):
        extracted, _, tail = self._tail([_rule(optional=True)], {"data": {"id": 7}})
        assert tail is True
        assert extracted["v1"] == 7
