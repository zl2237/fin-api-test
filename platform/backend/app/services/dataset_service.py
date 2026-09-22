"""dataset_service：数据集（变量池）服务层。

单套语义（定案）：每个数据集 = 一套数据（存储上即唯一一行），取消多行
数据驱动的行概念——多场景 = 多个数据集（换绑 / 执行面板切换）。

职责：
- 数据集 CRUD 校验与编排（列定义校验、引用保护、级联删行）
- 变量池视图（build_params_view：按节点分组的入参清单）与单套值保存
- 数据集复制（隔离语义下的复用）与数据集间覆盖合并

概念定案（用例级 1:N）：
- 数据集归用例私有（case_id），用例间隔离，复用靠复制；
- 列中文名不落库，实时引用项目字段字典（FieldDictionary）；
- 编排唯一来源是用例当前配置（数据集只管数据，不做编排快照）。

列名即变量名：列 key 直接进执行变量池，因此校验比普通命名更严——
点号撞嵌套路径语法、${} 撞表达式占位符、空格撞变量引用。
"""
import json
import re
from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from .. import crud, models
from ..engine.topo import topo_order
from .body_builder import parse_field_value

# 列 key 合法字符：点路径段。段 = 标识符（字母/数字/下划线，不以数字开头）或纯数字
# （列表下标，如 select_node_user.0.user_id——编排声明的参数路径原样成键，行为等价）。
# 数据集模式：列键是参数的点路径名（嵌套 JSON 递归拆叶，如 to_customer.put_amount），
# 段内仍不允许空格/${}（撞表达式语法与变量引用）；收集器拆叶不拆数组下标（数组值整列保存）
_COL_KEY_RE = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*|\d+)(?:\.(?:[A-Za-z_][A-Za-z0-9_]*|\d+))*$")

_VALID_COL_TYPES = {"string", "int", "bool", "array", "object", "file"}


def _validate_columns(columns: list) -> None:
    """列定义校验：非空、key 唯一且合法、type 在白名单；label 剥离（中文名实时引用字段字典）"""
    if not columns:
        raise ValueError("数据集至少需要一列")
    seen = set()
    for col in columns:
        key = str(col.get("key") or "").strip()
        if not _COL_KEY_RE.match(key):
            raise ValueError(f"列名 {key!r} 不合法：仅允许字母/数字/下划线/点号（点路径段，如 a.b.c，每段不以数字开头；段内空格/表达式符会与表达式语法冲突）")
        if key in seen:
            raise ValueError(f"列名重复：{key}（列名即变量名，重复会相互覆盖）")
        seen.add(key)
        col["key"] = key
        col.pop("label", None)  # 列中文名实时引用项目字段字典，不落库
        ctype = col.get("type") or "string"
        if ctype not in _VALID_COL_TYPES:
            raise ValueError(f"列 {key} 类型 {ctype!r} 不支持：{'/'.join(sorted(_VALID_COL_TYPES))}")
        col["type"] = ctype


def _validate_row_data(columns: list, data: dict) -> None:
    """行数据校验：key 必须都在列定义内（缺列允许=置空语义）"""
    keys = {c["key"] for c in columns}
    unknown = set(data.keys()) - keys
    if unknown:
        raise ValueError(f"行数据含未定义的列：{'、'.join(sorted(unknown))}")


# ============ 数据集 CRUD ============

def create_dataset(db: Session, project_id: int | None, name: str, columns: list,
                   user_id: int | None, description: str | None = None,
                   rows_data: list | None = None, case_id: int | None = None) -> models.DataSet:
    """建数据集；rows_data 可选（创建即带值的原子写入路径）"""
    columns = [dict(c) for c in columns]
    _validate_columns(columns)
    obj: models.DataSet = models.DataSet(project_id=project_id, case_id=case_id, name=name, description=description,
                         columns=columns,
                         created_by=user_id, updated_by=user_id)
    db.add(obj)
    if rows_data:
        db.flush()  # 先拿 id，行数据外键依赖
        for data in rows_data:
            _validate_row_data(columns, data)
        for i, data in enumerate(rows_data, start=1):
            db.add(models.DataSetRow(dataset_id=obj.id, row_index=i, data=data))
    db.commit()
    db.refresh(obj)
    return obj


def get_dataset(db: Session, dataset_id: int) -> models.DataSet:
    obj = crud.get_dataset(db, dataset_id)
    if not obj:
        raise ValueError(f"数据集不存在: {dataset_id}")
    return obj


def update_dataset(db: Session, dataset_id: int, name: str | None = None,
                   description: str | None = None, columns: list | None = None) -> models.DataSet:
    """更新数据集。改列定义时校验现有行数据不含被删的列（防行悬空）。"""
    obj = get_dataset(db, dataset_id)
    if name is not None:
        obj.name = name
    if description is not None:
        obj.description = description
    if columns is not None:
        new_cols = [dict(c) for c in columns]
        _validate_columns(new_cols)
        new_keys = {c["key"] for c in new_cols}
        for row in (obj.rows or []):
            used = set((row.data or {}).keys()) - new_keys
            if used:
                raise ValueError(f"行 #{row.row_index} 的行数据仍使用已删列：{'、'.join(sorted(used))}，请先清理行数据")
        obj.columns = new_cols
    db.commit()
    db.refresh(obj)
    return obj


