"""step_records 加 retry_history：重试失败快照留存

Revision ID: dd77ee88ff99
Revises: cc55dd66ee77
Create Date: 2026-10-16

问题：请求层失败自动重试后，失败尝试的响应被成功响应覆盖，
「重试后成功」的步骤无法回看首次失败原因（如报告 1306 提交订单节点）。

方案：新列 retry_history（JSON 可空）记录每次被顶替的失败尝试快照
{attempt, ts, elapsed_ms, status_code, error, response(截断2KB)}；
最终失败的那次仍完整保留在主行 response_body。
"""
import sqlalchemy as sa
from alembic import op

revision = "dd77ee88ff99"
down_revision = "cc55dd66ee77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("step_records", sa.Column("retry_history", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("step_records", "retry_history")
