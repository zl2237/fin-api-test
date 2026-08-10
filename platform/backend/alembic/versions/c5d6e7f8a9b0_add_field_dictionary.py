"""add field dictionary

新增字段字典表 field_dictionaries：项目级英文字段名 → 中文含义映射，
用于在节点配置、接口编辑等界面自动展示字段中文标签，避免逐接口手写 label。

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-08-09 14:00:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "field_dictionaries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, comment="主键ID"),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False, comment="所属项目ID"),
        sa.Column("key", sa.String(length=200), nullable=False, comment="字段英文名：如 order_id / bl_no"),
        sa.Column("label", sa.String(length=100), nullable=False, comment="字段中文名：如 订单ID / 提单号"),
        sa.Column("created_at", sa.DateTime(), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), comment="最近更新时间"),
        sa.Column("created_by", sa.Integer(), nullable=True, comment="创建人 user_id"),
        sa.Column("updated_by", sa.Integer(), nullable=True, comment="更新人 user_id"),
        sa.UniqueConstraint("project_id", "key", name="uq_field_dict_project_key"),
        comment="字段字典：项目级字段中英文映射",
    )
    op.create_index("ix_field_dictionaries_project_id", "field_dictionaries", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_field_dictionaries_project_id", table_name="field_dictionaries")
    op.drop_table("field_dictionaries")
