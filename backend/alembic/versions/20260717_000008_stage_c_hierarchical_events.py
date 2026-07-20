"""stage c hierarchical events

Revision ID: 20260717_000008
Revises: 20260717_000007
Create Date: 2026-07-17 00:00:08
"""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260717_000008"
down_revision = "20260717_000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chapter_segments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("chapter_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, server_default="活动阶段"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("segment_type", sa.String(length=64), nullable=False, server_default="scene"),
        sa.Column("time_range", sa.String(length=128), nullable=True),
        sa.Column("clustering_confidence", sa.Float(), nullable=True),
        sa.Column("clustering_needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("clustering_explanation", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chapter_id", "order_index", name="uq_chapter_segments_chapter_order"),
    )
    op.add_column("chapter_photos", sa.Column("segment_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_chapter_photos_segment_id",
        "chapter_photos",
        "chapter_segments",
        ["segment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_chapter_photos_segment_id", "chapter_photos", ["segment_id"])

    connection = op.get_bind()
    chapters = connection.execute(sa.text("SELECT id, name, description FROM chapters")).mappings().all()
    for chapter in chapters:
        segment_id = str(uuid4())
        connection.execute(
            sa.text(
                """
                INSERT INTO chapter_segments (
                    id, chapter_id, name, description, order_index, segment_type,
                    clustering_needs_review, created_at, updated_at
                ) VALUES (
                    :id, :chapter_id, :name, :description, 0, 'legacy', false, now(), now()
                )
                """
            ),
            {
                "id": segment_id,
                "chapter_id": chapter["id"],
                "name": chapter["name"] or "活动阶段",
                "description": chapter["description"] or "",
            },
        )
        connection.execute(
            sa.text("UPDATE chapter_photos SET segment_id = :segment_id WHERE chapter_id = :chapter_id"),
            {"segment_id": segment_id, "chapter_id": chapter["id"]},
        )


def downgrade() -> None:
    op.drop_index("ix_chapter_photos_segment_id", table_name="chapter_photos")
    op.drop_constraint("fk_chapter_photos_segment_id", "chapter_photos", type_="foreignkey")
    op.drop_column("chapter_photos", "segment_id")
    op.drop_table("chapter_segments")