def delete_dataset(db: Session, dataset_id: int) -> None:
    """删除数据集：被用例绑定时拒绝；归属用例名下最后一个拒绝
    （至少保留一个池，否则派生用例执行 400「未绑定数据集」）；成功级联删行"""
    obj = get_dataset(db, dataset_id)
    n = crud.count_cases_bound_to_dataset(db, dataset_id)
    if n:
        raise ValueError(f"数据集被 {n} 个用例绑定，请先在用例中解绑后再删除")
    siblings = (db.query(models.DataSet)
                .filter(models.DataSet.case_id == obj.case_id).count())
    if siblings <= 1:
        raise ValueError("用例至少需保留一个数据集，不允许删除唯一的一个")
    db.query(models.DataSetRow).filter(models.DataSetRow.dataset_id == dataset_id).delete()
    db.delete(obj)
    db.commit()


# ============ 变量池视图与单套值保存（每个数据集 = 一套数据） ============

def build_params_view(db: Session, dataset_id: int) -> dict:
    """用例级变量池视图（变量池界面数据源）：归属用例当前编排 × 接口字段 × 池值。

    变量池是用例级单池（键全局去重），nodes 只是按节点的筛选视角：
    - all_params：全用例去重参数清单（含各节点状态合并：手动覆盖 > 动态配置）
    - nodes：拓扑执行序的节点视角，每节点 params = 接口字段 key ∪ pre_process
      路径（去重保序）；每参数带 value（池中现值）/ manual（节点编排字面量 =
      手动覆盖）/ dynamic（编排 ${} 动态绑定）
    - orphan_keys：池中存在但当前编排无节点使用的键（悬空变量）
    - 无必填概念：三层皆空的参数执行时按字段类型发空值（见 prepare_request）
    """
    ds = get_dataset(db, dataset_id)
    case = crud.get_testcase(db, ds.case_id)
    if not case:
        raise ValueError(f"归属用例不存在: {ds.case_id}")
    cfgs = (db.query(models.CaseNodeConfig)
            .filter(models.CaseNodeConfig.case_id == ds.case_id).all())
    cfg_by_node = {c.node_id: c for c in cfgs}
    api_ids = {c.api_id for c in cfgs if c.api_id}
    apis = (db.query(models.ApiDefinition)
            .filter(models.ApiDefinition.id.in_(api_ids)).all()) if api_ids else []
    apis_by_id = {a.id: a for a in apis}

    rows = crud.list_rows(db, dataset_id)
    values = dict(rows[0].data or {}) if rows else {}
    labels = {n.get("id"): (n.get("label") or n.get("id"))
              for n in (getattr(case, "dag_config", None) or {}).get("nodes", [])
              if isinstance(n, dict)}
    used_keys: set = set()
    nodes = []
    for node_id in _topo_node_ids(getattr(case, "dag_config", None)):
        cfg = cfg_by_node.get(node_id)
        if not cfg or not cfg.api_id:
            continue
        api = apis_by_id.get(cfg.api_id)
        if not api:
            continue
        # 编排非空值分两类：字面量 = 手动覆盖；${} = 动态绑定（运行时求值）
        manual: dict = {}
        dynamic: dict = {}
        ref_paths: list[str] = []
        for act in cfg.pre_process or []:
            if act.get("type") not in ("set_field", "add_field"):
                continue
            path = act.get("path") or ""
            if not path:
                continue
            val = act.get("value")
            if val is None or val == "":
                ref_paths.append(path)
            elif isinstance(val, str) and "${" in val:
                dynamic[path] = val
            else:
                manual[path] = val
        field_types = {f.key: (f.field_type or "string")
                       for f in (getattr(api, "fields", None) or []) if f.key}
        # 参数清单：接口字段 → 自动引用占位 → 动态/手动覆盖（去重保序）
        keys = list(dict.fromkeys([
            *(k for k in field_types if k),
            *ref_paths,
            *dynamic.keys(),
            *manual.keys(),
        ]))
        params = []
        for k in keys:
            used_keys.add(k)
            has_value = k in values and values[k] is not None and values[k] != ""
            params.append({
                "key": k,
                "type": field_types.get(k) or (
                    ds_col_type(ds, k) if has_value else "string"),
                "value": values.get(k) if has_value else "",
                "manual": k in manual,
                "manual_value": manual.get(k) or dynamic.get(k),
                "dynamic": k in dynamic,
            })
        nodes.append({
            "node_id": node_id,
            "label": labels.get(node_id, node_id),
            "api_id": api.id,
            "api_name": api.name,
            "params": params,
        })

    # 用例级单池：跨节点同名键合并为一份（状态取最强：手动覆盖 > 动态配置）
    all_params: dict[str, dict] = {}
    for node in nodes:
        for p in node["params"]:
            cur = all_params.get(p["key"])
            if cur is None:
                all_params[p["key"]] = dict(p)
                continue
            cur["manual"] = cur["manual"] or p["manual"]
            cur["dynamic"] = cur["dynamic"] or p["dynamic"]
            if p["manual"] or (p["dynamic"] and not cur["manual"]):
                cur["manual_value"] = p["manual_value"]
    return {
        "dataset_id": ds.id,
        "all_params": list(all_params.values()),
        "nodes": nodes,
        # 悬空 = 池值键不被任何编排键使用：排除前缀关联键（拆叶子键 audit_msg.code
        # 服务于编排键 audit_msg 的前缀展开；整对象列 to_customer 服务于子路径键）——
        # 它们运行时按名正常消费，不是悬空
        "orphan_keys": [k for k in values
                        if k not in used_keys
                        and not any(k.startswith(u + ".") or u.startswith(k + ".")
                                    for u in used_keys)],
    }


