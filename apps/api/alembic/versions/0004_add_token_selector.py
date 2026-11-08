"""add token_selector to invitations

Revision ID: 0004_add_token_selector
Revises: 0003_s09_invitation_phase
Create Date: 2026-10-09 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_add_token_selector"
down_revision: str | Sequence[str] | None = "0003_s09_invitation_phase"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add token_selector column (nullable for legacy invitations)
    op.add_column(
        "invitations",
        sa.Column("token_selector", sa.String(16), nullable=True),
    )

    # Unique index (PostgreSQL allows multiple NULLs in unique index)
    op.create_index(
        op.f("ix_invitations_token_selector"),
        "invitations",
        ["token_selector"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_invitations_token_selector"), table_name="invitations")
    op.drop_column("invitations", "token_selector")