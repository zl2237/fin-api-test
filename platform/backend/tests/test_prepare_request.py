"""prepare_request 单测：参数解析优先级与编排顺序的直接测试面。

定案的取值优先级链（按参数名自动解析）：
1. 手动覆盖：pre_process set_field/add_field 非空值（字面量或 ${}）
2. 套件注入：context.suite_vars（上游成员白名单快照，最高优先级注入）
3. 数据集域静态变量：row_vars（绑定数据集当前行，点路径键）
运行时变量（extracted：后置提取 / set_field 同步）不参与按名解析，
仅 ${} 显式引用可取；接口字段默认值不再兜底；无必填概念：
三层皆空按类型发空值（""/null）。
"""
from types import SimpleNamespace

import pytest

from app.engine.prepare_request import prepare_request


def _field(key, field_type="string", default=None, required=False):
    return SimpleNamespace(key=key, field_type=field_type, default_value=default,
                           required=required)


def _api(fields, template=None, **kw):
    return SimpleNamespace(fields=fields, request_template=template, **kw)


def _config(pre_process=None):
    return SimpleNamespace(pre_process=pre_process)


class _Ctx:
    """ExecutionContext 最小替身：to_dict 返回三池结构（env/extracted/global），
    测试变量放 extracted（无前缀 ${name} 从该池取值）；extracted 保持引用，
    set_field 回写对二次求值可见；suite_vars 为套件注入域（按名自动解析可见）
    ——与真实 ExecutionContext 一致"""

    def __init__(self, vars=None, suite_vars=None):
        self.extracted = dict(vars or {})
        self.suite_vars = dict(suite_vars or {})

    def to_dict(self):
        return {"env": {}, "extracted": self.extracted, "global": {}}


def _run(api, config=None, ctx=None, row_vars=None, headers=None):
    return prepare_request(api, config, context=ctx or _Ctx(),
                           row_vars=row_vars,
                           base_headers=headers or {}, db_client=None)


class TestPriority:
    """取值优先级：手动覆盖(1) > 套件注入(2) > 数据集域(3)；
    运行时变量不参与按名解析（仅 ${} 显式引用）"""

    def test_manual_literal_beats_suite_and_row(self):
        """手动覆盖字面量压过套件注入与数据集域（有值=覆盖）"""
        api = _api([_field("bl_no")])
        config = _config([{"type": "set_field", "path": "bl_no", "value": "MANUAL"}])

        parts = _run(api, config, _Ctx(suite_vars={"bl_no": "SUITE"}),
                     row_vars={"bl_no": "ROW"})

        assert parts.body == {"bl_no": "MANUAL"}

    def test_suite_injection_beats_row_domain(self):
        """套件注入（上游白名单快照）压过数据集域行值"""
        api = _api([_field("bl_no")])

        parts = _run(api, ctx=_Ctx(suite_vars={"bl_no": "SUITE"}),
                     row_vars={"bl_no": "ROW"})

        assert parts.body == {"bl_no": "SUITE"}

    def test_row_domain_used_when_no_suite_var(self):
        api = _api([_field("bl_no")])

        parts = _run(api, row_vars={"bl_no": "ROW"})

        assert parts.body == {"bl_no": "ROW"}

    def test_runtime_vars_not_resolved_by_name(self):
        """运行时变量（extracted：后置提取/set_field 同步）不参与按名解析，
        仅 ${} 显式引用可取——非动态参数要么取自变量池，要么手动填"""
        api = _api([_field("bl_no"), _field("teu", field_type="int")])

        parts = _run(api, ctx=_Ctx(vars={"bl_no": "RUNTIME", "teu": 3}))

        assert parts.body == {"bl_no": "", "teu": None}

    def test_api_default_not_used_as_fallback(self):
        """接口字段默认值不再兜底：三层皆空发空值占位（默认值无效）"""
        api = _api([_field("bl_no", default="DEFAULT")])

        parts = _run(api)

        assert parts.body == {"bl_no": ""}

    def test_dynamic_binding_wins_as_manual(self):
        """${} 动态绑定属手动层（显式引用），照常求值"""
        api = _api([_field("order_id")])
        config = _config([{"type": "set_field", "path": "order_id", "value": "${oid}"}])

        parts = _run(api, config, _Ctx({"oid": "A123"}), row_vars={"order_id": "ROWVAL"})

        assert parts.body == {"order_id": "A123"}

    def test_unfilled_param_sends_empty_by_type(self):
        """无必填概念：三层皆空的参数按类型发空值（string → ""，其余 → None）"""
        api = _api([_field("bl_no"), _field("teu", field_type="int")])

        parts = _run(api)

        assert parts.body == {"bl_no": "", "teu": None}

    def test_unfilled_when_row_cell_empty(self):
        """行单元格空值 = 未配置：同样发空值占位"""
        api = _api([_field("bl_no")])

        parts = _run(api, row_vars={"bl_no": ""})

        assert parts.body == {"bl_no": ""}

    def test_no_required_error_any_more(self):
        """必填概念已取消：任何参数三层皆空都不再报错"""
        api = _api([_field("bl_no", required=True)])

        parts = _run(api)

        assert parts.body == {"bl_no": ""}

    def test_empty_placeholder_resolves_from_pools(self):
        """空值占位（清空转引用后的形态）参与按名解析——无标记维持自动引用（存量兼容）"""
        api = _api([])
        config = _config([{"type": "set_field", "path": "bl_no", "value": ""}])

        parts = _run(api, config, row_vars={"bl_no": "ROW"})

        assert parts.body == {"bl_no": "ROW"}

    def test_explicit_empty_sends_empty_not_pool(self):
        """显式空值（explicit_empty 标记）：发送空串，不回落变量池——
        用户明确要求为空时不再被静默解释为取池值（case 92 交互实证）"""
        api = _api([_field("customer_id")])
        config = _config([{"type": "set_field", "path": "customer_id",
                           "value": "", "explicit_empty": True}])

        parts = _run(api, config, row_vars={"customer_id": ["343612351695552512"]})

        assert parts.body == {"customer_id": ""}


