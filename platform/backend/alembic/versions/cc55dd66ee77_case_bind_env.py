"""用例严格绑定环境：test_cases.env_id

Revision ID: cc55dd66ee77
Revises: bb44cc55dd66
Create Date: 2026-10-15

执行环境从「执行时选什么就用什么」收敛为「用例属性」：
- 每条用例绑定唯一执行环境，所有触发入口（手动/批量/定时/套件成员）
  一律读 case.env_id，请求/配置里的环境选择不再生效
- 存量回填：每用例最近一条执行记录的环境（无执行记录的保持 NULL，
  首次执行/编辑时补绑）
"""
from alembic import op
import sqlalchemy as sa

revision = "cc55dd66ee77"
down_revision = "bb44cc55dd66"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "test_cases",
        sa.Column("env_id", sa.Integer(), nullable=True,
                  comment="绑定的执行环境ID（严格绑定：所有触发入口一律用此环境）"),
    )
    op.create_index("ix_test_cases_env_id", "test_cases", ["env_id"])
    # 存量回填：每用例最近一条执行记录的环境（MySQL 8 UPDATE + 派生表 JOIN）
    op.execute(
        """
        UPDATE test_cases tc
        JOIN (
            SELECT e.case_id, e.env_id
            FROM execution_records e
            JOIN (
                SELECT case_id, MAX(id) AS max_id
                FROM execution_records
                WHERE env_id IS NOT NULL
                GROUP BY case_id
            ) latest ON latest.max_id = e.id
        ) src ON src.case_id = tc.id
        SET tc.env_id = src.env_id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_test_cases_env_id", table_name="test_cases")
    op.drop_column("test_cases", "env_id")
