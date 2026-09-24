"""sync_case_variable_pool 单测：变量池收集器（保存钩子：清空转引用）。

数据集模式定案的数据侧迁移：静态入参拆叶入池 + 节点字面量清空为自动引用占位；
接口默认值退役（静态入池 / 动态迁为节点引用）；有值=覆盖（键已在池保留字面量）。
"""
from types import SimpleNamespace
from unittest.mock import patch

from app import models
from app.services import dataset_service as svc


class _Query:
    def __init__(self, items):
        self._items = items

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)


def _db(cfgs=(), apis=()):
    def query(model):
        if model is models.CaseNodeConfig:
            return _Query(cfgs)
        if model is models.ApiDefinition:
            return _Query(apis)
        return _Query([])

    added = []
    db = SimpleNamespace(query=query, add=added.append, commit=lambda: None,
                         refresh=lambda o: None, flush=lambda: None)
    return db, added


def _case(dataset_id=None, nodes=("n1",)):
    return SimpleNamespace(id=11, project_id=1, dataset_id=dataset_id, name="下单用例",
                           dag_config={"nodes": [{"id": n} for n in nodes], "edges": []})


def _cfg(node_id="n1", api_id=7, pre=None):
    return SimpleNamespace(node_id=node_id, api_id=api_id, pre_process=list(pre or []))


def _field(key, ftype="string", default=None):
    return SimpleNamespace(key=key, field_type=ftype, default_value=default)


def _api(api_id=7, fields=(), name="下单"):
    return SimpleNamespace(id=api_id, name=name, fields=list(fields))


class TestSaveNodeValues:
    """节点级手动覆盖（数据集页节点页签编辑语义）"""

    def _env(self, pre=None):
        """dataset + 单节点 cfg 的最小环境"""
        ds = SimpleNamespace(id=90, case_id=11, project_id=1, columns=[], rows=[])
        cfg = _cfg(pre=pre)
        db, _ = _db([cfg], [])
        db._ds = ds
        return db, cfg, ds

    def test_set_appends_new_action_and_updates_existing(self):
        pre = [{"type": "set_field", "path": "status", "value": 1},
               {"type": "iterate_set", "field": "unique_id", "value": "${uuid()}",
                "list_path": "items", "sync_list": "items2"}]
        db, cfg, ds = self._env(pre)
        with patch.object(svc, "get_dataset", return_value=ds):
            n = svc.save_node_values(db, ds.id, "n1",
                                     sets={"status": 2, "entrust_status": 2}, clears=[])
        assert n == 2
        assert cfg.pre_process == [
            {"type": "set_field", "path": "status", "value": 2},          # 就地更新
            {"type": "iterate_set", "field": "unique_id", "value": "${uuid()}",
             "list_path": "items", "sync_list": "items2"},                # 不动
            {"type": "set_field", "path": "entrust_status", "value": 2},  # 追加
        ]

    def test_clear_removes_literal_but_rejects_dynamic(self):
        db, cfg, ds = self._env(pre=[{"type": "set_field", "path": "status", "value": 1}])
        with patch.object(svc, "get_dataset", return_value=ds):
            assert svc.save_node_values(db, ds.id, "n1", sets={}, clears=["status"]) == 1
        assert cfg.pre_process == []

        db, cfg, ds = self._env(pre=[{"type": "set_field", "path": "bl_no", "value": "${gen()}"}])
        with patch.object(svc, "get_dataset", return_value=ds):
            try:
                svc.save_node_values(db, ds.id, "n1", sets={}, clears=["bl_no"])
                raise AssertionError("应拒绝清除动态绑定")
            except ValueError as e:
                assert "动态绑定" in str(e)

    def test_noop_when_no_change(self):
        db, cfg, ds = self._env(pre=[{"type": "set_field", "path": "status", "value": 1}])
        with patch.object(svc, "get_dataset", return_value=ds):
            assert svc.save_node_values(db, ds.id, "n1", sets={}, clears=[]) == 0
        assert cfg.pre_process == [{"type": "set_field", "path": "status", "value": 1}]


