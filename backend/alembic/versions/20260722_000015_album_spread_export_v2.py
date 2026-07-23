"""album spread layout and export cache v2

Revision ID: 20260722_000015
Revises: 20260720_000014
"""

from alembic import op
import sqlalchemy as sa


revision = "20260722_000015"
down_revision = "20260720_000014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("albums", sa.Column("layout_version", sa.String(length=32), nullable=False, server_default="legacy_page_v1"))
    op.create_table(
        "spreads",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("album_id", sa.String(length=36), sa.ForeignKey("albums.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.String(length=36), sa.ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("spread_number", sa.Integer(), nullable=False),
        sa.Column("recipe_key", sa.String(length=64), nullable=False),
        sa.Column("headline", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("planning_version", sa.String(length=64), nullable=False, server_default="spread-v2"),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("album_id", "spread_number", name="uq_spreads_album_number"),
    )
    op.create_index("ix_spreads_album_id", "spreads", ["album_id"])
    op.add_column("pages", sa.Column("spread_id", sa.String(length=36), nullable=True))
    op.add_column("pages", sa.Column("side", sa.String(length=8), nullable=True))
    op.add_column("pages", sa.Column("physical_page_number", sa.Integer(), nullable=True))
    op.add_column("pages", sa.Column("display_page_number", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_pages_spread_id", "pages", "spreads", ["spread_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_pages_spread_id", "pages", ["spread_id"])
    op.add_column("page_photos", sa.Column("slot_key", sa.String(length=64), nullable=True))
    op.add_column("page_photos", sa.Column("focal_x", sa.Float(), nullable=False, server_default="0.5"))
    op.add_column("page_photos", sa.Column("focal_y", sa.Float(), nullable=False, server_default="0.5"))
    op.add_column("exports", sa.Column("render_revision", sa.Integer(), nullable=True))
    op.add_column("exports", sa.Column("profile_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_exports_render_revision", "exports", ["render_revision"])
    op.create_index("ix_exports_profile_hash", "exports", ["profile_hash"])


def downgrade() -> None:
    op.drop_index("ix_exports_profile_hash", table_name="exports")
    op.drop_index("ix_exports_render_revision", table_name="exports")
    op.drop_column("exports", "profile_hash")
    op.drop_column("exports", "render_revision")
    op.drop_column("page_photos", "focal_y")
    op.drop_column("page_photos", "focal_x")
    op.drop_column("page_photos", "slot_key")
    op.drop_index("ix_pages_spread_id", table_name="pages")
    op.drop_constraint("fk_pages_spread_id", "pages", type_="foreignkey")
    op.drop_column("pages", "display_page_number")
    op.drop_column("pages", "physical_page_number")
    op.drop_column("pages", "side")
    op.drop_column("pages", "spread_id")
    op.drop_index("ix_spreads_album_id", table_name="spreads")
    op.drop_table("spreads")
    op.drop_column("albums", "layout_version")
