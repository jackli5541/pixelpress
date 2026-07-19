"""Use image embeddings only for chapter classification.

Revision ID: 20260719_000013
Revises: 20260719_000012
"""

from alembic import op
import sqlalchemy as sa


revision = "20260719_000013"
down_revision = "20260719_000012"
branch_labels = None
depends_on = None


OLD_CONSTRAINT = "uq_photo_chapter_feature_cache_key"
NEW_FEATURE_VERSION = "c4-image-embedding-only-v1"


def upgrade() -> None:
    with op.batch_alter_table("photo_chapter_features") as batch:
        batch.drop_constraint(OLD_CONSTRAINT, type_="unique")

    op.execute(
        sa.text(
            """
            UPDATE photo_chapter_features
            SET feature_version = :version,
                status = 'success',
                error_code = NULL,
                error_message = NULL
            WHERE embedding IS NOT NULL
            """
        ).bindparams(version=NEW_FEATURE_VERSION)
    )
    op.execute(
        """
        DELETE FROM photo_chapter_features
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY photo_id, content_sha256, feature_version,
                                        embedding_provider, embedding_model, embedding_dimension
                           ORDER BY updated_at DESC, id DESC
                       ) AS duplicate_index
                FROM photo_chapter_features
            ) AS ranked
            WHERE duplicate_index > 1
        )
        """
    )

    with op.batch_alter_table("photo_chapter_features") as batch:
        batch.drop_column("semantic_descriptor_hash")
        batch.drop_column("semantic_embedding")
        batch.drop_column("semantic_payload")
        batch.drop_column("semantic_model")
        batch.drop_column("semantic_provider")
        batch.create_unique_constraint(
            OLD_CONSTRAINT,
            [
                "photo_id",
                "content_sha256",
                "feature_version",
                "embedding_provider",
                "embedding_model",
                "embedding_dimension",
            ],
        )


def downgrade() -> None:
    with op.batch_alter_table("photo_chapter_features") as batch:
        batch.drop_constraint(OLD_CONSTRAINT, type_="unique")
        batch.add_column(sa.Column("semantic_provider", sa.String(length=64), nullable=True))
        batch.add_column(
            sa.Column("semantic_model", sa.String(length=128), nullable=False, server_default="")
        )
        batch.add_column(sa.Column("semantic_payload", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("semantic_embedding", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("semantic_descriptor_hash", sa.String(length=64), nullable=True))
        batch.create_unique_constraint(
            OLD_CONSTRAINT,
            [
                "photo_id",
                "content_sha256",
                "feature_version",
                "embedding_model",
                "embedding_dimension",
                "semantic_model",
            ],
        )