def ds_col_type(ds: models.DataSet, key: str) -> str:
    """数据集列定义里的类型（无定义回退 string）"""
    for c in ds.columns or []:
        if isinstance(c, dict) and c.get("key") == key:
            return c.get("type") or "string"
    return "string"


def save_dataset_values(db: Session, dataset_id: int, values: dict,
                        user_id: int | None = None,
                        column_types: dict | None = None) -> models.DataSet:
    """保存单套数据：values 即该数据集的唯一一套值。

    - 列定义随参数走：现有列类型保留，新键按值推断补列，不在 values 中的旧键剔除
      （数据集 = 当前编排参数的值集，悬空键随保存清理）
    - column_types 可选：新键（或空值成键）以显式类型建列（空值默认推断 string，
      新增 int/bool/file 等变量时前端传入）
    - 行存储整体替换为单行（row_index=1，存量多行就地收敛）
    """
    ds = get_dataset(db, dataset_id)
    column_types = column_types or {}
    old_types = {c.get("key"): c.get("type")
                 for c in (ds.columns or []) if isinstance(c, dict) and c.get("key")}
    columns = [{"key": k,
                "type": old_types.get(k) or column_types.get(k) or _infer_col_type(v)}
               for k, v in values.items()]
    _validate_columns(columns)
    _validate_row_data(columns, values)
    db.query(models.DataSetRow).filter(models.DataSetRow.dataset_id == dataset_id).delete()
    db.add(models.DataSetRow(dataset_id=dataset_id, row_index=1, data=dict(values)))
    ds.columns = columns
    if user_id is not None:
        ds.updated_by = user_id
    db.commit()
    db.refresh(ds)
    return ds


def save_node_values(db: Session, dataset_id: int, node_id: str,
                     sets: dict, clears: list[str]) -> int:
    """保存节点级手动覆盖（数据集页节点页签的编辑语义）。

    同字段跨节点异值（如状态流转）不能进池（池一键一值），由各节点在
    pre_process 配字面量——三层解析第 1 层手动覆盖，天然压过池值。
    - sets：key → 值（顶层键、纯字面量）；已有同 path 的 set_field/add_field
      动作就地更新 value，否则追加 set_field 动作
    - clears：移除该 path 的字面量动作（回落池值）；动态绑定（值含 ${}）
      属编排配置，不在此清除，误传报错
    - 其余动作类型（iterate_set/exec_sql/sleep 等）一律不动

    返回受影响的参数个数。pre_process 为 JSON 列：整列表重建后重新赋值，
    确保 SQLAlchemy 变更检测（in-place 修改不触发 dirty）。
    """
    ds = get_dataset(db, dataset_id)
    for k in list(sets) + list(clears):
        if not _COL_KEY_RE.match(k):
            raise ValueError(f"参数名不合法: {k}（仅允许字母/数字/下划线/点路径段）")
    cfg = (db.query(models.CaseNodeConfig)
           .filter(models.CaseNodeConfig.case_id == ds.case_id,
                   models.CaseNodeConfig.node_id == node_id).first())
    if not cfg:
        raise ValueError(f"节点不存在: {node_id}（用例编排可能已调整，请刷新变量池视图）")

    def _is_action(a: dict, path: str) -> bool:
        return (isinstance(a, dict) and a.get("type") in ("set_field", "add_field")
                and a.get("path") == path)

    pre: list = []
    touched = 0
    for a in (cfg.pre_process or []):
        path = a.get("path") if isinstance(a, dict) else None
        if path in sets and _is_action(a, path):
            pre.append({**a, "value": sets[path]})  # 就地更新（保留原动作类型）
            touched += 1
        elif path in clears and _is_action(a, path):
            if "${" in str(a.get("value") or ""):
                raise ValueError(f"{path} 为动态绑定（${{}}），请在用例编排中调整")
            touched += 1  # 移除（跳过追加）
        else:
            pre.append(a)
    for k, v in sets.items():
        if not any(_is_action(a, k) for a in pre):
            pre.append({"type": "set_field", "path": k, "value": v})
            touched += 1
    if touched:
        cfg.pre_process = pre  # 整列表重新赋值触发 JSON dirty
        db.commit()
    return touched


# ============ 执行展开（单套语义：每个数据集 = 一套数据，一次执行） ============

def plan_case_expansion(db: Session, case, dataset_id=None) -> list:
    """按用例绑定生成执行展开计划。

    - 未绑定且未临时指定 dataset_id → ValueError：入参已无接口默认值兜底
      （数据集模式一刀切），未绑定数据集的执行=全空参数，禁止
    - 绑定数据集 → 单条：该数据集的唯一一套数据（首行）作为本次执行的变量组
      （多场景 = 多个数据集，换绑/执行面板切换执行）
    - 绑定但 0 行 → ValueError（先录入数据再执行）
    - dataset_id 传入时临时覆盖用例绑定（执行面板换数据集，不改绑定本身）
    - 编排唯一来源是用例当前配置（快照覆盖机制已下线：数据集只管数据）
    """
    effective = dataset_id if dataset_id is not None else getattr(case, "dataset_id", None)
    if not effective:
        raise ValueError(
            "该用例未绑定数据集，无法执行；请先在用例的「数据」入口绑定数据集")
    ds = crud.get_dataset(db, effective)
    if not ds:
        raise ValueError(f"用例绑定的数据集不存在: {effective}")
    if ds.case_id != case.id:
        raise ValueError("数据集不属于该用例（数据集按用例隔离，请在用例自己的数据集中选择）")
    rows = crud.list_rows(db, effective)
    if not rows:
        raise ValueError("数据集无数据，请先在变量池中录入参数值再执行")
    first_key = (ds.columns or [{}])[0].get("key") if ds.columns else None
    r = rows[0]
    return [{
        "dataset_id": effective,
        "row": {
            "row_index": r.row_index,
            "data": dict(r.data or {}),
            "label": str((r.data or {}).get(first_key)) if first_key else str(r.row_index),
        },
    }]


