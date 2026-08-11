"""深入测试 db.query_value 的参数解析。"""
import re
import sys

sys.path.insert(0, r"d:\CODE\PyCharm\pythonProject\fin-api-test\platform\backend")

from app.engine.expression import _parse_kwargs, _strip_quotes


def test_parse_kwargs():
    """测试 _parse_kwargs 对 db.query_value 参数的解析"""
    inner = "db.query_value('SELECT order_sub_id from sys_order_sub WHERE order_id = ${order_id} and order_sub_type = 2', field='order_sub_id')"

    func_name = inner[:inner.index("(")]
    args_str = inner[inner.index("(") + 1:-1]
    print("func_name:", func_name)
    print("args_str:", repr(args_str))
    print()

    kwargs = _parse_kwargs(args_str)
    print("_parse_kwargs 结果:", kwargs)
    print()

    # 测试回退逻辑
    parts = re.split(r",\s*(?![^']*['])", args_str.strip(), maxsplit=1)
    print("回退 split parts 数:", len(parts))
    for i, p in enumerate(parts):
        print(f"  [{i}]: {p!r}")
    print()

    sql = kwargs.get("sql") or kwargs.get("0")
    print("kwargs.get('sql') or kwargs.get('0'):", repr(sql))
    if not sql:
        print("回退: 取 parts[0]")
        sql = _strip_quotes(parts[0]) if parts else ""
        if len(parts) > 1:
            for p in re.split(r",\s*(?![^']*['])", parts[1].strip()):
                if "=" in p:
                    k, v = p.split("=", 1)
                    kwargs[k.strip()] = _strip_quotes(v)
        print("回退后 kwargs:", kwargs)
        print("回退后 sql:", repr(sql))


if __name__ == "__main__":
    test_parse_kwargs()
