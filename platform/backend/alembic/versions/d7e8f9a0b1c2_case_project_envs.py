"""跨系统用例按项目环境绑定（2026-11-13）

- 新表 case_project_envs：非原生项目视角的执行环境绑定，(case_id, project_id) 唯一
- 数据迁移：跨项目节点的自动绑定（env 属于非原生项目）清空为 NULL，改落
  (case_id, env.project_id) 绑定行——运行行为不变，但环境在该项目视角可见可切换；
  解析优先级变为：节点显式绑定 > 项目绑定 > 该项目默认环境 > 用例环境（原生节点）

Revision ID: d7e8f9a0b1c2
Revises: c4d5e6f7a9b0
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'd7e8f9a0b1c2'
down_revision = 'c4d5e6f7a9b0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_project_envs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("test_cases.id", ondelete="CASCADE"),
                  nullable=False, comment="用例ID"),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False, comment="项目视角ID（非原生项目）"),
        sa.Column("env_id", sa.Integer(), sa.ForeignKey("environments.id", ondelete="CASCADE"),
                  nullable=False, comment="该项目视角下的执行环境ID（删行=回退该项目默认环境）"),
        sa.Column("created_at", sa.DateTime(), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), comment="最近更新"),
        sa.UniqueConstraint("case_id", "project_id", name="uq_case_project_env_case_project"),
        comment="跨系统用例的按项目环境绑定",
    )
    op.create_index("ix_case_project_envs_case_id", "case_project_envs", ["case_id"])
    op.create_index("ix_case_project_envs_project_id", "case_project_envs", ["project_id"])

    # 数据迁移（可移植写法：先查后改，不依赖 UPDATE JOIN 方言）：
    # ① 跨项目节点的节点级 env（属于非原生项目）→ 记下 (case, project, env) 后清 NULL
    conn = op.get_bind()
    cross_rows = conn.execute(sa.text("""
        SELECT cnc.id, cnc.case_id, e.project_id, cnc.env_id
        FROM case_node_configs cnc
        JOIN environments e ON e.id = cnc.env_id
        JOIN test_cases c ON c.id = cnc.case_id
        WHERE cnc.env_id IS NOT NULL AND e.project_id <> c.project_id
    """)).fetchall()
    for row in cross_rows:
        conn.execute(sa.text(
            "UPDATE case_node_configs SET env_id = NULL WHERE id = :id"), {"id": row[0]})
    # ② 清掉的绑定落位成项目环境绑定（同 (case, project) 多节点取 env 最小值，幂等跳过已存在行）
    seen: dict[tuple[int, int], int] = {}
    for row in cross_rows:
        key = (row[1], row[2])
        if key not in seen or row[3] < seen[key]:
            seen[key] = row[3]
    for (case_id, project_id), env_id in seen.items():
        exists = conn.execute(sa.text(
            "SELECT 1 FROM case_project_envs WHERE case_id = :c AND project_id = :p"
        ), {"c": case_id, "p": project_id}).first()
        if not exists:
            now_sql = "NOW()" if conn.dialect.name == "mysql" else "CURRENT_TIMESTAMP"
            conn.execute(sa.text(
                "INSERT INTO case_project_envs (case_id, project_id, env_id, created_at, updated_at) "
                f"VALUES (:c, :p, :e, {now_sql}, {now_sql})"
            ), {"c": case_id, "p": project_id, "e": env_id})


def downgrade() -> None:
    # 不可逆数据迁移：节点级 env 已清空，无法还原哪些是自动绑定
    op.drop_index("ix_case_project_envs_project_id", table_name="case_project_envs")
    op.drop_index("ix_case_project_envs_case_id", table_name="case_project_envs")
    op.drop_table("case_project_envs")