class TestLookup:
    """按名解析的三种形态：精确（含点路径）/ 拆叶展开 / 整对象列"""

    def test_dot_path_exact_match(self):
        """点路径键精确匹配：嵌套结构按路径还原"""
        api = _api([_field("to_customer.put_amount", field_type="int")])

        parts = _run(api, row_vars={"to_customer.put_amount": 100})

        assert parts.body == {"to_customer": {"put_amount": 100}}

    def test_prefix_leaves_expansion(self):
        """父路径键解析：池存拆叶键（收集器拆叶入池的逆操作）"""
        api = _api([_field("to_customer", field_type="object")])

        parts = _run(api, row_vars={"to_customer.put_amount": 100,
                                    "to_customer.remark": "r"})

        assert parts.body == {"to_customer": {"put_amount": 100, "remark": "r"}}

    def test_whole_object_column(self):
        """整对象列（存量数据集）：池键为前缀且值为 dict，按子路径取值"""
        api = _api([_field("to_customer.put_amount", field_type="int")])

        parts = _run(api, row_vars={"to_customer": {"put_amount": 200}})

        assert parts.body == {"to_customer": {"put_amount": 200}}

    def test_empty_cell_sends_empty_not_runtime_var(self):
        """空单元格 = 未配置：发空值占位，不再让位给运行时变量（按名解析已移除）"""
        api = _api([_field("bl_no")])

        parts = _run(api, ctx=_Ctx(vars={"bl_no": "RUNTIME"}),
                     row_vars={"bl_no": ""})

        assert parts.body == {"bl_no": ""}

    def test_leaf_key_overrides_whole_list_value(self):
        """整键与叶键并存：叶键（细粒度配置）覆盖整键值对应位置，其余元素保留。
        曾致 select_list=[{order_id:666}] 精确命中后叶键 ${order_id} 引用不生效"""
        api = _api([_field("select_list", field_type="array")])

        parts = _run(
            api,
            ctx=_Ctx(vars={"order_id": 10293}),
            row_vars={"select_list": [{"order_id": 666, "qty": 2}],
                      "select_list.0.order_id": "${order_id}"},
        )

        assert parts.body == {"select_list": [{"order_id": 10293, "qty": 2}]}

    def test_leaf_key_overrides_whole_dict_value(self):
        """dict 整键同理：仅覆盖指定叶，未涉及的子键保留"""
        api = _api([_field("to_customer", field_type="object")])

        parts = _run(
            api,
            ctx=_Ctx(vars={"bl_no": "BL001"}),
            row_vars={"to_customer": {"put_amount": 100, "remark": "r"},
                      "to_customer.put_amount": "${bl_no}"},
        )

        assert parts.body == {"to_customer": {"put_amount": "BL001", "remark": "r"}}


