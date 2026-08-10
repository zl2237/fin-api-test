"""add project versions table

新增项目版本表 project_versions：保存项目每次手动快照（接口+用例完整快照），
支持版本历史查看、Diff 对比、回滚到任意历史版本。

Revision ID: e7f8a9b0c1d2
Revises: 9555ad43e3ac
Create Date: 2026-08-10 00:10:00
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7f8a9b0c1d2'
down_revision = '9555ad43e3ac'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, comment="主键ID"),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, comment="所属项目ID"),
        sa.Column("version_no", sa.Integer(), nullable=False, comment="版本号：从 1 递增"),
        sa.Column("name", sa.String(length=200), nullable=False, comment="版本名称：如 v1.0 / 冒烟基线"),
        sa.Column("description", sa.Text(), comment="版本说明/变更备注"),
        sa.Column("snapshot", sa.JSON(), nullable=False, comment="完整快照：{api_groups, case_groups, apis, cases}，不含环境"),
        sa.Column("created_by", sa.Integer(), nullable=True, comment="创建人 user_id"),
        sa.Column("created_at", sa.DateTime(), comment="版本创建时间"),
        sa.UniqueConstraint("project_id", "version_no", name="uq_project_version"),
        comment="项目版本快照：手动触发的项目整体快照，支持回滚和 Diff 对比",
    )
    op.create_index("ix_project_versions_project_id", "project_versions", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_project_versions_project_id", table_name="project_versions")
    op.drop_table("project_versions")
