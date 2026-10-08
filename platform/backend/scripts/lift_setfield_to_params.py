# -*- coding: utf-8 -*-
"""存量收敛：前置 set_field（值为纯 spec）提升合并进数据集行 params.body。

背景（2026-09-30 用户定案「一遍 + 声明来源」）：
- 老引擎是「模板静态值 + 前置 set_field 运行期覆盖」两层；四来源迁移时把模板值
  转成了 params.body 来源声明，但历史 set_field 动作被原样保留 → 同一批字段在
  「body 参数表」与「前置动作表」重复配置/渲染两遍。
- 值为纯 spec（constant/func/ref）的 set_field 在语义上就是该字段的参数来源声明，
  应提升为 params.body[path]（同路径整体替换——运行期 set_field 本就覆盖参数值）。

提升规则（保守闭包，运行期语义严格等价）：
1. 硬阻塞集 blocked：下列引用到的 (节点, 变量) 一律不提升（其运行期注册值必须保留）：
   - 全行任意 SQL {{节点.变量}} 占位（含结构层提取/断言 SQL）
   - 结构层（case_node_configs）断言期望值 ref spec
   - 值为容器（内嵌 spec）/ iterate_set 值引用的本节点变量（这些动作保留，
     其引用的变量须继续注册；容器内对「已提升」变量的引用会改写为原上游 spec）
2. 顺序扫描 + 不动点：动作可提升 ⇔ set_field 且值为纯 spec 且溯源终态干净
   （ref 本节点变量须命中已提升产出，链至 constant/func/ref上游）；任一「保留」
   动作产出同名变量 → 该变量阻塞（后写覆盖语义下，引用须指向保留动作的值）。
3. 提升后全行改写：ref (节点, 已提升变量) → 原 spec 拷贝（params/pre 各处、
   func arg、保留动作容器内嵌）。
4. 空动作（value None/""）运行期本就不写不注册 → 直接删除。
5. 每个数据集行改完跑 validate_case_configs，报错则整行回滚不落库。

幂等：可提升动作已并入 params 后再跑无新动作可提升，重跑无副作用。
"""
import copy
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app import path_setup  # noqa: E402, F401
from app.database import SessionLocal  # noqa: E402
from app.models import CaseNodeConfig, DataSet, TestCase  # noqa: E402
from app.engine.validation import validate_case_configs  # noqa: E402
from app.engine.variables import extract_refs  # noqa: E402
from sqlalchemy import text  # noqa: E402

PLACEHOLDER_RE = re.compile(r"\{\{([\w.\-]+)\}\}")


def _is_pure_spec(v) -> bool:
    return isinstance(v, dict) and v.get("source") in ("constant", "func", "ref")


def _iter_ref_specs(obj):
    """递归产出容器/结构中的全部 ref spec dict（含 func args 与容器内嵌）。"""
    if isinstance(obj, list):
        for it in obj:
            yield from _iter_ref_specs(it)
    elif isinstance(obj, dict):
        if obj.get("source") == "ref":
            yield obj
        elif obj.get("source") == "func":
            for a in obj.get("args") or []:
                if isinstance(a, dict) and a.get("kind") == "ref":
                    yield a
        elif not obj.get("source"):
            for v in obj.values():
                yield from _iter_ref_specs(v)


def _iter_sql_texts(obj):
    """递归产出全部含 {{}} 占位的 SQL 文本字段（规则：键名为 sql 的字符串）。"""
    if isinstance(obj, list):
        for it in obj:
            yield from _iter_sql_texts(it)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k == "sql" and isinstance(v, str):
                yield v
            elif isinstance(v, (dict, list)):
                yield from _iter_sql_texts(v)


def _last(path: str) -> str:
    return (path or "").split(".")[-1]


def _sub_spec(src: dict, consumer_as_array: bool | None) -> dict:
    """引用替换产物：深拷贝源 spec，as_array 以消费方为准（原运行期只看消费方 spec 的开关）"""
    out = copy.deepcopy(src)
    if consumer_as_array:
        out["as_array"] = True
    else:
        out.pop("as_array", None)
    return out


