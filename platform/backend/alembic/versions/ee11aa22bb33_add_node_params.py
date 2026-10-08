"""节点参数四来源配置列

Revision ID: ee11aa22bb33
Revises: c2e9f8a4b6d8
Create Date: 2026-09-30

参数模型 v2（2026-09-30 需求拷问定案）：节点入参仅四种取值来源（constant/func/ref/sql），
结构化存储于 case_node_configs.params；数据集变量池按名自动注入随之废止，
池值迁移为 {"source":"ref","node_id":"__dataset__","var_path":<列key>} 显式引用。
"""
import sqlalchemy as sa
from alembic import op

revision = "ee11aa22bb33"
down_revision = "c2e9f8a4b6d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("case_node_configs",
                  sa.Column("params", sa.JSON(), nullable=True,
                            comment="节点参数四来源配置：{body: {路径: {source,...}}, headers: {头名: {...}}}"))


def downgrade() -> None:
    op.drop_column("case_node_configs", "params")
