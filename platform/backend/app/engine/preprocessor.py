"""
前置处理器。

支持动作类型：
- set_field       设置字段（含嵌套路径，如 order_id / to_customer.put_amount.xxx）
- delete_field    删除字段
- add_field       新增字段（与 set_field 等价，语义区分）
- iterate_set     遍历列表，为每个元素设置字段（费用录入的 unique_id 关联）
"""
import time
from copy import deepcopy
from typing import Any, Dict, List

from .expression import ExpressionEngine


def get_nested_value(data: Any, path: str) -> Any:
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


def set_nested_value(data: Any, path: str, value: Any):
    """按点号路径设值，自动创建中间字典"""
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


def delete_nested_value(data: Any, path: str):
    """按点号路径删除字段"""
    keys = path.split(".")
    parent = get_nested_value(data, ".".join(keys[:-1]))
    last = keys[-1]
    if isinstance(parent, dict):
        parent.pop(last, None)
    elif isinstance(parent, list) and last.isdigit():
        idx = int(last)
        if idx < len(parent):
            parent.pop(idx)


class PreProcessor:
    def __init__(self, context: Dict[str, Any], db_client=None):
        self.expr = ExpressionEngine(context, db_client=db_client)

    def process(self, body: Dict, actions: List[Dict], extracted: Dict[str, Any] = None) -> Dict:
        """
        执行前置处理动作。

        :param body: 请求体（会被 deepcopy，不修改原对象）
        :param actions: 动作列表
        :param extracted: 上下文已提取变量字典（引用），set_field 求值后的值会同步写入此字典，
                          使后续 post_extract 的 SQL 和后续节点的 ${context.xxx} 能引用到。
                          未传入时不同步（兼容旧调用）。
        """
        body = deepcopy(body) if body else {}
        for action in actions or []:
            action_type = action.get("type")

            if action_type in ("set_field", "add_field"):
                value = self.expr.evaluate(action.get("value"))
                path = action["path"]
                set_nested_value(body, path, value)
                # 同步到上下文：用 path 末段作为 key（bl_no / order_id 等顶层字段直接可用）
                if extracted is not None:
                    extracted[path.split(".")[-1]] = value

            elif action_type == "delete_field":
                delete_nested_value(body, action["path"])

            elif action_type == "sleep":
                seconds = self.expr.evaluate(action.get("seconds", 0))
                try:
                    seconds = float(seconds)
                except Exception:
                    seconds = 0
                if seconds > 0:
                    time.sleep(seconds)

            elif action_type == "iterate_set":
                # list_path 兼容简写为 path（前端表格统一用 path 字段）
                list_path = action.get("list_path") or action.get("path")
                field = action.get("field")
                value_template = action.get("value")
                # sync_list：同步设置的另一个列表路径，同位置元素用相同值（费用录入的 unique_id 关联）
                sync_list_path = action.get("sync_list")
                target_list = get_nested_value(body, list_path)
                sync_list = get_nested_value(body, sync_list_path) if sync_list_path else None
                if isinstance(target_list, list):
                    for idx, item in enumerate(target_list):
                        if isinstance(item, dict):
                            val = self.expr.evaluate(value_template)
                            item[field] = val
                            # 同步设置另一个列表的对应位置
                            if isinstance(sync_list, list) and idx < len(sync_list) and isinstance(sync_list[idx], dict):
                                sync_list[idx][field] = val

        return body
