# -*- coding: utf-8 -*-
"""contract_sync 单测：数据集节点参数 与 接口字段契约 的一致性口径（2026-10-10 定案）。

覆盖：
- field_param_specs：示例值 → 初始参数（结构拆解 Q9-B / 原生类型还原 / 空占位语义）
- node_contract_gaps：missing / extra 判定（前缀链、父级容器、通配、模板接口防御）
- apply_node_sync：补 missing、删 constant extra、动态来源红线（Q8）
"""
from types import SimpleNamespace

from app.services.contract_sync import (
    apply_node_sync,
    field_param_specs,
    node_contract_gaps,
)


def _field(key, field_type="string", default=None):
    return SimpleNamespace(key=key, field_type=field_type, default_value=default)


def _const(v):
    return {"source": "constant", "value": v}


def _ref(node="n1", path="x"):
    return {"source": "ref", "node_id": node, "var_path": path}


class TestFieldParamSpecs:
    def test_string_example_text(self):
        assert field_param_specs(_field("bl_no", default="BL001")) == {"bl_no": _const("BL001")}

    def test_string_numeric_example_native(self):
        """数字示例值还原原生类型（与前端 constant 输入的类型自动转换同口径）"""
        assert field_param_specs(_field("teu", default="5")) == {"teu": _const(5)}

    def test_no_example_empty_placeholder_semantics(self):
        """无示例值对齐引擎空占位：string/file→""，int/bool→None"""
        assert field_param_specs(_field("bl_no")) == {"bl_no": _const("")}
        assert field_param_specs(_field("doc", field_type="file")) == {"doc": _const("")}
        assert field_param_specs(_field("teu", field_type="int")) == {"teu": _const(None)}

    def test_object_structure_split(self):
        """object 示例值按 JSON 结构拆叶子路径（Q9-B）"""
        f = _field("to_customer", field_type="object",
                   default='{"name": "ACO", "addr": {"city": "SH"}}')
        assert field_param_specs(f) == {
            "to_customer.name": _const("ACO"),
            "to_customer.addr.city": _const("SH"),
        }

    def test_object_no_example_null(self):
        assert field_param_specs(_field("extra", field_type="object")) == {"extra": _const(None)}

    def test_array_dict_first_element_split(self):
        """array 首元素 dict：拆 x.0.叶子（元素结构契约源，Q1/Q9-B）"""
        f = _field("statement", field_type="array",
                   default='[{"receipt_account": "ACC", "fee": 1}]')
        assert field_param_specs(f) == {
            "statement.0.receipt_account": _const("ACC"),
            "statement.0.fee": _const(1),
        }

    def test_array_scalar_example_kept_as_text(self):
        """标量数组元素无字段名：整字段 constant JSON 文本（引擎转回 list）"""
        f = _field("ids", field_type="array", default='["3439281444", "1"]')
        assert field_param_specs(f) == {"ids": _const('["3439281444", "1"]')}

    def test_array_no_example_or_illegal_empty_list(self):
        assert field_param_specs(_field("ids", field_type="array")) == {"ids": _const([])}
        assert field_param_specs(_field("ids", field_type="array", default="abc")) == {"ids": _const([])}

    def test_empty_key_skipped(self):
        assert field_param_specs(_field("")) == {}


class TestNodeContractGaps:
    def test_consistent(self):
        fields = [_field("bl_no"), _field("ids", field_type="array")]
        params = {"bl_no": _const("B1"), "ids": _const([])}
        assert node_contract_gaps(fields, params) == {}

    def test_missing_field(self):
        assert node_contract_gaps([_field("bl_no")], {}) == {"missing": ["bl_no"]}

    def test_array_leaf_param_covers_field(self):
        """数组元素路径参数（statement.0.acc）覆盖 array 字段（不 missing）"""
        fields = [_field("statement", field_type="array")]
        assert node_contract_gaps(fields, {"statement.0.acc": _const("A")}) == {}

    def test_wildcard_param_covers_field(self):
        assert node_contract_gaps([_field("list", field_type="array")],
                                  {"list.*.id": _ref()}) == {}

    def test_parent_container_param_covers_nested_field_key(self):
        """嵌套字段 key（to_customer.put_amount）的父级整体参数（to_customer
        容器常量）是合法写法：既不 missing 也不 extra"""
        fields = [_field("to_customer.put_amount", field_type="int")]
        assert node_contract_gaps(fields, {"to_customer": _const({"put_amount": 1})}) == {}

    def test_extra_constant_and_dynamic_flagged(self):
        fields = [_field("bl_no")]
        gaps = node_contract_gaps(fields, {
            "bl_no": _const("B"),
            "legacy": _const("x"),
            "dyn": _ref(),
        })
        assert gaps == {"extra": [
            {"path": "legacy", "source": "constant", "dynamic": False},
            {"path": "dyn", "source": "ref", "dynamic": True},
        ]}

    def test_template_api_no_fields_no_gaps(self):
        """无字段契约（模板接口）：参数对齐 request_template，不做比对"""
        assert node_contract_gaps(None, {"anything": _const(1)}) == {}
        assert node_contract_gaps([], {"anything": _const(1)}) == {}


