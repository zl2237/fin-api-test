# -*- coding: utf-8 -*-
"""报告虚拟上下文测试：重放断言求值与续跑 seed 共用的节点命名空间拼装。

口径（参数模型 v2 / 断点续跑设计定稿）：
- 产出按节点分组 {node_id: {变量名: 值}}（不再平铺；row_vars 打底已随入参
  收敛到数据集行而移除——行数据承载 per-node 配置，不进注册表）
- 各 node「最新一次成功步骤」的 extracted_vars 覆盖合并（运行时提取赢）
- 失败步骤的提取值不进 seed（重跑时会重新提取）
- before_node：重放场景只拼步骤顺序在该 node 之前的成功步骤
"""
from types import SimpleNamespace

from app.engine.report_context import build_report_context


def _step(node_id, status, extracted=None, sid=0):
    return SimpleNamespace(id=sid, node_id=node_id, status=status,
                           extracted_vars=extracted)


class TestBuildReportContext:
    def test_empty_steps_returns_empty_seed(self):
        """无步骤：空 seed（数据集行不再以键值打底）"""
        assert build_report_context([]) == {}

    def test_same_name_vars_isolated_by_node(self):
        """同名变量按节点命名空间隔离还原（平铺覆盖已废止，冲突根治）"""
        steps = [
            _step("n1", "success", {"order_id": 777}, sid=1),
            _step("n2", "success", {"order_id": 888}, sid=2),
        ]
        ctx = build_report_context(steps)
        assert ctx == {"n1": {"order_id": 777}, "n2": {"order_id": 888}}

    def test_latest_success_wins_per_node(self):
        """同 node 多条成功（重跑替换场景）：步骤顺序后者覆盖生效"""
        steps = [
            _step("n1", "success", {"fee_id": "old"}, sid=1),
            _step("n2", "success", {"x": 1}, sid=2),
            _step("n1", "success", {"fee_id": "new"}, sid=3),
        ]
        ctx = build_report_context(steps)
        assert ctx["n1"]["fee_id"] == "new"
        assert ctx["n2"] == {"x": 1}

    def test_failed_step_extraction_excluded(self):
        """失败步骤的提取值不进 seed（其重跑时会重新提取）"""
        steps = [
            _step("n1", "success", {"a": 1}, sid=1),
            _step("n2", "failed", {"b": 2}, sid=2),
        ]
        ctx = build_report_context(steps)
        assert ctx == {"n1": {"a": 1}}

    def test_before_node_truncates_order(self):
        """before_node：只拼步骤顺序在该 node 之前的成功步骤（重放口径）"""
        steps = [
            _step("n1", "success", {"a": 1}, sid=1),
            _step("n2", "success", {"b": 2}, sid=2),
            _step("n3", "success", {"c": 3}, sid=3),
        ]
        ctx = build_report_context(steps, before_node="n3")
        assert ctx == {"n1": {"a": 1}, "n2": {"b": 2}}

    def test_before_node_not_found_includes_all(self):
        """before_node 不在步骤中（如 leftover 首节点）：拼全部成功步骤"""
        steps = [_step("n1", "success", {"a": 1}, sid=1)]
        ctx = build_report_context(steps, before_node="nX")
        assert ctx == {"n1": {"a": 1}}

    def test_none_extracted_vars_skipped(self):
        """extracted_vars 为 None 的步骤安全跳过"""
        steps = [
            _step("n1", "success", None, sid=1),
            _step("n2", "success", {"b": 2}, sid=2),
        ]
        ctx = build_report_context(steps)
        assert ctx == {"n2": {"b": 2}}
