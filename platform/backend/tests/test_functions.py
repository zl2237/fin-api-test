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


class TestTimestampMs:
    """13 位毫秒时间戳：requestCipher 协议的 requestTime 必须毫秒级（±5 分钟窗口），
    既有 timestamp 是 10 位秒级。"""

    def test_returns_13_digit_ms(self):
        ts = call_function("timestamp_ms", {})
        assert isinstance(ts, int)
        assert 10**12 <= ts < 10**13  # 13 位（2026 年 ≈ 1.79×10^12）

    def test_no_args_close_to_wall_clock_ms(self):
        assert abs(call_function("timestamp_ms", {}) - time.time() * 1000) < 2000

    def test_offset_in_seconds(self):
        base = call_function("timestamp_ms", {})
        delta = call_function("timestamp_ms", {"offset": 60}) - base
        assert 59_000 <= delta <= 61_000  # offset 秒语义，×1000 成毫秒

    def test_offset_negative(self):
        base = call_function("timestamp_ms", {})
        assert base - call_function("timestamp_ms", {"offset": -86400}) > 86_399_000

    def test_offset_accepts_string_const(self):
        # UI 入参常量以字符串保存（kind=const），与 timestamp 同口径
        assert call_function("timestamp_ms", {"offset": "10"}) - call_function("timestamp_ms", {}) \
            >= 9_000

    def test_params_metadata_registered(self):
        assert FUNCTIONS["timestamp_ms"]["params"] == ["offset"]


class TestCallFunctionGuard:
    def test_unknown_function_raises(self):
        with pytest.raises(ValueError, match="未知的内置函数"):
            call_function("no_such_fn", {})
