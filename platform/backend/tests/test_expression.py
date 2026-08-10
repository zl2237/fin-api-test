"""expression 模块单测：表达式引擎（变量引用、函数调用、字符串替换、SQL注入转义）。"""
from app.engine.expression import ExpressionEngine, _parse_kwargs


class TestParseKwargs:
    def test_string_value(self):
        assert _parse_kwargs("s='abc'") == {"s": "abc"}

    def test_int_value(self):
        assert _parse_kwargs("n=10") == {"n": 10}

    def test_float_value(self):
        assert _parse_kwargs("f=1.5") == {"f": 1.5}

    def test_multiple_kwargs(self):
        result = _parse_kwargs("s='abc', n=10")
        assert result == {"s": "abc", "n": 10}

    def test_empty_string(self):
        assert _parse_kwargs("") == {}

    def test_double_quoted_string(self):
        assert _parse_kwargs('s="hello"') == {"s": "hello"}

    def test_negative_int(self):
        assert _parse_kwargs("n=-5") == {"n": -5}


class TestEvaluateVariable:
    def test_extracted_variable(self):
        engine = ExpressionEngine({"extracted": {"order_id": 123}})
        assert engine.evaluate("${order_id}") == 123

    def test_env_variable(self):
        engine = ExpressionEngine({"env": {"base_url": "http://api.test"}})
        assert engine.evaluate("${env.base_url}") == "http://api.test"

    def test_context_prefix(self):
        engine = ExpressionEngine({"extracted": {"bl_no": "BL001"}})
        assert engine.evaluate("${context.bl_no}") == "BL001"

    def test_undefined_variable_preserved(self):
        engine = ExpressionEngine({"extracted": {}})
        # 未定义变量保留原占位符
        assert engine.evaluate("${unknown}") == "${unknown}"

    def test_nested_env_path(self):
        engine = ExpressionEngine({"env": {"db": {"host": "127.0.0.1"}}})
        assert engine.evaluate("${env.db.host}") == "127.0.0.1"


class TestEvaluateFunction:
    def test_upper(self):
        engine = ExpressionEngine({})
        assert engine.evaluate("${upper(s='abc')}") == "ABC"

    def test_lower(self):
        engine = ExpressionEngine({})
        assert engine.evaluate("${lower(s='ABC')}") == "abc"

    def test_md5(self):
        engine = ExpressionEngine({})
        assert engine.evaluate("${md5(s='abc')}") == "900150983cd24fb0d6963f7d28e17f72"

    def test_uuid_format(self):
        engine = ExpressionEngine({})
        result = engine.evaluate("${uuid()}")
        assert isinstance(result, str)
        # UUID 格式：8-4-4-4-12
        assert len(result) == 36

    def test_random_int_range(self):
        engine = ExpressionEngine({})
        for _ in range(20):
            val = engine.evaluate("${random_int(min=1, max=10)}")
            assert 1 <= val <= 10

    def test_random_string_length(self):
        engine = ExpressionEngine({})
        result = engine.evaluate("${random_string(length=16)}")
        assert isinstance(result, str)
        assert len(result) == 16

    def test_now_with_format(self):
        engine = ExpressionEngine({})
        result = engine.evaluate("${now(format='%Y-%m-%d')}")
        assert len(result) == 10  # YYYY-MM-DD

    def test_date_add(self):
        engine = ExpressionEngine({})
        result = engine.evaluate("${date_add(days=1, format='%Y-%m-%d')}")
        assert len(result) == 10


class TestEvaluateStringReplace:
    def test_embedded_variable(self):
        engine = ExpressionEngine({"extracted": {"id": 5}})
        assert engine.evaluate("id=${id}") == "id=5"

    def test_multiple_embedded(self):
        engine = ExpressionEngine({"extracted": {"a": 1, "b": 2}})
        assert engine.evaluate("${a}+${b}=3") == "1+2=3"

    def test_plain_string(self):
        engine = ExpressionEngine({})
        assert engine.evaluate("plain text") == "plain text"

    def test_undefined_in_embedded_preserved(self):
        engine = ExpressionEngine({"extracted": {}})
        assert engine.evaluate("val=${missing}") == "val=${missing}"


class TestEvaluateDictList:
    def test_dict_evaluate(self):
        engine = ExpressionEngine({"extracted": {"id": 99}})
        result = engine.evaluate({"key": "${id}", "static": "abc"})
        assert result == {"key": 99, "static": "abc"}

    def test_list_evaluate(self):
        engine = ExpressionEngine({"extracted": {"id": 99}})
        result = engine.evaluate(["${id}", "static"])
        assert result == [99, "static"]


class TestInjectVars:
    def test_string_value_escaped(self):
        # _inject_vars 自己负责给字符串值加引号，SQL 中不应预先带引号
        engine = ExpressionEngine({"extracted": {"name": "O'Brien"}})
        result = engine._inject_vars("WHERE name=${name}")
        # 单引号转义为两个单引号，整体被引号包裹
        assert result == "WHERE name='O''Brien'"

    def test_int_value(self):
        engine = ExpressionEngine({"extracted": {"id": 123}})
        result = engine._inject_vars("WHERE id=${id}")
        assert result == "WHERE id=123"

    def test_none_value_to_null(self):
        engine = ExpressionEngine({"extracted": {"x": None}})
        result = engine._inject_vars("WHERE x=${x}")
        assert result == "WHERE x=NULL"

    def test_context_prefix(self):
        engine = ExpressionEngine({"extracted": {"bl_no": "BL001"}})
        result = engine._inject_vars("WHERE bl_no=${context.bl_no}")
        assert result == "WHERE bl_no='BL001'"

    def test_undefined_wrapped_in_quotes(self):
        # 未定义变量：m.group(0) 作为字符串返回，会被加引号
        engine = ExpressionEngine({"extracted": {}})
        result = engine._inject_vars("WHERE x=${missing}")
        assert result == "WHERE x='${missing}'"