class TestTemplateBody:
    """无字段定义（request_template）接口的解析口径"""

    def test_template_statics_preserved(self):
        """模板体静态值原样保留，未解析到的模板键不删除"""
        api = _api([], template={"keep": "T1", "drop_me": "T2"})

        parts = _run(api, row_vars={"drop_me": "ROW"})

        assert parts.body == {"keep": "T1", "drop_me": "ROW"}

    def test_template_top_keys_resolve_from_pools(self):
        """模板顶层键即事实参数声明，参与按名解析"""
        api = _api([], template={"bl_no": "OLD"})

        parts = _run(api, ctx=_Ctx(suite_vars={"bl_no": "SUITE"}))

        assert parts.body == {"bl_no": "SUITE"}


class TestAssemblyOrder:
    """编排顺序本身：求值后还原类型、pre_process 后二次求值"""

    def test_array_string_evaluated_then_coerced(self):
        """'[${a}, 2]' 求值成 '[1, 2]' 字符串后必须还原成原生 list"""
        api = _api([_field("ids", field_type="array")])
        config = _config([{"type": "set_field", "path": "ids", "value": "[${a}, 2]"}])

        parts = _run(api, config, _Ctx({"a": 1}))

        assert parts.body == {"ids": [1, 2]}

    def test_field_type_coercion_after_evaluation(self):
        """int 提取值按字段定义 string 强转：12345 → '12345'"""
        api = _api([_field("order_id", field_type="string")])
        config = _config([{"type": "set_field", "path": "order_id", "value": "${oid}"}])

        parts = _run(api, config, _Ctx({"oid": 12345}))

        assert parts.body == {"order_id": "12345"}

    def test_array_body_wrapped_from_field_skeleton(self):
        """字段骨架 + list 模板 → 数组请求体 [{...}]"""
        api = _api([_field("bl_no")], template=[{"bl_no": "OLD"}])

        parts = _run(api, row_vars={"bl_no": "ROW"})

        assert parts.body == [{"bl_no": "ROW"}]

    def test_set_field_value_synced_to_extracted(self):
        """set_field 求值结果同步写入 extracted（后续节点 ${} 显式引用可取）"""
        api = _api([_field("bl_no")])
        ctx = _Ctx()
        config = _config([{"type": "set_field", "path": "bl_no", "value": "SYNCED"}])

        _run(api, config, ctx)

        assert ctx.extracted.get("bl_no") == "SYNCED"

    def test_second_evaluation_injects_set_field_values(self):
        """pre_process 写入上下文后二次求值：后续字段引用 set_field 的产物"""
        api = _api([
            _field("src"),
            _field("dst"),
        ])
        config = _config([
            {"type": "set_field", "path": "src", "value": "FROM_CASE"},
            {"type": "set_field", "path": "dst", "value": "${src}"},
        ])

        parts = _run(api, config)

        assert parts.body == {"src": "FROM_CASE", "dst": "FROM_CASE"}


