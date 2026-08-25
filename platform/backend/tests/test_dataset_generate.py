"""从用例生成数据集（collect_case_params / generate_dataset_from_case）单测。

语义（与数据集"绑定即生效"覆盖口径一致）：
- 收集范围 = 用例中所有"写死"的请求参数（非上游 ${} 提取注入）：
  ① API 字段默认值（顶层 key、非 file、非空、不含 ${}）
  ② 前置处理 set_field/add_field 字面量（path 顶层、value 不含 ${}）
- 节点内同 key：set_field 晚于默认值组装执行，最终生效值 = set_field 值
- 跨节点同名同值合并一列（绑定即生效会同时覆盖所有同名节点）；
  同名异值冲突 → 跳过该列（合并会改变链路行为），stats 记录
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

    def test_conflicting_values_skipped(self):
        """跨节点同名异值 → 跳过（合并会改变链路行为），stats 记录冲突"""
        case = _case([("n1", 7), ("n2", 8)])
        apis = {
            7: _api([_field("action", "create")]),
            8: _api([_field("action", "audit")]),
        }
        out = svc.collect_case_params(case, [_cfg("n1", 7), _cfg("n2", 8)], apis)
        assert "action" not in [c["key"] for c in out["columns"]]
        assert any(c["key"] == "action" for c in out["stats"]["conflicts"])

    def test_dynamic_expression_skipped(self):
        """含 ${}（上游提取注入）不属"写死参数"→ 跳过并计入 dynamic"""
        case = _case([("n1", 7)])
        apis = {7: _api([_field("order_id", "${order_id}")])}
        cfg = _cfg("n1", 7, pre=[{"type": "set_field", "path": "bl_no", "value": "${bl_no}"}])
        out = svc.collect_case_params(case, [cfg], apis)
        assert out["columns"] == []
        assert out["stats"]["dynamic"] == 2

    def test_nested_path_skipped(self):
        """含点号路径（嵌套字段）→ 跳过（列名不允许点号，自动覆盖不生效）"""
        case = _case([("n1", 7)])
        apis = {7: _api([_field("to_customer.name", "张三")])}
        cfg = _cfg("n1", 7, pre=[{"type": "set_field", "path": "to_customer.amount", "value": 100}])
        out = svc.collect_case_params(case, [cfg], apis)
        assert out["columns"] == []
        assert out["stats"]["nested"] == 2

    def test_empty_and_file_skipped(self):
        """空默认值 / file 类型（值是 file_id 非业务参数）→ 跳过"""
        case = _case([("n1", 7)])
        apis = {7: _api([_field("remark", ""), _field("id_card", "12", ftype="file"),
                         _field("memo", None)])}
        out = svc.collect_case_params(case, [_cfg("n1", 7)], apis)
        assert out["columns"] == []
        assert out["stats"]["empty"] == 2

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
        assert kw["columns"] == [{"key": "bl_no", "type": "string"}, {"key": "teu", "type": "int"}]
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
