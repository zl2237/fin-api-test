# -*- coding: utf-8 -*-
"""保存校验器单测：四来源参数模型静态完整性。"""
from app.engine.validation import validate_case_configs

DAG = {"nodes": [{"id": "n1"}, {"id": "n2"}], "edges": [{"source": "n1", "target": "n2"}]}


def n1_config(**kw):
    base = {"node_id": "n1", "params": {},
            "post_extract": [{"name": "order_id", "source": "response", "json_path": "$.data.id"}],
            "assertions": []}
    base.update(kw)
    return base


class TestPass:
    def test_ok_config(self):
        errs = validate_case_configs(DAG, [
            n1_config(params={"body": {"bl_no": {"source": "func", "func": "generate_bl_no", "args": []}}}),
            {"node_id": "n2", "params": {"body": {"oid": {"source": "ref", "node_id": "n1", "var_path": "order_id"}}},
             "post_extract": [], "assertions": []},
        ])
        assert errs == []

    def test_suite_ref_allowed(self):
        """__suite__ 白名单运行期注入，保存期放行（__dataset__ 平铺键已退役）"""
        errs = validate_case_configs(DAG, [
            n1_config(params={"body": {"pol": {"source": "ref", "node_id": "__suite__", "var_path": "pol"}}}),
        ])
        assert errs == []

    def test_self_sql_param_ref(self):
        errs = validate_case_configs(DAG, [
            n1_config(params={"body": {
                "a": {"source": "sql", "sql": "SELECT 1"},
                "b": {"source": "func", "func": "upper", "args": [
                    {"name": "s", "kind": "ref", "node_id": "n1", "var_path": "a"}]},
            }}),
        ])
        assert errs == []

    def test_param_self_ref_to_own_param_path(self):
        """参数自引用本节点其他参数（完整路径或末段别名）：合法——
        解析顺序由 order_params 拓扑保证（成环另有用例拒绝）。"""
        errs = validate_case_configs(DAG, [
            n1_config(params={"body": {
                "user.city": {"source": "constant", "value": "SH"},
                "memo": {"source": "ref", "node_id": "n1", "var_path": "city"},  # 末段别名引用
                "tag": {"source": "ref", "node_id": "n1", "var_path": "memo"},  # 完整路径链式引用
            }}),
        ])
        assert errs == []


class TestReject:
    def test_dangling_var(self):
        errs = validate_case_configs(DAG, [
            {"node_id": "n2", "params": {"body": {"x": {"source": "ref", "node_id": "n1", "var_path": "ghost"}}},
             "post_extract": [], "assertions": []},
        ])
        assert any("悬空引用" in e for e in errs)

    def test_unknown_node(self):
        errs = validate_case_configs(DAG, [
            n1_config(params={"body": {"x": {"source": "ref", "node_id": "n9", "var_path": "a"}}}),
        ])
        assert any("不存在的节点" in e for e in errs)

    def test_posterior_node_ref(self):
        """引用拓扑后置节点必须拒绝（未执行先引用）。"""
        errs = validate_case_configs(DAG, [
            n1_config(params={"body": {"x": {"source": "ref", "node_id": "n2", "var_path": "a"}}}),
        ])
        assert any("拓扑后置" in e for e in errs)

    def test_dataset_ns_retired(self):
        """__dataset__ 伪命名空间已退役：引用它按「不存在的节点」拒绝（跨节点共享值改引用上游产出）"""
        errs = validate_case_configs(DAG, [
            n1_config(params={"body": {"x": {"source": "ref", "node_id": "__dataset__", "var_path": "nope"}}}),
        ])
        assert any("不存在的节点" in e for e in errs)

    def test_unknown_function(self):
        errs = validate_case_configs(DAG, [
            n1_config(params={"body": {"x": {"source": "func", "func": "nope", "args": []}}}),
        ])
        assert any("未知函数" in e for e in errs)

    def test_param_cycle(self):
        errs = validate_case_configs(DAG, [
            n1_config(params={"body": {
                "a": {"source": "sql", "sql": "SELECT {{n1.b}}"},
                "b": {"source": "sql", "sql": "SELECT {{n1.a}}"},
            }}),
        ])
        assert any("成环" in e for e in errs)

    def test_old_syntax_residue(self):
        errs = validate_case_configs(DAG, [
            n1_config(params={"body": {"x": {"source": "constant", "value": "${order_id}"}}}),
        ])
        assert any("旧表达式" in e for e in errs)

    def test_constant_container_embedded_sql_forbidden(self):
        """constant 容器值内嵌 SQL 来源：拒绝——读库取值须声明为独立参数。"""
        errs = validate_case_configs(DAG, [
            n1_config(params={"body": {
                "x": {"source": "constant",
                      "value": ["plain", {"source": "sql", "sql": "SELECT 1"}]},
            }}),
        ])
        assert any("容器常量内嵌 SQL 来源禁用" in e for e in errs)

    def test_param_self_ref_to_missing_var_rejected(self):
        """参数引用本节点不存在的变量：拒绝（合法集只含本节点参数路径/末段）。"""
        errs = validate_case_configs(DAG, [
            n1_config(params={"body": {
                "x": {"source": "ref", "node_id": "n1", "var_path": "ghost_var"},
            }}),
        ])
        assert any("自引用" in e and "未在本节点产出" in e for e in errs)

    def test_param_ref_to_extract_var_rejected(self):
        """参数自引用 post_extract 提名：拒绝——提取在请求后执行，
        参数解析先于提取，提取提名不在参数自引用合法集。"""
        errs = validate_case_configs(DAG, [
            n1_config(params={"body": {
                "x": {"source": "ref", "node_id": "n1", "var_path": "order_id"},
            }}),
        ])
        assert any("自引用 'order_id'" in e and "未在本节点产出" in e for e in errs)

    def test_sql_placeholder_dangling(self):
        errs = validate_case_configs(DAG, [
            n1_config(params={"body": {"x": {"source": "sql", "sql": "SELECT {{n1.ghost}}"}}}),
        ])
        assert any("ghost" in e for e in errs)
