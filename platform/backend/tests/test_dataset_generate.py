"""从用例生成数据集（collect_case_params / generate_dataset_from_case）单测。

语义（与三级取值优先级一致：数据集 = 除动态绑定外的所有字段集合）：
- 收集范围 = 用例中所有"写死"的请求参数（非上游 ${} 提取注入）：
  ① API 字段默认值（顶层 key、非空、不含 ${}；file 字段成列 type=file，值是文件 ID）
  ② 前置处理 set_field/add_field 字面量（path 顶层、value 不含 ${}）
- 节点内同 key：set_field 晚于默认值组装执行，最终生效值 = set_field 值
- 跨节点同名 → 合并一列（一列统一覆盖所有同名节点）；同名异值取首节点值成列，
  stats.conflicts 仅作提示（并集口径，不剔除）
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import dataset_service as svc


def _fake_db():
    """带 query 链的空 db 替身（copy 重名查重等惰性查询返回空）"""
    return SimpleNamespace(query=lambda *a: SimpleNamespace(
        filter=lambda *b: SimpleNamespace(first=lambda: None)))


def _field(key, default=None, ftype="string", label=None):
    return SimpleNamespace(key=key, field_type=ftype, default_value=default, label=label)


def _api(fields, api_id=7):
    return SimpleNamespace(id=api_id, fields=fields, request_template={})


def _cfg(node_id, api_id, pre=None, post=None, asserts=None, wait=0):
    return SimpleNamespace(node_id=node_id, api_id=api_id, pre_process=pre or [],
                           post_extract=post or [], assertions=asserts or [], wait_after_ms=wait)


def _case(nodes):
    """nodes: [(node_id, api_id)] 按 dag 定义顺序"""
    return SimpleNamespace(
        id=92, name="最长链路", project_id=1,
        dag_config={"nodes": [{"id": nid} for nid, _ in nodes], "edges": []},
    )


# ============ collect_case_params：字段收集（纯函数） ============

class TestCollectCaseParams:
    def test_collects_top_level_defaults(self):
        """API 顶层字段写死默认值 → 列 + 行值"""
        case = _case([("n1", 7)])
        apis = {7: _api([_field("bl_no", "BL001"), _field("voy", "V001")])}
        out = svc.collect_case_params(case, [_cfg("n1", 7)], apis)
        assert [c["key"] for c in out["columns"]] == ["bl_no", "voy"]
        assert out["row"] == {"bl_no": "BL001", "voy": "V001"}

    def test_collects_set_field_literal(self):
        """set_field 字面量（str/int）→ 列；value 非字符串原生类型直接用"""
        case = _case([("n1", 7)])
        apis = {7: _api([_field("bl_no", "BL001")])}
        cfg = _cfg("n1", 7, pre=[
            {"type": "set_field", "path": "teu", "value": 2},
            {"type": "add_field", "path": "remark", "value": "加急"},
        ])
        out = svc.collect_case_params(case, [cfg], apis)
        assert out["row"]["teu"] == 2 and out["row"]["remark"] == "加急"
        teu_col = next(c for c in out["columns"] if c["key"] == "teu")
        assert teu_col["type"] == "int"

    def test_set_field_overrides_default_same_key(self):
        """同节点同 key：默认值 + set_field → 取 set_field 值（执行顺序最终生效）"""
        case = _case([("n1", 7)])
        apis = {7: _api([_field("bl_no", "BL-DEFAULT")])}
        cfg = _cfg("n1", 7, pre=[{"type": "set_field", "path": "bl_no", "value": "BL-SET"}])
        out = svc.collect_case_params(case, [cfg], apis)
        assert out["row"]["bl_no"] == "BL-SET"

    def test_same_key_same_value_across_nodes_merged(self):
        """跨节点同名同值 → 合并一列（一列覆盖所有同名节点，值不变无风险）"""
        case = _case([("n1", 7), ("n2", 8)])
        apis = {
            7: _api([_field("action", "submit")]),
            8: _api([_field("action", "submit"), _field("fee", "100")]),
        }
        out = svc.collect_case_params(case, [_cfg("n1", 7), _cfg("n2", 8)], apis)
        keys = [c["key"] for c in out["columns"]]
        assert keys.count("action") == 1
        assert out["row"]["action"] == "submit"

    def test_conflicting_values_takes_first(self):
        """跨节点同名异值 → 并集口径仍成一列，取执行序首个（源头）节点值；conflicts 仅提示"""
        case = _case([("n1", 7), ("n2", 8)])
        apis = {
            7: _api([_field("action", "create")]),
            8: _api([_field("action", "audit")]),
        }
        out = svc.collect_case_params(case, [_cfg("n1", 7), _cfg("n2", 8)], apis)
        assert out["row"]["action"] == "create"
        assert any(c["key"] == "action" for c in out["stats"]["conflicts"])

    def test_conflicting_values_follow_topo_order_not_array(self):
        """dag 数组顺序 ≠ 执行顺序：同名异值取拓扑执行序源头节点值。

        场景：数组里下游节点排最前（用户拖拽），但有边 create→audit；
        源头（create）值应胜出，而不是数组首个（audit）"""
        case = SimpleNamespace(
            id=92, name="拖拽乱序", project_id=1,
            dag_config={
                "nodes": [{"id": "n_audit"}, {"id": "n_create"}],
                "edges": [{"source": "n_create", "target": "n_audit"}],
            },
        )
        apis = {
            7: _api([_field("main_ids", "3,1")]),   # create：源头
            8: _api([_field("main_ids", ",3,1,")]),  # audit：回显格式
        }
        out = svc.collect_case_params(
            case, [_cfg("n_create", 7), _cfg("n_audit", 8)], apis)
        assert out["row"]["main_ids"] == "3,1"

    def test_columns_carry_origin(self):
        """列记录 origin（生成时源头值）：执行时快照保真的比对基准"""
        case = _case([("n1", 7)])
        apis = {7: _api([_field("voy", "V001")])}
        out = svc.collect_case_params(case, [_cfg("n1", 7)], apis)
        col = next(c for c in out["columns"] if c["key"] == "voy")
        assert col["origin"] == "V001"

    def test_dynamic_expression_skipped(self):
        """含 ${}（上游提取注入）不属"写死参数"→ 跳过并计入 dynamic"""
        case = _case([("n1", 7)])
        apis = {7: _api([_field("order_id", "${order_id}")])}
        cfg = _cfg("n1", 7, pre=[{"type": "set_field", "path": "bl_no", "value": "${bl_no}"}])
        out = svc.collect_case_params(case, [cfg], apis)
        assert out["columns"] == []
        assert out["stats"]["dynamic"] == 2

    def test_dynamic_set_field_excludes_field_default(self):
        """set_field 动态注入（value 含 ${}）→ 同名字段默认值一并剔除，不建列。

        场景：audit_ids 字段默认值是写死旧值（如 ["343..."]），但前置处理
        用 [${audit_id}] 动态注入 → audit_ids 不能成为数据列（列会拦截表达式）"""
        case = _case([("n1", 7)])
        apis = {7: _api([_field("audit_ids", '["343317004406489088"]', ftype="array"),
                         _field("remark", "保留")])}
        cfg = _cfg("n1", 7, pre=[{"type": "set_field", "path": "audit_ids", "value": "[${audit_id}]"}])
        out = svc.collect_case_params(case, [cfg], apis)
        keys = [c["key"] for c in out["columns"]]
        assert "audit_ids" not in keys
        assert "audit_ids" not in out["row"]
        assert keys == ["remark"]

    def test_dynamic_set_field_excludes_earlier_node_value(self):
        """节点1 写死收集了 key，节点2 对同 key 动态注入 → 整体剔除（跨节点）"""
        case = _case([("n1", 7), ("n2", 8)])
        apis = {7: _api([_field("audit_ids", '["1"]', ftype="array")]), 8: _api([])}
        cfgs = [
            _cfg("n1", 7),
            _cfg("n2", 8, pre=[{"type": "set_field", "path": "audit_ids", "value": "[${audit_id}]"}]),
        ]
        out = svc.collect_case_params(case, cfgs, apis)
        assert "audit_ids" not in [c["key"] for c in out["columns"]]

    def test_dynamic_set_field_excludes_later_node_default(self):
        """节点1 动态注入后，节点2 的同名字段默认值也不再收集"""
        case = _case([("n1", 7), ("n2", 8)])
        apis = {
            7: _api([]),
            8: _api([_field("audit_ids", '["1"]', ftype="array")]),
        }
        cfgs = [
            _cfg("n1", 7, pre=[{"type": "set_field", "path": "audit_ids", "value": "[${audit_id}]"}]),
            _cfg("n2", 8),
        ]
        out = svc.collect_case_params(case, cfgs, apis)
        assert out["columns"] == []

    def test_nested_path_skipped(self):
        """含点号路径（嵌套字段）→ 跳过（列名不允许点号，自动覆盖不生效）"""
        case = _case([("n1", 7)])
        apis = {7: _api([_field("to_customer.name", "张三")])}
        cfg = _cfg("n1", 7, pre=[{"type": "set_field", "path": "to_customer.amount", "value": 100}])
        out = svc.collect_case_params(case, [cfg], apis)
        assert out["columns"] == []
        assert out["stats"]["nested"] == 2

    def test_empty_skipped_file_collected(self):
        """空默认值跳过；file 字段成列（type=file，值是文件中心文件 ID）"""
        case = _case([("n1", 7)])
        apis = {7: _api([_field("remark", ""), _field("id_card", "12", ftype="file"),
                         _field("memo", None)])}
        out = svc.collect_case_params(case, [_cfg("n1", 7)], apis)
        cols = {c["key"]: c for c in out["columns"]}
        assert cols["id_card"]["type"] == "file"
        assert cols["id_card"]["origin"] == "12"
        assert out["row"]["id_card"] == "12"
        assert "remark" not in cols and "memo" not in cols
        assert out["stats"]["empty"] == 2

    def test_set_field_file_path_typed_file(self):
        """前置 set_field 绑定 file 字段（值是文件 ID）→ 列 type=file（按 api 字段定义识别）"""
        case = _case([("n1", 7)])
        apis = {7: _api([_field("id_card", None, ftype="file")])}
        cfg = _cfg("n1", 7, pre=[{"type": "set_field", "path": "id_card", "value": "35"}])
        out = svc.collect_case_params(case, [cfg], apis)
        col = next(c for c in out["columns"] if c["key"] == "id_card")
        assert col["type"] == "file"
        assert col["origin"] == "35"

    def test_empty_set_field_path_skipped(self):
        """set_field 空 path（前端表格空行占位）→ 跳过不炸、不生成空名列"""
        case = _case([("n1", 7)])
        apis = {7: _api([_field("bl_no", "B1")])}
        cfg = _cfg("n1", 7, pre=[{"type": "set_field", "path": "", "value": "x"}])
        out = svc.collect_case_params(case, [cfg], apis)
        assert [c["key"] for c in out["columns"]] == ["bl_no"]

    def test_type_inference(self):
        """列类型按值推断：str→string / int→int / bool→bool / list→array / dict→object / float→string"""
        case = _case([("n1", 7)])
        apis = {7: _api([
            _field("s", "x"), _field("i", "5", ftype="int"), _field("b", "true", ftype="bool"),
            _field("l", '[{"a":1}]', ftype="array"), _field("o", '{"a":1}', ftype="object"),
            _field("f", "0.5"),
        ])}
        out = svc.collect_case_params(case, [_cfg("n1", 7)], apis)
        types = {c["key"]: c["type"] for c in out["columns"]}
        assert types == {"s": "string", "i": "int", "b": "bool",
                         "l": "array", "o": "object", "f": "string"}
        # 默认值按 field_type 解析后入行（int 5 / bool True / list[dict]）
        assert out["row"]["i"] == 5 and out["row"]["b"] is True
        assert out["row"]["l"] == [{"a": 1}]

    def test_label_not_collected(self):
        """列 label 已废除：中文名实时引用项目字段字典，生成时不再快照接口字段 label"""
        case = _case([("n1", 7)])
        apis = {7: _api([_field("bl_no", "BL001", label="提单号")])}
        cfg = _cfg("n1", 7, pre=[{"type": "set_field", "path": "teu", "value": 1}])
        out = svc.collect_case_params(case, [cfg], apis)
        assert all("label" not in c for c in out["columns"])

    def test_columns_follow_node_order(self):
        """列顺序 = 节点定义顺序（跟链路顺序一致，用户好找）"""
        case = _case([("n1", 7), ("n2", 8)])
        apis = {7: _api([_field("bl_no", "B1")]), 8: _api([_field("fee", "9")])}
        out = svc.collect_case_params(case, [_cfg("n1", 7), _cfg("n2", 8)], apis)
        assert [c["key"] for c in out["columns"]] == ["bl_no", "fee"]

    def test_node_without_config_or_api_skipped(self):
        """节点缺配置或缺接口 → 跳过不计（不炸）"""
        case = _case([("n1", 7), ("n2", None)])
        apis = {7: _api([_field("bl_no", "B1")])}
        out = svc.collect_case_params(case, [_cfg("n1", 7)], apis)
        assert [c["key"] for c in out["columns"]] == ["bl_no"]

    def test_no_params_returns_empty(self):
        """全部参数不可提取（全动态/嵌套/空）→ 纯函数返回空结果不炸，错误由服务层抛"""
        case = _case([("n1", 7)])
        apis = {7: _api([_field("order_id", "${x}")])}
        out = svc.collect_case_params(case, [_cfg("n1", 7)], apis)
        assert out["columns"] == [] and out["row"] == {}
        assert out["stats"]["dynamic"] == 1

    def test_stats_counts(self):
        """stats：nodes 节点数 / columns 列数"""
        case = _case([("n1", 7), ("n2", 8)])
        apis = {7: _api([_field("bl_no", "B1")]), 8: _api([_field("bl_no", "B1"), _field("voy", "V1")])}
        out = svc.collect_case_params(case, [_cfg("n1", 7), _cfg("n2", 8)], apis)
        assert out["stats"]["nodes"] == 2
        assert out["stats"]["columns"] == 2


# ============ filter_row_vars_for_node：执行时快照保真过滤（纯函数） ============

class TestFilterRowVarsForNode:
    """同名异值列的过滤语义（快照保真）：
    - 未编辑快照值（行值 == origin）：只作用于"节点配置值 == origin"的节点
    - 用户编辑过的单元格（行值 != origin）：无条件作用于全部节点
    """

    def test_matching_node_gets_row_value(self):
        """节点配置值 == origin → 行值应用（数据驱动正常生效）"""
        api = _api([_field("main_ids", "3,1")])
        out = svc.filter_row_vars_for_node(
            {"main_ids": "5,2"}, {"main_ids": "3,1"}, api, [])
        assert out == {"main_ids": "5,2"}

    def test_edited_row_value_overrides_mismatched_node(self):
        """用户编辑过单元格（行值 != origin）→ 即使节点配置与 origin 异值也覆盖。
        supplier 场景：提交订单接口的 supplier 默认值是从真实订单拷贝的
        "带 order_id 版本"（≠ origin 干净版），用户在数据集行里设置的新供应商
        应整体替换到所有节点"""
        api = _api([_field("supplier", '[{"supplier_id": "61224", "order_id": "343"}]', ftype="array")])
        out = svc.filter_row_vars_for_node(
            {"supplier": [{"supplier_id": "26"}]},
            {"supplier": [{"supplier_id": "61224", "order_id": ""}]}, api, [])
        assert out == {"supplier": [{"supplier_id": "26"}]}

    def test_mismatched_node_keeps_own_config(self):
        """未编辑快照值（行值 == origin）+ 节点配置值 ≠ origin（跨节点异值，
        如 ',3,1,' 回显格式）→ 排除，节点保留自身配置——原样执行与原用例行为一致"""
        api = _api([_field("main_ids", ",3,1,")])
        out = svc.filter_row_vars_for_node(
            {"main_ids": "3,1"}, {"main_ids": "3,1"}, api, [])
        assert out == {}

    def test_empty_default_node_excluded(self):
        """节点默认值为空（列值来自其他节点）→ 排除：空值字段不被列值盖掉"""
        api = _api([_field("customer_name", "")])
        out = svc.filter_row_vars_for_node(
            {"customer_name": "青岛统济机电"}, {"customer_name": "青岛统济机电"}, api, [])
        assert out == {}

    def test_set_field_literal_is_effective_value(self):
        """节点自身配置值 = pre_process set_field 字面量（优先于 API 默认值）"""
        api = _api([_field("teu", "56")])
        # 未编辑快照值（56 == origin）+ set_field 字面量 3 ≠ origin → 排除（防污染）
        pre = [{"type": "set_field", "path": "teu", "value": "3"}]
        out = svc.filter_row_vars_for_node({"teu": "56"}, {"teu": "56"}, api, pre)
        assert out == {}
        # 未编辑快照值 + set_field 字面量 == origin → 应用
        pre2 = [{"type": "set_field", "path": "teu", "value": "56"}]
        out2 = svc.filter_row_vars_for_node({"teu": "56"}, {"teu": "56"}, api, pre2)
        assert out2 == {"teu": "56"}
        # 编辑过行值（99 != origin）→ 无条件应用（用户覆盖意图优先于异值保护）
        out3 = svc.filter_row_vars_for_node({"teu": "99"}, {"teu": "56"}, api, pre)
        assert out3 == {"teu": "99"}

    def test_no_origins_no_filter(self):
        """origins 为空（手工列/旧数据集）→ 不过滤，行为与现状一致"""
        api = _api([_field("main_ids", ",3,1,")])
        out = svc.filter_row_vars_for_node({"main_ids": "5,2"}, None, api, [])
        assert out == {"main_ids": "5,2"}
        out2 = svc.filter_row_vars_for_node({"main_ids": "5,2"}, {}, api, [])
        assert out2 == {"main_ids": "5,2"}

    def test_key_without_origin_kept(self):
        """行值里的 key 无对应 origin（手工加列）→ 不过滤"""
        api = _api([_field("voy", "V")])
        out = svc.filter_row_vars_for_node(
            {"voy": "NEW", "extra": "x"}, {"voy": "V"}, api, [])
        assert out == {"voy": "NEW", "extra": "x"}

    def test_key_not_in_node_kept(self):
        """节点没有该 key（请求体无此字段）→ 保留（apply_row_overrides 只覆盖已存在字段）"""
        api = _api([_field("voy", "V")])
        out = svc.filter_row_vars_for_node(
            {"teu": "3"}, {"teu": "56"}, api, [])
        assert out == {"teu": "3"}

    def test_dynamic_injection_key_excluded(self):
        """pre_process 对该 key 动态注入（值含 ${}）→ 排除（动态绑定不在数据集范围）"""
        api = _api([_field("audit_ids", '["OLD"]', ftype="array")])
        pre = [{"type": "set_field", "path": "audit_ids", "value": "[${audit_id}]"}]
        out = svc.filter_row_vars_for_node(
            {"audit_ids": "whatever"}, {"audit_ids": '["OLD"]'}, api, pre)
        assert out == {}


# ============ generate_dataset_from_case：服务编排（mock db） ============

class TestGenerateDatasetFromCase:
    def _case_obj(self):
        return _case([("n1", 7)])

    def test_generate_creates_dataset_with_snapshot_row(self):
        """生成：默认名 {用例名}-参数集，1 行原值快照 + 节点配置快照，返回 (dataset, stats)"""
        case = self._case_obj()
        apis = {7: _api([_field("bl_no", "BL001", label="提单号")])}
        cfgs = [_cfg("n1", 7, pre=[{"type": "set_field", "path": "teu", "value": 2}],
                     post=[{"name": "order_id", "source": "json"}],
                     asserts=[{"type": "eq", "expected": "0"}], wait=300)]

        def fake_query(model):
            if getattr(model, "__name__", "") == "TestCase":
                return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: case))
            if getattr(model, "__name__", "") == "CaseNodeConfig":
                return SimpleNamespace(filter=lambda *a: SimpleNamespace(all=lambda: cfgs))
            return SimpleNamespace(filter=lambda *a: SimpleNamespace(all=lambda: list(apis.values())))

        db = SimpleNamespace(query=fake_query, add=lambda o: None, commit=lambda: None, refresh=lambda o: None)
        with patch.object(svc, "create_dataset") as fake_create:
            fake_create.return_value = SimpleNamespace(id=20, name="最长链路-参数集")
            ds, stats = svc.generate_dataset_from_case(db, case_id=92, user_id=1)
        kw = fake_create.call_args.kwargs
        assert kw["name"] == "最长链路-参数集"
        assert kw["case_id"] == 92
        assert kw["columns"] == [{"key": "bl_no", "type": "string", "origin": "BL001"},
                                 {"key": "teu", "type": "int", "origin": 2}]
        assert kw["rows_data"] == [{"bl_no": "BL001", "teu": 2}]
        # 节点配置快照：按节点整块存 pre/post/assert/wait/api_id
        assert kw["node_configs"] == [{
            "node_id": "n1", "api_id": 7,
            "pre_process": [{"type": "set_field", "path": "teu", "value": 2}],
            "post_extract": [{"name": "order_id", "source": "json"}],
            "assertions": [{"type": "eq", "expected": "0"}],
            "wait_after_ms": 300,
        }]
        assert stats["columns"] == 2

    def test_generate_case_not_found(self):
        def fake_query(model):
            return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: None))

        db = SimpleNamespace(query=fake_query)
        with pytest.raises(ValueError, match="用例不存在"):
            svc.generate_dataset_from_case(db, case_id=999, user_id=1)

    def test_default_name_truncated_when_case_name_long(self):
        """用例名超长（DataSet.name 上限 100）→ 默认名截断用例名部分，保留 -参数集 后缀"""
        case = SimpleNamespace(
            id=1, name="长" * 105, project_id=1,
            dag_config={"nodes": [{"id": "n1"}], "edges": []},
        )

        def fake_query(model):
            name = getattr(model, "__name__", "")
            if name == "TestCase":
                return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: case))
            if name == "CaseNodeConfig":
                return SimpleNamespace(filter=lambda *a: SimpleNamespace(all=list))
            return SimpleNamespace(filter=lambda *a: SimpleNamespace(all=list))

        with patch.object(svc, "collect_case_params") as fake_collect:
            fake_collect.return_value = {"columns": [{"key": "a", "type": "string"}], "row": {"a": 1},
                                         "stats": {"columns": 1}}
            with patch.object(svc, "create_dataset") as fake_create:
                fake_create.return_value = SimpleNamespace(id=1)
                svc.generate_dataset_from_case(SimpleNamespace(query=fake_query), case_id=1, user_id=1)
        gen_name = fake_create.call_args.kwargs["name"]
        assert len(gen_name) <= 100 and gen_name.endswith("-参数集")

    def test_generate_custom_name_too_long_raises(self):
        """自定义名超 100 字符 → ValueError（DB DataError 对用户不可读）"""
        case = SimpleNamespace(
            id=1, name="x", project_id=1,
            dag_config={"nodes": [{"id": "n1"}], "edges": []},
        )

        def fake_query(model):
            name = getattr(model, "__name__", "")
            if name == "TestCase":
                return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: case))
            return SimpleNamespace(filter=lambda *a: SimpleNamespace(all=list))

        with patch.object(svc, "collect_case_params") as fake_collect:
            fake_collect.return_value = {"columns": [{"key": "a", "type": "string"}], "row": {"a": 1},
                                         "stats": {"columns": 1}}
            with pytest.raises(ValueError, match="名称.*100"):
                svc.generate_dataset_from_case(SimpleNamespace(query=fake_query), case_id=1,
                                               name="长" * 101, user_id=1)

    def test_generate_no_params_raises(self):
        """收集结果 0 列 → 服务层抛用户可读错误（create 至少一列的语义前置）"""
        case = self._case_obj()
        cfgs = [_cfg("n1", 7)]

        def fake_query(model):
            name = getattr(model, "__name__", "")
            if name == "TestCase":
                return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: case))
            if name == "CaseNodeConfig":
                return SimpleNamespace(filter=lambda *a: SimpleNamespace(all=lambda: cfgs))
            return SimpleNamespace(filter=lambda *a: SimpleNamespace(all=list))

        db = SimpleNamespace(query=fake_query)
        with patch.object(svc, "collect_case_params",
                          return_value={"columns": [], "row": {}, "stats": {"columns": 0}}):
            with pytest.raises(ValueError, match="没有可提取"):
                svc.generate_dataset_from_case(db, case_id=92, user_id=1)


# ============ 数据集复制 / 快照重新同步 ============

class TestCopyDataset:
    def _ds(self):
        return SimpleNamespace(
            id=5, project_id=1, case_id=9, name="场景A",
            description="描述", columns=[{"key": "bl_no", "type": "string"}],
            node_configs=[{"node_id": "n1", "api_id": 7, "pre_process": [],
                           "post_extract": [], "assertions": [], "wait_after_ms": 0}],
            rows=[SimpleNamespace(id=51, row_index=1, data={"bl_no": "B1"}),
                  SimpleNamespace(id=52, row_index=2, data={"bl_no": "B2"})],
        )

    def test_copy_deep_clones_all(self):
        """复制：列/行/节点配置快照全量深拷贝，命名「原名-副本」，归属同用例"""
        src = self._ds()
        db = _fake_db()
        with patch.object(svc.crud, "get_dataset", return_value=src), \
             patch.object(svc, "create_dataset") as fake_create:
            fake_create.return_value = SimpleNamespace(id=21)
            cp = svc.copy_dataset(db, 5, user_id=1)
        kw = fake_create.call_args.kwargs
        assert kw["name"] == "场景A-副本"
        assert kw["case_id"] == 9 and kw["project_id"] == 1
        assert kw["columns"] == [{"key": "bl_no", "type": "string"}]
        assert kw["node_configs"] == src.node_configs and kw["node_configs"] is not src.node_configs
        assert kw["rows_data"] == [{"bl_no": "B1"}, {"bl_no": "B2"}]
        assert cp.id == 21

    def test_copy_missing_rejected(self):
        with patch.object(svc.crud, "get_dataset", return_value=None):
            with pytest.raises(ValueError, match="数据集不存在"):
                svc.copy_dataset(_fake_db(), 99, user_id=1)

    def test_copy_name_suffix_strips_old_suffix(self):
        """连续复制「副本」不叠后缀：场景A-副本 → 场景A-副本2"""
        src = self._ds()
        src.name = "场景A-副本"
        db = _fake_db()
        with patch.object(svc.crud, "get_dataset", return_value=src), \
             patch.object(svc, "create_dataset") as fake_create:
            fake_create.return_value = SimpleNamespace(id=22)
            svc.copy_dataset(db, 5, user_id=1)
        assert fake_create.call_args.kwargs["name"] == "场景A-副本2"


class TestResyncNodeConfigs:
    def test_resync_replaces_snapshot_keeps_data(self):
        """重新同步：用例当前节点配置整块替换快照；列/行数据不动"""
        ds = SimpleNamespace(id=5, case_id=9, columns=[{"key": "a", "type": "string"}],
                             node_configs=[{"node_id": "old", "api_id": 1, "pre_process": [],
                                            "post_extract": [], "assertions": [], "wait_after_ms": 0}],
                             rows=[SimpleNamespace(id=1, row_index=1, data={"a": 1})])
        cfgs = [_cfg("n1", 7, pre=[{"type": "set_field", "path": "teu", "value": 2}], wait=100)]

        def fake_query(model):
            if getattr(model, "__name__", "") == "CaseNodeConfig":
                return SimpleNamespace(filter=lambda *a: SimpleNamespace(all=lambda: cfgs))
            return SimpleNamespace(filter=lambda *a: SimpleNamespace(all=list))

        db = SimpleNamespace(query=fake_query, commit=lambda: None)
        with patch.object(svc.crud, "get_testcase",
                          return_value=SimpleNamespace(id=9, dag_config={"nodes": [{"id": "n1"}], "edges": []})), \
             patch.object(svc.crud, "get_dataset", return_value=ds):
            n = svc.resync_node_configs(db, 5)
        assert n == 1
        assert ds.node_configs[0]["node_id"] == "n1" and ds.node_configs[0]["wait_after_ms"] == 100
        assert ds.columns == [{"key": "a", "type": "string"}]  # 列不动
        assert ds.rows[0].data == {"a": 1}  # 行不动

    def test_resync_missing_rejected(self):
        with patch.object(svc.crud, "get_dataset", return_value=None):
            with pytest.raises(ValueError, match="数据集不存在"):
                svc.resync_node_configs(_fake_db(), 99)


# ============ 数据集间对比与覆盖合并 ============

class TestCompareAndMerge:
    """对比按 api_id 配对相同节点；可覆盖列=节点参数化列∩两侧数据集列。"""

    def _mk_env(self):
        """目标 bb（用例B）：节点 n1(api7)/n2(api8)；源 aa（用例A）：m1(api7)/m3(api9)。
        api7 相同（可覆盖）；api9 目标没有（跳过）；api8 源没有（跳过）。"""
        t_ds = SimpleNamespace(
            id=101, name="bb", case_id=2, project_id=1,
            columns=[{"key": "bl_no", "type": "string"}, {"key": "teu", "type": "int"},
                     {"key": "only_b", "type": "string"}],
            node_configs=[
                {"node_id": "n1", "api_id": 7, "pre_process": [], "post_extract": [], "assertions": [], "wait_after_ms": 0},
                {"node_id": "n2", "api_id": 8, "pre_process": [], "post_extract": [], "assertions": [], "wait_after_ms": 0},
            ],
            rows=[SimpleNamespace(id=1, row_index=1, data={"bl_no": "B1", "teu": 1, "only_b": "keep"})],
        )
        s_ds = SimpleNamespace(
            id=202, name="aa", case_id=1, project_id=1,
            columns=[{"key": "bl_no", "type": "string"}, {"key": "teu", "type": "int"},
                     {"key": "only_a", "type": "string"}],
            node_configs=[
                {"node_id": "m1", "api_id": 7, "pre_process": [], "post_extract": [], "assertions": [], "wait_after_ms": 0},
                {"node_id": "m3", "api_id": 9, "pre_process": [], "post_extract": [], "assertions": [], "wait_after_ms": 0},
            ],
            rows=[SimpleNamespace(id=9, row_index=1, data={"bl_no": "A1", "teu": 9, "only_a": "x"})],
        )
        apis = {
            7: SimpleNamespace(id=7, name="新建订单",
                               fields=[_field("bl_no", "X"), _field("teu", "1", ftype="int"),
                                       _field("order_id", "${order_id}")]),
            8: SimpleNamespace(id=8, name="审核", fields=[_field("only_b", "v")]),
            9: SimpleNamespace(id=9, name="独有API", fields=[_field("only_a", "v")]),
        }

        def fake_get(_self, pk):
            return apis.get(pk)

        db = SimpleNamespace(get=fake_get, query=lambda *a: SimpleNamespace(
            filter=lambda *b: SimpleNamespace(first=lambda: None)), commit=lambda: None)
        return db, t_ds, s_ds, apis

    def test_compare_pairs_by_api_id(self):
        """相同 api_id 配对；可覆盖列=节点参数化列∩两侧列（动态注入列剔除）"""
        db, t_ds, s_ds, _ = self._mk_env()
        datasets = {101: t_ds, 202: s_ds}
        with patch.object(svc.crud, "get_dataset", side_effect=lambda _db, i: datasets[i]), \
             patch.object(svc.crud, "list_rows", return_value=s_ds.rows):
            out = svc.compare_datasets(db, 101, 202)
        assert [n["api_id"] for n in out["common_nodes"]] == [7]
        node = out["common_nodes"][0]
        assert node["api_name"] == "新建订单"
        assert node["columns"] == ["bl_no", "teu"]  # order_id 动态剔除，only_b/only_a 不交集
        assert out["columns_total"] == 2
        assert out["source"]["rows"] == 1

    def test_compare_no_common_nodes(self):
        """无相同节点 → common_nodes 空（前端提示无覆盖必要）"""
        db, t_ds, s_ds, _ = self._mk_env()
        s_ds.node_configs = [c for c in s_ds.node_configs if c["api_id"] == 9]
        datasets = {101: t_ds, 202: s_ds}
        with patch.object(svc.crud, "get_dataset", side_effect=lambda _db, i: datasets[i]), \
             patch.object(svc.crud, "list_rows", return_value=s_ds.rows):
            out = svc.compare_datasets(db, 101, 202)
        assert out["common_nodes"] == [] and out["columns_total"] == 0

    def test_compare_same_dataset_rejected(self):
        db, _, _, _ = self._mk_env()
        with pytest.raises(ValueError, match="不能相同"):
            svc.compare_datasets(db, 1, 1)

    def test_merge_overrides_common_columns_only(self):
        """合并：源行同节点列值刷到目标全部行；目标独有列保留；空值不覆盖"""
        db, t_ds, s_ds, apis = self._mk_env()
        t_ds.rows.append(SimpleNamespace(id=2, row_index=2, data={"bl_no": "B2", "teu": 2, "only_b": "keep2"}))
        s_ds.rows[0].data["only_a"] = "x"
        s_ds.rows[0].data["bl_no"] = ""  # 空值：不覆盖
        datasets = {101: t_ds, 202: s_ds}

        def fake_query(model):
            name = getattr(model, "__name__", "")
            if name == "DataSetRow":
                return SimpleNamespace(filter=lambda *a, **k: SimpleNamespace(first=lambda: s_ds.rows[0]))
            return SimpleNamespace(filter=lambda *a: SimpleNamespace(all=list))

        db = SimpleNamespace(get=lambda _s, pk: apis.get(pk), query=fake_query, commit=lambda: None)
        with patch.object(svc.crud, "get_dataset", side_effect=lambda _db, i: datasets[i]), \
             patch.object(svc.crud, "list_rows", side_effect=lambda _db, i: s_ds.rows if i == 202 else t_ds.rows):
            result = svc.merge_from_dataset(db, 101, 202)
        assert result["columns"] == 1 and result["keys"] == ["teu"]
        assert all(r.data["teu"] == 9 for r in t_ds.rows)            # teu 刷成源值
        assert [r.data["bl_no"] for r in t_ds.rows] == ["B1", "B2"]  # 源空值不覆盖
        assert all(r.data["only_b"] for r in t_ds.rows)              # 目标独有列保留

    def test_merge_selected_apis_only(self):
        """指定 api_ids 只刷所选节点列（不在相同节点列表内报错）"""
        db, t_ds, s_ds, apis = self._mk_env()
        datasets = {101: t_ds, 202: s_ds}

        def fake_query(model):
            name = getattr(model, "__name__", "")
            if name == "DataSetRow":
                return SimpleNamespace(filter=lambda *a, **k: SimpleNamespace(first=lambda: s_ds.rows[0]))
            return SimpleNamespace(filter=lambda *a: SimpleNamespace(all=list))

        db = SimpleNamespace(get=lambda _s, pk: apis.get(pk), query=fake_query, commit=lambda: None)
        with patch.object(svc.crud, "get_dataset", side_effect=lambda _db, i: datasets[i]), \
             patch.object(svc.crud, "list_rows", side_effect=lambda _db, i: s_ds.rows if i == 202 else t_ds.rows):
            with pytest.raises(ValueError, match="不在相同节点列表"):
                svc.merge_from_dataset(db, 101, 202, api_ids=[8])


# ============ config_drift：快照过期检测（执行前提示） ============

class TestConfigDrift:
    def _mk_env(self, snapshot: list, cur_cfgs: list):
        """snapshot: 数据集 node_configs；cur_cfgs: 用例当前 CaseNodeConfig 列表"""
        ds = SimpleNamespace(id=54, case_id=177, node_configs=snapshot)
        case = SimpleNamespace(id=177, dag_config={"nodes": [
            {"id": "n_gen", "label": "生成子订单"},
            {"id": "n_audit", "label": "审核"},
        ], "edges": []})
        db = SimpleNamespace(query=lambda *a: SimpleNamespace(
            filter=lambda *b: SimpleNamespace(all=lambda: cur_cfgs)))
        return db, ds, case

    def _run(self, snapshot, cur_cfgs):
        db, ds, case = self._mk_env(snapshot, cur_cfgs)
        with patch.object(svc.crud, "get_dataset", return_value=ds), \
             patch.object(svc.crud, "get_testcase", return_value=case):
            return svc.config_drift(db, 54)

    def test_in_sync_returns_not_stale(self):
        """快照与当前编排一致 → stale=False"""
        cfg = _cfg("n_gen", 5, asserts=[{"type": "db_query_count_equals", "expected": "2"}])
        snap = svc.snapshot_node_configs(SimpleNamespace(dag_config={"nodes": [{"id": "n_gen"}]}), [cfg])
        out = self._run(snap, [cfg])
        assert out == {"stale": False, "nodes": []}

    def test_assertion_removed_reports_drift(self):
        """用户删除断言后未同步 → 报告该节点 drift（本次 debug 场景）"""
        old = _cfg("n_gen", 5, asserts=[{"type": "db_query_count_equals", "expected": "2"}])
        cur = _cfg("n_gen", 5)  # 断言已删
        snap = svc.snapshot_node_configs(SimpleNamespace(dag_config={"nodes": [{"id": "n_gen"}]}), [old])
        out = self._run(snap, [cur])
        assert out["stale"] is True
        assert len(out["nodes"]) == 1
        node = out["nodes"][0]
        assert node["node_id"] == "n_gen"
        assert node["label"] == "生成子订单"
        assert any("断言" in c for c in node["changes"])

    def test_field_level_change_description(self):
        """字段级差异描述：前置/断言给条数变化，标量给值变化"""
        old = _cfg("n_audit", 30, pre=[{"type": "set_field", "path": "a", "value": 1}], wait=100)
        cur = _cfg("n_audit", 30, wait=200)
        snap = svc.snapshot_node_configs(SimpleNamespace(dag_config={"nodes": [{"id": "n_audit"}]}), [old])
        out = self._run(snap, [cur])
        changes = out["nodes"][0]["changes"]
        assert any("前置处理：1 条 → 0 条" in c for c in changes)
        assert any("等待时长：100 → 200" in c for c in changes)

    def test_node_missing_on_one_side_ignored(self):
        """仅一侧存在的节点不报 drift：快照缺位执行回落用例配置，用例缺位节点不再执行"""
        snap_cfg = _cfg("n_gen", 5)
        new_cfg = _cfg("n_extra", 6)
        snap = svc.snapshot_node_configs(
            SimpleNamespace(dag_config={"nodes": [{"id": "n_gen"}]}), [snap_cfg])
        out = self._run(snap, [snap_cfg, new_cfg])
        assert out == {"stale": False, "nodes": []}
