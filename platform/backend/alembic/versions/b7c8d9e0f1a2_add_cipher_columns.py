"""接口级 RSA 加密传输（requestCipher 协议）三列（2026-11-13）

- environments.cipher_config：环境级密钥库 {key_pairs:[{name,public_key,private_key}]}
- api_definitions.crypto_config：接口级加密开关
  {request:{enabled,key,wrapper_field,segment_size}, response:{enabled,key,mode(body|field),field}}
- step_records.cipher_snapshot：加密传输密文快照 {request,response}（明文仍在原列）

三列均可空、零数据迁移：NULL 即「未配置」，存量行为完全不变。

Revision ID: b7c8d9e0f1a2
Revises: d7e8f9a0b1c2
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'b7c8d9e0f1a2'
down_revision = 'd7e8f9a0b1c2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("environments", sa.Column(
        "cipher_config", sa.JSON(), nullable=True,
        comment="加密配置：{key_pairs:[{name,public_key,private_key}]}——接口级传输加解密密钥库"
                "（名称多对，如 customs/cfca；测试/生产密钥分环境录入，禁止共用）"))
    op.add_column("api_definitions", sa.Column(
        "crypto_config", sa.JSON(), nullable=True,
        comment="接口级加密配置：{request:{enabled,key,wrapper_field,segment_size},"
                "response:{enabled,key,mode(body|field),field}}；开启后明文参数执行期"
                "自动加密为 {wrapper_field: 密文} 发送（requestCipher 协议）"))
    op.add_column("step_records", sa.Column(
        "cipher_snapshot", sa.JSON(), nullable=True,
        comment="加密传输密文快照 {request,response}（整体 Base64 串）；明文仍在 "
                "request_body/response_body，重放按接口加密配置重新加密"))


def downgrade() -> None:
    op.drop_column("step_records", "cipher_snapshot")
    op.drop_column("api_definitions", "crypto_config")
    op.drop_column("environments", "cipher_config")
