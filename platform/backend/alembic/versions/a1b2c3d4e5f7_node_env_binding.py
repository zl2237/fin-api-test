"""node env binding

跨系统编排（2026-11-12）：case_node_configs 新增 env_id 节点级环境绑定。
编排用例时可跨项目选择接口，节点绑其所属项目环境后，执行期该节点用
此环境的 base_url/登录态/DB（HttpClient/DBClient/401 重登均按环境隔离），
NULL = 沿用用例环境。同批后端支持「派生归属」：用例归属 = 原生项目 ∪
节点引用接口的项目（运行时 EXISTS 子查询，无冗余列）。

Revision ID: a1b2c3d4e5f7
Revises: e9b2f6d4c8a1
Create Date: 2026-11-12 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, Sequence[str], None] = 'e9b2f6d4c8a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('case_node_configs', sa.Column(
        'env_id', sa.Integer(), nullable=True,
        comment='节点级环境绑定（跨系统编排）：指向接口所属项目的环境，'
                '执行时该节点用此环境的 base_url/登录态/DB；NULL=沿用用例环境'))
    op.create_index('ix_case_node_configs_env_id', 'case_node_configs', ['env_id'])
    op.create_foreign_key('fk_case_node_configs_env_id', 'case_node_configs',
                          'environments', ['env_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_case_node_configs_env_id', 'case_node_configs', type_='foreignkey')
    op.drop_index('ix_case_node_configs_env_id', table_name='case_node_configs')
    op.drop_column('case_node_configs', 'env_id')
