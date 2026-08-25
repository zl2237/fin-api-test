"""PreProcessor 行值覆盖 set_field（数据驱动：绑定即生效，节点配置零修改）。

语义（spec 增补）：数据集行值按列名自动覆盖前置处理 set_field 的同名字段——
- 列名 == set_field 完整 path（顶层字段）：行值直接覆盖，原值（字面量/生成函数/${context.x}）不执行
- 列名不匹配：原逻辑不变（表达式求值）
- iterate_set / delete_field 不受影响
"""
from app.engine.preprocessor import PreProcessor


class TestRowVarsOverride:
    def _mk(self, row_vars=None):
        return PreProcessor({}, row_vars=row_vars or {})

    def test_literal_value_overridden_by_row(self):
        """set_field 字面量被同名列行值覆盖（核心语义）"""
        pp = self._mk({"voy": "MY-VOYAGE"})
        body = pp.process(
            {"voy": "old"},
            [{"type": "set_field", "path": "voy", "value": "old"}],
        )
        assert body["voy"] == "MY-VOYAGE"

    def test_expression_value_not_evaluated_when_overridden(self):
        """原值为生成函数表达式时也不执行，直接用行值"""
        pp = self._mk({"bl_no": "ROW001"})
        body = pp.process(
            {},
            [{"type": "set_field", "path": "bl_no", "value": "${generate_bl_no(prefix='smoke')}"}],
        )
        assert body["bl_no"] == "ROW001"

    def test_context_ref_value_overridden_by_row(self):
        """${context.x} 引用同样被行值覆盖（下游节点不必改配置）"""
        pp = self._mk({"bl_no": "ROW002"})
        body = pp.process(
            {"bl_no": "PREV"},
            [{"type": "set_field", "path": "bl_no", "value": "${context.bl_no}"}],
        )
        assert body["bl_no"] == "ROW002"

    def test_no_row_var_keeps_original(self):
        """列名不匹配 → 原逻辑（表达式求值）"""
        pp = self._mk({"other": "x"})
        body = pp.process(
            {},
            [{"type": "set_field", "path": "bl_no", "value": "LITERAL"}],
        )
        assert body["bl_no"] == "LITERAL"

    def test_nested_path_not_matched_by_leaf_name(self):
        """仅完整 path 匹配：嵌套 a.b 不被列名 b 覆盖"""
        pp = self._mk({"b": "ROW"})
        body = pp.process(
            {"a": {"b": "old"}},
            [{"type": "set_field", "path": "a.b", "value": "old"}],
        )
        assert body["a"]["b"] == "old"

    def test_override_syncs_to_extracted_pool(self):
        """覆盖后的行值同步进上下文池（下游 ${xxx} 引用拿到行值）"""
        pp = self._mk({"bl_no": "ROW003"})
        extracted = {}
        pp.process(
            {},
            [{"type": "set_field", "path": "bl_no", "value": "${generate_bl_no()}"}],
            extracted,
        )
        assert extracted["bl_no"] == "ROW003"

    def test_expr_ref_row_var_still_works(self):
        """既有机制不变：value 里显式 ${列名} 引用行值（列名 != path）。
        生产路径中行值已合入 context 池（ExecutionContext），此处直接构造等价状态"""
        pp = PreProcessor({"extracted": {"bl_no": "ROW004"}}, row_vars={"bl_no": "ROW004"})
        body = pp.process(
            {},
            [{"type": "set_field", "path": "track_bl_no", "value": "${bl_no}"}],
        )
        assert body["track_bl_no"] == "ROW004"

    def test_no_row_vars_at_all(self):
        """普通执行（无数据集）行为完全不变"""
        pp = self._mk(None)
        body = pp.process(
            {},
            [{"type": "set_field", "path": "voy", "value": "LITERAL"}],
        )
        assert body["voy"] == "LITERAL"


class TestApiDefaultOverride:
    """API 字段默认值同样被行值覆盖（所有"写死"的请求参数都可数据驱动）"""

    def test_top_level_field_overridden(self):
        from app.services.body_builder import apply_row_overrides
        body = apply_row_overrides({"voy": "我是航次", "teu": "56"}, {"voy": "V-01", "teu": "11"})
        assert body == {"voy": "V-01", "teu": "11"}

    def test_only_existing_fields_overridden(self):
        """只覆盖请求中已存在的字段，不新增参数"""
        from app.services.body_builder import apply_row_overrides
        body = apply_row_overrides({"voy": "old"}, {"voy": "NEW", "extra": "x"})
        assert body == {"voy": "NEW"}

    def test_no_row_vars_returns_body_unchanged(self):
        from app.services.body_builder import apply_row_overrides
        body = {"voy": "old"}
        assert apply_row_overrides(body, None) is body
        assert apply_row_overrides(body, {}) is body

    def test_array_body_first_element(self):
        """数组请求体作用于首元素（与前置处理数组语义一致）"""
        from app.services.body_builder import apply_row_overrides
        body = apply_row_overrides([{"voy": "old"}, {"voy": "keep"}], {"voy": "NEW"})
        assert body[0]["voy"] == "NEW" and body[1]["voy"] == "keep"

    def test_expression_field_not_overridden(self):
        """上游提取注入的字段（默认值含 ${}）不在数据集覆盖范围：
        只覆盖写死的字面量，动态注入的交给表达式引擎"""
        from app.services.body_builder import apply_row_overrides
        body = apply_row_overrides(
            {"order_id": "${order_id}", "voy": "old"},
            {"order_id": "999", "voy": "NEW"},
        )
        assert body["order_id"] == "${order_id}"
        assert body["voy"] == "NEW"