# ============ 用例绑定校验（方案定案 #5：用例级绑定，同项目） ============

def validate_binding(db: Session, case, dataset_id) -> None:
    """用例绑定数据集前的校验：None=解绑直过；须存在且为本用例名下（用例间隔离，复用靠复制）"""
    if dataset_id is None:
        return
    ds = crud.get_dataset(db, dataset_id)
    if not ds:
        raise ValueError(f"数据集不存在: {dataset_id}")
    if ds.case_id != case.id:
        raise ValueError("不能绑定其他用例的数据集（数据集按用例隔离，复用请复制）")


# ============ 列类型推断与拓扑执行序（变量池收集辅助） ============

def _infer_col_type(value) -> str:
    """列类型按值推断（bool 先于 int：bool 是 int 子类）"""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def _topo_node_ids(dag: dict | None) -> list:
    """dag 节点的拓扑执行序（engine.topo_order 唯一实现，此处口径：环/断链节点排末尾）。

    收集口径需按执行序取值：同名异值列取业务链路源头节点（执行序首个）的值，
    而非 dag 数组顺序（数组可能是用户拖拽后的任意顺序，源头节点不一定排最前）。
    环/断链节点按引擎同口径排到末尾（引擎也不执行它们，只是收集时仍扫一遍兜底）。
    """
    if not dag:
        return []
    order, leftover = topo_order(dag)
    return order + leftover


# ============ 变量池收集器（用例保存钩子：清空转引用，数据集模式定案） ============

def _flatten_leaves(path: str, value) -> dict | None:
    """值递归拆叶（点路径键）：dict 拆到 path.leaf，list/标量为叶。

    字符串值仅当以 { 或 [ 开头才尝试 JSON 解析（嵌套对象/数组以 JSON 文本表达；
    纯数字字符串不解析，防 "001"/"12345" 这类单号被转成 int 改变类型）。
    拆出的键不合法（_COL_KEY_RE）或拆叶结果为空 → None：调用方保留节点字面量
    作手动覆盖，不强行入池（键无法成为变量名的值没有池形态）。
    """
    if isinstance(value, str) and value[:1] in ("{", "["):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return {path: value}
    if isinstance(value, dict):
        out: dict = {}
        for k, v in value.items():
            if not isinstance(k, str) or not _COL_KEY_RE.match(f"{path}.{k}"):
                return None
            sub = _flatten_leaves(f"{path}.{k}", v)
            if sub is None:
                return None
            out.update(sub)
        return out or None
    return {path: value}


def _pool_prefix_conflict(pool_keys: set, key: str) -> bool:
    """点路径键与现有池键互为父子前缀（a 与 a.b）：形状冲突，不能同池。
    同键（a 与 a）不算冲突——force 收口下同键覆盖合法。"""
    return any(key.startswith(k + ".") or k.startswith(key + ".")
               for k in pool_keys)


_REF_EXPR_RE = re.compile(r"\$\{([^{}]+)\}")


def _collect_ref_names(text: str, out: set) -> None:
    """提取文本中 ${name} 引用的变量名（首段）加入 out。

    函数调用（inner 带 '('，如 generate_bl_no() / db.query_value(...)）跳过；
    context. 前缀剥掉（等价写法）；其余前缀（db./env./global. 不带括号的罕见
    形态）取首段保留（误留只是少清一个键，无行为风险）。"""
    for m in _REF_EXPR_RE.finditer(text):
        inner = m.group(1).strip()
        if "(" in inner:
            continue
        if inner.startswith("context."):
            inner = inner[len("context."):]
        seg = inner.split(".")[0]
        if seg:
            out.add(seg)


