"""api_keys

新增 api_keys 表：外部触发（CI/Jenkins）用 API 密钥。
明文不落库（只存 sha256 哈希），创建时一次性返回；认证双通道
Authorization: Bearer fin_* 或 X-API-Key 头，密钥身份 = 创建人身份。

Revision ID: e9b2f6d4c8a1
Revises: c3f8a92d5e17
Create Date: 2026-11-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e9b2f6d4c8a1'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), nullable=False, comment='主键ID'),
        sa.Column('project_id', sa.Integer(), nullable=False, comment='所属项目ID（密钥管理页按项目分组）'),
        sa.Column('name', sa.String(length=100), nullable=False, comment='用途名：如 jenkins-nightly'),
        sa.Column('key_hash', sa.String(length=64), nullable=False,
                  comment='sha256(明文) 十六进制——明文永不落库'),
        sa.Column('key_prefix', sa.String(length=20), nullable=False,
                  comment='明文前 12 字符（fin_xxxxxxxx），仅列表展示辨识用'),
        sa.Column('last_used_at', sa.DateTime(), nullable=True, comment='最近一次认证成功时间（每次使用回写）'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.Column('created_by', sa.Integer(), nullable=True, comment='创建人 user_id（密钥身份 = 该用户）'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash', name='uq_api_keys_key_hash'),
    )
    op.create_index('ix_api_keys_id', 'api_keys', ['id'])
    op.create_index('ix_api_keys_project_id', 'api_keys', ['project_id'])
    op.create_index('ix_api_keys_key_hash', 'api_keys', ['key_hash'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_api_keys_key_hash', table_name='api_keys')
    op.drop_index('ix_api_keys_project_id', table_name='api_keys')
    op.drop_index('ix_api_keys_id', table_name='api_keys')
    op.drop_table('api_keys')
