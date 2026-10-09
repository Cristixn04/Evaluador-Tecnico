"""initial s02 persistence schema

Revision ID: 0001_initial_s02
Revises:
Create Date: 2026-04-08 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial_s02"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vacancies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("raw_description", sa.Text(), nullable=False),
        sa.Column("role_category", sa.String(length=100), nullable=True),
        sa.Column("seniority", sa.String(length=20), nullable=True),
        sa.Column("profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vacancies")),
    )
    op.create_index(
        op.f("ix_vacancies_role_category"), "vacancies", ["role_category"], unique=False
    )
    op.create_index(op.f("ix_vacancies_seniority"), "vacancies", ["seniority"], unique=False)

    op.create_table(
        "problems",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=False),
        sa.Column("scenario_preview", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_problems")),
    )
    op.create_index(op.f("ix_problems_difficulty"), "problems", ["difficulty"], unique=False)
    op.create_index(op.f("ix_problems_language"), "problems", ["language"], unique=False)

    op.create_table(
        "interviews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("vacancy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_email", sa.String(length=255), nullable=False),
        sa.Column("candidate_name", sa.String(length=255), nullable=False),
        sa.Column("access_token", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"],
            ["problems.id"],
            name=op.f("fk_interviews_problem_id_problems"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancies.id"],
            name=op.f("fk_interviews_vacancy_id_vacancies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interviews")),
        sa.UniqueConstraint("access_token", name=op.f("uq_interviews_access_token")),
    )
    op.create_index(op.f("ix_interviews_problem_id"), "interviews", ["problem_id"], unique=False)
    op.create_index(op.f("ix_interviews_status"), "interviews", ["status"], unique=False)
    op.create_index(op.f("ix_interviews_vacancy_id"), "interviews", ["vacancy_id"], unique=False)

    op.create_table(
        "turns",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("speaker", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_turns_interview_id_interviews"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_turns")),
    )
    op.create_index(op.f("ix_turns_interview_id"), "turns", ["interview_id"], unique=False)

    op.create_table(
        "snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_snapshots_interview_id_interviews"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_snapshots")),
    )
    op.create_index(op.f("ix_snapshots_interview_id"), "snapshots", ["interview_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_snapshots_interview_id"), table_name="snapshots")
    op.drop_table("snapshots")
    op.drop_index(op.f("ix_turns_interview_id"), table_name="turns")
    op.drop_table("turns")
    op.drop_index(op.f("ix_interviews_vacancy_id"), table_name="interviews")
    op.drop_index(op.f("ix_interviews_status"), table_name="interviews")
    op.drop_index(op.f("ix_interviews_problem_id"), table_name="interviews")
    op.drop_table("interviews")
    op.drop_index(op.f("ix_problems_language"), table_name="problems")
    op.drop_index(op.f("ix_problems_difficulty"), table_name="problems")
    op.drop_table("problems")
    op.drop_index(op.f("ix_vacancies_seniority"), table_name="vacancies")
    op.drop_index(op.f("ix_vacancies_role_category"), table_name="vacancies")
    op.drop_table("vacancies")
