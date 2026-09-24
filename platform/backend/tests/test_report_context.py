# -*- coding: utf-8 -*-
"""报告虚拟上下文测试：重放断言求值与续跑 seed 共用的 extracted 拼装。

口径（断点续跑设计定稿）：
- 数据集当前 row_vars 打底（${} 池初始语义，同 ExecutionContext）
- 各 node「最新一次成功步骤」的 extracted_vars 覆盖合并（运行时提取赢）
- 失败步骤的提取值不进池（重跑时会重新提取）
- before_node：重放场景只拼拓扑序在该 node 之前的成功步骤
"""
from types import SimpleNamespace

from app.engine.report_context import build_report_context


def _step(node_id, status, extracted=None, sid=0):
    return SimpleNamespace(id=sid, node_id=node_id, status=status,
                           extracted_vars=extracted)


class TestBuildReportContext:
    def test_empty_steps_returns_row_vars(self):
        """无步骤：extracted 即数据集行值（${} 池初始语义）"""
        ctx = build_report_context([], row_vars={"order_id": 666})
        assert ctx == {"order_id": 666}

    def test_extraction_overrides_row_vars_same_name(self):
        """运行时提取覆盖数据集同名值（与 ExecutionContext update 语义一致）"""
        steps = [_step("n1", "success", {"order_id": 777}, sid=1)]
        ctx = build_report_context(steps, row_vars={"order_id": 666})
        assert ctx["order_id"] == 777

    def test_latest_success_wins_per_node(self):
        """同 node 多条成功（重跑替换场景）：id 最大的成功步骤值生效"""
        steps = [
            _step("n1", "success", {"fee_id": "old"}, sid=1),
            _step("n2", "success", {"x": 1}, sid=2),
            _step("n1", "success", {"fee_id": "new"}, sid=3),
        ]
        ctx = build_report_context(steps)
        assert ctx["fee_id"] == "new"
        assert ctx["x"] == 1

    def test_failed_step_extraction_excluded(self):
        """失败步骤的提取值不进池（其重跑时会重新提取）"""
        steps = [
            _step("n1", "success", {"a": 1}, sid=1),
            _step("n2", "failed", {"b": 2}, sid=2),
        ]
        ctx = build_report_context(steps)
        assert ctx == {"a": 1}

    def test_before_node_truncates_order(self):
        """before_node：只拼步骤顺序在该 node 之前的成功步骤（重放口径）"""
        steps = [
            _step("n1", "success", {"a": 1}, sid=1),
            _step("n2", "success", {"b": 2}, sid=2),
            _step("n3", "success", {"c": 3}, sid=3),
        ]
        ctx = build_report_context(steps, before_node="n3")
        assert ctx == {"a": 1, "b": 2}

    def test_before_node_not_found_includes_all(self):
        """before_node 不在步骤中（如 leftover 首节点）：拼全部成功步骤"""
        steps = [_step("n1", "success", {"a": 1}, sid=1)]
        ctx = build_report_context(steps, before_node="nX")
        assert ctx == {"a": 1}

    def test_none_extracted_vars_skipped(self):
        """extracted_vars 为 None 的步骤安全跳过"""
        steps = [
            _step("n1", "success", None, sid=1),
            _step("n2", "success", {"b": 2}, sid=2),
        ]
        ctx = build_report_context(steps, row_vars={"r": 0})
        assert ctx == {"r": 0, "b": 2}
