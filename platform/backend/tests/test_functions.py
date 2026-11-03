# -*- coding: utf-8 -*-
"""内置函数注册表测试：timestamp 的 offset 语义与 call_function 防御。"""
import time

import pytest

from app.engine.functions import FUNCTIONS, call_function


class TestTimestampOffset:
    def test_no_args_returns_now(self):
        assert abs(call_function("timestamp", {}) - time.time()) < 2

    def test_offset_positive(self):
        base = call_function("timestamp", {})
        assert call_function("timestamp", {"offset": 86400}) - base == 86400

    def test_offset_negative(self):
        base = call_function("timestamp", {})
        assert base - call_function("timestamp", {"offset": -86400}) == 86400

    def test_offset_accepts_string_const(self):
        # UI 入参常量以字符串保存（kind=const），与 random_int 等既有函数口径一致
        assert call_function("timestamp", {"offset": "86400"}) - call_function("timestamp", {}) >= 86399

    def test_params_metadata_registered(self):
        assert FUNCTIONS["timestamp"]["params"] == ["offset"]


class TestConcat:
    def test_suffix_join(self):
        # Q1 场景：上游 id + 业务后缀
        assert call_function("concat", {"a": "375820537252807680", "b": "_CustomerFinance"}) \
            == "375820537252807680_CustomerFinance"

    def test_sep(self):
        assert call_function("concat", {"a": "x", "b": "y", "sep": "-"}) == "x-y"

    def test_numeric_coerced(self):
        # ref 到数值型变量时按字符串拼接
        assert call_function("concat", {"a": 123, "b": "_T"}) == "123_T"

    def test_missing_part_treated_empty(self):
        assert call_function("concat", {"a": "x"}) == "x"

    def test_params_metadata_registered(self):
        assert FUNCTIONS["concat"]["params"] == ["a", "b", "sep"]


class TestCallFunctionGuard:
    def test_unknown_function_raises(self):
        with pytest.raises(ValueError, match="未知的内置函数"):
            call_function("no_such_fn", {})
