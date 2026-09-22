"""PreProcessor 取值优先级（数据集模式定案）。

请求体参数取值：手动覆盖(1) > 套件注入(2) > 数据集域静态变量(3)。
本文件测 PreProcessor 层（第 1 层）：set_field/add_field 的非空值直接生效
（字面量或 ${} 动态绑定），不再被数据集行值压制——行值属第 3 层，由
prepare_request 在自动解析阶段处理；pre_process 在其之后执行，天然取胜。

- 非空值（字面量）：直接写入（手动覆盖，最高优先级）
- 非空值（${}）：表达式求值（动态绑定）
- 空值（None/""）：自动引用占位（清空转引用后的形态），不写空串——
  参数值由 prepare_request 按名解析取值（套件注入 > 数据集域）
- 求值结果同步进 extracted 池（下游 ${xxx} 显式引用可用；
  运行时变量不参与按名解析）
- iterate_set / delete_field / exec_sql / sleep 不受影响
"""
from app.engine.preprocessor import PreProcessor


class TestManualOverrideWins:
    """第 1 层手动覆盖：非空 set_field 值直接生效（不再让位数据集行值）"""

    def test_literal_value_always_wins(self):
        """set_field 字面量直接写入（核心语义：有值=覆盖，行值压制已废除）"""
        pp = PreProcessor({})
        body = pp.process(
            {"voy": "old"},
            [{"type": "set_field", "path": "voy", "value": "CASE-LITERAL"}],
        )
        assert body["voy"] == "CASE-LITERAL"

    def test_dynamic_binding_evaluates(self):
        """${} 动态绑定照常求值（生成函数）"""
        pp = PreProcessor({})
        body = pp.process(
            {},
            [{"type": "set_field", "path": "bl_no", "value": "${generate_bl_no(prefix='smoke')}"}],
        )
        assert body["bl_no"].startswith("smoke")

    def test_dynamic_context_ref_evaluates(self):
        """${context.x} 上游提取注入：取上下文池的值"""
        pp = PreProcessor({"extracted": {"bl_no": "PREV"}})
        body = pp.process(
            {},
            [{"type": "set_field", "path": "bl_no", "value": "${context.bl_no}"}],
        )
        assert body["bl_no"] == "PREV"

    def test_explicit_row_var_ref_still_works(self):
        """既有机制不变：value 里显式 ${列名} 引用行值（行值由调用方合入 context 池）"""
        pp = PreProcessor({"extracted": {"bl_no": "ROW004"}})
        body = pp.process(
            {},
            [{"type": "set_field", "path": "track_bl_no", "value": "${bl_no}"}],
        )
        assert body["track_bl_no"] == "ROW004"

    def test_nested_literal_written(self):
        """嵌套字面量正常写入（无行值整块替换的压制逻辑）"""
        pp = PreProcessor({})
        body = pp.process(
            {"to_customer": {"policy_sub_id": "old"}},
            [{"type": "set_field", "path": "to_customer.policy_sub_id", "value": "NEW"}],
        )
        assert body["to_customer"]["policy_sub_id"] == "NEW"

    def test_nested_expression_written(self):
        """嵌套 ${} 表达式写入（运行时注入仍执行）"""
        pp = PreProcessor({"extracted": {"order_id": "OID-1"}})
        body = pp.process(
            {"to_customer": {"remark": "row"}},
            [{"type": "set_field", "path": "to_customer.order_id", "value": "${context.order_id}"}],
        )
        assert body["to_customer"]["order_id"] == "OID-1"
        assert body["to_customer"]["remark"] == "row"

    def test_zero_and_false_values_are_manual(self):
        """0 / False 是有效值不是空值：照常写入（边界：bool/int 语义）"""
        pp = PreProcessor({})
        body = pp.process(
            {"import_status": 1, "enabled": True},
            [{"type": "set_field", "path": "import_status", "value": 0},
             {"type": "set_field", "path": "enabled", "value": False}],
        )
        assert body["import_status"] == 0
        assert body["enabled"] is False


class TestEmptyPlaceholder:
    """三态之一：空值占位（自动引用）不写空串"""

    def test_empty_string_value_skipped(self):
        """value="" 的占位行不写字面空串——参数值由 prepare_request 按名解析"""
        pp = PreProcessor({})
        body = pp.process(
            {"voy": "RESOLVED"},
            [{"type": "set_field", "path": "voy", "value": ""}],
        )
        assert body["voy"] == "RESOLVED"

    def test_none_value_skipped(self):
        pp = PreProcessor({})
        body = pp.process(
            {},
            [{"type": "set_field", "path": "voy", "value": None}],
        )
        assert "voy" not in body

    def test_empty_path_row_skipped(self):
        """空 path（前端表格空行占位）→ 跳过不炸"""
        pp = PreProcessor({})
        body = pp.process(
            {},
            [{"type": "set_field", "path": "", "value": "x"}],
        )
        assert body == {}


class TestSyncPools:
    """求值结果同步进 extracted 池（${} 显式引用；不参与按名解析）"""

    def test_literal_syncs_to_extracted(self):
        pp = PreProcessor({})
        extracted = {}
        pp.process(
            {},
            [{"type": "set_field", "path": "bl_no", "value": "BL-SET"}],
            extracted,
        )
        assert extracted["bl_no"] == "BL-SET"

    def test_nested_path_syncs_last_segment(self):
        """嵌套 path 同步末段作 key（bl_no / order_id 等顶层名直接可引用）"""
        pp = PreProcessor({})
        extracted = {}
        pp.process(
            {},
            [{"type": "set_field", "path": "to_customer.put_amount", "value": "100"}],
            extracted,
        )
        assert extracted["put_amount"] == "100"

    def test_dynamic_eval_syncs(self):
        pp = PreProcessor({"extracted": {"order_id": "OID-9"}})
        extracted = {}
        pp.process(
            {},
            [{"type": "set_field", "path": "order_id", "value": "${order_id}"}],
            extracted,
        )
        assert extracted["order_id"] == "OID-9"

    def test_no_pools_passed_no_sync(self):
        """不传池（兼容旧调用）：只写 body 不炸"""
        pp = PreProcessor({})
        body = pp.process(
            {},
            [{"type": "set_field", "path": "voy", "value": "LITERAL"}],
        )
        assert body["voy"] == "LITERAL"


class TestOtherActionsUnaffected:
    """iterate_set / delete_field 不受优先级改造影响"""

    def test_delete_field(self):
        pp = PreProcessor({})
        body = pp.process(
            {"a": 1, "b": 2},
            [{"type": "delete_field", "path": "a"}],
        )
        assert body == {"b": 2}

    def test_iterate_set(self):
        pp = PreProcessor({"extracted": {"uid": "U1"}})
        body = pp.process(
            {"items": [{"sku": "a"}, {"sku": "b"}]},
            [{"type": "iterate_set", "path": "items", "field": "unique_id",
              "value": "${uid}-${generate_int(100,100)}"}],
        )
        assert all("unique_id" in it for it in body["items"])
