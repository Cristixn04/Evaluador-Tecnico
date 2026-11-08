"""s09 invitation interview phase

Revision ID: 0003_s09_invitation_phase
Revises: 0002_auth_s03
Create Date: 2026-10-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_s09_invitation_phase"
down_revision: str | Sequence[str] | None = "0002_auth_s03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create invitations table
    op.create_table(
        "invitations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("vacancy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_name", sa.String(length=255), nullable=False),
        sa.Column("candidate_email", sa.String(length=255), nullable=False),
        sa.Column("candidate_phone", sa.String(length=50), nullable=True),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_invitations_interview_id_interviews"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancies.id"],
            name=op.f("fk_invitations_vacancy_id_vacancies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
        sa.UniqueConstraint("interview_id", name=op.f("uq_invitations_interview_id")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_invitations_token_hash")),
    )
    op.create_index(
        op.f("ix_invitations_vacancy_id"), "invitations", ["vacancy_id"], unique=False
    )
    op.create_index(
        op.f("ix_invitations_interview_id"), "invitations", ["interview_id"], unique=False
    )

    # Add phase column to interviews
    op.add_column(
        "interviews",
        sa.Column(
            "phase",
            sa.String(length=20),
            server_default=sa.text("'INTRO'"),
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_interviews_phase"), "interviews", ["phase"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_interviews_phase"), table_name="interviews")
    op.drop_column("interviews", "phase")

    op.drop_index(op.f("ix_invitations_interview_id"), table_name="invitations")
    op.drop_index(op.f("ix_invitations_vacancy_id"), table_name="invitations")
    op.drop_table("invitations")