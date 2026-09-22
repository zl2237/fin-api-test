"""ExecutionContext 变量池构成 + DagExecutor 注入（测试数据来源唯一性定案）。

环境变量池已退役：extracted 只由数据集单套数据（row_vars）与运行时注入
（套件上游 suite_vars、后置提取、set_field 同步）构成——测试数据严格来自数据集。
"""
from types import SimpleNamespace

from app.engine.context import ExecutionContext
from app.engine.dag_executor import DagExecutor


class TestVariableMerge:
    def test_row_vars_into_pool(self):
        """数据集单套数据进统一变量池（${列名} 显式引用可取）"""
        ctx = ExecutionContext(row_vars={"bl_no": "BL001", "amount": 100})
        assert ctx.extracted == {"bl_no": "BL001", "amount": 100}

    def test_pool_not_writing_back_row_vars(self):
        """运行时产出写池（extracted 新 dict），不回写数据集域原始引用"""
        ctx = ExecutionContext(row_vars={"a": "row"})
        ctx.update_extracted({"b": 1})
        assert ctx.row_vars == {"a": "row"}
        assert ctx.extracted == {"a": "row", "b": 1}

    def test_update_extracted_only_feeds_extracted(self):
        """后置提取等运行时产出只进 ${} 统一池（显式引用可见），
        不进按名解析域（运行时变量不参与按名自动解析）"""
        ctx = ExecutionContext(row_vars={"bl_no": "ROW"})
        ctx.update_extracted({"order_id": "O1"})
        assert ctx.extracted == {"bl_no": "ROW", "order_id": "O1"}
        assert ctx.suite_vars == {}
        assert ctx.row_vars == {"bl_no": "ROW"}  # 数据集域不受污染

    def test_env_pool_retired(self):
        """环境变量池退役：构造不再接受 env_vars，${} 池无环境来源"""
        import pytest
        with pytest.raises(TypeError):
            ExecutionContext(env_vars={"a": 1})


class TestSuiteVarsMerge:
    """套件共享变量优先级：数据集值 < 套件共享值（链语义传递契约）"""

    def test_suite_vars_override_row_vars(self):
        ctx = ExecutionContext(row_vars={"bl_no": "ROW", "b": 2},
                               suite_vars={"bl_no": "SUITE"})
        assert ctx.extracted == {"bl_no": "SUITE", "b": 2}
        assert ctx.suite_vars == {"bl_no": "SUITE"}  # 套件注入（按名解析最高优先级来源）

    def test_no_suite_vars_keeps_current_behavior(self):
        """非套件链执行（单独跑用例）无注入：行为与普通执行完全一致"""
        ctx = ExecutionContext(row_vars={"bl_no": "ROW"})
        assert ctx.extracted == {"bl_no": "ROW"}
        assert ctx.suite_vars == {}

    def test_executor_accepts_suite_vars(self):
        """DagExecutor 透传套件注入：最高优先级合并进 context.extracted"""
        env = SimpleNamespace(variables={"bl_no": "ENV_RETIRED"})
        executor = DagExecutor(db=SimpleNamespace(), case=SimpleNamespace(id=1), env=env,
                               row_vars={"bl_no": "ROW"}, suite_vars={"bl_no": "SUITE"})
        assert executor.context.extracted == {"bl_no": "SUITE"}


class TestDagExecutorInject:
    def test_executor_accepts_row_vars(self):
        """DagExecutor 透传数据集单套数据：构造即进 context.extracted"""
        env = SimpleNamespace(variables={"bl_no": "ENV_RETIRED"})
        case = SimpleNamespace(id=1)
        executor = DagExecutor(db=SimpleNamespace(), case=case, env=env,
                               row_vars={"bl_no": "BL001"})
        assert executor.context.extracted == {"bl_no": "BL001"}

    def test_executor_env_variables_not_in_pool(self):
        """环境 variables 不再进 ${} 池（测试数据来源唯一为数据集）"""
        env = SimpleNamespace(variables={"a": 1})
        executor = DagExecutor(db=SimpleNamespace(), case=SimpleNamespace(id=1), env=env)
        assert executor.context.extracted == {}
