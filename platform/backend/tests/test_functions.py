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


class TestCallFunctionGuard:
    def test_unknown_function_raises(self):
        with pytest.raises(ValueError, match="未知的内置函数"):
            call_function("no_such_fn", {})
