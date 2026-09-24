"""保存防护单测：后置提取 SQL 基本校验 + 执行中拦截。"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.crud.executions import ensure_case_not_running, running_execution_of
from app.routers.testcases import validate_post_extract_sql


def _cfg(sql: str | None = None, source: str = "db"):
    rule = {"name": "pay_apply_id", "source": source, "json_path": "", "field": "x"}
    if sql is not None:
        rule["sql"] = sql
    return [{"node_id": "n1", "api_id": 1, "post_extract": [rule]}]


class TestValidatePostExtractSql:
    def test_ok_sql_with_expr_and_underscore_columns(self):
        """正常 SQL（${} 变量 + 下划线列名 user_group）不误报"""
        validate_post_extract_sql(_cfg(
            "SELECT user_group, bl_no FROM sys_order WHERE user_group = ${group} AND bl_no = ${bl_no}"))

    def test_glued_keyword_rejected(self):
        """列名与 FROM 粘连（idfrom）→ 拒绝（真实事故：静默坏 SQL 提取为空）"""
        with pytest.raises(ValueError, match="粘连"):
            validate_post_extract_sql(_cfg(
                "SELECT pay_invoice__apply_idfrom sys_pay_invoice_apply where bl_nos = ${bl_no}"))

    def test_select_missing_from_rejected(self):
        """SELECT 无独立 FROM → 拒绝（粘连的另一信号）"""
        with pytest.raises(ValueError, match="FROM"):
            validate_post_extract_sql(_cfg("SELECT pay_id, bl_no WHERE x = 1"))

    def test_not_starting_with_keyword_rejected(self):
        """不以 SQL 关键字开头 → 拒绝"""
        with pytest.raises(ValueError, match="开头"):
            validate_post_extract_sql(_cfg("pay_id from sys_order"))

    def test_update_glued_where_rejected(self):
        """UPDATE 语句 where 粘连同样拦截；response 来源不校验"""
        with pytest.raises(ValueError, match="粘连"):
            validate_post_extract_sql(_cfg("UPDATE sys_order set x = 1where id = ${id}"))
        validate_post_extract_sql(_cfg("$.data.id", source="response"))

    def test_empty_and_none_pass(self):
        """空 SQL / 空配置直过（json_path 来源不涉及）"""
        validate_post_extract_sql(_cfg(""))
        validate_post_extract_sql(None)
        validate_post_extract_sql([{"node_id": "n1", "post_extract": []}])


class _Query:
    def __init__(self, first_val):
        self._first_val = first_val

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def first(self):
        return self._first_val


class TestEnsureCaseNotRunning:
    def _db(self, running):
        rec = SimpleNamespace(id=77, case_id=5) if running else None
        db = SimpleNamespace(query=lambda m: _Query(rec))
        return db

    def test_running_blocks(self):
        with pytest.raises(ValueError, match="正在执行中.*#77"):
            ensure_case_not_running(self._db(True), 5, "保存用例")

    def test_not_running_passes(self):
        with patch("app.crud.executions.running_execution_of", return_value=None):
            ensure_case_not_running(SimpleNamespace(), 5)

    def test_zombie_running_ignored_by_cutoff(self):
        """僵尸 running（started_at 早于阈值）不拦截——SQL 过滤条件带 cutoff，
        用查询捕获验证 filter 含 started_at 条件"""
        captured = {}

        class _Cap:
            def filter(self, *a, **k):
                captured["conds"] = [str(x) for x in a]
                return self

            def order_by(self, *a, **k):
                return self

            def first(self):
                return None

        running_execution_of(SimpleNamespace(query=lambda m: _Cap()), 5)
        assert any("started_at" in c for c in captured["conds"])
