"""ExecutionContext 变量池合并 + DagExecutor 注入（数据驱动测试周期 4）。

方案定案 #4：列名即变量名，行值直接进统一变量池，优先于同名环境变量；
无行值时行为与现状完全一致（回归保护）。
"""
from types import SimpleNamespace

from app.engine.context import ExecutionContext
from app.engine.dag_executor import DagExecutor


class TestVariableMerge:
    def test_row_vars_override_env(self):
        """行值覆盖同名环境变量，不同名变量共存"""
        ctx = ExecutionContext(env_vars={"bl_no": "ENV_DEFAULT", "other": 1},
                               row_vars={"bl_no": "BL001", "amount": 100})
        assert ctx.extracted == {"bl_no": "BL001", "other": 1, "amount": 100}

    def test_no_row_vars_keeps_current_behavior(self):
        """未传行值：变量池 = env_vars 拷贝（现状回归）"""
        ctx = ExecutionContext(env_vars={"a": 1})
        assert ctx.extracted == {"a": 1}

    def test_env_vars_not_polluted(self):
        """行值合并进的是池（extracted 新 dict），不回写 env_vars"""
        env = {"a": "env"}
        ctx = ExecutionContext(env_vars=env, row_vars={"a": "row"})
        assert env == {"a": "env"}
        assert ctx.env_vars == {"a": "env"}
        assert ctx.extracted == {"a": "row"}


class TestSuiteVarsMerge:
    """套件共享变量优先级：环境变量 < 数据行变量 < 套件共享值（链语义传递契约）"""

    def test_suite_vars_override_everything(self):
        ctx = ExecutionContext(env_vars={"bl_no": "ENV", "a": 1},
                               row_vars={"bl_no": "ROW", "b": 2},
                               suite_vars={"bl_no": "SUITE"})
        assert ctx.extracted == {"bl_no": "SUITE", "a": 1, "b": 2}

    def test_no_suite_vars_keeps_current_behavior(self):
        """非套件链执行（单独跑用例）无注入：行为与普通执行完全一致"""
        ctx = ExecutionContext(env_vars={"bl_no": "ENV"}, row_vars={"bl_no": "ROW"})
        assert ctx.extracted == {"bl_no": "ROW"}

    def test_executor_accepts_suite_vars(self):
        """DagExecutor 透传套件注入：最高优先级合并进 context.extracted"""
        env = SimpleNamespace(variables={"bl_no": "ENV_DEFAULT"})
        executor = DagExecutor(db=SimpleNamespace(), case=SimpleNamespace(id=1), env=env,
                               row_vars={"bl_no": "ROW"}, suite_vars={"bl_no": "SUITE"})
        assert executor.context.extracted == {"bl_no": "SUITE"}


class TestDagExecutorInject:
    def test_executor_accepts_row_vars(self):
        """DagExecutor 透传行值：构造即合并进 context.extracted"""
        env = SimpleNamespace(variables={"bl_no": "ENV_DEFAULT"})
        case = SimpleNamespace(id=1)
        executor = DagExecutor(db=SimpleNamespace(), case=case, env=env,
                               row_vars={"bl_no": "BL001"})
        assert executor.context.extracted == {"bl_no": "BL001"}

    def test_executor_without_row_vars_unchanged(self):
        env = SimpleNamespace(variables={"a": 1})
        executor = DagExecutor(db=SimpleNamespace(), case=SimpleNamespace(id=1), env=env)
        assert executor.context.extracted == {"a": 1}
