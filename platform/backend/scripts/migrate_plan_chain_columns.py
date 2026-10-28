# -*- coding: utf-8 -*-
"""执行方案串行链模式 DDL（2026-10-28 套件收口 + 链式定向传参/批量策略正交）：
execution_plans / execution_plan_items 增删列，幂等收敛到当前模型。

- execution_plans.mode VARCHAR(20) NOT NULL DEFAULT 'combo'：combo 并行组合 / chain 串行链
- execution_plans.rounds INT NOT NULL DEFAULT 1：chain 整链执行轮数（combo 恒 1）
- execution_plan_items.pass_vars JSON NULL：chain 相邻定向传参（本成员成功后
  按 pass_vars 名单快照传给下一棒，下一棒 __prev__.变量名 引用）
- 废弃列自动清理：execution_plans.shared_vars（链 v1 全局白名单，语义已下沉到
  成员级 pass_vars；列存在则 DROP——部署收口前的过渡列，无存量数据依赖）

幂等：加列前查 information_schema，删列同理；新库/旧库重复执行结果一致。
套件收口后 test_cases.shared_vars / suite_members / execution_records.suite_execution_id
列与数据废弃（模型已不映射，列保留仅历史）。

用法（platform/backend 目录下）：
    python scripts/migrate_plan_chain_columns.py            # 默认本地库
    DB_HOST=192.168.2.51 DB_PORT=20001 DB_USER=dev-wifi DB_PASSWORD=... \
        python scripts/migrate_plan_chain_columns.py        # 线上共享库
"""
import os

import pymysql

# (表, 列, 加列 DDL)
ADD_COLUMNS = [
    ("execution_plans", "mode",
     "ALTER TABLE execution_plans ADD COLUMN mode VARCHAR(20) NOT NULL "
     "DEFAULT 'combo' COMMENT '方案模式：combo 并行组合 / chain 串行链（按序+相邻传参+失败阻断）'"),
    ("execution_plans", "rounds",
     "ALTER TABLE execution_plans ADD COLUMN rounds INT NOT NULL DEFAULT 1 "
     "COMMENT 'chain 专用：整链执行轮数（1~9999，轮内串行、轮间并行）；combo 恒 1'"),
    ("execution_plan_items", "pass_vars",
     "ALTER TABLE execution_plan_items ADD COLUMN pass_vars JSON NULL "
     "COMMENT 'chain 专用：传给下一棒的输出变量名单（相邻定向传参；combo 忽略）'"),
]

# (表, 列)：链 v1 过渡列，语义已迁移（shared_vars 全局白名单 → 成员级 pass_vars）
DROP_COLUMNS = [
    ("execution_plans", "shared_vars"),
]


def _columns(c, table: str) -> set:
    c.execute("SELECT column_name FROM information_schema.columns "
              "WHERE table_schema = DATABASE() AND table_name = %s", (table,))
    return {r[0] for r in c.fetchall()}


def main():
    conn = pymysql.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", "123456"),
        database=os.environ.get("DB_NAME", "fin_api_test"),
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as c:
            for table, name, ddl in ADD_COLUMNS:
                if name in _columns(c, table):
                    print(f"  {table}.{name} 已存在，跳过")
                    continue
                c.execute(ddl)
                print(f"  已加列 {table}.{name}")
            for table, name in DROP_COLUMNS:
                if name not in _columns(c, table):
                    print(f"  {table}.{name} 不存在，免删")
                    continue
                c.execute(f"ALTER TABLE {table} DROP COLUMN {name}")
                print(f"  已删过渡列 {table}.{name}")
        conn.commit()
    finally:
        conn.close()
    print("完成")


if __name__ == "__main__":
    main()