def _rewrite_func_args(spec: dict, node_id: str, lifted: dict) -> bool:
    """func spec 的 args 中 kind=ref 指向 (node_id, x∈lifted) → 改指原上游；
    原 spec 为 constant/func 时降级 const（值取 constant；func 结果无法在 arg 表达，
    blocked 阶段应已罕见）。返回是否有改写。"""
    changed = False
    for a in spec.get("args") or []:
        if isinstance(a, dict) and a.get("kind") == "ref" \
                and a.get("node_id") == node_id and a.get("var_path") in lifted:
            src = lifted[a["var_path"]]
            if src.get("source") == "ref":
                a["node_id"], a["var_path"] = src.get("node_id"), src.get("var_path")
            else:
                a.clear()
                a.update({"kind": "const", "name": a.get("name"),
                          "value": src.get("value") if src.get("source") == "constant" else None})
            changed = True
    return changed


def _rewrite_refs(obj, node_id: str, lifted: dict, stats: dict) -> None:
    """递归改写容器/动作值中的 ref (node_id, x∈lifted) → 终态 spec（原地修改）。"""
    if isinstance(obj, list):
        for i, it in enumerate(obj):
            if _is_pure_spec(it) and it.get("source") == "ref" \
                    and it.get("node_id") == node_id and it.get("var_path") in lifted:
                obj[i] = _sub_spec(lifted[it["var_path"]], it.get("as_array"))
                stats["rewritten"] += 1
            elif isinstance(it, dict) and it.get("source") == "func":
                if _rewrite_func_args(it, node_id, lifted):
                    stats["rewritten"] += 1
            else:
                _rewrite_refs(it, node_id, lifted, stats)
    elif isinstance(obj, dict):
        if obj.get("source") == "func":
            if _rewrite_func_args(obj, node_id, lifted):
                stats["rewritten"] += 1
            return
        for k, v in list(obj.items()):
            if _is_pure_spec(v) and v.get("source") == "ref" \
                    and v.get("node_id") == node_id and v.get("var_path") in lifted:
                obj[k] = _sub_spec(lifted[v["var_path"]], v.get("as_array"))
                stats["rewritten"] += 1
            else:
                _rewrite_refs(v, node_id, lifted, stats)


