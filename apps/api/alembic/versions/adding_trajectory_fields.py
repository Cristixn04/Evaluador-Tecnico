"""Adding trajectory fields to snapshots table

Revision ID: adding_trajectory_fields
Revises: 9d55e0bb5769
Create Date: 2026-10-13 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "adding_trajectory_fields"
down_revision: str | Sequence[str] | None = "9d55e0bb5769"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "snapshots",
        sa.Column(
            "phase",
            sa.String(length=50),
            nullable=False,
            server_default="INTRO",
        ),
    )
    op.add_column(
        "snapshots",
        sa.Column(
            "language",
            sa.String(length=50),
            nullable=False,
            server_default="python",
        ),
    )
    op.add_column(
        "snapshots",
        sa.Column(
            "reason",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "snapshots",
        sa.Column(
            "tests_passed",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "snapshots",
        sa.Column(
            "total_tests",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "snapshots",
        sa.Column(
            "execution_status",
            sa.String(length=50),
            nullable=True,
        ),
    )
    op.add_column(
        "snapshots",
        sa.Column(
            "event_note",
            sa.String(length=500),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("snapshots", "event_note")
    op.drop_column("snapshots", "execution_status")
    op.drop_column("snapshots", "total_tests")
    op.drop_column("snapshots", "tests_passed")
    op.drop_column("snapshots", "reason")
    op.drop_column("snapshots", "language")
    op.drop_column("snapshots", "phase")