def sync_case_variable_pool(db: Session, case, user_id: int | None = None,
                            force: bool = False, unbind: bool = False) -> dict:
    """用例保存钩子：静态入参收集入池 + 清空转引用（三层优先级的数据侧迁移）。

    按拓扑执行序逐节点收集，同节点先 pre_process 后字段默认值（set_field 覆盖
    默认值、最终生效值为准）：
    - pre_process set_field/add_field 静态字面量：递归拆叶入池（新键写入全部现有行）
      后值清空为 ""（清空转引用：运行时按参数名自动解析，节点保留占位行）；
      键已在池 → 默认保留字面量为手动覆盖（有值=覆盖，收集幂等：二次保存
      不会把手动覆盖收走）；force=True 时统一收口——以节点值为准覆盖池值后清空
      （节点字面量当前实际生效，收口后行为不变），仅形状冲突/键不合法仍保留
    - API 字段静态默认（运行时已不兜底，仅作迁移源）：键不在池时入池；
      键已在池 → 跳过（池值才是生效值，默认值覆盖池会改行为）；
      force=True 时例外——统一收口，接口默认值也以当前生效值为准刷新池中旧值
      （池若来自旧快照/旧接口定义，会偏离当前生效语义，如旧值 entrust_status=1
      而当前默认=2）；多节点同名默认值不同（旧快照接口与现网接口并存）时，
      按拓扑序**首个使用节点的默认值为准**（订单创建时确立的数据向下游传播，
      而非最后一个覆盖——后者会把开票接口的 customer_id=[] 等误写进全池）
    - API 字段动态 ${} 默认：迁为该节点 pre_process 动态引用（节点未显式配置
      该 path 时追加，绑定语义原样保留，只是从接口定义搬到用例编排）
    - 悬空清理：用例增删节点后，池中不再被剩余编排使用的键（含列与行值）
      剔除；${} 显式引用的变量名与前缀关联键（拆叶族/整对象列）保留

    池 = 用例绑定的数据集（case.dataset_id）；无绑定且确有可收集值时自动创建
    「{用例名}-变量池」（含 1 行快照）并绑定。返回 stats。
    """
    cfgs = (db.query(models.CaseNodeConfig)
            .filter(models.CaseNodeConfig.case_id == case.id).all())
    stats: dict[str, Any] = {"nodes": 0, "columns": 0, "collected": [],
                             "kept": 0, "dynamic": 0, "conflicts": [], "invalid": 0}
    if not cfgs:
        return stats
    api_ids = {c.api_id for c in cfgs if c.api_id}
    apis = (db.query(models.ApiDefinition)
            .filter(models.ApiDefinition.id.in_(api_ids)).all()) if api_ids else []
    apis_by_id = {a.id: a for a in apis}

    ds = crud.get_dataset(db, case.dataset_id) if getattr(case, "dataset_id", None) else None
    if ds is None:
        # 显式解绑（unbind=True）：尊重用户意图，不做自动复用/新建绑定（收集一并跳过）
        if unbind:
            return stats
        # 无绑定时复用名下已有数据集（最旧），避免一用例多池；
        # 确无任何数据集才在落库时新建（见 pending_values 分支）
        existing = (db.query(models.DataSet)
                    .filter(models.DataSet.case_id == case.id)
                    .order_by(models.DataSet.id).first())
        if existing:
            ds = existing
            case.dataset_id = ds.id
    pool_keys = {c.get("key") for c in ((ds.columns if ds else None) or [])
                 if isinstance(c, dict) and c.get("key")}
    # 池现值（首行，单套语义）：空值键（None/""）= 未配置语义，不阻止字面量吸收——
    # 否则列存在但值空的键会让节点静态字面量永远收不进池（幂等保护误伤）
    _rows = (ds.rows if ds else None) or []
    pool_vals = dict(_rows[0].data or {}) if _rows else {}
    pending_cols: list = []   # 新列（按收集顺序）
    pending_values: dict = {}  # 新键初值（写入全部行）
    evict_keys: set = set()   # force 键族替换时被驱逐的池键（落库时从列/行剔除）

    def _evict_family(key: str) -> None:
        """键族替换（force 收口）：驱逐池/待写中与 key 父子冲突的键。

        场景：拓扑序前节点的接口默认值拆叶先入池（service_project.booking_space…），
        后节点的顶层标量字面量（service_project="customs_clearance"）与其形状冲突——
        而线上实际生效的是字面量（整键覆盖为标量），拆叶族已不参与运行，驱逐保行为。"""
        fam = {k for k in pool_keys if k != key and (
            k.startswith(key + ".") or key.startswith(k + "."))}
        fam |= {k for k in pending_values if k != key and (
            k.startswith(key + ".") or key.startswith(k + "."))}
        for k in fam:
            pool_keys.discard(k)
            evict_keys.add(k)
            pending_cols[:] = [c for c in pending_cols if c["key"] != k]
            pending_values.pop(k, None)

    def _collect(leaves: dict, origin: str, col_type: str | None = None,
                 force_collect: bool = False) -> str:
        """全部叶键无形状冲突才收集；返回 collected / in_pool / conflict。

        - 默认：键已在池 → in_pool（调用方保留为手动覆盖，幂等语义）；
          父子形状冲突 → conflict（同样保留）
        - force_collect：统一收口——键已在池覆盖池值；父子冲突做键族替换
          （驱逐对方键族后收入本键，以节点生效值为准），列不重复追加
        """
        if not force_collect:
            for k in leaves:
                if _pool_prefix_conflict(pool_keys, k):
                    # 冲突对方全是空值键（未配置，从未参与运行；pool_vals 是收集前
                    # 快照，须叠加 pending_values 才是当前事实值）→ 驱逐空键族后
                    # 正常吸收（拆叶族以节点字面量生效值为准入池，行为不变）；
                    # 任一对方有值 → 真形状冲突，保留为手动覆盖
                    conflicting = {p for p in pool_keys
                                   if k.startswith(p + ".") or p.startswith(k + ".")}
                    if all(pool_vals.get(p) in (None, "") and p not in pending_values
                           for p in conflicting):
                        _evict_family(k)
                    else:
                        stats["conflicts"].append(k)
                        return "conflict"
            # 键在池且有值（或本 run 已收集过，防拓扑序后值覆盖前值）→ in_pool
            # （保留为手动覆盖，幂等语义）；键在池但值为空（未配置）→ 允许吸收，
            # pending_values 覆盖空值
            if any(k in pool_keys and (pool_vals.get(k) not in (None, "")
                                       or k in pending_values)
                   for k in leaves):
                return "in_pool"
        else:
            for k in leaves:
                _evict_family(k)
        for k, v in leaves.items():
            if k not in pool_keys:
                pool_keys.add(k)
                pending_cols.append({"key": k, "type": col_type or _infer_col_type(v)})
            pending_values[k] = v
            stats["collected"].append({"key": k, "value": v, "from": origin})
        return "collected"

    dirty = False
    cfg_by_node = {c.node_id: c for c in cfgs}
    for node_id in _topo_node_ids(getattr(case, "dag_config", None)):
        cfg = cfg_by_node.get(node_id)
        if not cfg or not cfg.api_id:
            continue
        api = apis_by_id.get(cfg.api_id)
        if not api:
            continue
        stats["nodes"] += 1
        api_field_types = {f.key: (f.field_type or "string")
                           for f in (getattr(api, "fields", None) or []) if f.key}
        # 深拷贝再改：就地清空浅拷贝里的 dict 会同步污染 ORM 历史快照，
        # commit 时新旧相等被判"未变更"而不落库（真实 ORM 环境的隐蔽坑）
        pre = deepcopy(cfg.pre_process or [])
        node_dirty = False
        node_paths: set[str] = set()  # 本节点显式配置的 path（字段默认迁移的去重基准）
        # 先 pre_process：静态字面量拆叶入池 + 清空转引用；${} 动态绑定原样保留
        for act in pre:
            if act.get("type") not in ("set_field", "add_field"):
                continue
            path = act.get("path") or ""
            val = act.get("value")
            if not path:
                continue  # 空行占位（前端表格留空）非有效动作
            if isinstance(val, str) and "${" in val:
                stats["dynamic"] += 1
                node_paths.add(path)
                continue
            if val is None or val == "":
                node_paths.add(path)
                continue
            if not _COL_KEY_RE.match(path):
                stats["invalid"] += 1
                continue
            leaves = _flatten_leaves(path, val)
            if leaves is None:
                stats["invalid"] += 1
            elif _collect(leaves, f"节点 {node_id}",
                          "file" if api_field_types.get(path) == "file" else None,
                          force_collect=force) == "collected":
                act["value"] = ""  # 清空转引用（节点保留占位行，运行时按名解析）
                node_dirty = True
            else:
                stats["kept"] += 1  # 形状冲突 → 保留为手动覆盖（force 下仅此不收口）
            node_paths.add(path)
        # 后字段默认值（一刀切迁移源：运行时不再兜底，保存时迁入池/编排）
        for f in getattr(api, "fields", None) or []:
            key = f.key
            if not key:
                continue
            if not _COL_KEY_RE.match(key):
                stats["invalid"] += 1
                continue
            raw = getattr(f, "default_value", None)
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                continue
            if key in node_paths:
                continue  # 节点已显式配置（手动覆盖/动态绑定/空占位）
            if isinstance(raw, str) and "${" in raw:
                # 动态默认 → 迁为节点动态引用（绑定语义不变，从接口定义搬到用例编排）
                pre.append({"type": "set_field", "path": key, "value": raw})
                node_paths.add(key)
                stats["dynamic"] += 1
                node_dirty = True
                continue
            leaves = _flatten_leaves(key, parse_field_value(raw, f.field_type or "string"))
            if leaves is None:
                stats["invalid"] += 1
            else:
                # force 统一收口：接口默认值也以当前生效值为准刷新池中旧值；但多节点
                # 同名默认值不同时按拓扑首个使用节点为准（本 run 该键已被更早节点的
                # 字面量或默认值写过 → 跳过本次默认，避免最后一个节点误覆盖全池）
                if force and any(k in pending_values for k in leaves):
                    continue
                _collect(leaves, f"接口默认 {api.name}.{key}",
                         "file" if f.field_type == "file" else None,
                         force_collect=force)
        if node_dirty:
            cfg.pre_process = pre  # 整列重赋值（JSON 列的原地变更不被 ORM 跟踪）
            dirty = True

    # ---- 悬空清理：用例增删节点后，池中不再被剩余编排使用的键剔除 ----
    # used = 接口字段 ∪ pre_process 路径（全部剩余节点，去重口径同参数清单）；
    # ${} 显式引用的变量名保留（手动新增的自定义变量常以表达式引用，删了会断链）；
    # 前缀关联键（拆叶族/整对象列服务于某 used 键）不算悬空（口径同 orphan_keys）
    drop_keys: set = set()
    if ds is not None:
        used: set[str] = set()
        ref_names: set[str] = set()
        for cfg in cfgs:
            api = apis_by_id.get(cfg.api_id)
            if api:
                for f in (getattr(api, "fields", None) or []):
                    if f.key:
                        used.add(f.key)
            for act in (cfg.pre_process or []):
                if act.get("path"):
                    used.add(act["path"])
                if isinstance(act.get("value"), str):
                    _collect_ref_names(act["value"], ref_names)
            for r in (getattr(cfg, "post_extract", None) or []):
                if isinstance(r, dict) and r.get("sql"):
                    _collect_ref_names(r["sql"], ref_names)
            for a in (getattr(cfg, "assertions", None) or []):
                _collect_ref_names(json.dumps(a, ensure_ascii=False), ref_names)
        pool_existing = (set(pool_vals)
                         | {c.get("key") for c in (ds.columns or [])
                            if isinstance(c, dict) and c.get("key")})
        for k in pool_existing:
            if k in pending_values:
                continue  # 本 run 刚收集的（来源必在 used）
            if k in used or k in ref_names or k.split(".")[0] in ref_names:
                continue
            if any(k.startswith(u + ".") or u.startswith(k + ".") for u in used):
                continue  # 前缀关联：拆叶族/整对象列服务于某 used 键
            drop_keys.add(k)

    if pending_values or evict_keys or drop_keys:
        if ds is None:
            assert case.project_id is not None  # 用例必然属于某项目
            suffix = "-变量池"
            name = f"{case.name}{suffix}"
            if len(name) > 100:
                name = case.name[:100 - len(suffix) - 1] + f"…{suffix}"
            ds = create_dataset(
                db, project_id=case.project_id, case_id=case.id, name=name,
                columns=pending_cols, user_id=user_id,
                description=f"用例「{case.name}」保存时自动收集的静态参数变量池",
                rows_data=[dict(pending_values)],
            )
            case.dataset_id = ds.id
        else:
            if evict_keys or drop_keys:
                # 键族替换/悬空清理：对应列从池中剔除
                gone = evict_keys | drop_keys
                ds.columns = [c for c in (ds.columns or [])
                              if not (isinstance(c, dict) and c.get("key") in gone)]
            ds.columns = [*(ds.columns or []), *pending_cols]
            if ds.rows:
                gone = evict_keys | drop_keys
                for r in ds.rows:
                    data = {k: v for k, v in (r.data or {}).items()
                            if k not in gone}
                    r.data = {**data, **pending_values}
            elif pending_values:
                db.add(models.DataSetRow(dataset_id=ds.id, row_index=1, data=dict(pending_values)))
        db.commit()
    elif dirty:
        db.commit()  # 仅动态默认迁移（无新列）：清空转引用/迁引用的编排变更单独落库
    stats["columns"] = len(pending_cols)
    if evict_keys:
        stats["evicted"] = sorted(evict_keys)
    if drop_keys:
        stats["cleaned"] = sorted(drop_keys)
    return stats


