# -*- coding: utf-8 -*-
"""prepare_request 单测：四来源参数模型的取值与编排顺序（v3 直接测试面）。

取值语义（2026-09-30 定案，取代旧三层按名解析 + ${} 双次求值；同日
「动作概念退场」后前置处理动作已删除，容器常量/通配路径语义见
test_row_override）：
1. 参数取值唯一来自数据集行的 per-node 配置（config.params.body），
   spec 四选一：constant / func / ref / sql——显式配置即取值，无优先级链
2. 未配置字段按类型发空值占位（string/file → ""，array → []，其余 → None）；
   接口字段默认值不兜底；无必填概念
3. 运行时变量（后置提取 / 其他参数产出）不参与按名解析，须显式 ref
   （{"node_id", "var_path"} 结构化引用，取不到抛 ReferenceError）
"""
from types import SimpleNamespace

import pytest

from app.engine.context import ExecutionContext
from app.engine.param_resolver import SqlExecutionError
from app.engine.prepare_request import prepare_request
from app.engine.variables import ReferenceError

SELF = "n_case"


def _field(key, field_type="string", default=None, required=False):
    return SimpleNamespace(key=key, field_type=field_type, default_value=default,
                           required=required)


def _api(fields, template=None, **kw):
    return SimpleNamespace(fields=fields, request_template=template, **kw)


def _config(body=None, headers=None):
    return SimpleNamespace(params={"body": body or {}, "headers": headers or {}})


def _ctx(suite_vars=None, seed=None):
    return ExecutionContext(suite_vars=suite_vars, resume_seed=seed)


def _const(v):
    return {"source": "constant", "value": v}


def _ref(node_id, var_path, as_array=False):
    spec = {"source": "ref", "node_id": node_id, "var_path": var_path}
    if as_array:
        spec["as_array"] = True
    return spec


def _run(api, config=None, ctx=None, headers=None, self_node=SELF):
    return prepare_request(api, config, context=ctx or ExecutionContext(),
                           self_node=self_node,
                           base_headers=headers or {}, db_client=None)


class TestPriority:
    """取值模型：constant 显式值生效 / 未配置不按名解析 / 空占位规则"""

    def test_constant_beats_suite_and_upstream(self):
        """constant 显式配置即取值：注册表里同名套件/上游变量不参与（旧「手动覆盖优先」的等价迁移）"""
        api = _api([_field("bl_no")])
        config = _config(body={"bl_no": _const("MANUAL")})

        parts = _run(api, config, _ctx(suite_vars={"bl_no": "SUITE"},
                                       seed={"n_up": {"bl_no": "UP"}}))

        assert parts.body == {"bl_no": "MANUAL"}

    def test_suite_ns_ref_resolves(self):
        """ref __suite__：套件白名单注入（上游成员快照）直接可引用"""
        api = _api([_field("bl_no")])

        parts = _run(api, _config(body={"bl_no": _ref("__suite__", "bl_no")}),
                     _ctx(suite_vars={"bl_no": "SUITE"}))

        assert parts.body == {"bl_no": "SUITE"}

    def test_row_config_value_used(self):
        """数据集行配置（constant）即参数值（入参收敛到数据集行的直接体现）"""
        api = _api([_field("bl_no")])

        parts = _run(api, _config(body={"bl_no": _const("ROW")}))

        assert parts.body == {"bl_no": "ROW"}

    def test_unconfigured_param_not_resolved_by_name(self):
        """运行时变量（上游提取等）不参与按名解析：未配置字段发空占位，
        要取上游值必须显式 ref（旧按名解析已废止）"""
        api = _api([_field("bl_no"), _field("teu", field_type="int")])

        parts = _run(api, ctx=_ctx(seed={"n_up": {"bl_no": "RUNTIME", "teu": 3}}))

        assert parts.body == {"bl_no": "", "teu": None}

    def test_api_default_not_used_as_fallback(self):
        """接口字段默认值不兜底：未配置发空值占位（默认值无效）"""
        api = _api([_field("bl_no", default="DEFAULT")])

        parts = _run(api)

        assert parts.body == {"bl_no": ""}

    def test_upstream_ref_resolves(self):
        """ref 显式引用上游产出（旧 ${} 动态绑定的等价迁移）"""
        api = _api([_field("order_id")])

        parts = _run(api, _config(body={"order_id": _ref("n_up", "oid")}),
                     _ctx(seed={"n_up": {"oid": "A123"}}))

        assert parts.body == {"order_id": "A123"}

    def test_unfilled_param_sends_empty_by_type(self):
        """无必填概念：未配置参数按类型发空值（string → ""，int → None，array → []）"""
        api = _api([_field("bl_no"), _field("teu", field_type="int"),
                    _field("ids", field_type="array")])

        parts = _run(api)

        assert parts.body == {"bl_no": "", "teu": None, "ids": []}

    def test_constant_empty_sends_empty(self):
        """constant 空串（数据集空单元格迁移形态）= 显式空：发空串"""
        api = _api([_field("bl_no")])

        parts = _run(api, _config(body={"bl_no": _const("")}))

        assert parts.body == {"bl_no": ""}

    def test_no_required_error_any_more(self):
        """必填概念已取消：任何参数未配置都不再报错"""
        api = _api([_field("bl_no", required=True)])

        parts = _run(api)

        assert parts.body == {"bl_no": ""}


