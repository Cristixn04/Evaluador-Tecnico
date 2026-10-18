"""s10 add hint_reservation_token column

Revision ID: 9d55e0bb5769
Revises: 02c74c24508e
Create Date: 2026-10-11 15:30:38.214023

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d55e0bb5769'
down_revision: Union[str, Sequence[str], None] = '02c74c24508e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'interviews',
        sa.Column(
            'hint_reservation_token',
            sa.UUID(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('interviews', 'hint_reservation_token')