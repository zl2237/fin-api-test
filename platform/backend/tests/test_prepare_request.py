"""prepare_request 单测：三级优先级与编排顺序的直接测试面。

此前这段编排只活在 DagExecutor._execute_node 的胶水里——各纯函数
（apply_row_overrides / coerce_json_strings / apply_field_types 等）有单测，
但顺序本身（先求值后还原类型、pre_process 后二次求值）无任何测试可及。
"""
from types import SimpleNamespace

import pytest

from app.engine.prepare_request import prepare_request


def _field(key, field_type="string", default=None):
    return SimpleNamespace(key=key, field_type=field_type, default_value=default)


def _api(fields, template=None):
    return SimpleNamespace(fields=fields, request_template=template)


def _config(pre_process=None):
    return SimpleNamespace(pre_process=pre_process)


class _Ctx:
    """ExecutionContext 最小替身：to_dict 返回三池结构（env/extracted/global），
    测试变量放 extracted（无前缀 ${name} 从该池取值）；extracted 保持引用，
    set_field 回写对二次求值可见——与真实 ExecutionContext 的引用语义一致"""

    def __init__(self, vars=None):
        self.extracted = dict(vars or {})

    def to_dict(self):
        return {"env": {}, "extracted": self.extracted, "global": {}}


def _run(api, config=None, ctx=None, row_vars=None, row_origins=None,
         headers=None):
    return prepare_request(api, config, context=ctx or _Ctx(),
                           row_vars=row_vars, row_origins=row_origins,
                           base_headers=headers or {}, db_client=None)


class TestPriority:
    """三级取值优先级：数据集行值(1) > 编排 set_field(2) > 接口默认值(3)"""

    def test_row_value_beats_set_field_and_default(self):
        api = _api([_field("bl_no", default="DEFAULT")])
        config = _config([{"type": "set_field", "path": "bl_no", "value": "CASE"}])

        parts = _run(api, config, _Ctx(), row_vars={"bl_no": "ROW"})

        assert parts.body == {"bl_no": "ROW"}

    def test_set_field_beats_default_when_no_row(self):
        api = _api([_field("bl_no", default="DEFAULT")])
        config = _config([{"type": "set_field", "path": "bl_no", "value": "CASE"}])

        parts = _run(api, config)

        assert parts.body == {"bl_no": "CASE"}

    def test_default_used_when_nothing_overrides(self):
        parts = _run(_api([_field("bl_no", default="DEFAULT")]))

        assert parts.body == {"bl_no": "DEFAULT"}

    def test_dynamic_binding_not_suppressed_by_row(self):
        """${} 动态绑定不在数据集覆盖范围：行值同名列不压制，表达式照常求值"""
        api = _api([_field("order_id", default="${oid}")])
        ctx = _Ctx({"oid": "A123"})

        parts = _run(api, ctx=ctx, row_vars={"order_id": "ROWVAL"})

        assert parts.body == {"order_id": "A123"}


class TestAssemblyOrder:
    """编排顺序本身：求值后还原类型、pre_process 后二次求值"""

    def test_array_string_evaluated_then_coerced(self):
        """'[${a}, 2]' 求值成 '[1, 2]' 字符串后必须还原成原生 list"""
        api = _api([_field("ids", field_type="array", default="[${a}, 2]")])
        ctx = _Ctx({"a": 1})

        parts = _run(api, ctx=ctx)

        assert parts.body == {"ids": [1, 2]}

    def test_field_type_coercion_after_evaluation(self):
        """int 提取值按字段定义 string 强转：12345 → '12345'"""
        api = _api([_field("order_id", field_type="string", default="${oid}")])
        ctx = _Ctx({"oid": 12345})

        parts = _run(api, ctx=ctx)

        assert parts.body == {"order_id": "12345"}

    def test_set_field_value_synced_to_context_extracted(self):
        """set_field 求值结果同步写入 context.extracted（后续节点 ${xxx} 可引用）"""
        api = _api([_field("bl_no", default="DEFAULT")])
        ctx = _Ctx()
        config = _config([{"type": "set_field", "path": "bl_no", "value": "SYNCED"}])

        _run(api, config, ctx)

        assert ctx.extracted.get("bl_no") == "SYNCED"

    def test_second_evaluation_injects_set_field_values(self):
        """pre_process 写入上下文后二次求值：后续字段引用 set_field 的产物"""
        api = _api([
            _field("src", default="X"),
            _field("dst", default="${src}"),
        ])
        config = _config([{"type": "set_field", "path": "src", "value": "FROM_CASE"}])

        parts = _run(api, config)

        assert parts.body == {"src": "FROM_CASE", "dst": "FROM_CASE"}


class TestExecSql:
    """前置处理 exec_sql：请求前执行 SQL 造数（如节点执行前先 INSERT 一条依赖数据）。

    ${} 引用统一变量池（context.extracted + 前序 set_field 同步值），
    转义与 post_extract 的 db 提取同一实现（inject_sql_vars）。"""

    def _run_sql(self, ctx, actions, sqls):
        fake_db = SimpleNamespace(execute=lambda sql: sqls.append(sql))
        api = _api([_field("bl_no", default="B1")])
        return prepare_request(api, _config(actions), context=ctx,
                               row_vars=None, row_origins=None,
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
            {"type": "set_field", "path": "bl_no", "value": "BL-SET"},
            {"type": "exec_sql", "sql": "INSERT INTO t (bl_no) VALUES (${bl_no})"},
        ], sqls)
        assert sqls == ["INSERT INTO t (bl_no) VALUES ('BL-SET')"]

    def test_exec_sql_no_db_client_raises(self):
        """环境未配置数据库连接 → RuntimeError（上层兜底为失败步骤，原因可见）"""
        api = _api([])
        with pytest.raises(RuntimeError, match="数据库连接"):
            prepare_request(api, _config([{"type": "exec_sql", "sql": "SELECT 1"}]),
                            context=_Ctx(), row_vars=None, row_origins=None,
                            base_headers={}, db_client=None)

    def test_exec_sql_empty_skipped(self):
        """空 SQL（前端表格空行占位）→ 跳过不炸"""
        sqls = []
        self._run_sql(_Ctx(), [{"type": "exec_sql", "sql": "   "}], sqls)
        assert sqls == []


class TestFileAndHeaders:

    def test_file_field_popped_from_body(self):
        """file 字段剥离出 JSON body，进入 file_fields 列表"""
        api = _api([
            _field("bl_no", default="BL1"),
            _field("doc", field_type="file", default="FILE123"),
        ])

        parts = _run(api)

        assert parts.body == {"bl_no": "BL1"}
        assert parts.file_fields == [("doc", "FILE123")]

    def test_headers_expression_evaluated(self):
        api = _api([_field("bl_no", default="BL1")])
        ctx = _Ctx({"token": "T1"})

        parts = _run(api, ctx=ctx,
                     headers={"Authorization": "Bearer ${token}", "X-Plain": "v"})

        assert parts.headers == {"Authorization": "Bearer T1", "X-Plain": "v"}

    def test_base_headers_not_mutated(self):
        """headers 深拷贝求值，不污染 http_client 共享的 headers"""
        api = _api([_field("bl_no", default="BL1")])
        base = {"Authorization": "Bearer ${token}"}

        _run(api, ctx=_Ctx({"token": "T1"}), headers=base)

        assert base == {"Authorization": "Bearer ${token}"}  # 原引用保持占位符
