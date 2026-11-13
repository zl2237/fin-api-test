# -*- coding: utf-8 -*-
"""内置函数注册表测试：timestamp 的 offset 语义与 call_function 防御。"""
import time

import pytest

from app.engine.functions import FUNCTIONS, call_function, parse_function_call


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


class TestParseFunctionCall:
    """`函数名(参数...)` 调用语法解析（调试链路示例值求值）。

    仅已注册函数名认领；未注册/非调用形态一律 None（原样发送不误伤）。
    """

    def test_no_args(self):
        assert parse_function_call("timestamp_ms()") == {"func": "timestamp_ms", "kwargs": {}}

    def test_whitespace_tolerant(self):
        assert parse_function_call("  timestamp_ms( ) ") == {"func": "timestamp_ms", "kwargs": {}}

    def test_positional_maps_to_declared_params(self):
        # 位置参数按 FUNCTIONS 声明顺序补位：timestamp_ms(60) ≡ offset=60
        assert parse_function_call("timestamp_ms(60)") == \
            {"func": "timestamp_ms", "kwargs": {"offset": 60}}

    def test_keyword_raw_text_value(self):
        # 裸文本值（非 JSON）：format=%Y-%m-%d 原样成串
        assert parse_function_call("now(format=%Y-%m-%d)") == \
            {"func": "now", "kwargs": {"format": "%Y-%m-%d"}}

    def test_keyword_json_scalars(self):
        assert parse_function_call('md5(s="hello")') == {"func": "md5", "kwargs": {"s": "hello"}}
        assert parse_function_call("random_int(min=1, max=99)") == \
            {"func": "random_int", "kwargs": {"min": 1, "max": 99}}

    def test_quoted_comma_not_split(self):
        assert parse_function_call('concat(a="x,y", b=2)') == \
            {"func": "concat", "kwargs": {"a": "x,y", "b": 2}}

    def test_eq_inside_quoted_value_not_keyword(self):
        # 引号内的 = 是值的一部分，不切成关键字参数
        spec = parse_function_call('md5(s="a=b")')
        assert spec == {"func": "md5", "kwargs": {"s": "a=b"}}

    def test_positional_and_keyword_mix(self):
        # date_add 声明 [base, days, format]：位置 3 补到未被关键字占用的 base
        spec = parse_function_call("date_add(3, format=%Y/%m/%d)")
        assert spec == {"func": "date_add", "kwargs": {"base": 3, "format": "%Y/%m/%d"}}

    def test_keyword_beats_positional(self):
        # offset 已被关键字占用，位置参数不覆盖
        spec = parse_function_call("timestamp_ms(999, offset=60)")
        assert spec == {"func": "timestamp_ms", "kwargs": {"offset": 60}}

    def test_unregistered_name_returns_none(self):
        assert parse_function_call("foo(1)") is None
        assert parse_function_call("timestmap_ms()") is None  # 拼错=未注册=原样发送

    def test_non_call_shape_returns_none(self):
        assert parse_function_call("timestamp_ms") is None  # 裸函数名不求值（防误伤）
        assert parse_function_call("hello world") is None
        assert parse_function_call("(x)") is None
        assert parse_function_call("a b(1)") is None  # 名字后有杂字符

    def test_non_string_returns_none(self):
        assert parse_function_call(123) is None
        assert parse_function_call(None) is None

    def test_parse_then_call_end_to_end(self):
        spec = parse_function_call("timestamp_ms(offset=60)")
        val = call_function(spec["func"], spec["kwargs"])
        assert abs(val - time.time() * 1000 - 60_000) < 5_000