class TestLookup:
    """参数路径还原：点路径 / 叶路径合并 / 整对象 / 整键与叶键并存"""

    def test_dot_path_param_builds_nested(self):
        """点路径参数（旧点路径列的等价迁移）：按路径还原嵌套结构"""
        api = _api([_field("to_customer.put_amount", field_type="int")])

        parts = _run(api, _config(body={"to_customer.put_amount": _const(100)}))

        assert parts.body == {"to_customer": {"put_amount": 100}}

    def test_leaf_params_merge_into_object(self):
        """多个叶路径参数合并进同一父对象（旧拆叶展开的逆操作）"""
        api = _api([_field("to_customer", field_type="object")])

        parts = _run(api, _config(body={"to_customer.put_amount": _const(100),
                                        "to_customer.remark": _const("r")}))

        assert parts.body == {"to_customer": {"put_amount": 100, "remark": "r"}}

    def test_whole_object_param(self):
        """整对象参数（旧整对象列的等价迁移）：dict 值原样落到路径"""
        api = _api([_field("to_customer.put_amount", field_type="int")])

        parts = _run(api, _config(body={"to_customer": _const({"put_amount": 200})}))

        assert parts.body == {"to_customer": {"put_amount": 200}}

    def test_unconfigured_field_ignores_same_name_runtime_var(self):
        """未配置字段发空占位，同名运行时变量不生效（按名解析已移除）"""
        api = _api([_field("bl_no")])

        parts = _run(api, ctx=_ctx(seed={"n_up": {"bl_no": "RUNTIME"}}))

        assert parts.body == {"bl_no": ""}

    def test_leaf_param_overrides_whole_list_value(self):
        """整键与叶键并存：叶参数（细粒度配置）写入整键值对应位置，其余元素保留。
        曾致 select_list=[{order_id:666}] 精确命中后叶键引用不生效（等价迁移）"""
        api = _api([_field("select_list", field_type="array")])

        parts = _run(
            api,
            _config(body={
                "select_list": _const([{"order_id": 666, "qty": 2}]),
                "select_list.0.order_id": _ref("n_up", "order_id"),
            }),
            ctx=_ctx(seed={"n_up": {"order_id": 10293}}),
        )

        assert parts.body == {"select_list": [{"order_id": 10293, "qty": 2}]}

    def test_leaf_param_overrides_whole_dict_value(self):
        """dict 整键同理：仅覆盖指定叶，未涉及的子键保留"""
        api = _api([_field("to_customer", field_type="object")])

        parts = _run(
            api,
            _config(body={
                "to_customer": _const({"put_amount": 100, "remark": "r"}),
                "to_customer.put_amount": _ref("n_up", "bl_no"),
            }),
            ctx=_ctx(seed={"n_up": {"bl_no": "BL001"}}),
        )

        assert parts.body == {"to_customer": {"put_amount": "BL001", "remark": "r"}}