def process_row(case: TestCase, struct: dict, row_nodes: dict) -> tuple[dict, dict]:
    """提升一个数据集行；返回 (新 nodes, 统计)。不变式：报错时调用方不落库。"""
    stats = {"lifted": 0, "dropped": 0, "rewritten": 0, "kept": 0}

    # ---- 1. 硬阻塞集（节点, 变量名）----
    blocked: set[tuple[str, str]] = set()
    for nid, rc in row_nodes.items():
        for sqlt in _iter_sql_texts({"params": rc.get("params"), "pre": rc.get("pre_process")}):
            for n, vp in extract_refs(sqlt):
                if n in row_nodes:
                    blocked.add((n, vp.split(".")[0]))
    for nid, c in struct.items():
        for sqlt in _iter_sql_texts({"e": c.get("post_extract"), "a": c.get("assertions")}):
            for n, vp in extract_refs(sqlt):
                if n in row_nodes:
                    blocked.add((n, vp.split(".")[0]))
        for r in _iter_ref_specs({"a": c.get("assertions")}):
            n, vp = r.get("node_id"), (r.get("var_path") or "").split(".")[0]
            if n in row_nodes:
                blocked.add((n, vp))

    # ---- 2. 逐节点：不动点提升决策 ----
    lifted_map: dict[str, dict[str, dict]] = {}  # nid -> {变量名: 原 spec}
    for nid, rc in row_nodes.items():
        actions = [a for a in (rc.get("pre_process") or []) if isinstance(a, dict)]
        body = dict((rc.get("params") or {}).get("body") or {})
        hard = {v for (n, v) in blocked if n == nid}

        blocked_now: set[str] = set()
        while True:
            produced: dict[str, dict | None] = {}   # 变量 -> 原 spec（None=保留动作）
            decide: list[tuple[dict, str, dict | None]] = []  # (动作, 变量, 提升spec|None)
            for act in actions:
                at = act.get("type")
                path = act.get("path") or ""
                var = _last(path)
                spec = None
                if at in ("set_field", "add_field") and path and act.get("explicit_empty"):
                    spec = {"source": "constant", "value": ""}
                elif at in ("set_field", "add_field") and path and _is_pure_spec(act.get("value")):
                    # v2 前置处理器中 set/add 行为完全一致（set_nested_value + 注册）→ 均可提升
                    spec = act["value"]
                    # 溯源：ref 本节点变量须命中已提升产出
                    hops = 0
                    while spec and spec.get("source") == "ref" and spec.get("node_id") == nid:
                        key = spec.get("var_path")
                        if key not in produced or produced[key] is None:
                            spec = None
                            break
                        spec = produced[key]
                        hops += 1
                        if hops > 20:
                            spec = None
                            break
                if spec is not None and var not in blocked_now and var not in hard:
                    decide.append((act, var, spec))
                    produced[var] = spec
                else:
                    decide.append((act, var, None))
                    produced[var] = None
                    if var and var not in blocked_now:
                        blocked_now.add(var)  # 保留动作产出 → 同名变量不可提升
            # 不动点检查：blocked_now 变化会改变决策 → 重算
            stable = True
            for act, var, spec in decide:
                if spec is not None and var in blocked_now:
                    stable = False
                    break
            if stable:
                break

        # ---- 应用 ----
        lifted: dict[str, dict] = {}
        new_actions: list[dict] = []
        for act, var, spec in decide:
            if spec is not None and var not in blocked_now:
                body[act.get("path") or ""] = copy.deepcopy(spec)
                lifted[var] = spec
                stats["lifted"] += 1
            elif act.get("type") in ("set_field", "add_field") and not act.get("explicit_empty") \
                    and (not (act.get("path") or "").strip() or act.get("value") in (None, "")):
                # 空动作：运行期不写不注册（无 path 或空值）→ 直接删
                stats["dropped"] += 1
            else:
                new_actions.append(act)
                stats["kept"] += 1

        if lifted:
            lifted_map[nid] = lifted
            new_params = {"body": body}
            headers = (rc.get("params") or {}).get("headers") or {}
            if headers:
                new_params["headers"] = headers
            rc["params"] = new_params
            rc["pre_process"] = new_actions

    # ---- 3. lifted 集解析到终态：A 提升值引用 B 已提升值 → 递归溯源到 constant/func/ref上游 ----
    def _terminal(spec: dict) -> dict:
        if spec.get("source") == "ref":
            lm2 = lifted_map.get(spec.get("node_id")) or {}
            vp = spec.get("var_path")
            if vp in lm2:
                return copy.deepcopy(lm2[vp])
            return spec
        return spec

    for _ in range(10):  # 链式收口（跨节点提升链按 DAG 序，有限步收敛）
        dirty = False
        for nid, lifted in lifted_map.items():
            for var, spec in list(lifted.items()):
                new = copy.deepcopy(spec)
                touched = False
                if new.get("source") == "ref":
                    lm2 = lifted_map.get(new.get("node_id")) or {}
                    if new.get("var_path") in lm2:
                        new = copy.deepcopy(lm2[new["var_path"]])
                        new.pop("as_array", None)  # 引用读值不包数组
                        touched = True
                elif new.get("source") == "func":
                    for a in new.get("args") or []:
                        if isinstance(a, dict) and a.get("kind") == "ref":
                            lm2 = lifted_map.get(a.get("node_id")) or {}
                            if a.get("var_path") in lm2:
                                src = _terminal(lm2[a["var_path"]])
                                if src.get("source") == "ref":
                                    a["node_id"], a["var_path"] = src.get("node_id"), src.get("var_path")
                                else:
                                    a.clear()
                                    a.update({"kind": "const", "name": a.get("name"),
                                              "value": src.get("value") if src.get("source") == "constant" else None})
                                touched = True
                if touched:
                    lifted[var] = new
                    dirty = True
        if not dirty:
            break

    # ---- 4. 全行改写：所有节点 params + pre_process 中 ref (节点, 已提升变量) → 终态 spec ----
    for nid, lifted in lifted_map.items():
        for rc in row_nodes.values():
            params = rc.get("params") or {}
            for scope in ("body", "headers"):
                for path, spec in list((params.get(scope) or {}).items()):
                    if not isinstance(spec, dict):
                        continue
                    if spec.get("source") == "ref" and spec.get("node_id") == nid \
                            and spec.get("var_path") in lifted:
                        params[scope][path] = _sub_spec(lifted[spec["var_path"]], spec.get("as_array"))
                        stats["rewritten"] += 1
                    elif spec.get("source") == "func":
                        if _rewrite_func_args(spec, nid, lifted):
                            stats["rewritten"] += 1
            _rewrite_refs(rc.get("pre_process"), nid, lifted, stats)
    return row_nodes, stats


