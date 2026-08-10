"""json_safe 模块单测：大整数序列化，防止前端精度丢失。"""
from app.json_safe import sanitize_bigints, _is_big_int, JS_MAX_SAFE_INT, JS_MIN_SAFE_INT


class TestIsBigInt:
    def test_normal_int_not_big(self):
        assert _is_big_int(100) is False
        assert _is_big_int(0) is False
        assert _is_big_int(-100) is False

    def test_big_int_over_max(self):
        assert _is_big_int(JS_MAX_SAFE_INT + 1) is True

    def test_big_int_under_min(self):
        assert _is_big_int(JS_MIN_SAFE_INT - 1) is True

    def test_boundary_not_big(self):
        # 恰好等于边界值，不超出，不算 big int
        assert _is_big_int(JS_MAX_SAFE_INT) is False
        assert _is_big_int(JS_MIN_SAFE_INT) is False

    def test_bool_excluded(self):
        # bool 是 int 子类，但不应被当作大整数
        assert _is_big_int(True) is False
        assert _is_big_int(False) is False

    def test_float_integer_over_max(self):
        assert _is_big_int(float(JS_MAX_SAFE_INT + 1)) is True

    def test_float_non_integer(self):
        assert _is_big_int(1.5) is False

    def test_string_not_big(self):
        assert _is_big_int("123") is False
        assert _is_big_int("very long string") is False


class TestSanitizeBigints:
    def test_dict_big_int_to_str(self):
        snowflake_id = 343557272766513152
        result = sanitize_bigints({"id": snowflake_id})
        assert result == {"id": "343557272766513152"}

    def test_list_big_int_to_str(self):
        result = sanitize_bigints([343557272766513152, 100])
        assert result == ["343557272766513152", 100]

    def test_nested_dict(self):
        result = sanitize_bigints({"data": {"id": 343557272766513152, "code": 200}})
        assert result == {"data": {"id": "343557272766513152", "code": 200}}

    def test_nested_list(self):
        result = sanitize_bigints({"items": [343557272766513152, {"sub": 343557272766513153}]})
        assert result == {"items": ["343557272766513152", {"sub": "343557272766513153"}]}

    def test_bool_preserved(self):
        result = sanitize_bigints({"flag": True, "active": False})
        assert result == {"flag": True, "active": False}

    def test_small_int_preserved(self):
        result = sanitize_bigints({"count": 42, "code": 200})
        assert result == {"count": 42, "code": 200}

    def test_string_preserved(self):
        result = sanitize_bigints({"name": "test", "id_str": "343557272766513152"})
        assert result == {"name": "test", "id_str": "343557272766513152"}

    def test_does_not_mutate_original(self):
        original = {"id": 343557272766513152}
        sanitize_bigints(original)
        # 原对象不被修改
        assert original == {"id": 343557272766513152}

    def test_empty_containers(self):
        assert sanitize_bigints({}) == {}
        assert sanitize_bigints([]) == []