def copy_dataset(db: Session, dataset_id: int, name: str | None = None, user_id: int | None = None) -> models.DataSet:
    """复制数据集：列/单套值全量深拷贝，归属同一用例（隔离语义下的复用方式）。

    命名：默认「原名-副本」；原名已带 -副本 后缀时递增编号（场景A-副本 → 场景A-副本2），
    与该用例名下已有名冲突时继续递增。
    """
    src = get_dataset(db, dataset_id)
    base = name or src.name
    if not name:
        if base.endswith("-副本") or "-副本" in base:
            stem, _, num = base.rpartition("-副本")
            try:
                n = int(num) if num else 1
            except ValueError:
                stem, n = base, 1
            base = f"{stem}-副本{n + 1}"
        else:
            base = f"{base}-副本"
        # 同用例下重名递增
        dup = (db.query(models.DataSet)
               .filter(models.DataSet.case_id == src.case_id, models.DataSet.name == base)
               .first())
        while dup:
            stem, _, num = base.rpartition("-副本")
            n = int(num) + 1 if num.isdigit() else 2
            base = f"{stem}-副本{n}"
            dup = (db.query(models.DataSet)
                   .filter(models.DataSet.case_id == src.case_id, models.DataSet.name == base)
                   .first())
        if len(base) > 100:
            raise ValueError("名称最多 100 字符")
    elif len(name) > 100:
        raise ValueError("名称最多 100 字符")
    return create_dataset(
        db, project_id=src.project_id, case_id=src.case_id,
        name=base, user_id=user_id,
        description=src.description,
        columns=deepcopy(src.columns or []),
        rows_data=[deepcopy(r.data or {}) for r in (src.rows or [])],
    )


