"""drop data_sets.node_configs（编排快照机制下线：编排唯一来源是用例当前配置）

数据集只管数据（变量池）；执行恒按用例当前编排跑，快照/覆盖/drift 机制整体移除。

Revision ID: a1b2c3d4e5f6
Revises: e9f0a1b2c3d4
Create Date: 2026-09-22
"""
from alembic import op

revision = 'a1b2c3d4e5f6'
down_revision = 'e9f0a1b2c3d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('data_sets', 'node_configs')


def downgrade() -> None:
    from sqlalchemy import JSON
    op.add_column('data_sets',
                  op.Column('node_configs', JSON, nullable=True,
                            comment='（已废弃）历史编排配置快照'))
