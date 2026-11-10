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

from app.engine.report_context import build_report_context, iter_replay_paths


def _step(node_id, status, extracted=None, sid=0, body=None):
    return SimpleNamespace(id=sid, node_id=node_id, status=status,
                           extracted_vars=extracted, request_body=body)


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
        assert ctx["n2"] == {"b": 2}

    def test_request_body_replayed_as_input_vars(self):
        """入参回放：请求体快照按执行期口径（完整路径+末段别名）进 seed——
        续跑前缀节点被跳过不再真实执行，下游 {{节点.入参}} 引用靠此还原（915）"""
        steps = [
            _step("n_create", "success", {"order_id": 1}, sid=1,
                  body={"bl_no": "BL001", "select_list": [{"order_id": 9}]}),
        ]
        ctx = build_report_context(steps)
        assert ctx["n_create"]["bl_no"] == "BL001"
        # 嵌套路径 + 末段别名（与 prepare_request._register 同口径）
        assert ctx["n_create"]["select_list.0.order_id"] == 9
        assert ctx["n_create"]["order_id"] == 1  # 提取名优先，入参别名不覆盖

    def test_array_body_replayed_by_first_element(self):
        """数组请求体：锚定首元素字段展开（配置路径口径 currency 而非 0.currency）"""
        steps = [_step("n1", "success", body=[{"currency": "USD"}, {"currency": "CNY"}], sid=1)]
        ctx = build_report_context(steps)
        assert ctx["n1"]["currency"] == "USD"

    def test_latest_success_body_overrides_history(self):
        """同 node 重跑成功：入参回放同提取值一样「最新成功覆盖」"""
        steps = [
            _step("n1", "success", body={"bl_no": "OLD"}, sid=1),
            _step("n1", "success", body={"bl_no": "NEW"}, sid=2),
        ]
        ctx = build_report_context(steps)
        assert ctx["n1"]["bl_no"] == "NEW"

    def test_body_string_json_parsed(self):
        """request_body 为 JSON 字符串（如 pymysql 直查场景）也能回放"""
        steps = [_step("n1", "success", body='{"bl_no": "BL9"}', sid=1)]
        ctx = build_report_context(steps)
        assert ctx["n1"]["bl_no"] == "BL9"

    def test_nested_tail_literal_does_not_clobber_exact_key(self):
        """exec 1571 回归：嵌套同尾字段（录制残留字面值/空串）不得顶掉顶层同名人参。

        事故链：追加服务项目 body 的 order_sub.0.order_id 携带录制时代的
        老订单字面值、supplier.1.order_id 为空串，旧「后写覆盖」别名把它们
        依次盖到顶层 order_id 上，下游 {{node.order_id}} 全部引用错单。
        """
        body = {
            "bl_no": "BL001",
            "order_id": "378385244119630848",           # 本次运行真实值（顶层实参）
            "supplier": [{"order_id": "378385244119630848"}, {"order_id": ""}],
            "order_sub": [{"order_id": "348342035100467200"}],  # 录制残留
        }
        # 生成器层：精确键先出、别名被精确键屏蔽
        writes = dict(iter_replay_paths(body))
        assert writes["order_id"] == "378385244119630848"
        assert writes["order_sub.0.order_id"] == "348342035100467200"  # 嵌套精确路径保留
        # seed 层（消费方盲写覆盖口径）最终值不受别名污染
        steps = [_step("n_edit", "success", body=body, sid=1)]
        ctx = build_report_context(steps)
        assert ctx["n_edit"]["order_id"] == "378385244119630848"

    def test_alias_fills_vacancy_first_wins(self):
        """无同名精确键时别名照常补位（legacy {{节点.末段}} 引用可用）；多别名先到先得"""
        body = {"a": {"user_id": 5}, "b": {"user_id": 7}}
        writes = dict(iter_replay_paths(body))
        assert writes["user_id"] == 5
        assert writes["b.user_id"] == 7
