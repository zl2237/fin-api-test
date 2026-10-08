"""存量迁移：节点配置 params/pre_process → 数据集行（入参收敛，2026-09-30 定案）。

背景：
- 旧形态：case_node_configs.params / pre_process 存四来源入参配置；数据集行为
  平铺键值（{"bl_no": "X"}），经 __dataset__ 伪命名空间被 spec/SQL 引用。
- 新形态：数据集行 data = {"nodes": {节点ID: {params, pre_process}}}；节点配置
  只剩结构层；__dataset__ 退役（跨节点共享值改引用上游产出）。

迁移语义：
1. 每个普通用例（非 suite）：读画布内节点的 params/pre_process（ORM 模型已删列，
   经原生 SQL 读取），逐数据集生成行内配置：
   - __dataset__ 引用按各数据集旧行值内联为 constant（多数据集 = 多场景各自内联）；
     SQL {{__dataset__.key}} 占位替换为 SQL 字面量。
   - 未绑定且有待搬配置的用例：建「{用例名}-数据」默认数据集并绑定再搬
     （无旧行值，__dataset__ 引用内联空串并计警告）。
2. 搬完清空全部节点配置的 params/pre_process（含画布外孤儿行）。
3. 幂等：节点配置两列已空则跳过（重复运行无副作用）。

运行（严格按序）：
1. python scripts/migrate_params_to_dataset.py   # 本脚本（列仍在）
2. alembic upgrade head                           # drop case_node_configs 两列
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

import re  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import path_setup  # noqa: E402, F401
from app.database import SessionLocal  # noqa: E402
from app.models import DataSet, DataSetRow, TestCase  # noqa: E402

DATASET_NS = "__dataset__"
PLACEHOLDER_RE = re.compile(r"\{\{([\w.\-]+)\}\}")


def _sql_literal(v) -> str:
    """值 → SQL 字面量（数字/布尔原样；字符串加引号并转义；None→NULL；容器 JSON）"""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return str(v)
    s = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
    return "'" + s.replace("\\", "\\\\").replace("'", "''") + "'"


def _inline_obj(obj, values: dict, warns: list, where: str):
    """递归把 __dataset__ 引用内联为 constant（返回可能修改后的新结构）。

    - ref spec → constant（as_array 时值包单元素数组）
    - func arg ref __dataset__ → const arg
    - SQL 占位 {{__dataset__.k}} → SQL 字面量
    - 容器（list/无 source 的 dict）递归
    """
    if isinstance(obj, list):
        return [_inline_obj(v, values, warns, where) for v in obj]
    if isinstance(obj, dict):
        src = obj.get("source")
        if src == "ref" and obj.get("node_id") == DATASET_NS:
            key = obj.get("var_path") or ""
            if key not in values:
                warns.append(f"{where}：数据集无键 {key!r}，内联为空串")
            v = values.get(key, "")
            if obj.get("as_array"):
                v = [v]
            return {"source": "constant", "value": v}
        if src == "func":
            args = []
            for a in obj.get("args") or []:
                if isinstance(a, dict) and a.get("kind") == "ref" and a.get("node_id") == DATASET_NS:
                    key = a.get("var_path") or ""
                    if key not in values:
                        warns.append(f"{where}：函数参数 {a.get('name')} 数据集无键 {key!r}，内联为空串")
                    args.append({"name": a.get("name"), "kind": "const",
                                 "value": values.get(key, "")})
                else:
                    args.append(_inline_obj(a, values, warns, where))
            return {**obj, "args": args}
        if src == "sql":
            def _sub(m):
                full = m.group(0)
                node_id, _, rest = full[2:-2].partition(".")
                if node_id != DATASET_NS:
                    return full
                if rest not in values:
                    warns.append(f"{where}：SQL 占位数据集无键 {rest!r}，内联 NULL")
                return _sql_literal(values.get(rest))
            return {**obj, "sql": PLACEHOLDER_RE.sub(_sub, obj.get("sql") or "")}
        if src:  # constant / 普通 ref
            return obj
        return {k: _inline_obj(v, values, warns, f"{where}.{k}") for k, v in obj.items()}
    return obj


def _parse_json(v, default):
    """原生 SQL 查 MySQL JSON 列返回 str，需 json.loads；兼容 dict/list/None"""
    if v is None:
        return default
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            return default
    return v if isinstance(v, type(default)) else default


def _raw_node_params(db, case_id: int) -> dict[str, dict]:
    """原生 SQL 读节点配置旧列（ORM 模型已删列）；返回 {node_id: {params, pre_process}}"""
    rows = db.execute(text(
        "SELECT node_id, params, pre_process FROM case_node_configs WHERE case_id = :cid"
    ), {"cid": case_id}).fetchall()
    out = {}
    for node_id, params, pre in rows:
        cfg = {"params": _parse_json(params, {}),
               "pre_process": _parse_json(pre, [])}
        if not _cfg_empty(cfg):
            out[node_id] = cfg
    return out


def _cfg_empty(cfg: dict) -> bool:
    p = cfg.get("params") or {}
    return not (p.get("body") or p.get("headers")) and not (cfg.get("pre_process") or [])


def main() -> None:
    db = SessionLocal()
    stats = {"cases": 0, "datasets_written": 0, "datasets_created": 0,
             "nodes_moved": 0, "inlined_refs": 0, "warns": 0, "skipped_clean": 0}
    warns_all: list[str] = []
    try:
        cases = (db.query(TestCase)
                 .filter(TestCase.case_type != "suite")
                 .order_by(TestCase.id).all())
        for case in cases:
            dag_ids = {n.get("id") for n in (case.dag_config or {}).get("nodes", [])
                       if isinstance(n, dict) and n.get("id")}
            raw = _raw_node_params(db, case.id)
            canvas_cfg = {nid: cfg for nid, cfg in raw.items() if nid in dag_ids}
            if not canvas_cfg:
                stats["skipped_clean"] += 1
                continue
            stats["cases"] += 1

            # 该用例全部数据集（多数据集 = 多场景，各自内联旧行值）
            dss = (db.query(DataSet)
                   .filter(DataSet.case_id == case.id)
                   .order_by(DataSet.id).all())
            if not dss:
                ds = DataSet(project_id=case.project_id, case_id=case.id,
                             name=f"{case.name}-数据",
                             created_by=None, updated_by=None)
                db.add(ds)
                db.flush()
                dss = [ds]
                stats["datasets_created"] += 1
                print(f"  case#{case.id} {case.name}: 未绑定且有待搬配置 → 建默认数据集 #{ds.id}")

            for ds in dss:
                # 旧行值（平铺键值）→ 内联映射；行结构随后整体替换
                old_rows = (db.query(DataSetRow)
                            .filter(DataSetRow.dataset_id == ds.id)
                            .order_by(DataSetRow.row_index).all())
                old_values: dict = {}
                if old_rows:
                    old_values = _parse_json(old_rows[0].data, {})

                nodes_out: dict = {}
                for nid, cfg in canvas_cfg.items():
                    warns: list[str] = []
                    params = _inline_obj(cfg["params"], old_values, warns, f"case#{case.id}/{nid}/params")
                    actions = _inline_obj(cfg["pre_process"], old_values, warns, f"case#{case.id}/{nid}/pre")
                    nodes_out[nid] = {"params": params, "pre_process": actions}
                    stats["inlined_refs"] += len(warns)
                    warns_all.extend(warns)

                # 行收敛为唯一一行（nodes 形态）
                for extra in old_rows[1:]:
                    db.delete(extra)
                if old_rows:
                    old_rows[0].data = {"nodes": nodes_out}
                    old_rows[0].row_index = 1
                else:
                    db.add(DataSetRow(dataset_id=ds.id, row_index=1, data={"nodes": nodes_out}))
                stats["datasets_written"] += 1
                stats["nodes_moved"] += len(nodes_out)

            # 绑定（未绑定时绑首个/新建的数据集）
            if not case.dataset_id:
                case.dataset_id = dss[0].id

            # 清空全部节点配置旧列（含画布外孤儿行）
            db.execute(text(
                "UPDATE case_node_configs SET params = NULL, pre_process = NULL WHERE case_id = :cid"
            ), {"cid": case.id})
            db.commit()
            print(f"  case#{case.id} {case.name}: {len(canvas_cfg)} 节点配置 → "
                  f"{len(dss)} 数据集（绑定 #{case.dataset_id}）")

        print("\n===== 迁移完成 =====")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        if warns_all:
            print(f"\n警告 {len(warns_all)} 条（数据集缺键内联空串/NULL）：")
            for w in warns_all[:30]:
                print(f"  - {w}")
            if len(warns_all) > 30:
                print(f"  … 共 {len(warns_all)} 条")
    finally:
        db.close()


if __name__ == "__main__":
    main()
