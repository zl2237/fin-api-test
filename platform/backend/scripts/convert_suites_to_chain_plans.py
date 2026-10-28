# -*- coding: utf-8 -*-
"""套件收口迁移（2026-10-28）：线上套件用例 → chain 串行链执行方案，然后删除套件。

对每个 case_type='suite' 用例：
1. 建 ExecutionPlan（mode='chain'，名称加「（串行链）」后缀）
2. 按 suite_members.sort_order 建 ExecutionPlanItem（成员用例各自绑定数据集/环境，
   run_count=1）；原套件 shared_vars 白名单下放到成员级 pass_vars——除末棒外
   每个成员都按名单把输出传给下一棒（相邻定向传参，下一棒 __prev__.变量名 引用）
3. 归档套件主执行记录到 backups/suite_archive_*.json（含 summary 全文）
4. 删 suite_members 行 → 删套件主执行记录（RESTRICT 外键，归档后删）→ 删套件用例行

幂等：方案名已存在 / 套件用例已删除的步骤自动跳过；dry-run 默认，APPLY=1 落库。

用法（platform/backend 目录下）：
    python scripts/convert_suites_to_chain_plans.py              # dry-run
    DB_HOST=192.168.2.51 DB_PORT=20001 DB_USER=dev-wifi DB_PASSWORD=... \
        APPLY=1 python scripts/convert_suites_to_chain_plans.py  # 线上执行
"""
import json
import os
from datetime import datetime
from pathlib import Path

import pymysql

APPLY = os.environ.get("APPLY") == "1"
PLAN_SUFFIX = "（串行链）"


def main():
    conn = pymysql.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", "123456"),
        database=os.environ.get("DB_NAME", "fin_api_test"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as c:
            c.execute("SELECT id, project_id, name, shared_vars FROM test_cases WHERE case_type='suite'")
            suites = c.fetchall()
            print(f"套件用例 {len(suites)} 个")
            for s in suites:
                convert(c, s)
        if APPLY:
            conn.commit()
            print("\nAPPLY 已提交")
        else:
            conn.rollback()
            print("\nDRY-RUN（APPLY=1 落库）")
    finally:
        conn.close()


def convert(c, suite):
    sid, name = suite["id"], suite["name"]
    plan_name = name + PLAN_SUFFIX
    print(f"\n== 套件 #{sid} {name}（project {suite['project_id']}，shared_vars={suite['shared_vars']}）")

    # 成员链（sort_order 序）；顺带核对成员用例仍存在
    c.execute("SELECT member_case_id, sort_order FROM suite_members WHERE suite_case_id=%s ORDER BY sort_order", (sid,))
    members = c.fetchall()
    if not members:
        print("  无成员，跳过")
        return
    for m in members:
        c.execute("SELECT id, name, project_id, env_id FROM test_cases WHERE id=%s", (m["member_case_id"],))
        mc = c.fetchone()
        if not mc:
            print(f"  成员 #{m['member_case_id']} 已删除，中止本套件")
            return
        print(f"  成员 #{mc['id']} {mc['name']}（project {mc['project_id']} env {mc['env_id']}）")

    # 1) 建方案（幂等：同名已建则跳过）
    c.execute("SELECT id FROM execution_plans WHERE name=%s AND project_id=%s", (plan_name, suite["project_id"]))
    existing = c.fetchone()
    if existing:
        plan_id = existing["id"]
        print(f"  方案已存在 #{plan_id}，跳过创建")
    elif APPLY:
        c.execute(
            "INSERT INTO execution_plans (project_id, name, description, mode, rounds, concurrency, enabled,"
            " schedule_enabled, created_at, updated_at)"
            " VALUES (%s,%s,%s,'chain',1,4,1,0,NOW(),NOW())",
            (suite["project_id"], plan_name,
             "套件收口自动转换（原套件 #%s；成员按序串行、相邻定向传参、失败阻断本轮下游）" % sid))
        plan_id = c.lastrowid
        print(f"  已建 chain 方案 #{plan_id}「{plan_name}」")
        pass_vars_json = suite["shared_vars"]  # 原套件白名单 → 成员级 pass_vars（末棒除外）
        for m in members:
            c.execute(
                "INSERT INTO execution_plan_items (plan_id, case_id, dataset_id, run_count, pass_vars, sort_order)"
                " VALUES (%s,%s,NULL,1,%s,%s)",
                (plan_id, m["member_case_id"],
                 pass_vars_json if m is not members[-1] else None, m["sort_order"]))
        print(f"  已建 {len(members)} 个成员项（dataset_id=NULL=各用例自身绑定；"
              f"前 {max(0, len(members) - 1)} 棒带 pass_vars={pass_vars_json}）")
    else:
        print(f"  [dry] 建 chain 方案「{plan_name}」+ {len(members)} 个成员项"
              f"（前 {max(0, len(members) - 1)} 棒带 pass_vars={suite['shared_vars']}）")

    # 2) 归档套件主执行记录
    c.execute("SELECT * FROM execution_records WHERE case_id=%s ORDER BY id", (sid,))
    execs = c.fetchall()
    if execs:
        out_dir = Path(__file__).resolve().parent / "backups"
        out_dir.mkdir(exist_ok=True)
        out = out_dir / f"suite_archive_{sid}_{datetime.now():%Y%m%d_%H%M%S}.json"
        payload = {"suite_case": suite, "members": members, "executions": execs,
                   "archived_at": datetime.now().isoformat()}
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"  归档 {len(execs)} 条主执行记录 → {out.name}")
    else:
        print("  无主执行记录，免归档")

    # 3) 删套件（幂等：用例已删则整组跳过）
    c.execute("SELECT id FROM test_cases WHERE id=%s", (sid,))
    if not c.fetchone():
        print("  套件用例已删除，跳过")
        return
    if not APPLY:
        print(f"  [dry] 删 suite_members {len(members)} 行 + 主执行记录 {len(execs)} 行 + 用例 #{sid}")
        return
    c.execute("DELETE FROM suite_members WHERE suite_case_id=%s", (sid,))
    c.execute("DELETE FROM step_records WHERE execution_id IN (SELECT id FROM (SELECT id FROM execution_records WHERE case_id=%s) t)", (sid,))
    c.execute("DELETE FROM execution_records WHERE case_id=%s", (sid,))
    c.execute("DELETE FROM test_cases WHERE id=%s", (sid,))
    print(f"  已删除 suite_members {len(members)} 行、主执行记录 {len(execs)} 行、套件用例 #{sid}")


if __name__ == "__main__":
    main()
