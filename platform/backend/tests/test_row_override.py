"""PreProcessor 三级取值优先级（引擎定案）。

请求体参数取值：数据集行值(1) > 用例编排 set_field(2) > 接口字段默认值(3)。
动态绑定例外：数据集 = 除动态绑定（值为 ${} 表达式：上游提取注入/生成函数）外
的所有字段集合——表达式照常求值，行值同名列不压制。

- 列名 == set_field 完整 path（顶层）且值为字面量：行值直接生效（优先级 1）
- 嵌套 path 顶层段 == 列名（行值已整块替换该对象）且值为字面量：写入跳过（防盖回行值）
- 值含 ${}（动态绑定）：表达式求值，优先级 2 生效，行值不压制
- 列名不匹配 / 行值为空（单元格未配置）：原逻辑不变（表达式求值或字面量）
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

    def test_dynamic_generate_not_suppressed_by_row(self):
        """动态绑定（生成函数）不被行值压制：表达式照常求值（三级优先级例外）"""
        pp = self._mk({"bl_no": "ROW001"})
        body = pp.process(
            {},
            [{"type": "set_field", "path": "bl_no", "value": "${generate_bl_no(prefix='smoke')}"}],
        )
        assert body["bl_no"].startswith("smoke")
        assert body["bl_no"] != "ROW001"

    def test_dynamic_context_ref_not_suppressed_by_row(self):
        """动态绑定（${context.x} 上游提取注入）不被行值压制：取上下文池的值"""
        pp = PreProcessor({"extracted": {"bl_no": "PREV"}}, row_vars={"bl_no": "ROW002"})
        body = pp.process(
            {},
            [{"type": "set_field", "path": "bl_no", "value": "${context.bl_no}"}],
        )
        assert body["bl_no"] == "PREV"

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

    def test_nested_literal_under_row_column_skipped(self):
        """嵌套字面量写入落在行值整块替换的对象下 → 跳过（快照残留防盖回行值）。

        场景：数据集列 to_customer 整对象行值覆盖后，快照 pre_process 里
        生成期的字面量 set_field to_customer.xxx.yyy 不得再改写它"""
        pp = self._mk({"to_customer": {"put_amount": {"standard_list": [{"policy_sub_id": "460"}]}}})
        body = pp.process(
            {"to_customer": {"put_amount": {"standard_list": [{"policy_sub_id": "460"}]}}},
            [{"type": "set_field", "path": "to_customer.put_amount.standard_list.0.policy_sub_id",
              "value": "343613802069098496"}],
        )
        assert body["to_customer"]["put_amount"]["standard_list"][0]["policy_sub_id"] == "460"

    def test_nested_expression_under_row_column_still_runs(self):
        """嵌套 ${} 表达式写入不受行值覆盖影响（运行时注入仍执行）"""
        pp = PreProcessor({"extracted": {"order_id": "OID-1"}},
                          row_vars={"to_customer": {"remark": "row"}})
        body = pp.process(
            {"to_customer": {"remark": "row"}},
            [{"type": "set_field", "path": "to_customer.order_id", "value": "${context.order_id}"}],
        )
        assert body["to_customer"]["order_id"] == "OID-1"
        assert body["to_customer"]["remark"] == "row"

    def test_nested_literal_under_non_row_column_kept(self):
        """嵌套字面量顶层段不是行列 → 原逻辑不变（正常写入）"""
        pp = self._mk({"other": "x"})
        body = pp.process(
            {"to_customer": {"policy_sub_id": "old"}},
            [{"type": "set_field", "path": "to_customer.policy_sub_id", "value": "NEW"}],
        )
        assert body["to_customer"]["policy_sub_id"] == "NEW"

    def test_override_syncs_to_extracted_pool(self):
        """行值覆盖后（字面量 set_field 让位）同步进上下文池（下游 ${xxx} 拿到行值）"""
        pp = self._mk({"bl_no": "ROW003"})
        extracted = {}
        pp.process(
            {},
            [{"type": "set_field", "path": "bl_no", "value": "CFG-LITERAL"}],
            extracted,
        )
        assert extracted["bl_no"] == "ROW003"

    def test_dynamic_eval_syncs_to_extracted_pool(self):
        """动态绑定求值结果同步进上下文池（行值同名列不压制）"""
        pp = PreProcessor({"extracted": {"order_id": "OID-9"}},
                          row_vars={"order_id": "ROW-9"})
        extracted = {}
        pp.process(
            {},
            [{"type": "set_field", "path": "order_id", "value": "${order_id}"}],
            extracted,
        )
        assert extracted["order_id"] == "OID-9"

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

    def test_empty_row_value_falls_back_to_expression(self):
        """空值列（None/""，单元格未配置）不拦截：set_field 恢复表达式求值。

        场景：数据集误含 audit_ids 列且清空后，[${audit_id}] 注入应正常执行"""
        pp = PreProcessor({"extracted": {"audit_id": "350514100771487744"}},
                          row_vars={"audit_ids": "", "unused": None})
        body = pp.process(
            {"audit_ids": ["旧值"]},
            [{"type": "set_field", "path": "audit_ids", "value": "[${audit_id}]"}],
        )
        assert body["audit_ids"] == "[350514100771487744]"

    def test_zero_row_value_still_overrides(self):
        """0 是有效值不是空值，照常覆盖（边界：bool/int 语义）"""
        pp = self._mk({"import_status": 0})
        body = pp.process(
            {"import_status": 1},
            [{"type": "set_field", "path": "import_status", "value": 1}],
        )
        assert body["import_status"] == 0


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

    def test_empty_row_value_not_overridden(self):
        """空值单元格（None/""）= 未配置：不覆盖，沿用字段默认值"""
        from app.services.body_builder import apply_row_overrides
        body = apply_row_overrides(
            {"audit_ids": ["343317004406489088"], "import_status": 0},
            {"audit_ids": "", "import_status": None, "voy": ""},
        )
        assert body["audit_ids"] == ["343317004406489088"]
        assert body["import_status"] == 0
