"""s10 add hint_reserved_at column

Revision ID: 02c74c24508e
Revises: 8d9dc162d3fd
Create Date: 2026-10-11 15:11:55.099268

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '02c74c24508e'
down_revision: Union[str, Sequence[str], None] = '8d9dc162d3fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'interviews',
        sa.Column(
            'hint_reserved_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('interviews', 'hint_reserved_at')