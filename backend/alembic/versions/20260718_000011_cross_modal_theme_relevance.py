"""Persist cross-modal theme relevance evidence."""

from alembic import op
import sqlalchemy as sa


revision = "20260718_000011"
down_revision = "20260718_000010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "photo_theme_assessments",
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "photo_theme_assessments",
        sa.Column("scoring_version", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("photo_theme_assessments", "scoring_version")
    op.drop_column("photo_theme_assessments", "evidence_json")
