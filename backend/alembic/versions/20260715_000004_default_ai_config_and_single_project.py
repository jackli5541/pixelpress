"""add default ai configs and enforce one project per user

Revision ID: 20260715_000004
Revises: 20260704_000003
Create Date: 2026-07-15 00:00:04
"""

from __future__ import annotations

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260715_000004"
down_revision = "20260707_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    unbound = bind.execute(sa.text("SELECT id FROM projects WHERE user_id IS NULL LIMIT 1")).scalar()
    if unbound:
        raise RuntimeError("cannot enforce one project per user while unbound projects exist")

    users_without_project = bind.execute(
        sa.text("SELECT id FROM users WHERE NOT EXISTS (SELECT 1 FROM projects WHERE projects.user_id = users.id)")
    ).scalars().all()
    for user_id in users_without_project:
        project_id = str(uuid4())
        bind.execute(
            sa.text("INSERT INTO projects (id, user_id, name, code, status) VALUES (:id, :user_id, :name, :code, 'active')"),
            {"id": project_id, "user_id": user_id, "name": "Default Project", "code": f"default-{user_id[:8]}"},
        )

    duplicate_user_ids = bind.execute(
        sa.text("SELECT user_id FROM projects GROUP BY user_id HAVING count(*) > 1")
    ).scalars().all()
    for user_id in duplicate_user_ids:
        project_ids = bind.execute(
            sa.text("SELECT id FROM projects WHERE user_id = :user_id ORDER BY created_at, id"), {"user_id": user_id}
        ).scalars().all()
        keep_id, *duplicate_ids = project_ids
        active_task = bind.execute(
            sa.text("SELECT tasks.id FROM tasks JOIN albums ON albums.id = tasks.album_id WHERE albums.project_id = ANY(:project_ids) AND tasks.task_status IN ('queued', 'running') LIMIT 1"),
            {"project_ids": duplicate_ids},
        ).scalar()
        if active_task:
            raise RuntimeError(f"cannot merge projects for user {user_id} while tasks are active")
        for duplicate_id in duplicate_ids:
            bind.execute(sa.text("UPDATE albums SET project_id = :keep_id WHERE project_id = :duplicate_id"), {"keep_id": keep_id, "duplicate_id": duplicate_id})
            bind.execute(sa.text("UPDATE ai_provider_configs SET project_id = :keep_id WHERE project_id = :duplicate_id"), {"keep_id": keep_id, "duplicate_id": duplicate_id})
            bind.execute(sa.text("DELETE FROM projects WHERE id = :project_id"), {"project_id": duplicate_id})

    op.alter_column("projects", "user_id", existing_type=sa.String(length=36), nullable=False)
    op.create_unique_constraint("uq_projects_user_id", "projects", ["user_id"])

    op.create_table(
        "default_ai_provider_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=False),
        sa.Column("api_key_masked", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_by_admin_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_admin_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("stage", name="uq_default_ai_provider_configs_stage"),
    )


def downgrade() -> None:
    op.drop_table("default_ai_provider_configs")
    op.drop_constraint("uq_projects_user_id", "projects", type_="unique")
    op.alter_column("projects", "user_id", existing_type=sa.String(length=36), nullable=True)