class TestTemplateBody:
    """无字段定义（request_template）接口的解析口径"""

    def test_template_statics_preserved(self):
        """模板体静态值原样保留；模板顶层键可被参数覆盖"""
        api = _api([], template={"keep": "T1", "drop_me": "T2"})

        parts = _run(api, _config(body={"drop_me": _const("ROW")}))

        assert parts.body == {"keep": "T1", "drop_me": "ROW"}

    def test_template_top_key_param_ref(self):
        """模板顶层键即事实参数声明，可配 ref 引用（旧模板键参与按名解析的等价迁移）"""
        api = _api([], template={"bl_no": "OLD"})

        parts = _run(api, _config(body={"bl_no": _ref("__suite__", "bl_no")}),
                     _ctx(suite_vars={"bl_no": "SUITE"}))

        assert parts.body == {"bl_no": "SUITE"}


class TestAssemblyOrder:
    """编排顺序本身：解析后还原类型、参数结果注册进本节点命名空间"""

    def test_array_string_coerced(self):
        """'[1, 2]' 常量字符串（旧 '[${a}, 2]' 求值产物的等价迁移形态）还原成原生 list"""
        api = _api([_field("ids", field_type="array")])

        parts = _run(api, _config(body={"ids": _const("[1, 2]")}))

        assert parts.body == {"ids": [1, 2]}

    def test_ref_as_array_wraps_single_value(self):
        """as_array: true——单值包成单元素数组（旧 '[${x}]' 写法的等价迁移）"""
        api = _api([_field("ids", field_type="array")])

        parts = _run(api, _config(body={"ids": _ref("n_up", "a", as_array=True)}),
                     _ctx(seed={"n_up": {"a": 1}}))

        assert parts.body == {"ids": [1]}

    def test_array_field_empty_scalar_normalized(self):
        """array 字段空标量归一（""/None → []）：数据集空值引用后路径参数才能按下标建元素"""
        api = _api([_field("writeoff_object", field_type="array")])

        parts = _run(api, _config(body={"writeoff_object": _const("")}))

        assert parts.body == {"writeoff_object": []}

    def test_field_type_coercion_after_resolution(self):
        """int 引用值按字段定义 string 强转：12345 → '12345'"""
        api = _api([_field("order_id", field_type="string")])

        parts = _run(api, _config(body={"order_id": _ref("n_up", "oid")}),
                     _ctx(seed={"n_up": {"oid": 12345}}))

        assert parts.body == {"order_id": "12345"}

    def test_array_body_wrapped_from_field_skeleton(self):
        """字段骨架 + list 模板 → 数组请求体 [{...}]"""
        api = _api([_field("bl_no")], template=[{"bl_no": "OLD"}])

        parts = _run(api, _config(body={"bl_no": _const("ROW")}))

        assert parts.body == [{"bl_no": "ROW"}]

    def test_param_result_registers_to_registry(self):
        """参数求值结果注册进本节点命名空间（下游经 节点.路径 / 节点.末段 引用）"""
        api = _api([_field("bl_no")])
        ctx = _ctx()

        _run(api, _config(body={"bl_no": _const("SYNCED")}), ctx)

        assert ctx.registry.read(SELF, "bl_no") == "SYNCED"


