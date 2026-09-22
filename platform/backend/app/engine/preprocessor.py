"""
前置处理器。

支持动作类型：
- set_field       设置字段（含嵌套路径，如 order_id / to_customer.put_amount.xxx）
- delete_field    删除字段
- add_field       新增字段（与 set_field 等价，语义区分）
- iterate_set     遍历列表，为每个元素设置字段（费用录入的 unique_id 关联）
- exec_sql        执行 SQL（INSERT/UPDATE/DELETE 等准备工作），支持 ${} 引用上下文变量
"""
import time
from copy import deepcopy
from typing import Any

from .expression import ExpressionEngine, inject_sql_vars


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

    请求体参数取值优先级（定案）：
    1. 手动覆盖（最高，本层）：set_field/add_field 的非空值——字面量直接生效，
       ${} 动态绑定照常求值；pre_process 在自动解析之后执行，天然压过第 2/3 层
    2. 套件注入（prepare_request 自动解析，上游白名单快照）
    3. 数据集域静态变量（prepare_request 自动解析）

    空值占位（三态之一）：value 为 None/"" 的 set_field 行是"自动引用"占位
    （清空转引用后的形态），不写字面空串——参数值由 prepare_request 按名解析
    （套件注入 > 数据集域；运行时变量不参与按名解析，仅 ${} 显式引用可取）。
    """

    def __init__(self, context: dict[str, Any], db_client=None):
        self.expr = ExpressionEngine(context, db_client=db_client)
        self.db_client = db_client

    def process(self, body: Any, actions: list[dict], extracted: dict[str, Any] | None = None) -> Any:
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

    def _process_dict(self, body: dict, actions: list[dict], extracted: dict[str, Any] | None = None) -> dict:
        """对 dict 请求体执行前置处理动作"""
        for action in actions or []:
            action_type = action.get("type")

            if action_type in ("set_field", "add_field"):
                path = action.get("path") or ""
                raw_value = action.get("value")
                if not path or raw_value is None or raw_value == "":
                    # 空 path（前端表格空行占位）或三态空值占位（自动引用）：
                    # 均非有效写入，参数值由 prepare_request 按名解析
                    continue
                # 优先级 1（手动覆盖）：字面量直接生效；${} 动态绑定表达式求值
                value = self.expr.evaluate(raw_value)
                set_nested_value(body, path, value)
                # 同步到上下文：用 path 末段作为 key（bl_no / order_id 等顶层字段直接可用）；
                # 后续节点通过 ${xxx} 显式引用本节点产出（不参与按名解析）
                if extracted is not None:
                    extracted[path.split(".")[-1]] = value

            elif action_type == "delete_field":
                delete_nested_value(body, action["path"])

            elif action_type == "exec_sql":
                # 请求前执行 SQL（INSERT/UPDATE/DELETE 等数据准备工作）。
                # ${} 引用统一变量池（环境变量 + 后置提取 + 前序 set_field 同步值），
                # 字符串值防注入转义（与 post_extract 的 db 提取同一实现）。
                # 执行失败抛异常 → 该节点产出失败步骤（原因可见），与断言失败口径一致。
                sql = action.get("sql") or ""
                if not sql.strip():
                    continue
                if not self.db_client:
                    raise RuntimeError("环境未配置数据库连接，无法执行前置 SQL")
                vars_pool = dict(self.expr.context.get("extracted", {}) or {})
                if extracted is not None:
                    vars_pool.update(extracted)
                self.db_client.execute(inject_sql_vars(sql, vars_pool))

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
                target_list = get_nested_value(body, list_path or "")
                sync_list = get_nested_value(body, sync_list_path or "") if sync_list_path else None
                if isinstance(target_list, list):
                    for idx, item in enumerate(target_list):
                        if isinstance(item, dict):
                            val = self.expr.evaluate(value_template)
                            item[field] = val
                            # 同步设置另一个列表的对应位置
                            if isinstance(sync_list, list) and idx < len(sync_list) and isinstance(sync_list[idx], dict):
                                sync_list[idx][field] = val

        return body
