# -*- coding: utf-8 -*-
"""存量迁移：旧变量池/`${}` 格式 → 四来源参数模型（2026-09-30 定案）。

迁移内容（幂等，可重复执行；--dry-run 仅出报告不改库）：
1. `${xxx}` 引用 → 结构化：
   - pre_process set_field/add_field/iterate_set 值：ref/func spec
   - post_extract / assertion / exec_sql SQL：`${xxx}` → `{{节点.xxx}}`
   - assertion expected：ref/func spec
   消歧规则 = 运行时旧语义等价：拓扑序中该引用节点之前**最近产出**该变量的节点；
   无节点产出 → 数据集行数据键 → `__dataset__`；仍无 → 保留原样并记入报告
   （保存校验/运行时会显性拦截，人工处理）。`context.xxx` 老写法先归一化。
2. 池按名自动注入 → 显式 params：
   - 接口骨架字段/模板顶层键 与 行数据键（含点路径叶键）同名命中且无手动覆盖
     → params.body[key] = {"source":"ref","node_id":"__dataset__","var_path":key}
   - 三态空值动作（value 空）：同上迁移为 params 引用后删除空动作；
     行数据无命中 → 直接删除（新模型无三态语义）
3. 手动覆盖字面量动作保留原样（v2 仍生效）；explicit_empty 保留。

用法：
    python scripts/migrate_to_param_model.py --dry-run   # 报告
    python scripts/migrate_to_param_model.py             # 执行
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app import models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.engine.topo import topo_order  # noqa: E402
from app.engine.functions import FUNCTIONS  # noqa: E402

VAR_RE = re.compile(r"\$\{([^}]+)\}")
# 单变量数组包裹老写法：'[${x}]' / '[ ${context.x} ]'
ARRAY_WRAP_RE = re.compile(r"^\[\s*\$\{([^}]+)\}\s*\]$")

KNOWN_PREFIXES = ("context.", "extracted.", "env.", "global.")


def normalize_expr(expr: str) -> str:
    """`context.x` / `extracted.x` 等老前缀归一化为裸名。"""
    for p in KNOWN_PREFIXES:
        if expr.startswith(p):
            return expr[len(p):]
    return expr


class CaseMigrator:
    def __init__(self, db, dry_run: bool):
        self.db = db
        self.dry_run = dry_run
        self.stats = Counter()
        self.issues: list[str] = []
        self.suite_vars: set[str] = set()  # 全部套件 shared_vars 并集（跨链共享变量）

    def load_suite_vars(self) -> None:
        """预载套件共享变量白名单：unresolved 引用命中 → __suite__ 伪节点引用
        （运行期由套件 executor 注入；单跑时显性失败符合新语义）。"""
        for suite in self.db.query(models.TestCase).filter(
                models.TestCase.case_type == "suite").all():
            for v in (getattr(suite, "shared_vars", None) or []):
                if isinstance(v, str) and v:
                    self.suite_vars.add(v)

    # ---------- 产出集 ----------
    @staticmethod
    def node_outputs(cfg) -> set[str]:
        out = set()
        for pe in (cfg.post_extract or []):
            if isinstance(pe, dict) and pe.get("name"):
                out.add(pe["name"])
        for act in (cfg.pre_process or []):
            if isinstance(act, dict) and act.get("type") in ("set_field", "add_field"):
                p = act.get("path") or ""
                if p and act.get("value") not in (None, ""):
                    out.add(p.split(".")[-1])
        return out

    # ---------- 消歧 ----------
    def resolve_var(self, var: str, produced: dict, row_keys: set, case_id, node_id, where: str) -> tuple[str, str]:
        """返回 (node_id, var_path)；无解返回 ("", var) 并记 issue。produced={var: 最近节点}。"""
        if var in produced:
            return produced[var], var
        if var.split(".")[0] in row_keys:
            return "__dataset__", var
        if var.split(".")[0] in self.suite_vars:
            return "__suite__", var
        self.stats["unresolved"] += 1
        self.issues.append(f"case {case_id} 节点 {node_id} {where}：引用 {var!r} 无产出节点且不在数据集键中（保留原样，待人工处理）")
        return "", var

    # ---------- 值转换 ----------
    def convert_value_spec(self, raw, lookup, row_keys, case_id, node_id, where):
        """set_field/iterate_set/expected 值：整串单表达式/数组包裹 → spec；纯字面量 → 原样。

        list/dict 容器（如 set_field 整组数组值）递归转换内嵌字符串引用为
        内嵌 spec——容器内常量元素原样保留，运行时 preprocessor 递归解析。
        lookup：消歧域（produced 截至本节点前 ∪ 本节点动作产出——运行时提取/断言
        在 set_field 之后执行，同节点引用合法）。
        """
        if isinstance(raw, list):
            out, changed = [], False
            for i, item in enumerate(raw):
                v, ch = self.convert_value_spec(item, lookup, row_keys, case_id, node_id,
                                                f"{where}[{i}]")
                out.append(v)
                changed = changed or ch
            return out, changed
        if isinstance(raw, dict):
            out, changed = {}, False
            for k, v in raw.items():
                nv, ch = self.convert_value_spec(v, lookup, row_keys, case_id, node_id,
                                                 f"{where}.{k}")
                out[k] = nv
                changed = changed or ch
            return out, changed
        if not isinstance(raw, str) or "${" not in raw:
            return raw, False
        m = ARRAY_WRAP_RE.match(raw.strip())
        if m:  # '[${x}]' → as_array 引用/函数
            expr = normalize_expr(m.group(1).strip())
            if "(" in expr and expr.endswith(")") and expr[:expr.index("(")] in FUNCTIONS:
                self.stats["array_wrap_func"] += 1
                return {"source": "func", "func": expr[:expr.index("(")], "args": [],
                        "as_array": True}, True
            nid, vp = self.resolve_var(expr, lookup, row_keys, case_id, node_id, where)
            if nid:
                self.stats["array_wrap_ref"] += 1
                return {"source": "ref", "node_id": nid, "var_path": vp, "as_array": True}, True
            return raw, False
        m = VAR_RE.fullmatch(raw.strip())
        if m:
            expr = normalize_expr(m.group(1).strip())
            # 函数调用
            if "(" in expr and expr.endswith(")"):
                fname = expr[:expr.index("(")]
                if fname in FUNCTIONS:
                    return {"source": "func", "func": fname, "args": []}, True
                self.stats["unknown_func"] += 1
                self.issues.append(f"case {case_id} 节点 {node_id} {where}：未知函数 {fname}（保留原样）")
                return raw, False
            nid, vp = self.resolve_var(expr, lookup, row_keys, case_id, node_id, where)
            if not nid:
                return raw, False
            self.stats["value_ref"] += 1
            return {"source": "ref", "node_id": nid, "var_path": vp}, True
        # JSON 字符串模板（如多行数组 '[{"k": "${x}"}]'）→ 结构化 + 内嵌 spec
        if raw.strip().startswith(("[", "{")):
            try:
                parsed = json.loads(raw)
            except ValueError:
                parsed = None
            if isinstance(parsed, (list, dict)):
                v, ch = self.convert_value_spec(parsed, lookup, row_keys, case_id, node_id, where)
                if ch:
                    self.stats["json_struct"] += 1
                    return v, True
        # 混合字符串（表达式+文本）→ 无新模型等价物，报告人工处理
        self.stats["mixed_expr"] += 1
        self.issues.append(f"case {case_id} 节点 {node_id} {where}：混合表达式 {raw!r} 无新模型等价（保留原样，待人工拆分）")
        return raw, False

    def convert_sql(self, sql, lookup, row_keys, case_id, node_id, where):
        """SQL：`${xxx}` → `{{节点.xxx}}`（含函数调用的 ${fn()} → 报告，新模型 SQL 内禁函数）。"""
        if not isinstance(sql, str) or "${" not in sql:
            return sql, False

        def repl(m):
            expr = normalize_expr(m.group(1).strip())
            if "(" in expr and expr.endswith(")"):
                fname = expr[:expr.index("(")]
                self.stats["sql_func"] += 1
                self.issues.append(f"case {case_id} 节点 {node_id} {where}：SQL 内函数 {fname}（新模型 SQL 禁函数，保留原样）")
                return m.group(0)
            nid, vp = self.resolve_var(expr, lookup, row_keys, case_id, node_id, where)
            if not nid:
                return m.group(0)
            self.stats["sql_ref"] += 1
            return "{{" + nid + "." + vp + "}}"

        out = VAR_RE.sub(repl, sql)
        return out, out != sql

    # ---------- 池按名注入 → params ----------
    @staticmethod
    def _api_keys(db, cfg) -> list[str]:
        if not cfg.api_id:
            return []
        api = db.get(models.ApiDefinition, cfg.api_id)
        if not api:
            return []
        keys = [f.key for f in (api.fields or []) if f.key]
        tmpl = api.request_template
        if not (api.fields and api.fields):
            if isinstance(tmpl, dict):
                keys.extend(tmpl.keys())
        return list(dict.fromkeys(keys))

    def migrate_case(self, case) -> None:
        dag = case.dag_config or {}
        try:
            order, _ = topo_order(dag)
        except Exception:
            order = [n.get("id") for n in dag.get("nodes", []) if isinstance(n, dict)]
        cfgs = {c.node_id: c for c in
                self.db.query(models.CaseNodeConfig)
                .filter(models.CaseNodeConfig.case_id == case.id).all()}
        if not cfgs:
            return
        # 数据集行数据键
        row_keys: set[str] = set()
        if case.dataset_id:
            row = (self.db.query(models.DataSetRow)
                   .filter(models.DataSetRow.dataset_id == case.dataset_id)
                   .order_by(models.DataSetRow.row_index).first())
            if row and isinstance(row.data, dict):
                row_keys = set(row.data.keys())

        produced: dict[str, str] = {}  # var -> 最近产出节点（拓扑推进）
        for node_id in order:
            cfg = cfgs.get(node_id)
            if cfg is None:
                continue
            residue = self._has_dollar(cfg)
            self_ref = self._has_self_ref(cfg, node_id)
            if cfg.params and not residue and not self_ref:  # 已迁移（幂等）
                produced.update({v: node_id for v in self.node_outputs(cfg)})
                continue
            if cfg.params:  # 补迁模式：params 已迁移但残留 ${}（数组内嵌引用）或
                # 存在误迁移的自引用动作值——只做 ${} 转换与自引用还原；
                # 不重建 params（防三态空值动作已删除导致池注入键丢失）
                self.convert_dollar_fields(cfg, produced, row_keys, case.id, node_id)
                self.stats["nodes_remigrated"] += 1
                produced.update({v: node_id for v in self.node_outputs(cfg)})
                continue
            # 消歧域：截至本节点前的产出（动作级时序消歧在 convert_dollar_fields 内）
            params_body: dict = {}
            pre = [dict(a) if isinstance(a, dict) else a for a in (cfg.pre_process or [])]

            # 手动覆盖路径（非空值/显式空值）
            manual = {a.get("path") for a in pre
                      if isinstance(a, dict) and a.get("type") in ("set_field", "add_field")
                      and a.get("path") and (a.get("value") not in (None, "") or a.get("explicit_empty"))}

            # 2a. 骨架字段 × 行数据键（整键 + 叶键前缀）
            for key in self._api_keys(self.db, cfg):
                if key in manual:
                    continue
                if key in row_keys:
                    params_body[key] = {"source": "ref", "node_id": "__dataset__", "var_path": key}
                    self.stats["pool_param"] += 1
                else:  # 叶键：行数据有 key.xxx 拆叶键
                    for hk in row_keys:
                        if hk.startswith(key + "."):
                            params_body[hk] = {"source": "ref", "node_id": "__dataset__", "var_path": hk}
                            self.stats["pool_param_leaf"] += 1

            # 2b. 三态空值动作 → params 引用 / 删除
            new_pre = []
            for a in pre:
                if (isinstance(a, dict) and a.get("type") in ("set_field", "add_field")
                        and a.get("path") and a.get("value") in (None, "")
                        and not a.get("explicit_empty")):
                    p = a["path"]
                    if p in row_keys:
                        params_body[p] = {"source": "ref", "node_id": "__dataset__", "var_path": p}
                        self.stats["empty_to_ref"] += 1
                    else:
                        leaf_hit = False
                        for hk in row_keys:
                            if hk.startswith(p + "."):
                                params_body[hk] = {"source": "ref", "node_id": "__dataset__", "var_path": hk}
                                leaf_hit = True
                        if not leaf_hit:
                            self.stats["empty_dropped"] += 1
                    continue  # 删除空动作
                new_pre.append(a)
            cfg.pre_process = new_pre

            # 3a/3b/3c. ${} → spec / {{节点.变量}}（含写回三个 JSON 列）
            self.convert_dollar_fields(cfg, produced, row_keys, case.id, node_id)

            # 写回 params（JSON 列整量赋值触发 dirty）
            cfg.params = {"body": params_body} if params_body else {}
            self.stats["nodes_migrated"] += 1
            produced.update({v: node_id for v in self.node_outputs(cfg)})

        if not self.dry_run:
            self.db.commit()
        self.stats["cases_migrated"] += 1

    # ---------- ${} 转换（完整/补迁两模式共用） ----------
    @staticmethod
    def _has_dollar(cfg) -> bool:
        for field in ("pre_process", "post_extract", "assertions"):
            val = getattr(cfg, field, None)
            if val and "${" in (val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)):
                return True
        return False

    @staticmethod
    def _has_self_ref(cfg, node_id: str) -> bool:
        """动作值中存在指向本节点的 ref spec（误迁移产物：旧值在写入前解析，
        引用自身产出运行时必 ReferenceError）。断言 expected 引用本节点提取产出
        合法，不在检测范围。"""
        for a in (cfg.pre_process or []):
            if not isinstance(a, dict) or a.get("type") not in (
                    "set_field", "add_field", "iterate_set", "exec_sql"):
                continue
            obj = a.get("value") if a.get("type") != "exec_sql" else None
            if obj is None:
                continue

            def _scan(o):
                if isinstance(o, dict):
                    if o.get("source") == "ref" and o.get("node_id") == node_id:
                        return True
                    return any(_scan(v) for v in o.values())
                if isinstance(o, list):
                    return any(_scan(i) for i in o)
                return False

            if _scan(obj):
                return True
        return False

    @staticmethod
    def _restore_self_refs(obj, node_id: str):
        """自引用 ref spec → 还原 ${var_path} 字符串（随后按动作级时序重新消歧）。"""
        if isinstance(obj, dict) and obj.get("source") == "ref" and obj.get("node_id") == node_id:
            return "${" + str(obj.get("var_path")) + "}", True
        if isinstance(obj, list):
            out, ch = [], False
            for item in obj:
                v, c = CaseMigrator._restore_self_refs(item, node_id)
                out.append(v)
                ch = ch or c
            return out, ch
        if isinstance(obj, dict):
            out, ch = {}, False
            for k, v in obj.items():
                nv, c = CaseMigrator._restore_self_refs(v, node_id)
                out[k] = nv
                ch = ch or c
            return out, ch
        return obj, False

    def convert_dollar_fields(self, cfg, produced, row_keys, case_id, node_id) -> None:
        """原地转换节点内全部 ${}：动作值 spec 化 / SQL {{}} 化 / 期望值 spec 化。

        消歧域按运行时时序精确等价（旧引擎 preprocessor/extractor 顺序执行）：
        - 动作值/exec_sql：上游产出 ∪ 本节点**前序**动作产出（值在写入前解析，
          引用自身/后续动作产出 = 自引用 bug，禁止）
        - 提取：上游产出 ∪ 本节点动作产出 ∪ 本节点**前序**提取规则产出
        - 断言：上游产出 ∪ 本节点动作产出 ∪ 本节点全部提取产出
        """
        pre = [dict(a) if isinstance(a, dict) else a for a in (cfg.pre_process or [])]
        # 先还原误迁移的自引用动作值 → ${var}，再按动作级时序重新消歧
        for a in pre:
            if isinstance(a, dict) and a.get("type") in ("set_field", "add_field", "iterate_set"):
                a["value"], _ = self._restore_self_refs(a.get("value"), node_id)
        final_local: dict[str, str] = {}
        running_local: dict[str, str] = {}
        for a in pre:
            if not isinstance(a, dict):
                continue
            at = a.get("type")
            act_lookup = {**produced, **running_local}
            if at in ("set_field", "add_field", "iterate_set"):
                v, ch = self.convert_value_spec(a.get("value"), act_lookup, row_keys,
                                                case_id, node_id,
                                                f"动作 {at}({a.get('path') or a.get('field')})")
                if ch:
                    a["value"] = v
            elif at == "exec_sql":
                s, ch = self.convert_sql(a.get("sql"), act_lookup, row_keys, case_id, node_id, "exec_sql")
                if ch:
                    a["sql"] = s
            if at in ("set_field", "add_field") and a.get("path") \
                    and a.get("value") not in (None, ""):
                leaf = a["path"].split(".")[-1]
                running_local[leaf] = node_id
                final_local[leaf] = node_id

        pe = [dict(r) if isinstance(r, dict) else r for r in (cfg.post_extract or [])]
        ext_running: dict[str, str] = {}  # 前序提取规则产出（提取按序执行、实时注册）
        for r in pe:
            if isinstance(r, dict):
                s, ch = self.convert_sql(r.get("sql"),
                                         {**produced, **final_local, **ext_running},
                                         row_keys, case_id, node_id,
                                         f"提取 {r.get('name')}")
                if ch:
                    r["sql"] = s
                if r.get("name"):
                    ext_running[r["name"]] = node_id

        # 断言在全部提取之后执行：全集消歧（上游 ∪ 本节点动作产出 ∪ 本节点提取产出）
        post_lookup = {**produced, **final_local, **ext_running}
        asn = [dict(r) if isinstance(r, dict) else r for r in (cfg.assertions or [])]
        for r in asn:
            if not isinstance(r, dict):
                continue
            s, ch = self.convert_sql(r.get("sql"), post_lookup, row_keys, case_id, node_id,
                                     f"断言 {r.get('type')}")
            if ch:
                r["sql"] = s
            v, ch = self.convert_value_spec(r.get("expected"), post_lookup, row_keys,
                                            case_id, node_id, f"断言 {r.get('type')} 期望值")
            if ch:
                r["expected"] = v

        cfg.pre_process = pre
        cfg.post_extract = pe
        cfg.assertions = asn

    def run(self) -> None:
        self.load_suite_vars()
        cases = self.db.query(models.TestCase).order_by(models.TestCase.id).all()
        for case in cases:
            if not case.dag_config:
                continue
            self.migrate_case(case)
        print("\n== 迁移统计 ==")
        for k, v in sorted(self.stats.items()):
            print(f"  {k}: {v}")
        if self.issues:
            print(f"\n== 待人工处理 {len(self.issues)} 项 ==")
            for i in self.issues[:60]:
                print(f"  {i}")
            if len(self.issues) > 60:
                print(f"  ……（共 {len(self.issues)} 项）")
        else:
            print("\n无待人工项")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="仅出报告，不写库")
    args = ap.parse_args()
    db = SessionLocal()
    try:
        CaseMigrator(db, args.dry_run).run()
        if args.dry_run:
            db.rollback()
            print("\n[dry-run] 已回滚，未写库")
    finally:
        db.close()


if __name__ == "__main__":
    main()
