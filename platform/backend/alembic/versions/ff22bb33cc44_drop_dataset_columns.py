"""数据集退化为纯数据表：drop 列 schema

Revision ID: ff22bb33cc44
Revises: ee11aa22bb33
Create Date: 2026-09-30

变量池概念拆除（2026-09-30 参数模型定案）：data_sets.columns 列 schema 删除，
数据集只剩「一套完整键值对数据」语义；行数据（data_set_rows.data）不受影响。
"""
from alembic import op

revision = "ff22bb33cc44"
down_revision = "ee11aa22bb33"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("data_sets", "columns")


def downgrade() -> None:
    # 列 schema 已废弃，downgrade 仅恢复空列结构（历史定义不可还原）
    import sqlalchemy as sa
    op.add_column("data_sets", sa.Column("columns", sa.JSON(), nullable=True))