class TestExecSql:
    """前置处理 exec_sql：请求前执行 SQL 造数（如节点执行前先 INSERT 一条依赖数据）。

    ${} 引用统一变量池（context.extracted + 前序 set_field 同步值），
    转义与 post_extract 的 db 提取同一实现（inject_sql_vars）。"""

    def _run_sql(self, ctx, actions, sqls):
        fake_db = SimpleNamespace(execute=lambda sql: sqls.append(sql))
        api = _api([_field("bl_no")])
        return prepare_request(api, _config(actions), context=ctx,
                               row_vars={"bl_no": "B1"},
                               base_headers={}, db_client=fake_db)

    def test_exec_sql_with_vars(self):
        """${} 注入：字符串单引号转义包裹 / int 直接替换 / 未定义变量保留原样"""
        sqls = []
        ctx = _Ctx({"bl_no": "BL'001", "teu": 2})
        self._run_sql(ctx, [{"type": "exec_sql",
                             "sql": "INSERT INTO t (bl_no, teu, memo) VALUES (${bl_no}, ${teu}, ${missing})"}],
                      sqls)
        assert sqls == ["INSERT INTO t (bl_no, teu, memo) VALUES ('BL''001', 2, '${missing}')"]

    def test_exec_sql_sees_set_field_synced_vars(self):
        """同批前序 set_field 求值结果同步到变量池，exec_sql 可引用"""
        sqls = []
        self._run_sql(_Ctx(), [
            {"type": "set_field", "path": "memo", "value": "BL-SET"},
            {"type": "exec_sql", "sql": "INSERT INTO t (memo) VALUES (${memo})"},
        ], sqls)
        assert sqls == ["INSERT INTO t (memo) VALUES ('BL-SET')"]

    def test_exec_sql_no_db_client_raises(self):
        """环境未配置数据库连接 → RuntimeError（上层兜底为失败步骤，原因可见）"""
        api = _api([])
        with pytest.raises(RuntimeError, match="数据库连接"):
            prepare_request(api, _config([{"type": "exec_sql", "sql": "SELECT 1"}]),
                            context=_Ctx(), row_vars=None,
                            base_headers={}, db_client=None)

    def test_exec_sql_empty_skipped(self):
        """空 SQL（前端表格空行占位）→ 跳过不炸"""
        sqls = []
        self._run_sql(_Ctx(), [{"type": "exec_sql", "sql": "   "}], sqls)
        assert sqls == []


class TestFileAndHeaders:

    def test_file_field_popped_from_body(self):
        """file 字段剥离出 JSON body，进入 file_fields 列表（池值=文件 ID）"""
        api = _api([
            _field("bl_no"),
            _field("doc", field_type="file"),
        ])

        parts = _run(api, row_vars={"bl_no": "BL1", "doc": "FILE123"})

        assert parts.body == {"bl_no": "BL1"}
        assert parts.file_fields == [("doc", "FILE123")]

    def test_headers_expression_evaluated(self):
        api = _api([_field("bl_no")])
        ctx = _Ctx({"token": "T1"})

        parts = _run(api, ctx=ctx, row_vars={"bl_no": "BL1"},
                     headers={"Authorization": "Bearer ${token}", "X-Plain": "v"})

        assert parts.headers == {"Authorization": "Bearer T1", "X-Plain": "v"}

    def test_base_headers_not_mutated(self):
        """headers 深拷贝求值，不污染 http_client 共享的 headers"""
        api = _api([_field("bl_no")])
        base = {"Authorization": "Bearer ${token}"}

        _run(api, ctx=_Ctx({"token": "T1"}), row_vars={"bl_no": "BL1"}, headers=base)

        assert base == {"Authorization": "Bearer ${token}"}  # 原引用保持占位符

    def test_api_headers_template_overrides_base(self):
        """接口 headers_template 覆盖环境公共头：curl 导入的表单 Content-Type 生效，
        不必为表单接口改环境公共头（同环境 JSON 与表单接口并存互不干扰）"""
        api = SimpleNamespace(
            fields=[_field("order_no")], request_template={},
            headers_template={"Content-Type": "application/x-www-form-urlencoded"},
        )

        parts = _run(api, row_vars={"order_no": "YHL1"},
                     headers={"Content-Type": "application/json", "X-Req": "1"})

        assert parts.headers["Content-Type"] == "application/x-www-form-urlencoded"
        assert parts.headers["X-Req"] == "1"  # 未覆盖的公共头保留

    def test_api_headers_support_expression(self):
        """headers_template 的值支持 ${} 求值（与其他 headers 同口径）"""
        api = SimpleNamespace(
            fields=[_field("a")], request_template={},
            headers_template={"X-Bl": "${a}"},
        )

        parts = _run(api, ctx=_Ctx({"a": "V9"}), row_vars={"a": "1"})

        assert parts.headers["X-Bl"] == "V9"