def main() -> None:
    db = SessionLocal()
    total = {"lifted": 0, "dropped": 0, "rewritten": 0, "kept": 0, "rows": 0, "rolled": 0}
    try:
        rows = db.execute(text(
            "SELECT r.id AS rid, d.id AS did, d.case_id FROM data_set_rows r "
            "JOIN data_sets d ON d.id = r.dataset_id ORDER BY d.id"
        )).fetchall()
        for rid, did, case_id in rows:
            db.rollback()
            ds = db.get(DataSet, did)
            case = db.get(TestCase, case_id)
            if not ds or not case or case.case_type == "suite":
                continue
            raw = db.execute(text(
                "SELECT data FROM data_set_rows WHERE id = :rid"
            ), {"rid": rid}).scalar()
            try:
                data = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                data = {}
            row_nodes = data.get("nodes") or {}
            if not row_nodes:
                continue
            struct = {c.node_id: {"post_extract": c.post_extract or [],
                                  "assertions": c.assertions or []}
                      for c in db.query(CaseNodeConfig)
                      .filter(CaseNodeConfig.case_id == case_id).all()}
            before = json.dumps(row_nodes, ensure_ascii=False, sort_keys=True)
            new_nodes, st = process_row(case, struct, copy.deepcopy(row_nodes))
            if json.dumps(new_nodes, ensure_ascii=False, sort_keys=True) == before:
                continue
            # 校验：行内 params/pre × 结构层 extract/assertions 全量载荷
            dag_ids = [n["id"] for n in (case.dag_config or {}).get("nodes", [])
                       if isinstance(n, dict) and n.get("id")]
            payload = []
            for nid in dag_ids:
                rc = new_nodes.get(nid) or {}
                c = struct.get(nid) or {}
                payload.append({"node_id": nid,
                                "params": rc.get("params") or {},
                                "pre_process": rc.get("pre_process") or [],
                                "post_extract": c.get("post_extract") or [],
                                "assertions": c.get("assertions") or []})
            errs = validate_case_configs(case.dag_config, payload)
            if errs:
                print(f"  [回滚] dataset#{did} {ds.name}: 校验 {len(errs)} 条 → {errs[:3]}")
                total["rolled"] += 1
                continue
            db.execute(text("UPDATE data_set_rows SET data = :d WHERE id = :rid"),
                       {"d": json.dumps({"nodes": new_nodes}, ensure_ascii=False), "rid": rid})
            db.commit()
            total["rows"] += 1
            for k in ("lifted", "dropped", "rewritten", "kept"):
                total[k] += st[k]
            print(f"  dataset#{did} {ds.name}: 提升 {st['lifted']} / 删空 {st['dropped']} / "
                  f"改写 {st['rewritten']} / 保留 {st['kept']}")
        print("\n===== 完成 =====")
        for k, v in total.items():
            print(f"  {k}: {v}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
