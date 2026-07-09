"""initial task a schema

Revision ID: 20260704_000001
Revises: None
Create Date: 2026-07-04 00:00:01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260704_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("username", sa.String(length=100), nullable=False, unique=True),
        sa.Column("email", sa.String(length=255), nullable=True, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "albums",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("album_type", sa.String(length=64), nullable=False, server_default="yearbook"),
        sa.Column("book_size", sa.String(length=64), nullable=False, server_default="square_10inch"),
        sa.Column("theme_style", sa.String(length=64), nullable=False, server_default="minimal"),
        sa.Column("cover_title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("full_html", sa.Text(), nullable=True),
        sa.Column("photo_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "photos",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("album_id", sa.String(length=36), sa.ForeignKey("albums.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("url", sa.String(length=512), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quality_score", sa.Integer(), nullable=True),
        sa.Column("scene_tags", sa.JSON(), nullable=True),
        sa.Column("cleaning_recommendation", sa.String(length=32), nullable=True),
        sa.Column("cleaning_issues", sa.JSON(), nullable=True),
        sa.Column("custom_caption", sa.String(length=255), nullable=True),
    )

    op.create_table(
        "chapters",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("album_id", sa.String(length=36), sa.ForeignKey("albums.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, server_default="Untitled"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "pages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("album_id", sa.String(length=36), sa.ForeignKey("albums.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.String(length=36), sa.ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("template", sa.String(length=64), nullable=False, server_default="grid_3"),
        sa.Column("html", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_pages_album_page_number", "pages", ["album_id", "page_number"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("album_id", sa.String(length=36), sa.ForeignKey("albums.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("task_status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("error_message", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "exports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("album_id", sa.String(length=36), sa.ForeignKey("albums.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("format", sa.String(length=32), nullable=False, server_default="html"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("file_path", sa.String(length=512), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "chapter_photos",
        sa.Column("chapter_id", sa.String(length=36), sa.ForeignKey("chapters.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("photo_id", sa.String(length=36), sa.ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
    )
    op.create_unique_constraint("uq_chapter_photos_chapter_photo", "chapter_photos", ["chapter_id", "photo_id"])
    op.create_unique_constraint("uq_chapter_photos_chapter_order", "chapter_photos", ["chapter_id", "order_index"])

    op.create_table(
        "page_photos",
        sa.Column("page_id", sa.String(length=36), sa.ForeignKey("pages.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("photo_id", sa.String(length=36), sa.ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
    )
    op.create_unique_constraint("uq_page_photos_page_photo", "page_photos", ["page_id", "photo_id"])
    op.create_unique_constraint("uq_page_photos_page_order", "page_photos", ["page_id", "order_index"])


def downgrade() -> None:
    op.drop_constraint("uq_page_photos_page_order", "page_photos", type_="unique")
    op.drop_constraint("uq_page_photos_page_photo", "page_photos", type_="unique")
    op.drop_table("page_photos")

    op.drop_constraint("uq_chapter_photos_chapter_order", "chapter_photos", type_="unique")
    op.drop_constraint("uq_chapter_photos_chapter_photo", "chapter_photos", type_="unique")
    op.drop_table("chapter_photos")

    op.drop_table("exports")
    op.drop_table("tasks")
    op.drop_constraint("uq_pages_album_page_number", "pages", type_="unique")
    op.drop_table("pages")
    op.drop_table("chapters")
    op.drop_table("photos")
    op.drop_table("albums")
    op.drop_table("users")
