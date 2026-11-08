"""add s4 load runs and task executions with llm usage telemetry integration

Revision ID: s4_load_runs_and_tasks
Revises: s3_add_llm_usage_records
Create Date: 2026-11-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "s4_load_runs_and_tasks"
down_revision: Union[str, Sequence[str], None] = "s3_add_llm_usage_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Crear tabla s4_load_runs
    op.create_table(
        "s4_load_runs",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'planned'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "target_tasks",
            sa.Integer(),
            server_default=sa.text("1000"),
            nullable=False,
        ),
        sa.Column(
            "completed_tasks",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "failed_tasks",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "cancelled_tasks",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "budget_limit_usd",
            sa.Float(),
            server_default=sa.text("50.0"),
            nullable=False,
        ),
        sa.Column(
            "total_cost_usd",
            sa.Float(),
            server_default=sa.text("0.0"),
            nullable=False,
        ),
        sa.Column(
            "meta",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_s4_load_runs_status"), "s4_load_runs", ["status"], unique=False)
    op.create_index(op.f("ix_s4_load_runs_created_at"), "s4_load_runs", ["created_at"], unique=False)

    # 2. Crear tabla s4_task_executions
    op.create_table(
        "s4_task_executions",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("task_number", sa.Integer(), nullable=False),
        sa.Column(
            "task_type",
            sa.String(length=50),
            server_default=sa.text("'general_technical'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column("input_sanitized", sa.Text(), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column(
            "validation_passed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column(
            "lease_generation",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "model_calls",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "input_tokens",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "output_tokens",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "cost_usd",
            sa.Float(),
            server_default=sa.text("0.0"),
            nullable=False,
        ),
        sa.Column("error_sanitized", sa.Text(), nullable=True),
        sa.Column(
            "recovery_events",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["s4_load_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "task_number", name="uq_s4_task_run_number"),
    )
    op.create_index(op.f("ix_s4_task_executions_run_id"), "s4_task_executions", ["run_id"], unique=False)
    op.create_index(op.f("ix_s4_task_executions_task_type"), "s4_task_executions", ["task_type"], unique=False)
    op.create_index(op.f("ix_s4_task_executions_status"), "s4_task_executions", ["status"], unique=False)
    op.create_index(op.f("ix_s4_task_executions_heartbeat_at"), "s4_task_executions", ["heartbeat_at"], unique=False)
    op.create_index(op.f("ix_s4_task_executions_created_at"), "s4_task_executions", ["created_at"], unique=False)
    op.create_index(op.f("ix_s4_task_executions_started_at"), "s4_task_executions", ["started_at"], unique=False)
    op.create_index(op.f("ix_s4_task_executions_finished_at"), "s4_task_executions", ["finished_at"], unique=False)

    # 3. Integración en llm_usage_records
    op.add_column("llm_usage_records", sa.Column("s4_task_execution_id", sa.UUID(), nullable=True))
    op.add_column(
        "llm_usage_records",
        sa.Column("call_sequence", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column("llm_usage_records", sa.Column("gateway_request_id", sa.String(length=100), nullable=True))
    op.add_column(
        "llm_usage_records",
        sa.Column("gateway_metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.create_foreign_key(
        "fk_llm_usage_records_s4_task_execution_id",
        "llm_usage_records",
        "s4_task_executions",
        ["s4_task_execution_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_llm_usage_task_call_seq",
        "llm_usage_records",
        ["s4_task_execution_id", "call_sequence"],
    )
    op.create_index(
        op.f("ix_llm_usage_records_s4_task_execution_id"),
        "llm_usage_records",
        ["s4_task_execution_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_llm_usage_records_gateway_request_id"),
        "llm_usage_records",
        ["gateway_request_id"],
        unique=False,
    )
    op.alter_column("llm_usage_records", "interview_id", nullable=True)


def downgrade() -> None:
    op.alter_column("llm_usage_records", "interview_id", nullable=False)
    op.drop_index(op.f("ix_llm_usage_records_gateway_request_id"), table_name="llm_usage_records")
    op.drop_index(op.f("ix_llm_usage_records_s4_task_execution_id"), table_name="llm_usage_records")
    op.drop_constraint("uq_llm_usage_task_call_seq", "llm_usage_records", type_="unique")
    op.drop_constraint("fk_llm_usage_records_s4_task_execution_id", "llm_usage_records", type_="foreignkey")
    op.drop_column("llm_usage_records", "gateway_metadata")
    op.drop_column("llm_usage_records", "gateway_request_id")
    op.drop_column("llm_usage_records", "call_sequence")
    op.drop_column("llm_usage_records", "s4_task_execution_id")

    op.drop_index(op.f("ix_s4_task_executions_finished_at"), table_name="s4_task_executions")
    op.drop_index(op.f("ix_s4_task_executions_started_at"), table_name="s4_task_executions")
    op.drop_index(op.f("ix_s4_task_executions_created_at"), table_name="s4_task_executions")
    op.drop_index(op.f("ix_s4_task_executions_heartbeat_at"), table_name="s4_task_executions")
    op.drop_index(op.f("ix_s4_task_executions_status"), table_name="s4_task_executions")
    op.drop_index(op.f("ix_s4_task_executions_task_type"), table_name="s4_task_executions")
    op.drop_index(op.f("ix_s4_task_executions_run_id"), table_name="s4_task_executions")
    op.drop_table("s4_task_executions")

    op.drop_index(op.f("ix_s4_load_runs_created_at"), table_name="s4_load_runs")
    op.drop_index(op.f("ix_s4_load_runs_status"), table_name="s4_load_runs")
    op.drop_table("s4_load_runs")