def clone_dataset_to_case(db: Session, src: models.DataSet, target_case_id: int,
                          user_id: int | None = None) -> models.DataSet:
    """跨用例克隆数据集（列/行全量深拷贝，保持原名）。

    复制用例/拆分用例的数据资产随迁：静态值已收口进池，派生用例不同步池
    则节点引用解析不到值（执行 400）。
    """
    return create_dataset(
        db, project_id=src.project_id, case_id=target_case_id,
        name=src.name, user_id=user_id, description=src.description,
        columns=deepcopy(src.columns or []),
        rows_data=[deepcopy(r.data or {}) for r in (src.rows or [])],
    )


def merge_datasets_for_case(db: Session, sources: list, target_case_id: int,
                            project_id: int | None, name: str,
                            user_id: int | None = None) -> models.DataSet | None:
    """组合用例的池合并：按源顺序合并各绑定池（每池取首行，单套语义）。

    - 列：按键并集，顺序=首现顺序（类型冲突取首个源的列定义）
    - 值：同键同值合并；同键异值保留首个源的值（组合按序执行语义的近似），
      冲突清单记入新池 description 供用户在数据集界面调整
    - 未绑定池的源跳过；全部源无池返回 None（不建，留给保存钩子）
    """
    cols: list[dict] = []
    col_keys: set[str] = set()
    merged: dict = {}
    conflicts: list[str] = []
    for src in sources:
        for col in (src.columns or []):
            key = col.get("key")
            if key and key not in col_keys:
                col_keys.add(key)
                cols.append(dict(col))
        rows = src.rows or []
        if not rows:
            continue
        for k, v in (rows[0].data or {}).items():
            if k in merged and merged[k] != v:
                conflicts.append(f"{k}: {merged[k]!r} / {v!r}")
            else:
                merged[k] = v
    if not cols and not merged:
        return None
    desc = None
    if conflicts:
        desc = "组合合并同键异值（已保留首个源的值，可按需调整）：" + "；".join(conflicts)
    return create_dataset(db, project_id=project_id, case_id=target_case_id,
                          name=name, user_id=user_id, description=desc,
                          columns=cols, rows_data=[merged])


