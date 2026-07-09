"""add ai and print metadata

Revision ID: 20260704_000002
Revises: 20260704_000001
Create Date: 2026-07-04 00:00:02
"""

from alembic import op
import sqlalchemy as sa


revision = "20260704_000002"
down_revision = "20260704_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("albums", sa.Column("print_spec_json", sa.JSON(), nullable=True))

    op.add_column("pages", sa.Column("meta_json", sa.JSON(), nullable=True))

    op.add_column("tasks", sa.Column("provider", sa.String(length=64), nullable=True))
    op.add_column("tasks", sa.Column("model", sa.String(length=128), nullable=True))
    op.add_column("tasks", sa.Column("result_payload", sa.JSON(), nullable=True))
    op.add_column("tasks", sa.Column("debug_payload", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "debug_payload")
    op.drop_column("tasks", "result_payload")
    op.drop_column("tasks", "model")
    op.drop_column("tasks", "provider")
    op.drop_column("pages", "meta_json")
    op.drop_column("albums", "print_spec_json")
