"""跨系统用例按项目分组覆写（2026-11-13）

- 新表 case_group_overrides：非原生项目视角的分组覆写，(case_id, project_id) 唯一
- 背景：跨系统用例（派生归属出现在 ≥2 个项目）此前只有一个原生维度 group_id，
  在 B 项目移动分组会连坐 A 项目视角掉进未分组；覆写行让各项目分组互不干扰

Revision ID: c4d5e6f7a9b0
Revises: b3a4b5c6d7e8
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'c4d5e6f7a9b0'
down_revision = 'b3a4b5c6d7e8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_group_overrides",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("test_cases.id", ondelete="CASCADE"),
                  nullable=False, comment="用例ID"),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False, comment="项目视角ID（非原生项目）"),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("case_groups.id", ondelete="CASCADE"),
                  nullable=True, comment="该项目视角下的分组ID（移回未分组即删行回退）"),
        sa.Column("created_at", sa.DateTime(), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), comment="最近更新"),
        sa.UniqueConstraint("case_id", "project_id", name="uq_case_group_override_case_project"),
        comment="跨系统用例的按项目分组覆写",
    )
    op.create_index("ix_case_group_overrides_case_id", "case_group_overrides", ["case_id"])
    op.create_index("ix_case_group_overrides_project_id", "case_group_overrides", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_case_group_overrides_project_id", table_name="case_group_overrides")
    op.drop_index("ix_case_group_overrides_case_id", table_name="case_group_overrides")
    op.drop_table("case_group_overrides")
