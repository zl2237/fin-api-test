"""入参收敛到数据集：drop case_node_configs.params / pre_process

Revision ID: aa33bb44cc55
Revises: ff22bb33cc44
Create Date: 2026-09-30

入参收敛定案（2026-09-30）：节点入参配置（四来源 params + 前置动作）收敛到
数据集行（data_set_rows.data = {"nodes": {节点ID: {params, pre_process}}}），
case_node_configs 只承载结构层（接口绑定/后置提取/断言/等待）。
执行本迁移前须先跑 scripts/migrate_params_to_dataset.py 完成存量搬迁。
"""
from alembic import op
import sqlalchemy as sa

revision = "aa33bb44cc55"
down_revision = "ff22bb33cc44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("case_node_configs", "params")
    op.drop_column("case_node_configs", "pre_process")


def downgrade() -> None:
    # 入参配置已收敛到数据集行，downgrade 仅恢复空列结构（历史数据不可还原）
    op.add_column("case_node_configs", sa.Column("params", sa.JSON(), nullable=True))
    op.add_column("case_node_configs", sa.Column("pre_process", sa.JSON(), nullable=True))
