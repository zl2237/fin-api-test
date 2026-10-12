"""用例最近执行回写：test_cases.last_exec_at / last_exec_status

Revision ID: bb44cc55dd66
Revises: aa33bb44cc55
Create Date: 2026-10-12

用例列表「一眼看出哪些通过/多久没跑」的支撑列（免翻执行记录）：
- 执行终结（success/failed/terminated）时由执行链路回写 started_at + 终态
- 存量数据按「每用例最近一条终态记录」回填（running 不算终态）
"""
from alembic import op
import sqlalchemy as sa

revision = "bb44cc55dd66"
down_revision = "aa33bb44cc55"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "test_cases",
        sa.Column("last_exec_at", sa.DateTime(), nullable=True,
                  comment="最近一次执行开始时间（执行终结时回写；NULL=从未执行）"),
    )
    op.add_column(
        "test_cases",
        sa.Column("last_exec_status", sa.String(20), nullable=True,
                  comment="最近一次执行的终态：success/failed/terminated（执行中不回写，保持上一次终态）"),
    )
    op.create_index("ix_test_cases_last_exec_at", "test_cases", ["last_exec_at"])
    # 存量回填：每用例最近一条终态执行记录（MySQL 8 UPDATE + 派生表 JOIN）
    op.execute(
        """
        UPDATE test_cases tc
        JOIN (
            SELECT e.case_id, e.started_at, e.status
            FROM execution_records e
            JOIN (
                SELECT case_id, MAX(id) AS max_id
                FROM execution_records
                WHERE status IN ('success', 'failed', 'terminated')
                GROUP BY case_id
            ) latest ON latest.max_id = e.id
        ) src ON src.case_id = tc.id
        SET tc.last_exec_at = src.started_at,
            tc.last_exec_status = src.status
        """
    )


def downgrade() -> None:
    op.drop_index("ix_test_cases_last_exec_at", table_name="test_cases")
    op.drop_column("test_cases", "last_exec_status")
    op.drop_column("test_cases", "last_exec_at")
