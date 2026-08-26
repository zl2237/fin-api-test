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
from typing import Any

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
    # 顶层字段直接在 data 上删除（避免 get_nested_value(data, "") 返回 None）
    if len(keys) == 1:
        if isinstance(data, dict):
            data.pop(keys[0], None)
        elif isinstance(data, list) and keys[0].isdigit():
            idx = int(keys[0])
            if idx < len(data):
                data.pop(idx)
        return
    parent = get_nested_value(data, ".".join(keys[:-1]))
    last = keys[-1]
    if isinstance(parent, dict):
        parent.pop(last, None)
    elif isinstance(parent, list) and last.isdigit():
        idx = int(last)
        if idx < len(parent):
            parent.pop(idx)


class PreProcessor:
    """前置处理器（用例编排执行层）。

    请求体参数三级取值优先级（引擎定案）：
    1. 数据集行值（最高）：覆盖除动态绑定外的所有字段
    2. 用例编排 set_field/add_field（本层，字面量或动态表达式）
    3. 接口字段默认值（兜底，组装阶段已进 body）

    动态绑定例外：值为 ${} 表达式的字段（上游提取/生成函数注入，如 [${audit_id}]）
    不在数据集覆盖范围内——表达式照常求值，行值同名列不压制。
    """

    def __init__(self, context: dict[str, Any], db_client=None, row_vars: dict[str, Any] = None):
        self.expr = ExpressionEngine(context, db_client=db_client)
        # 数据集行值（原始引用，区别于 context 池中被覆盖过的值）：
        # 非动态字段的行值压制 set_field 原值；空值（None/""，单元格未配置）剔除
        # = 未配置让位下一优先级，set_field 恢复表达式求值（如 [${audit_id}]）
        self.row_vars = {k: v for k, v in (row_vars or {}).items()
                         if v is not None and v != ""} or None

    def process(self, body: Any, actions: list[dict], extracted: dict[str, Any] = None) -> Any:
        """
        执行前置处理动作。

        :param body: 请求体（会被 deepcopy，不修改原对象）。支持 dict 和 list（数组请求体）。
                     数组请求体 [{...}] 时，set_field/delete_field/iterate_set 作用于 body[0]。
        :param actions: 动作列表
        :param extracted: 上下文已提取变量字典（引用），set_field 求值后的值会同步写入此字典，
                          使后续 post_extract 的 SQL 和后续节点的 ${xxx} 能引用到。
                          未传入时不同步（兼容旧调用）。
        """
        body = deepcopy(body) if body else {}

        # 数组请求体：body 为 [{...}]，前置处理作用于第一个元素
        if isinstance(body, list):
            if not body:
                return body
            if isinstance(body[0], dict):
                body[0] = self._process_dict(body[0], actions, extracted)
            return body

        # 普通 dict 请求体
        return self._process_dict(body, actions, extracted)

    def _process_dict(self, body: dict, actions: list[dict], extracted: dict[str, Any] = None) -> dict:
        """对 dict 请求体执行前置处理动作"""
        for action in actions or []:
            action_type = action.get("type")

            if action_type in ("set_field", "add_field"):
                path = action["path"]
                raw_value = action.get("value")
                # 动态绑定判定：值含 ${}（上游提取/生成函数注入）。
                # 三级优先级：数据集(1) > 编排 set_field(2) > 接口默认值(3)；
                # 动态绑定字段不在数据集覆盖范围 → 表达式照常求值
                is_dynamic = isinstance(raw_value, str) and "${" in raw_value
                if self.row_vars and path in self.row_vars and not is_dynamic:
                    # 优先级 1：非动态字段，行值直接生效（编排原值不执行）
                    value = self.row_vars[path]
                elif (self.row_vars and "." in path
                        and path.split(".", 1)[0] in self.row_vars
                        and not is_dynamic):
                    # 优先级 1（嵌套）：行值已整块替换该顶层对象（如 to_customer 列），
                    # 编排里残留的字面量子路径写入跳过，防止盖回行值
                    continue
                else:
                    # 动态绑定（表达式求值）或数据集未覆盖 → 优先级 2 生效
                    value = self.expr.evaluate(raw_value)
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
