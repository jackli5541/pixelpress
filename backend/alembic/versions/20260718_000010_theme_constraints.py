"""Persist normalized theme constraints."""

from alembic import op
import sqlalchemy as sa


revision = "20260718_000010"
down_revision = "20260717_000009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "album_theme_profiles",
        sa.Column("constraints_json", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("album_theme_profiles", "constraints_json")
