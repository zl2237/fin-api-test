"""请求体树路径助手（get/set_nested_value 两个纯函数；2026-09-30「动作概念
退场」定案后前置动作引擎已删除，字段设置的全部语义收敛到数据集行 params 的
取值来源声明，见 prepare_request / param_resolver。原名 preprocessor.py，
因职责已收缩为路径助手而更名）。
"""


def get_nested_value(data, path: str):
    """按点号路径取值，支持列表下标（如 standard_list.0.unique_id）"""
    cur = data
    for k in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(k)
        elif isinstance(cur, list):
            if k.isdigit() and int(k) < len(cur):
                cur = cur[int(k)]
            else:
                return None
        else:
            return None
    return cur


def set_nested_value(data, path: str, value):
    """按点号路径设值，自动创建中间字典；下标段按需垫长列表"""
    keys = path.split(".")
    cur = data
    for k in keys[:-1]:
        if k.isdigit():
            idx = int(k)
            if isinstance(cur, list):
                while len(cur) <= idx:
                    cur.append({})
                cur = cur[idx]
            else:
                return
        else:
            if not isinstance(cur, dict):
                return
            if k not in cur or not isinstance(cur[k], (dict, list)):
                cur[k] = {}
            cur = cur[k]
    last = keys[-1]
    if last.isdigit() and isinstance(cur, list):
        idx = int(last)
        while len(cur) <= idx:
            cur.append(None)
        cur[idx] = value
    elif isinstance(cur, dict):
        cur[last] = value