class TestNodeContractGapsWithTemplate:
    """契约模板口径（Q2 2026-11-03）：模板内字段全 must；extra 按模板 key 集判。"""

    def _fields(self):
        # orderNotice 形态：action/order_id 两形态共有，finance_ids/bank_ids 仅 submit
        return [_field("action"), _field("order_id"),
                _field("finance_ids", field_type="array"), _field("bank_ids", field_type="array")]

    def test_template_filters_missing(self):
        """check 形态绑 {action, order_id}：模板外字段缺配置不算 missing"""
        params = {"action": _const("check"), "order_id": _ref()}
        gaps = node_contract_gaps(self._fields(), params,
                                  template_keys={"action", "order_id"})
        assert gaps == {}

    def test_template_inner_field_still_must(self):
        gaps = node_contract_gaps(self._fields(), {"action": _const("check")},
                                  template_keys={"action", "order_id"})
        assert gaps == {"missing": ["order_id"]}

    def test_param_outside_template_is_extra(self):
        """模板外字段上的参数（即便字段存在于接口）按契约外判"""
        params = {"action": _const("submit"), "order_id": _ref(),
                  "finance_ids": _const([])}
        gaps = node_contract_gaps(self._fields(), params,
                                  template_keys={"action", "order_id"})
        assert gaps == {"extra": [
            {"path": "finance_ids", "source": "constant", "dynamic": False}]}

    def test_stale_template_key_intersected_out(self):
        """模板 key 指向已删除字段：交集剔除后，其下参数按契约外判（不遮蔽 extra）"""
        fields = [_field("action"), _field("order_id")]
        gaps = node_contract_gaps(fields, {"action": _const("x"), "ghost": _const(1)},
                                  template_keys={"action", "ghost_key"})
        assert gaps == {"extra": [
            {"path": "ghost", "source": "constant", "dynamic": False}]}

    def test_no_template_keeps_full_contract(self):
        """未绑定（None）：全量字段口径（存量行为不变）"""
        params = {"action": _const("check")}
        gaps = node_contract_gaps(self._fields(), params)
        assert gaps == {"missing": ["order_id", "finance_ids", "bank_ids"]}


class TestApplyNodeSyncWithTemplate:
    def test_sync_respects_template_scope(self):
        """绑定模板的节点同步：只补模板内字段、只清模板外 extra；动态红线不变"""
        fields = [_field("action"), _field("order_id"),
                  _field("finance_ids", field_type="array"),
                  _field("bank_ids", field_type="array")]
        body = {"action": _const("check"), "finance_ids": _const([]), "dyn": _ref()}
        new_body, stats = apply_node_sync(body, fields,
                                          template_keys={"action", "order_id"})
        assert new_body == {"action": _const("check"), "order_id": _const(""), "dyn": _ref()}
        assert stats == {"added": 1, "removed": 1, "skipped_dynamic": 1}

    def test_sync_without_template_full_scope(self):
        fields = [_field("action"), _field("order_id")]
        new_body, stats = apply_node_sync({"action": _const("check")}, fields)
        assert "order_id" in new_body and stats["added"] == 1


class TestApplyNodeSync:
    def test_adds_missing_removes_constant_extra_keeps_dynamic(self):
        """同步三动作：补 missing（示例值）、删 constant extra、动态 extra 红线保留（Q8）"""
        fields = [_field("bl_no", default="BL1"),
                  _field("statement", field_type="array",
                         default='[{"acc": "A"}]')]
        body = {"legacy": _const("x"), "dyn": _ref()}
        new_body, stats = apply_node_sync(body, fields)
        assert new_body == {
            "dyn": _ref(),
            "bl_no": _const("BL1"),
            "statement.0.acc": _const("A"),
        }
        assert stats == {"added": 2, "removed": 1, "skipped_dynamic": 1}

    def test_partial_config_not_refilled(self):
        """字段已部分配置（元素叶子在）：不重复补（元素补空由引擎兜底）"""
        fields = [_field("statement", field_type="array", default='[{"a": 1, "b": 2}]')]
        new_body, stats = apply_node_sync({"statement.0.a": _const(9)}, fields)
        assert new_body == {"statement.0.a": _const(9)}
        assert stats["added"] == 0

    def test_no_fields_untouched(self):
        body = {"anything": _const(1)}
        new_body, stats = apply_node_sync(body, [])
        assert new_body == body and stats["added"] == 0 and stats["removed"] == 0

    def test_idempotent(self):
        fields = [_field("bl_no", default="BL1")]
        once, _ = apply_node_sync({}, fields)
        twice, stats = apply_node_sync(once, fields)
        assert twice == once and stats == {"added": 0, "removed": 0, "skipped_dynamic": 0}


