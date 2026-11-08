"""add server_default to reason column

Revision ID: a5fe8eec0469
Revises: b217eca9217b
Create Date: 2026-10-13 13:52:18.788138

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5fe8eec0469'
down_revision: Union[str, Sequence[str], None] = 'b217eca9217b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('snapshots', 'reason',
               existing_type=sa.VARCHAR(length=255),
               nullable=False,
               server_default='legacy',
               )


def downgrade() -> None:
    op.alter_column('snapshots', 'reason',
               existing_type=sa.VARCHAR(length=255),
               nullable=False,
               server_default=None,
               )