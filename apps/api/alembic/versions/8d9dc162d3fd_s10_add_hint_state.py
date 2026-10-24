"""s10 add hint state

Revision ID: 8d9dc162d3fd
Revises: 0005_access_token_null
Create Date: 2026-10-11 14:07:19.004082

"""
from alembic import op
import sqlalchemy as sa

revision: str = '8d9dc162d3fd'
down_revision: Union[str, Sequence[str], None] = '0005_access_token_null'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interviews",
        sa.Column(
            "hint_level",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "interviews",
        sa.Column(
            "last_hint_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("interviews", "last_hint_at")
    op.drop_column("interviews", "hint_level")
