"""api contract templates + node binding

Revision ID: c3d4e5f6a7b8
Revises: b8e5f2a7c9d1
Create Date: 2026-11-03

接口契约模板（Q2 定案 2026-11-03）：
- api_contract_templates：接口字段 key 清单的命名视图（api_fields 仍是唯一字段权威）
- case_node_configs.contract_template_id：节点级绑定；NULL = 隐式全量字段（存量零迁移）
"""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b8e5f2a7c9d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_contract_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("api_id", sa.Integer(), sa.ForeignKey("api_definitions.id"), nullable=True, comment="所属接口ID"),
        sa.Column("name", sa.String(100), nullable=False, comment="模板名：如 精简提交 / 全量"),
        sa.Column("field_keys", sa.JSON(), nullable=True, comment="字段 key 清单（须存在于 api_fields）"),
        sa.Column("created_at", sa.DateTime(), nullable=True, comment="创建时间"),
        comment="接口契约模板：字段 key 清单的命名视图",
    )
    op.create_index("ix_api_contract_templates_id", "api_contract_templates", ["id"])
    op.create_index("ix_api_contract_templates_api_id", "api_contract_templates", ["api_id"])

    op.add_column("case_node_configs", sa.Column(
        "contract_template_id", sa.Integer(),
        sa.ForeignKey("api_contract_templates.id"), nullable=True,
        comment="契约模板绑定：契约校验按模板 key 集判；NULL=隐式全量字段"))


def downgrade() -> None:
    op.drop_column("case_node_configs", "contract_template_id")
    op.drop_index("ix_api_contract_templates_api_id", table_name="api_contract_templates")
    op.drop_index("ix_api_contract_templates_id", table_name="api_contract_templates")
    op.drop_table("api_contract_templates")
