"""测试 db.query_value 表达式嵌套 ${} 的解析问题。"""
import re
import sys

sys.path.insert(0, r"d:\CODE\PyCharm\pythonProject\fin-api-test\platform\backend")

from app.engine.expression import ExpressionEngine


class FakeDbClient:
    def query(self, sql):
        print(f"[FakeDbClient] 执行 SQL: {sql}")
        if "sys_order_sub" in sql:
            return [{"order_sub_id": 99999, "order_sub_type": 2}]
        return []


def test_nested_dollar_brace():
    """用户场景：${db.query_value('...${order_id}...', field='order_sub_id')}"""
    context = {"extracted": {"order_id": 12345}, "env": {}}
    engine = ExpressionEngine(context, db_client=FakeDbClient())

    expr = "${db.query_value('SELECT order_sub_id from sys_order_sub WHERE order_id = ${order_id} and order_sub_type = 2', field='order_sub_id')}"
    print("原始表达式:", expr)
    print("长度:", len(expr))
    print()

    # 1) 先看正则如何匹配
    pattern = re.compile(r"\$\{([^}]+)\}")
    matches = list(pattern.finditer(expr))
    print("正则匹配数:", len(matches))
    for i, m in enumerate(matches):
        print(f"  [{i}] match={m.group(0)!r}")
        print(f"       inner={m.group(1)!r}")
    print()

    # 2) 整串场景判断
    starts = expr.startswith("${")
    ends = expr.endswith("}")
    print("expr.startswith('${'):", starts)
    print("expr.endswith('}'):", ends)
    inner_whole = expr[2:-1].strip()
    print("整串场景 inner:", repr(inner_whole))
    print()

    # 3) 实际调用 engine.evaluate
    print("调用 engine.evaluate(expr):")
    result = engine.evaluate(expr)
    print("结果:", repr(result))
    print()

    # 4) 单独测试 _eval_inner
    print("直接调用 engine._eval_inner(inner_whole):")
    result2 = engine._eval_inner(inner_whole)
    print("结果:", repr(result2))


def test_simple_db_func():
    """对照：SQL 内不嵌套 ${} 时是否正常"""
    print("\n========== 对照：SQL 内不嵌套 ${} ==========")
    context = {"extracted": {}, "env": {}}
    engine = ExpressionEngine(context, db_client=FakeDbClient())
    expr = "${db.query_value('SELECT order_sub_id from sys_order_sub WHERE order_sub_type = 2', field='order_sub_id')}"
    print("表达式:", expr)
    result = engine.evaluate(expr)
    print("结果:", repr(result))


if __name__ == "__main__":
    test_nested_dollar_brace()
    test_simple_db_func()
