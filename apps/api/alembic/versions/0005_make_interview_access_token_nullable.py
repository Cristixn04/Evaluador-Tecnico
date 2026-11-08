"""make interview access_token nullable for new interviews

Revision ID: 0005_make_interview_access_token_nullable
Revises: 0004_add_token_selector
Create Date: 2026-10-09 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0005_access_token_null"
down_revision: str | Sequence[str] | None = "0004_add_token_selector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Make access_token nullable for new interviews
    op.alter_column("interviews", "access_token", nullable=True)


def downgrade() -> None:
    # Note: This would fail if there are NULL values, but that's expected for downgrade
    op.alter_column("interviews", "access_token", nullable=False)