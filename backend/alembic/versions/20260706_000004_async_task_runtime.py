"""add async task runtime fields and render artifact refs

Revision ID: 20260706_000004
Revises: 20260704_000003
Create Date: 2026-07-06 00:00:04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260706_000004"
down_revision = "20260704_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("albums", sa.Column("content_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("albums", sa.Column("render_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("albums", sa.Column("preview_html_path", sa.String(length=512), nullable=True))
    op.add_column("albums", sa.Column("print_html_path", sa.String(length=512), nullable=True))
    op.add_column("albums", sa.Column("render_manifest_path", sa.String(length=512), nullable=True))

    op.add_column("tasks", sa.Column("job_id", sa.String(length=128), nullable=True))
    op.add_column("tasks", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.add_column("tasks", sa.Column("task_params", sa.JSON(), nullable=True))
    op.add_column("tasks", sa.Column("resource_type", sa.String(length=32), nullable=True))
    op.add_column("tasks", sa.Column("resource_id", sa.String(length=64), nullable=True))
    op.add_column("tasks", sa.Column("requested_revision", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("result_revision", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("progress_pct", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("progress_step", sa.String(length=128), nullable=True))
    op.add_column("tasks", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tasks", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("tasks", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("worker_name", sa.String(length=128), nullable=True))
    op.add_column("tasks", sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("tasks", sa.Column("error_code", sa.String(length=64), nullable=True))
    op.add_column("tasks", sa.Column("fallback_reason", sa.String(length=255), nullable=True))
    op.add_column("tasks", sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("tasks", sa.Column("pipeline_name", sa.String(length=64), nullable=True))
    op.add_column("tasks", sa.Column("pipeline_version", sa.String(length=64), nullable=True))
    op.add_column("tasks", sa.Column("metrics_payload", sa.JSON(), nullable=True))
    op.alter_column("tasks", "error_message", existing_type=sa.String(length=255), type_=sa.Text(), existing_nullable=True)

    op.create_index("ix_tasks_album_status", "tasks", ["album_id", "task_status"], unique=False)
    op.create_index("ix_tasks_idempotency_key", "tasks", ["idempotency_key"], unique=False)
    op.create_index("ix_tasks_job_id", "tasks", ["job_id"], unique=False)
    op.create_index("ix_tasks_status_heartbeat", "tasks", ["task_status", "heartbeat_at"], unique=False)

    op.create_table(
        "task_dispatches",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("job_name", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("dispatch_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.alter_column("albums", "content_revision", server_default=None)
    op.alter_column("albums", "render_revision", server_default=None)
    op.alter_column("tasks", "attempt_count", server_default=None)
    op.alter_column("tasks", "max_attempts", server_default=None)
    op.alter_column("tasks", "retryable", server_default=None)
    op.alter_column("tasks", "cancel_requested", server_default=None)


def downgrade() -> None:
    op.drop_table("task_dispatches")

    op.drop_index("ix_tasks_status_heartbeat", table_name="tasks")
    op.drop_index("ix_tasks_job_id", table_name="tasks")
    op.drop_index("ix_tasks_idempotency_key", table_name="tasks")
    op.drop_index("ix_tasks_album_status", table_name="tasks")

    op.alter_column("tasks", "error_message", existing_type=sa.Text(), type_=sa.String(length=255), existing_nullable=True)
    op.drop_column("tasks", "metrics_payload")
    op.drop_column("tasks", "pipeline_version")
    op.drop_column("tasks", "pipeline_name")
    op.drop_column("tasks", "cancel_requested")
    op.drop_column("tasks", "fallback_reason")
    op.drop_column("tasks", "error_code")
    op.drop_column("tasks", "retryable")
    op.drop_column("tasks", "worker_name")
    op.drop_column("tasks", "finished_at")
    op.drop_column("tasks", "heartbeat_at")
    op.drop_column("tasks", "started_at")
    op.drop_column("tasks", "max_attempts")
    op.drop_column("tasks", "attempt_count")
    op.drop_column("tasks", "progress_step")
    op.drop_column("tasks", "progress_pct")
    op.drop_column("tasks", "result_revision")
    op.drop_column("tasks", "requested_revision")
    op.drop_column("tasks", "resource_id")
    op.drop_column("tasks", "resource_type")
    op.drop_column("tasks", "task_params")
    op.drop_column("tasks", "idempotency_key")
    op.drop_column("tasks", "job_id")

    op.drop_column("albums", "render_manifest_path")
    op.drop_column("albums", "print_html_path")
    op.drop_column("albums", "preview_html_path")
    op.drop_column("albums", "render_revision")
    op.drop_column("albums", "content_revision")
