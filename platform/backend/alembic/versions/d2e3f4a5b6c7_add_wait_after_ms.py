"""add wait_after_ms to case_node_configs

新增 case_node_configs.wait_after_ms 字段：
- 当前节点接口执行完成后，到下一节点接口请求前的等待毫秒数
- 默认 0（立即执行下一节点），可配置如 3000 表示等待 3 秒
- 用于给后端处理事务、数据落库留出时间，避免下游接口读到未提交数据

Revision ID: d2e3f4a5b6c7
Revises: e7f8a9b0c1d2
Create Date: 2026-08-10 23:30:00
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2e3f4a5b6c7'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'case_node_configs',
        sa.Column('wait_after_ms', sa.Integer(), nullable=False, server_default='0',
                  comment='当前节点执行完后到下一节点请求前的等待毫秒数，默认0'),
    )


def downgrade() -> None:
    op.drop_column('case_node_configs', 'wait_after_ms')