class TestSqlParameter:
    """SQL 来源参数：{{节点.变量}} 占位渲染后查询取值。

    字符串单引号转义防注入；取不到值抛 ReferenceError（不静默放行）；
    结果按 本节点.参数路径 注册（下游与本节点后续参数可引用）。"""

    def _run_sql(self, ctx, body, sqls, rows=None, fields=None):
        fake_db = SimpleNamespace(query=lambda sql: (sqls.append(sql), rows or [])[1])
        api = _api(fields if fields is not None else [_field("order_id")])
        return prepare_request(api, _config(body=body), context=ctx,
                               self_node=SELF, base_headers={}, db_client=fake_db), sqls

    def test_sql_param_renders_placeholders(self):
        """{{}} 渲染：字符串单引号转义包裹 / int 直接替换"""
        sqls = []
        parts, _ = self._run_sql(
            _ctx(seed={"n_up": {"bl_no": "BL'001", "teu": 2}}),
            {"order_id": {"source": "sql", "column": "id",
                          "sql": "SELECT id FROM t WHERE bl_no={{n_up.bl_no}} AND teu={{n_up.teu}}"}},
            sqls, rows=[{"id": "77"}])
        assert sqls == ["SELECT id FROM t WHERE bl_no='BL''001' AND teu=2"]
        assert parts.body == {"order_id": "77"}

    def test_sql_param_missing_ref_raises(self):
        """占位符取不到值 → ReferenceError（旧「未定义变量保留原样」的行为已废止）"""
        with pytest.raises(ReferenceError):
            self._run_sql(_ctx(seed={"n_up": {}}),
                          {"order_id": {"source": "sql",
                                        "sql": "SELECT {{n_up.missing}}"}},
                          [])

    def test_sql_param_no_db_client_raises(self):
        """环境未配置数据库连接 → SqlExecutionError（上层兜底为失败步骤，原因可见）"""
        api = _api([_field("order_id")])
        with pytest.raises(SqlExecutionError, match="数据库连接"):
            prepare_request(api, _config(body={"order_id": {"source": "sql",
                                                            "sql": "SELECT 1"}}),
                            context=ExecutionContext(), self_node=SELF,
                            base_headers={}, db_client=None)

    def test_sql_param_result_registered_for_downstream_param(self):
        """SQL 参数结果按 本节点.参数路径 注册：本节点后续参数直接引用"""
        sqls = []
        parts, _ = self._run_sql(
            _ctx(),
            {"oid": {"source": "sql", "sql": "SELECT 1", "column": "id"},
             "memo": _ref(SELF, "oid")},
            sqls, rows=[{"id": "ID5"}], fields=[_field("oid"), _field("memo")])
        assert parts.body == {"oid": "ID5", "memo": "ID5"}

    def test_sql_param_orders_after_referenced_self_param(self):
        """{{self.参数}} 依赖：SQL 参数在本节点被引用参数解析之后执行（order_params）"""
        sqls = []
        parts, _ = self._run_sql(
            _ctx(),
            {"memo": _const("M1"),
             "oid": {"source": "sql",
                     "sql": "SELECT {{%s.memo}} AS v" % SELF, "column": "v"}},
            sqls, rows=[{"v": "OK"}], fields=[_field("oid"), _field("memo")])
        assert sqls == ["SELECT 'M1' AS v"]
        assert parts.body["oid"] == "OK"


class TestFileAndHeaders:

    def test_file_field_popped_from_body(self):
        """file 字段剥离出 JSON body，进入 file_fields 列表（参数值=文件 ID）"""
        api = _api([
            _field("bl_no"),
            _field("doc", field_type="file"),
        ])

        parts = _run(api, _config(body={"bl_no": _const("BL1"),
                                        "doc": _const("FILE123")}))

        assert parts.body == {"bl_no": "BL1"}
        assert parts.file_fields == [("doc", "FILE123")]

    def test_header_param_ref_resolved(self):
        """params.headers 逐头解析（ref 引用）：覆盖/追加到环境公共头之上"""
        api = _api([_field("bl_no")])

        parts = _run(api, _config(headers={"Authorization": _ref("__suite__", "token")}),
                     _ctx(suite_vars={"token": "T1"}),
                     headers={"X-Plain": "v"})

        assert parts.headers == {"Authorization": "T1", "X-Plain": "v"}

    def test_base_headers_not_mutated(self):
        """headers 深拷贝组装，不污染 http_client 共享的 headers"""
        api = _api([_field("bl_no")])
        base = {"Authorization": "Bearer X"}

        _run(api, _config(body={"bl_no": _const("BL1")}), headers=base)

        assert base == {"Authorization": "Bearer X"}

    def test_api_headers_template_overrides_base(self):
        """接口 headers_template 覆盖环境公共头：curl 导入的表单 Content-Type 生效，
        不必为表单接口改环境公共头（同环境 JSON 与表单接口并存互不干扰）"""
        api = SimpleNamespace(
            fields=[_field("order_no")], request_template={},
            headers_template={"Content-Type": "application/x-www-form-urlencoded"},
        )

        parts = _run(api, _config(body={"order_no": _const("YHL1")}),
                     headers={"Content-Type": "application/json", "X-Req": "1"})

        assert parts.headers["Content-Type"] == "application/x-www-form-urlencoded"
        assert parts.headers["X-Req"] == "1"  # 未覆盖的公共头保留

    def test_header_param_overrides_template(self):
        """节点参数头压过接口模板头（最高优先级，旧模板 ${} 求值的等价迁移）"""
        api = SimpleNamespace(
            fields=[_field("a")], request_template={},
            headers_template={"X-Bl": "tpl"},
        )

        parts = _run(api, _config(headers={"X-Bl": _ref("n_up", "a")}),
                     _ctx(seed={"n_up": {"a": "V9"}}))

        assert parts.headers["X-Bl"] == "V9"
