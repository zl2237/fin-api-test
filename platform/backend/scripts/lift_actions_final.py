# -*- coding: utf-8 -*-
"""存量收敛终态：数据集行内全部前置动作提升为参数声明（「动作概念退场」定案）。

背景（2026-09-30 用户定案）：
- 上一轮（lift_setfield_to_params.py）只提升了「值为纯 spec」的 set_field；
  值为标量/容器字面量的 set_field（1378+275 个）与容器内嵌 spec（43 个）、
  iterate_set（19 个）被保守保留 → 数据集节点 tab 仍呈「参数表 + 动作列表」
  两模块并存。
- 本轮引擎补齐等价能力后动作概念彻底删除：
  1. constant 容器值内嵌 spec 递归解析（容器动作 → constant 容器参数）
  2. 通配路径参数 列表.*.字段 逐元素求值（iterate_set 的声明式等价；
     sync_list → ref 通配按下标配对，保住两列表行关联键同值）
  3. 全部参数解析结果注册（节点.参数路径 + 末段别名）——旧 {{节点.末段}}
     SQL 占位与跨节点末段引用无需改写即可继续工作

提升规则（运行期语义严格等价）：
- set_field/add_field：值纯 spec → 原样；标量/容器 → constant spec；
  同路径后写覆盖先写（运行期动作覆盖参数的本义）；explicit_empty → constant ""
- 空动作（无 path 或 value None/""）运行期不写不注册 → 删除
- 动作值内 ref (本节点, 末段) → 改写为当时产出该末段的参数完整路径
  （与旧「动作按序执行读注册表现值」一致，且依赖对 order_params 可见）
- iterate_set → 参数 f"{list_path}.*.{field}" = value spec；
  sync_list → f"{sync_list}.*.{field}" = ref(本节点, 通配路径)
- delete_field/exec_sql/sleep：现网应为 0 个，遇即整行回滚（安全网）
- pre_process 键从节点配置中删除（节点配置只剩 params）

每行改完跑 validate_case_configs，报错整行回滚不落库。幂等：无动作行不变即跳过。
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app import path_setup  # noqa: E402, F401
from app.database import SessionLocal  # noqa: E402
from app.models import CaseNodeConfig, DataSet, TestCase  # noqa: E402
from app.engine.validation import validate_case_configs  # noqa: E402
from sqlalchemy import text  # noqa: E402

_SPEC_SOURCES = ("constant", "func", "ref", "sql")


def _tail(path: str) -> str:
    return (path or "").split(".")[-1]


def _rewrite_self_refs(obj, nid: str, producer: dict[str, str]) -> bool:
    """动作值内 ref (本节点, 末段) → 产出参数完整路径（含容器内嵌与 func 入参）。

    与旧运行期一致：读取此刻注册表里的值（producer 按序更新，后写覆盖）。
    返回是否有改写。
    """
    changed = False
    if isinstance(obj, list):
        for it in obj:
            changed |= _rewrite_self_refs(it, nid, producer)
    elif isinstance(obj, dict):
        src = obj.get("source")
        if src == "ref" and obj.get("node_id") == nid and obj.get("var_path") in producer:
            obj["var_path"] = producer[obj["var_path"]]
            changed = True
        elif src == "func":
            for a in obj.get("args") or []:
                if isinstance(a, dict) and a.get("kind") == "ref" \
                        and a.get("node_id") == nid and a.get("var_path") in producer:
                    a["var_path"] = producer[a["var_path"]]
                    changed = True
        elif src == "constant":
            changed |= _rewrite_self_refs(obj.get("value"), nid, producer)
        else:
            for v in obj.values():
                changed |= _rewrite_self_refs(v, nid, producer)
    return changed


def process_node(nid: str, rc: dict, stats: dict) -> dict:
    """单节点动作提升；返回新节点配置（{"params": ...}，pre_process 已删）。"""
    params = rc.get("params") or {}
    body = dict(params.get("body") or {})
    headers = params.get("headers") or {}

    # 现有参数先注册（旧引擎：参数解析在前，动作在后；同名末段后写覆盖）
    producer: dict[str, str] = {}
    for p in body:
        if "*" not in p:
            producer[_tail(p)] = p

    for act in rc.get("pre_process") or []:
        at = act.get("type")
        if at in ("set_field", "add_field"):
            path = act.get("path") or ""
            if not path:
                stats["dropped"] += 1  # 前端空行占位
                continue
            if act.get("explicit_empty"):
                spec = {"source": "constant", "value": ""}
            else:
                v = act.get("value")
                if v is None or v == "":
                    stats["dropped"] += 1  # 运行期不写不注册
                    continue
                if isinstance(v, dict) and v.get("source") in ("constant", "func", "ref"):
                    spec = copy.deepcopy(v)
                else:
                    spec = {"source": "constant", "value": copy.deepcopy(v)}
            if _rewrite_self_refs(spec, nid, producer):
                stats["rewritten"] += 1
            body[path] = spec
            producer[_tail(path)] = path
            stats["lifted"] += 1
        elif at == "iterate_set":
            list_path = act.get("list_path") or act.get("path") or ""
            field = act.get("field") or ""
            wp = f"{list_path}.*.{field}"
            spec = copy.deepcopy(act.get("value"))
            if not isinstance(spec, dict):
                spec = {"source": "constant", "value": spec}
            _rewrite_self_refs(spec, nid, producer)
            body[wp] = spec
            sync_list = act.get("sync_list")
            if sync_list:
                body[f"{sync_list}.*.{field}"] = {
                    "source": "ref", "node_id": nid, "var_path": wp}
            stats["iter_lifted"] += 1
        else:
            # delete_field/exec_sql/sleep/未知：引擎已删除对应能力，人工确认
            raise ValueError(f"不支持的残留动作类型 {at!r}: {act}")

    new_params = {"body": body}
    if headers:
        new_params["headers"] = headers
    return {"params": new_params}


def main() -> None:
    db = SessionLocal()
    total = {"lifted": 0, "dropped": 0, "rewritten": 0, "iter_lifted": 0,
             "rows": 0, "skipped": 0, "rolled": 0}
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

            has_actions = any(rc.get("pre_process") for rc in row_nodes.values()
                              if isinstance(rc, dict))
            if not has_actions:
                # 幂等：无动作行也要删干净残留的空 pre_process 键
                cleaned = {nid: ({"params": rc.get("params") or {}}
                                 if isinstance(rc, dict) else rc)
                           for nid, rc in row_nodes.items()}
                if json.dumps(cleaned, ensure_ascii=False, sort_keys=True) == \
                        json.dumps(row_nodes, ensure_ascii=False, sort_keys=True):
                    total["skipped"] += 1
                    continue
                row_nodes = cleaned
            else:
                new_nodes = {}
                st = {"lifted": 0, "dropped": 0, "rewritten": 0, "iter_lifted": 0}
                try:
                    for nid, rc in row_nodes.items():
                        new_nodes[nid] = process_node(nid, rc, st) \
                            if isinstance(rc, dict) and rc.get("pre_process") \
                            else {"params": rc.get("params") or {}}
                except ValueError as e:
                    print(f"  [回滚] dataset#{did} {ds.name}: {e}")
                    total["rolled"] += 1
                    continue
                row_nodes = new_nodes
                for k in ("lifted", "dropped", "rewritten", "iter_lifted"):
                    total[k] += st[k]

            # 校验：行内 params × 结构层 extract/assertions 全量载荷
            struct = {c.node_id: {"post_extract": c.post_extract or [],
                                  "assertions": c.assertions or []}
                      for c in db.query(CaseNodeConfig)
                      .filter(CaseNodeConfig.case_id == case_id).all()}
            dag_ids = [n["id"] for n in (case.dag_config or {}).get("nodes", [])
                       if isinstance(n, dict) and n.get("id")]
            payload = [{"node_id": nid,
                        "params": (row_nodes.get(nid) or {}).get("params") or {},
                        "post_extract": (struct.get(nid) or {}).get("post_extract") or [],
                        "assertions": (struct.get(nid) or {}).get("assertions") or []}
                       for nid in dag_ids]
            errs = validate_case_configs(case.dag_config, payload)
            if errs:
                print(f"  [回滚] dataset#{did} {ds.name}: 校验 {len(errs)} 条 → {errs[:3]}")
                total["rolled"] += 1
                continue
            db.execute(text("UPDATE data_set_rows SET data = :d WHERE id = :rid"),
                       {"d": json.dumps({"nodes": row_nodes}, ensure_ascii=False), "rid": rid})
            db.commit()
            total["rows"] += 1
            print(f"  dataset#{did} {ds.name}: 已收敛（无动作残留）")
        print("\n===== 完成 =====")
        for k, v in total.items():
            print(f"  {k}: {v}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
