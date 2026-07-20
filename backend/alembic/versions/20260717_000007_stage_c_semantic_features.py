"""stage c semantic photo features

Revision ID: 20260717_000007
Revises: 20260716_000006
Create Date: 2026-07-17 00:00:07
"""

from alembic import op
import sqlalchemy as sa


revision = "20260717_000007"
down_revision = "20260716_000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "photo_chapter_features",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("photo_id", sa.String(length=36), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("feature_version", sa.String(length=64), nullable=False),
        sa.Column("embedding_provider", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("semantic_provider", sa.String(length=64), nullable=True),
        sa.Column("semantic_model", sa.String(length=128), nullable=False),
        sa.Column("semantic_payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "photo_id",
            "content_sha256",
            "feature_version",
            "embedding_model",
            "embedding_dimension",
            "semantic_model",
            name="uq_photo_chapter_feature_cache_key",
        ),
    )
    op.create_index("ix_photo_chapter_features_photo_id", "photo_chapter_features", ["photo_id"])


def downgrade() -> None:
    op.drop_index("ix_photo_chapter_features_photo_id", table_name="photo_chapter_features")
    op.drop_table("photo_chapter_features")
