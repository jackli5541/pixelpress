"""theme curation and theme-aware chaptering

Revision ID: 20260717_000009
Revises: 20260717_000008
Create Date: 2026-07-17 00:00:09
"""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260717_000009"
down_revision = "20260717_000008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("albums", sa.Column("theme_input_revision", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "album_theme_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("album_id", sa.String(length=36), nullable=False),
        sa.Column("analysis_task_id", sa.String(length=36), nullable=True),
        sa.Column("selection_task_id", sa.String(length=36), nullable=True),
        sa.Column("analysis_revision", sa.Integer(), nullable=False),
        sa.Column("confirmed_revision", sa.Integer(), nullable=True),
        sa.Column("profile_version", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("include_concepts", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("exclude_concepts", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("candidates_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("chapter_strategy", sa.String(length=32), nullable=False, server_default="balanced"),
        sa.Column("recommended_strategy", sa.String(length=32), nullable=False, server_default="balanced"),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("custom_input", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["album_id"], ["albums.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["analysis_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["selection_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_album_theme_profiles_album_status", "album_theme_profiles", ["album_id", "status"])
    op.create_table(
        "photo_theme_assessments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("album_id", sa.String(length=36), nullable=False),
        sa.Column("photo_id", sa.String(length=36), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("relevance_label", sa.String(length=32), nullable=False),
        sa.Column("suggested_decision", sa.String(length=32), nullable=False),
        sa.Column("user_decision", sa.String(length=32), nullable=True),
        sa.Column("reasons_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("feature_version", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["album_theme_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["album_id"], ["albums.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "photo_id", name="uq_photo_theme_assessments_profile_photo"),
    )
    op.create_index("ix_photo_theme_assessments_album_id", "photo_theme_assessments", ["album_id"])
    op.create_index("ix_photo_theme_assessments_photo_id", "photo_theme_assessments", ["photo_id"])
    op.create_table(
        "photo_theme_decision_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("album_id", sa.String(length=36), nullable=False),
        sa.Column("photo_id", sa.String(length=36), nullable=False),
        sa.Column("previous_decision", sa.String(length=32), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["album_theme_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["album_id"], ["albums.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_photo_theme_decision_events_album_id", "photo_theme_decision_events", ["album_id"])
    op.create_index("ix_photo_theme_decision_events_photo_id", "photo_theme_decision_events", ["photo_id"])

    connection = op.get_bind()
    albums = connection.execute(sa.text("SELECT id, theme_input_revision FROM albums")).mappings().all()
    for album in albums:
        connection.execute(
            sa.text(
                """
                INSERT INTO album_theme_profiles (
                    id, album_id, analysis_revision, confirmed_revision, profile_version,
                    source, status, title, summary, include_concepts, exclude_concepts,
                    candidates_json, chapter_strategy, recommended_strategy, fallback_used,
                    confirmed_at, created_at, updated_at
                ) VALUES (
                    :id, :album_id, :revision, :revision, 'theme-curation-v1',
                    'migration', 'confirmed', '完整记录', '保留所有通过技术清洗的照片',
                    '[]', '[]', '[]', 'balanced', 'balanced', true, now(), now(), now()
                )
                """
            ),
            {"id": str(uuid4()), "album_id": album["id"], "revision": album["theme_input_revision"]},
        )


def downgrade() -> None:
    op.drop_index("ix_photo_theme_decision_events_photo_id", table_name="photo_theme_decision_events")
    op.drop_index("ix_photo_theme_decision_events_album_id", table_name="photo_theme_decision_events")
    op.drop_table("photo_theme_decision_events")
    op.drop_index("ix_photo_theme_assessments_photo_id", table_name="photo_theme_assessments")
    op.drop_index("ix_photo_theme_assessments_album_id", table_name="photo_theme_assessments")
    op.drop_table("photo_theme_assessments")
    op.drop_index("ix_album_theme_profiles_album_status", table_name="album_theme_profiles")
    op.drop_table("album_theme_profiles")
    op.drop_column("albums", "theme_input_revision")
