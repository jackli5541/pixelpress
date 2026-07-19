"""Clean up stage C fields and cache semantic embeddings."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260719_000012"
down_revision = "20260718_000011"
branch_labels = None
depends_on = None


def _normalize_candidates(connection) -> None:  # noqa: ANN001
    profile_table = sa.table(
        "album_theme_profiles",
        sa.column("id", sa.String()),
        sa.column("candidates_json", sa.JSON()),
    )
    profiles = connection.execute(
        sa.text("SELECT id, candidates_json FROM album_theme_profiles")
    ).mappings().all()
    for profile in profiles:
        normalized = []
        for raw in profile["candidates_json"] or []:
            candidate = dict(raw)
            constraints = dict(candidate.get("constraints") or {})
            include = candidate.pop("include_concepts", None)
            exclude = candidate.pop("exclude_concepts", None)
            candidate.pop("summary", None)
            if include and not constraints.get("include_concepts"):
                constraints["include_concepts"] = include
            if exclude and not constraints.get("exclude_concepts"):
                constraints["exclude_concepts"] = exclude
            candidate["constraints"] = constraints
            normalized.append(candidate)
        connection.execute(
            profile_table.update().where(profile_table.c.id == profile["id"]).values(candidates_json=normalized)
        )


def upgrade() -> None:
    op.add_column("photo_chapter_features", sa.Column("semantic_embedding", sa.JSON(), nullable=True))
    op.add_column(
        "photo_chapter_features",
        sa.Column("semantic_descriptor_hash", sa.String(length=64), nullable=True),
    )
    _normalize_candidates(op.get_bind())
    with op.batch_alter_table("album_theme_profiles") as batch:
        batch.drop_column("summary")
        batch.drop_column("include_concepts")
        batch.drop_column("exclude_concepts")
        batch.drop_column("recommended_strategy")
    with op.batch_alter_table("chapters") as batch:
        batch.alter_column(
            "clustering_confidence",
            new_column_name="clustering_quality",
            existing_type=sa.Float(),
            existing_nullable=True,
        )
    with op.batch_alter_table("chapter_segments") as batch:
        batch.alter_column(
            "clustering_confidence",
            new_column_name="clustering_quality",
            existing_type=sa.Float(),
            existing_nullable=True,
        )
    op.execute("UPDATE chapters SET clustering_quality = NULL")
    op.execute("UPDATE chapter_segments SET clustering_quality = NULL")


def downgrade() -> None:
    with op.batch_alter_table("chapter_segments") as batch:
        batch.alter_column(
            "clustering_quality",
            new_column_name="clustering_confidence",
            existing_type=sa.Float(),
            existing_nullable=True,
        )
    with op.batch_alter_table("chapters") as batch:
        batch.alter_column(
            "clustering_quality",
            new_column_name="clustering_confidence",
            existing_type=sa.Float(),
            existing_nullable=True,
        )
    with op.batch_alter_table("album_theme_profiles") as batch:
        batch.add_column(sa.Column("summary", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("include_concepts", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("exclude_concepts", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(
            sa.Column("recommended_strategy", sa.String(length=32), nullable=False, server_default="balanced")
        )
    op.drop_column("photo_chapter_features", "semantic_descriptor_hash")
    op.drop_column("photo_chapter_features", "semantic_embedding")
