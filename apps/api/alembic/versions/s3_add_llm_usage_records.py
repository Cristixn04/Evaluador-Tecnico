"""add llm_usage_records table for persistent telemetry

Revision ID: s3_add_llm_usage_records
Revises: merge_evaluation_invitations
Create Date: 2026-11-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "s3_add_llm_usage_records"
down_revision: Union[str, Sequence[str], None] = "merge_evaluation_invitations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_records",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("turn_id", sa.UUID(), nullable=True),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("tokens_input", sa.Integer(), nullable=True),
        sa.Column("tokens_output", sa.Integer(), nullable=True),
        sa.Column("tokens_total", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column(
            "measurement_status",
            sa.String(length=20),
            server_default=sa.text("'measured'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_llm_usage_records_interview_id"), "llm_usage_records", ["interview_id"], unique=False)
    op.create_index(op.f("ix_llm_usage_records_turn_id"), "llm_usage_records", ["turn_id"], unique=False)
    op.create_index(op.f("ix_llm_usage_records_stage"), "llm_usage_records", ["stage"], unique=False)
    op.create_index(op.f("ix_llm_usage_records_created_at"), "llm_usage_records", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_llm_usage_records_created_at"), table_name="llm_usage_records")
    op.drop_index(op.f("ix_llm_usage_records_stage"), table_name="llm_usage_records")
    op.drop_index(op.f("ix_llm_usage_records_turn_id"), table_name="llm_usage_records")
    op.drop_index(op.f("ix_llm_usage_records_interview_id"), table_name="llm_usage_records")
    op.drop_table("llm_usage_records")