# ============ 覆盖合并（数据集间字段流转） ============
def _case_cfg_dicts(db: Session, case_id: int) -> list[dict]:
    """归属用例当前编排的 dict 形式 [{node_id, api_id, pre_process}]（compare/merge 配对用）。"""
    cfgs = (db.query(models.CaseNodeConfig)
            .filter(models.CaseNodeConfig.case_id == case_id).all())
    return [{"node_id": c.node_id, "api_id": c.api_id,
             "pre_process": c.pre_process or []} for c in cfgs]


def _node_param_keys(cfg, api) -> set:
    """单节点可参数化列（顶层、非 file、非空、非 ${}；动态注入 key 剔除）。

    cfg 为编排 dict（node_id/api_id/pre_process）。
    - API 字段默认值：顶层、非 file、非空、不含 ${}
    - pre_process set_field/add_field：path 顶层、value 非动态
    - 动态注入（value 含 ${}）的 key 整体剔除
    """
    keys: set = set()
    for f in getattr(api, "fields", None) or []:
        if not f.key or "." in f.key or f.field_type == "file":
            continue
        raw = f.default_value
        if raw is None or (isinstance(raw, str) and (not raw.strip() or "${" in raw)):
            continue
        keys.add(f.key)
    for act in (cfg.get("pre_process") or []):
        if act.get("type") not in ("set_field", "add_field"):
            continue
        path = act.get("path") or ""
        val = act.get("value")
        if not path or "." in path:
            continue
        if isinstance(val, str) and "${" in val:
            keys.discard(path)
            continue
        keys.add(path)
    return keys


def compare_datasets(db: Session, target_id: int, source_id: int) -> dict:
    """对比两个数据集的归属用例当前编排：按 api_id 配对相同节点，算出可覆盖列。

    可覆盖列 = 节点参数化列 ∩ 源数据集列 ∩ 目标数据集列（三方交集：
    列不在数据集里则行数据里没有值可刷，或刷了也不生效）。
    无相同节点 → common_nodes=[]（调用方据此提示"没有覆盖的必要"）。
    """
    if target_id == source_id:
        raise ValueError("源数据集与目标数据集不能相同")
    t = get_dataset(db, target_id)
    s = get_dataset(db, source_id)
    t_keys = {c["key"] for c in (t.columns or [])}
    s_keys = {c["key"] for c in (s.columns or [])}

    t_by_api: dict = {}
    for c in _case_cfg_dicts(db, t.case_id):
        if c.get("api_id"):
            t_by_api.setdefault(c["api_id"], []).append(c)
    common = []
    seen = set()
    for c in _case_cfg_dicts(db, s.case_id):
        aid = c.get("api_id")
        if not aid or aid not in t_by_api or aid in seen:
            continue
        seen.add(aid)
        api = db.get(models.ApiDefinition, aid)
        if not api:
            continue
        keys: set = set()
        for sc in [c, *t_by_api[aid]]:
            keys |= _node_param_keys(sc, api)
        columns = sorted(keys & t_keys & s_keys)
        if not columns:
            continue
        common.append({
            "api_id": aid,
            "api_name": api.name,
            "target_nodes": [x.get("node_id") for x in t_by_api[aid]],
            "source_nodes": [c.get("node_id")],
            "columns": columns,
        })
    src_rows = crud.list_rows(db, source_id)
    return {
        "source": {"id": s.id, "name": s.name, "case_id": s.case_id, "rows": len(src_rows),
                   "row_labels": [str(r.row_index) for r in src_rows]},
        "common_nodes": common,
        "columns_total": len({k for n in common for k in n["columns"]}),
    }


def merge_from_dataset(db: Session, target_id: int, source_id: int,
                       api_ids: list | None = None, source_row_index: int = 1) -> dict:
    """覆盖合并：源数据集单套值的"相同节点涉及列"刷到目标数据集。

    - api_ids 不传 = 全部相同节点；传则只刷这些节点的列（与 compare 结果对齐）
    - 源空值（None/""）跳过：与池值语义一致（空=未配置，不覆盖不置空）
    - 目标独有列自然保留；目标无数据时报错（无可作用对象）
    """
    cmp_data = compare_datasets(db, target_id, source_id)
    nodes = cmp_data["common_nodes"]
    if not nodes:
        raise ValueError("两个数据集没有相同节点，无覆盖的必要")
    if api_ids is not None:
        wanted = set(api_ids)
        unknown = wanted - {n["api_id"] for n in nodes}
        if unknown:
            raise ValueError(f"接口不在相同节点列表内: {'、'.join(str(u) for u in sorted(unknown))}")
        nodes = [n for n in nodes if n["api_id"] in wanted]
    columns = {k for n in nodes for k in n["columns"]}
    if not columns:
        raise ValueError("所选节点没有两侧数据集共有的可覆盖列")

    src_row = (db.query(models.DataSetRow)
               .filter(models.DataSetRow.dataset_id == source_id,
                       models.DataSetRow.row_index == source_row_index).first())
    if not src_row:
        raise ValueError(f"源数据集不存在第 {source_row_index} 行")
    overrides = {k: v for k, v in (src_row.data or {}).items()
                 if k in columns and v is not None and v != ""}
    if not overrides:
        raise ValueError("源行在所选节点列上均为空值，没有可覆盖内容")

    target_rows = crud.list_rows(db, target_id)
    if not target_rows:
        raise ValueError("目标数据集无数据行，覆盖合并无可作用对象")
    for r in target_rows:
        r.data = {**(r.data or {}), **overrides}
    db.commit()
    return {"rows": len(target_rows), "columns": len(overrides), "keys": sorted(overrides)}