# ============ _api_bindings：画布已删节点残留过滤（生产 case 200 回归） ============

class _Q:
    """链式 fake query：按实体路由返回预设结果。"""
    def __init__(self, items):
        self._items = items

    def filter(self, *a, **kw):
        return self

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None


class TestApiBindingsSkipsStaleNodes:
    """case_node_configs 残留画布已删节点的结构配置时：影响面/同步必须跳过——
    否则残留节点被判全字段 missing，同步把参数写进行内造成悬空配置（死循环）。"""

    def _make_db(self, *, stale_bind=True, template_id=None):
        dag = {"nodes": [{"id": "n_live", "data": {"label": "审核"}}],
               "edges": []}
        case = SimpleNamespace(id=1, name="c1", dag_config=dag, dataset_id=10)
        row = SimpleNamespace(dataset_id=10, row_index=1,
                              data={"nodes": {"n_live": {"params": {"body": {"bl_no": _const("B1")}}}}})
        ds = SimpleNamespace(id=10, name="默认", case_id=1, rows=[row])
        api = SimpleNamespace(id=7, fields=[_field("bl_no", default="BL1")])
        binds = [SimpleNamespace(case_id=1, node_id="n_live", api_id=7,
                                 contract_template_id=template_id)]
        if stale_bind:
            binds.append(SimpleNamespace(case_id=1, node_id="n_stale", api_id=7,
                                         contract_template_id=None))
        table = {}

        class Db:
            def query(self, entity):
                return _Q(table.get(entity, []))

        from app import models
        table[models.ApiDefinition] = [api]
        table[models.CaseNodeConfig] = binds
        table[models.TestCase] = [case]
        table[models.DataSet] = [ds]
        if template_id is not None:
            table[models.ApiContractTemplate] = [
                SimpleNamespace(id=template_id, api_id=7, name="精简",
                                field_keys=["bl_no"])]
        return Db(), api, case, ds

    def test_stale_bind_excluded(self):
        from app.services.contract_sync import _api_bindings
        db, api, case, ds = self._make_db(stale_bind=True)
        got = [(nid, params) for _, _, _, nid, params, _b in _api_bindings(db, 7)]
        assert [nid for nid, _ in got] == ["n_live"]

    def test_live_only_no_stale_regression(self):
        from app.services.contract_sync import _api_bindings
        db, *_ = self._make_db(stale_bind=False)
        got = list(_api_bindings(db, 7))
        assert len(got) == 1 and got[0][3] == "n_live"


class TestImpactWithTemplate:
    """影响面按节点绑定模板判定 + 模板名透出（同步弹窗「按模板判定」标注）。"""

    def test_impact_uses_bound_template(self):
        from app.services.contract_sync import api_contract_impact
        # 构造：字段 bl_no+order_id；节点只配 bl_no 且模板只认 bl_no → 一致不列
        maker = TestApiBindingsSkipsStaleNodes()
        db, *_ = maker._make_db(stale_bind=False, template_id=99)
        assert api_contract_impact(db, 7) == []

    def test_impact_lists_gap_with_template_name(self):
        from app.services.contract_sync import api_contract_impact
        maker = TestApiBindingsSkipsStaleNodes()
        # 模板认 [bl_no, order_id]，行只配 bl_no → missing order_id，item 带模板名
        db, *_ = maker._make_db(stale_bind=False, template_id=99)
        from app import models
        # 模板与接口字段都扩为两键，行内只配 bl_no → 模板口径 missing order_id
        for t in db.query(models.ApiContractTemplate).all():
            t.field_keys = ["bl_no", "order_id"]
        for a in db.query(models.ApiDefinition).all():
            a.fields = [_field("bl_no", default="BL1"), _field("order_id")]
        out = api_contract_impact(db, 7)
        assert len(out) == 1
        assert out[0]["template_name"] == "精简"
        assert out[0]["gaps"] == {"missing": ["order_id"]}

    def test_unbound_node_keeps_full_contract(self):
        from app.services.contract_sync import api_contract_impact
        maker = TestApiBindingsSkipsStaleNodes()
        db, *_ = maker._make_db(stale_bind=False, template_id=None)
        # 字段 [bl_no] 行配置齐 → 无出入；再加一个字段制造 missing 验证全量口径
        from app import models
        for api in db.query(models.ApiDefinition).all():
            api.fields = [_field("bl_no", default="BL1"), _field("order_id")]
        out = api_contract_impact(db, 7)
        assert len(out) == 1 and out[0]["gaps"] == {"missing": ["order_id"]}
        assert "template_name" not in out[0]
