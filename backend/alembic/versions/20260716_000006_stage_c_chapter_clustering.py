"""stage c chapter clustering

Revision ID: 20260716_000006
Revises: 20260715_000005
Create Date: 2026-07-16 00:00:06
"""

from alembic import op
import sqlalchemy as sa


revision = "20260716_000006"
down_revision = "20260715_000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chapters",
        sa.Column("clustering_source", sa.String(length=32), nullable=False, server_default="legacy"),
    )
    op.add_column("chapters", sa.Column("clustering_algorithm_version", sa.String(length=64), nullable=True))
    op.add_column("chapters", sa.Column("clustering_confidence", sa.Float(), nullable=True))
    op.add_column(
        "chapters",
        sa.Column("clustering_needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("chapters", sa.Column("clustering_explanation", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("chapters", "clustering_explanation")
    op.drop_column("chapters", "clustering_needs_review")
    op.drop_column("chapters", "clustering_confidence")
    op.drop_column("chapters", "clustering_algorithm_version")
    op.drop_column("chapters", "clustering_source")