class TestCollectAndClear:
    """清空转引用：字面量入池后，接口字段的行直接删除（占位冗余——字段本身
    参与运行时按名解析）；非接口字段（add_field 自定义键）保留空占位行"""

    def test_literal_collected_and_cleared_with_pool_created(self):
        """无绑定数据集：自动创建「用例名-变量池」+ 绑定 + 1 行快照，接口字段行删除"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "bl_no", "value": "BL001"}])
        case = _case()
        db, added = _db([cfg], [_api(fields=[_field("bl_no")])])

        stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["columns"] == 1
        assert cfg.pre_process == []  # 接口字段收集后删行（不再保留空占位）
        pool = added[0]
        assert isinstance(pool, models.DataSet)
        assert pool.case_id == 11 and pool.name == "下单用例-变量池"
        assert pool.columns == [{"key": "bl_no", "type": "string"}]
        assert case.dataset_id is pool.id
        # create_dataset 内部添加的 1 行快照
        rows = [o for o in added if isinstance(o, models.DataSetRow)]
        assert len(rows) == 1 and rows[0].data == {"bl_no": "BL001"}

    def test_collect_idempotent(self):
        """二次保存幂等：空占位行被清理（接口字段），池不重复建"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "bl_no", "value": ""}])
        case = _case(dataset_id=99)
        pool = SimpleNamespace(id=99, case_id=11,
                               columns=[{"key": "bl_no", "type": "string"}],
                               rows=[SimpleNamespace(row_index=1, data={"bl_no": "BL001"})])
        db, added = _db([cfg], [_api(fields=[_field("bl_no")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["columns"] == 0
        assert cfg.pre_process == []  # 接口字段空占位行被清理（幂等）
        assert pool.columns == [{"key": "bl_no", "type": "string"}]  # 无重复列
        assert not added

    def test_key_already_in_pool_kept_as_manual_override(self):
        """池值与字面量同名不同值 → 值冲突：字面量保留为手动覆盖、池存量值保留
        （拦截收集已防串值；清存量会破坏"参数靠池"的用例——case 92 实证）"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "bl_no", "value": "MANUAL"}])
        case = _case(dataset_id=99)
        pool = SimpleNamespace(id=99, case_id=11,
                               columns=[{"key": "bl_no", "type": "string"}],
                               rows=[SimpleNamespace(row_index=1, data={"bl_no": "BL001"})])
        db, _ = _db([cfg], [_api(fields=[_field("bl_no")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["kept"] == 1 and stats["columns"] == 0
        assert stats["value_conflicts"] == ["bl_no"]
        assert cfg.pre_process[0]["value"] == "MANUAL"
        assert pool.rows[0].data == {"bl_no": "BL001"}  # 存量值保留
        assert pool.columns == [{"key": "bl_no", "type": "string"}]

    def test_equal_value_absorbed_to_reference(self):
        """值相等收编：字面量与池值一致 → 清空转引用（执行行为不变，池接管）"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "bl_no", "value": "BL001"}])
        case = _case(dataset_id=99)
        pool = SimpleNamespace(id=99, case_id=11,
                               columns=[{"key": "bl_no", "type": "string"}],
                               rows=[SimpleNamespace(row_index=1, data={"bl_no": "BL001"})])
        db, _ = _db([cfg], [_api(fields=[_field("bl_no")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["kept"] == 0 and stats["collected"]
        assert cfg.pre_process == []                  # 接口字段收编后删行
        assert pool.rows[0].data == {"bl_no": "BL001"}  # 池值不变（本来就相等）
        assert pool.columns == [{"key": "bl_no", "type": "string"}]  # 列不重复追加

    def test_equal_leaves_family_absorbed(self):
        """整对象字面量与池中拆叶族逐键全等 → 收编清空（父路径占位）"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "to_customer",
                         "value": '{"put_amount": 1, "remark": "r"}'}])
        case = _case(dataset_id=99)
        pool = SimpleNamespace(
            id=99, case_id=11,
            columns=[{"key": "to_customer.put_amount", "type": "int"},
                     {"key": "to_customer.remark", "type": "string"}],
            rows=[SimpleNamespace(row_index=1,
                                  data={"to_customer.put_amount": 1, "to_customer.remark": "r"})])
        db, _ = _db([cfg], [_api(fields=[_field("to_customer", ftype="object")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["kept"] == 0 and stats["collected"]
        assert cfg.pre_process == []  # 接口字段（to_customer）收编后删行
        assert pool.rows[0].data == {"to_customer.put_amount": 1, "to_customer.remark": "r"}
        assert [c["key"] for c in pool.columns] == ["to_customer.put_amount", "to_customer.remark"]

    def test_extra_pool_leaf_blocks_absorb(self):
        """池族有字面量之外的额外叶 → 不收编（清空后按名解析会取到额外叶，
        请求多出字段改变形状），保留为手动覆盖"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "to_customer",
                         "value": '{"put_amount": 1}'}])
        case = _case(dataset_id=99)
        pool = SimpleNamespace(
            id=99, case_id=11,
            columns=[{"key": "to_customer.put_amount", "type": "int"},
                     {"key": "to_customer.remark", "type": "string"}],
            rows=[SimpleNamespace(row_index=1,
                                  data={"to_customer.put_amount": 1, "to_customer.remark": "r"})])
        db, _ = _db([cfg], [_api(fields=[_field("to_customer", ftype="object")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["kept"] == 1 and not stats["collected"]
        assert cfg.pre_process[0]["value"] == '{"put_amount": 1}'  # 保留字面量
        assert pool.rows[0].data["to_customer.remark"] == "r"      # 池不动

    def test_force_collects_in_pool_literal(self):
        """force 统一收口：键已在池也收集——以节点值为准覆盖池值后清空节点"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "bl_no", "value": "NODE_VAL"}])
        case = _case(dataset_id=99)
        pool = SimpleNamespace(id=99, case_id=11,
                               columns=[{"key": "bl_no", "type": "string"}],
                               rows=[SimpleNamespace(row_index=1, data={"bl_no": "POOL_VAL"})])
        db, _ = _db([cfg], [_api(fields=[_field("bl_no")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1, force=True)

        assert stats["kept"] == 0 and stats["collected"]
        assert cfg.pre_process == []  # 接口字段收口后删行
        assert pool.rows[0].data == {"bl_no": "NODE_VAL"}  # 以节点值为准（当前生效值）
        assert pool.columns == [{"key": "bl_no", "type": "string"}]  # 列不重复追加

    def test_force_family_replace_on_conflict(self):
        """force 键族替换：节点子键字面量与池中整对象列冲突 → 驱逐整列收入子键；
        ${} 动态绑定不动"""
        cfg = _cfg(pre=[
            {"type": "set_field", "path": "to_customer.remark", "value": "r"},
            {"type": "set_field", "path": "k", "value": "${x}"},
        ])
        case = _case(dataset_id=99)
        pool = SimpleNamespace(id=99, case_id=11,
                               columns=[{"key": "to_customer", "type": "object"}],
                               rows=[SimpleNamespace(row_index=1, data={"to_customer": {"a": 1}})])
        db, _ = _db([cfg], [_api(fields=[_field("to_customer", ftype="object")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1, force=True)

        assert stats["evicted"] == ["to_customer"]
        assert cfg.pre_process[0]["value"] == ""   # 子键收口清空
        assert cfg.pre_process[1]["value"] == "${x}"  # 动态不动
        # 池：整对象列被驱逐，子键成列，行值替换
        assert [c["key"] for c in pool.columns] == ["to_customer.remark"]
        assert pool.rows[0].data == {"to_customer.remark": "r"}

    def test_force_scalar_replaces_leaves_family(self):
        """force 键族替换（反向）：顶层标量字面量先入池（pre 先于字段默认），
        同名 object 字段的拆叶默认因节点已显式配置被跳过——最终池以标量为准
        （线上生效值即标量，保行为）"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "service_project",
                         "value": "customs_clearance"}])
        api = SimpleNamespace(id=7, name="下单", fields=[
            SimpleNamespace(key="service_project", field_type="object",
                            default_value='{"booking_space": 1, "manifest": 2}',
                            required=False),
        ])
        case = _case(dataset_id=99)
        pool = SimpleNamespace(id=99, case_id=11, columns=[],
                               rows=[SimpleNamespace(row_index=1, data={})])
        db, _ = _db([cfg], [api])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            svc.sync_case_variable_pool(db, case, user_id=1, force=True)
        keys = {c["key"] for c in pool.columns}
        assert keys == {"service_project"}  # 拆叶默认未入池（节点显式配置优先）
        assert cfg.pre_process == []  # 接口字段收口后删行
        assert pool.rows[0].data == {"service_project": "customs_clearance"}

    def test_list_index_path_collected(self):
        """列表下标路径（select_node_user.0.user_id）原样成键入池；
        下标路径非接口字段名 → 保留空占位行（按名解析的键来源）"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "select_node_user.0.user_id",
                         "value": 60}])
        case = _case()
        db, added = _db([cfg], [_api(fields=[_field("select_node_user")])])

        stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["columns"] == 1
        pool = added[0]
        assert pool.columns[0]["key"] == "select_node_user.0.user_id"
        rows = [o for o in added if isinstance(o, models.DataSetRow)]
        assert rows[0].data == {"select_node_user.0.user_id": 60}
        assert cfg.pre_process == [{"type": "set_field", "path": "select_node_user.0.user_id", "value": ""}]

    def test_dynamic_binding_kept(self):
        """${} 动态绑定原样保留（属手动层显式引用），不入池不清空"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "order_id", "value": "${oid}"}])
        case = _case()
        db, added = _db([cfg], [_api(fields=[_field("order_id")])])

        stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["dynamic"] == 1 and stats["columns"] == 0
        assert cfg.pre_process[0]["value"] == "${oid}"
        assert not added  # 无可收集值 → 不建池

    def test_nested_object_literal_flattened_to_leaves(self):
        """嵌套对象字面量递归拆叶：to_customer={"put_amount":1,"remark":"r"} → 两列点路径键"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "to_customer",
                         "value": '{"put_amount": 1, "remark": "r"}'}])
        case = _case()
        db, added = _db([cfg], [_api(fields=[_field("to_customer", ftype="object")])])

        stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["columns"] == 2
        pool = added[0]
        assert [c["key"] for c in pool.columns] == ["to_customer.put_amount", "to_customer.remark"]
        assert cfg.pre_process == []  # 接口字段收集后删行
        rows = [o for o in added if isinstance(o, models.DataSetRow)]
        assert rows[0].data == {"to_customer.put_amount": 1, "to_customer.remark": "r"}

    def test_number_string_not_json_parsed(self):
        """纯数字字符串不 JSON 解析：单号 '001' 保类型入池（int 化会丢前导零）"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "bl_no", "value": "001"}])
        case = _case()
        db, added = _db([cfg], [_api(fields=[_field("bl_no")])])

        svc.sync_case_variable_pool(db, case, user_id=1)

        pool = added[0]
        assert pool.columns[0]["type"] == "string"
        rows = [o for o in added if isinstance(o, models.DataSetRow)]
        assert rows[0].data == {"bl_no": "001"}

    def test_invalid_leaf_key_keeps_literal(self):
        """对象内键不合法（含空格/表达式符）→ 不入池，字面量保留为手动覆盖"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "obj", "value": '{"a b": 1}'}])
        case = _case()
        db, added = _db([cfg], [_api(fields=[_field("obj")])])

        stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["invalid"] == 1 and stats["columns"] == 0
        assert cfg.pre_process[0]["value"] == '{"a b": 1}'
        assert not added

    def test_php_bracket_key_literal_collects(self):
        """PHP 表单风格方括号键（真实参数名）合法入池：file[] 字面量按
        接口 file 字段类型建列（文件 ID 值），search_time[x] 建字符串列"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "file[]", "value": "12"},
                        {"type": "set_field", "path": "search_time[delivery]", "value": "d1"}])
        case = _case()
        db, added = _db([cfg], [_api(fields=[_field("file[]", "file"),
                                             _field("search_time[delivery]")])])

        svc.sync_case_variable_pool(db, case, user_id=1)

        pool = added[0]
        col_types = {c["key"]: c["type"] for c in pool.columns}
        assert col_types == {"file[]": "file", "search_time[delivery]": "string"}
        rows = [o for o in added if isinstance(o, models.DataSetRow)]
        assert rows[0].data == {"file[]": "12", "search_time[delivery]": "d1"}

    def test_prefix_conflict_keeps_literal(self):
        """池已有 to_customer（整对象列），新字面量 to_customer.remark 与之父子冲突 → 保留"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "to_customer.remark", "value": "r"}])
        case = _case(dataset_id=99)
        pool = SimpleNamespace(id=99, case_id=11,
                               columns=[{"key": "to_customer", "type": "object"}],
                               rows=[SimpleNamespace(row_index=1, data={"to_customer": {}})])
        db, _ = _db([cfg], [_api(fields=[_field("to_customer.remark")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["conflicts"] == ["to_customer.remark"]
        assert cfg.pre_process[0]["value"] == "r"  # 保留为手动覆盖

    def test_file_field_collected_typed_file(self):
        """file 字段的字面量（文件 ID）→ 列 type=file（行编辑器渲染文件选择器）"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "id_card", "value": "35"}])
        case = _case()
        db, added = _db([cfg], [_api(fields=[_field("id_card", ftype="file")])])

        svc.sync_case_variable_pool(db, case, user_id=1)

        pool = added[0]
        assert pool.columns == [{"key": "id_card", "type": "file"}]


class TestApiDefaultsMigration:
    """接口默认值退役迁移：静态入池 / 动态迁为节点引用 / 已在池跳过"""

    def test_static_default_collected(self):
        """静态默认 → 入池（键不在池时）；节点不产生占位（字段键本身参与运行时解析）"""
        case = _case()
        db, added = _db([_cfg()], [_api(fields=[_field("bl_no", default="DEFAULT")])])

        stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["columns"] == 1
        pool = added[0]
        assert pool.columns == [{"key": "bl_no", "type": "string"}]
        rows = [o for o in added if isinstance(o, models.DataSetRow)]
        assert rows[0].data == {"bl_no": "DEFAULT"}

    def test_dynamic_default_migrated_to_node_binding(self):
        """动态 ${} 默认 → 迁为该节点 pre_process 动态引用（绑定语义不变）"""
        case = _case()
        cfg = _cfg()
        db, _ = _db([cfg], [_api(fields=[_field("order_id", default="${oid}")])])

        stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["dynamic"] == 1
        assert cfg.pre_process == [{"type": "set_field", "path": "order_id", "value": "${oid}"}]

    def test_default_in_pool_skipped(self):
        """池值与默认值同名不同值（非 force）→ 值冲突：默认不入池、池存量值保留
        （防默认值经池串改已有配置——拦截收集即可；force 收口另测）"""
        case = _case(dataset_id=99)
        pool = SimpleNamespace(id=99, case_id=11,
                               columns=[{"key": "bl_no", "type": "string"}],
                               rows=[SimpleNamespace(row_index=1, data={"bl_no": "POOL"})])
        db, _ = _db([_cfg()], [_api(fields=[_field("bl_no", default="DEFAULT")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["columns"] == 0
        assert stats["value_conflicts"] == ["bl_no"]
        assert pool.rows[0].data == {"bl_no": "POOL"}  # 存量值保留

    def test_force_refreshes_default_in_pool(self):
        """force 统一收口：接口默认值也刷新池中旧值——键已在池且节点未显式配置，
        以当前默认值为准（旧快照池值偏离接口定义时，如 entrust_status 旧=1 当前默认=2）"""
        case = _case(dataset_id=99)
        pool = SimpleNamespace(id=99, case_id=11,
                               columns=[{"key": "entrust_status", "type": "int"}],
                               rows=[SimpleNamespace(row_index=1, data={"entrust_status": 1})])
        db, _ = _db([_cfg()], [_api(fields=[_field("entrust_status", ftype="int", default="2")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1, force=True)

        assert stats["collected"]
        assert pool.rows[0].data == {"entrust_status": 2}   # 池值以当前默认刷新
        assert pool.columns == [{"key": "entrust_status", "type": "int"}]  # 列不重复

    def test_force_cross_api_default_not_collected(self):
        """force 多接口同名默认值不同（同型）→ 跨接口同名字段的默认值一律
        不入池（单侧非空快照默认值也会经池串值，case 193 实证；更早的
        "同名异值拦截"被跨接口声明拦截取代）；无冲突 → 池存量值保留"""
        case = _case(dataset_id=99, nodes=("n1", "n2"))
        c1 = _cfg(node_id="n1", api_id=7)
        c2 = _cfg(node_id="n2", api_id=8)
        api1 = _api(api_id=7, fields=[_field("customer_id", default="34361")])
        api2 = _api(api_id=8, fields=[_field("customer_id", default="99999")])
        pool = SimpleNamespace(id=99, case_id=11,
                               columns=[{"key": "customer_id", "type": "string"}],
                               rows=[SimpleNamespace(row_index=1, data={"customer_id": "OLD"})])
        db, _ = _db([c1, c2], [api1, api2])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1, force=True)

        assert stats["value_conflicts"] == []
        assert stats["columns"] == 0
        assert pool.rows[0].data == {"customer_id": "OLD"}  # 无冲突，池值保留
        assert pool.columns == [{"key": "customer_id", "type": "string"}]

    def test_set_field_wins_over_default(self):
        """同节点字面量与默认值同名不同值 → 值冲突：不入池，字面量保留为
        手动覆盖（不再"清空转引用"，默认值也不迁）"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "bl_no", "value": "CASE"}])
        case = _case()
        db, added = _db([cfg], [_api(fields=[_field("bl_no", default="DEFAULT")])])

        stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["value_conflicts"] == ["bl_no"]
        assert not added  # 不建池
        assert cfg.pre_process == [{"type": "set_field", "path": "bl_no", "value": "CASE"}]

    def test_node_explicit_config_shields_default(self):
        """节点已显式配置该 path（空占位被清理但 path 已记录）→ 默认值不再迁移"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "bl_no", "value": ""}])
        case = _case(dataset_id=99)
        pool = SimpleNamespace(id=99, case_id=11, columns=[{"key": "other", "type": "string"}],
                               rows=[SimpleNamespace(row_index=1, data={"other": "x"})])
        db, _ = _db([cfg], [_api(fields=[_field("bl_no", default="DEFAULT")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["columns"] == 0
        assert cfg.pre_process == []  # 接口字段空占位行被清理
        # other 键无人使用被悬空清理（既有行为，与本测试点无关）；
        # 默认值 DEFAULT 未迁入池（node_paths 屏蔽生效）
        assert pool.rows[0].data == {}


class TestExistingPool:
    """已有池的写入口径：新列追加、新键写全部行"""

    def test_new_key_written_to_all_rows(self):
        """新键写入全部现有行（字面量对所有行变体生效）；
        池中 bl_no 不被剩余编排使用 → 悬空清理剔除（增删节点后池自动维护）"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "voy", "value": "V1"}])
        case = _case(dataset_id=99)
        pool = SimpleNamespace(id=99, case_id=11,
                               columns=[{"key": "bl_no", "type": "string"}],
                               rows=[SimpleNamespace(row_index=1, data={"bl_no": "A"}),
                                     SimpleNamespace(row_index=2, data={"bl_no": "B"})])
        db, added = _db([cfg], [_api(fields=[_field("voy")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            svc.sync_case_variable_pool(db, case, user_id=1)

        assert [c["key"] for c in pool.columns] == ["voy"]
        assert pool.rows[0].data == {"voy": "V1"}
        assert pool.rows[1].data == {"voy": "V1"}
        assert not added  # 不新建行

    def test_pool_without_rows_creates_first_row(self):
        pool = SimpleNamespace(id=99, case_id=11, columns=[{"key": "bl_no", "type": "string"}],
                               rows=[])
        cfg = _cfg(pre=[{"type": "set_field", "path": "voy", "value": "V1"}])
        case = _case(dataset_id=99)
        db, added = _db([cfg], [_api(fields=[_field("voy")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            svc.sync_case_variable_pool(db, case, user_id=1)

        rows = [o for o in added if isinstance(o, models.DataSetRow)]
        assert len(rows) == 1 and rows[0].row_index == 1
        assert rows[0].data == {"voy": "V1"}


class TestNoCollectables:
    def test_reuses_existing_dataset_when_unbound(self):
        """无绑定但名下已有数据集 → 复用最旧并绑定，不再新建（防一用例多池）"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "bl_no", "value": "BL1"}])
        case = _case(dataset_id=None)
        existing = SimpleNamespace(id=42, case_id=11,
                                   columns=[{"key": "other", "type": "string"}],
                                   rows=[SimpleNamespace(row_index=1, data={"other": "x"})])
        added = []

        def fake_query(model):
            if model is models.DataSet:
                return SimpleNamespace(
                    filter=lambda *a, **k: SimpleNamespace(
                        order_by=lambda *b: SimpleNamespace(first=lambda: existing)))
            if model is models.CaseNodeConfig:
                return _Query([cfg])
            if model is models.ApiDefinition:
                return _Query([_api(fields=[_field("bl_no")])])
            return _Query([])

        db = SimpleNamespace(query=fake_query, add=added.append,
                             commit=lambda: None, refresh=lambda o: None,
                             flush=lambda: None)
        with patch.object(svc.crud, "get_dataset", return_value=existing):
            stats = svc.sync_case_variable_pool(db, case, user_id=1)
        assert case.dataset_id == 42  # 绑定复用
        assert stats["columns"] == 1
        assert not any(isinstance(o, models.DataSet) for o in added)  # 未新建
        assert existing.rows[0].data["bl_no"] == "BL1"  # 收进复用池

    def test_unbind_skips_auto_rebind(self):
        """显式解绑（unbind=True）→ 不自动复用名下数据集，绑定保持 None（尊重解绑意图）"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "bl_no", "value": "BL1"}])
        case = _case(dataset_id=None)
        existing = SimpleNamespace(id=42, case_id=11,
                                   columns=[{"key": "other", "type": "string"}],
                                   rows=[SimpleNamespace(row_index=1, data={"other": "x"})])
        added = []

        def fake_query(model):
            if model is models.DataSet:
                return SimpleNamespace(
                    filter=lambda *a, **k: SimpleNamespace(
                        order_by=lambda *b: SimpleNamespace(first=lambda: existing)))
            if model is models.CaseNodeConfig:
                return _Query([cfg])
            if model is models.ApiDefinition:
                return _Query([_api(fields=[_field("bl_no")])])
            return _Query([])

        db = SimpleNamespace(query=fake_query, add=added.append,
                             commit=lambda: None, refresh=lambda o: None,
                             flush=lambda: None)
        with patch.object(svc.crud, "get_dataset", return_value=existing):
            stats = svc.sync_case_variable_pool(db, case, user_id=1, unbind=True)
        assert case.dataset_id is None  # 解绑意图保留，未拉回
        assert stats == {"nodes": 0, "columns": 0, "collected": [],
                         "kept": 0, "dynamic": 0, "conflicts": [], "invalid": 0,
                         "type_conflicts": [], "value_conflicts": []}
        assert not added

    def test_no_configs_noop(self):
        """无节点配置（套件用例等）→ 空统计不建池"""
        case = _case()
        db, added = _db([], [])
        stats = svc.sync_case_variable_pool(db, case)
        assert stats == {"nodes": 0, "columns": 0, "collected": [],
                         "kept": 0, "dynamic": 0, "conflicts": [], "invalid": 0,
                         "type_conflicts": [], "value_conflicts": []}
        assert not added

    def test_all_dynamic_no_pool_created(self):
        """全动态绑定 → 不建池（无静态值可收集）"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "a", "value": "${x}"}])
        case = _case()
        db, added = _db([cfg], [_api(fields=[_field("a")])])
        svc.sync_case_variable_pool(db, case)
        assert not added
        assert case.dataset_id is None


class TestOrphanCleanup:
    """悬空清理：用例增删节点后池自动维护——删节点 → 无人使用的键（列+行值）剔除；
    ${} 显式引用的变量名（手动自定义变量防断链）与前缀关联键（拆叶族）保留"""

    def _pool(self, data):
        return SimpleNamespace(
            id=99, case_id=11,
            columns=[{"key": k, "type": "string"} for k in data],
            rows=[SimpleNamespace(row_index=1, data=dict(data))])

    def test_drops_keys_of_removed_node(self):
        """池中无人使用的键被清（列+行值），在用键保留"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "bl_no", "value": "${bl_no}"}])
        case = _case(dataset_id=99)
        pool = self._pool({"bl_no": "A", "gone_key": "x"})
        db, _ = _db([cfg], [_api(fields=[_field("bl_no")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1)
        assert stats["cleaned"] == ["gone_key"]
        assert "gone_key" not in pool.rows[0].data
        assert [c["key"] for c in pool.columns] == ["bl_no"]

    def test_keeps_expression_referenced_vars(self):
        """${} 引用的手动自定义变量保留（删了会断链）"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "title", "value": "单-${my_var}-尾"}])
        case = _case(dataset_id=99)
        pool = self._pool({"my_var": "V", "gone": "x"})
        db, _ = _db([cfg], [_api(fields=[_field("title")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1)
        assert stats["cleaned"] == ["gone"]
        assert pool.rows[0].data["my_var"] == "V"

    def test_keeps_post_extract_sql_refs(self):
        """后置提取 SQL 里引用的变量名保留"""
        cfg = _cfg()
        cfg.post_extract = [{"name": "x", "source": "db",
                             "sql": "select 1 from t where q = ${q_var}"}]
        case = _case(dataset_id=99)
        pool = self._pool({"q_var": "9", "gone": "x"})
        db, _ = _db([cfg], [_api(fields=[_field("bl_no")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1)
        assert stats["cleaned"] == ["gone"]
        assert pool.rows[0].data["q_var"] == "9"

    def test_keeps_prefix_related_leaves(self):
        """拆叶族键服务于 used 整键（前缀关联）→ 保留"""
        cfg = _cfg()
        case = _case(dataset_id=99)
        pool = self._pool({"service_project.booking_space": True, "gone": "x"})
        db, _ = _db([cfg], [_api(fields=[_field("service_project", ftype="object")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1)
        assert stats["cleaned"] == ["gone"]
        assert pool.rows[0].data["service_project.booking_space"] is True
