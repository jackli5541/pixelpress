"""stage b photo cleaning

Revision ID: 20260715_000005
Revises: 20260715_000004
Create Date: 2026-07-15 00:00:05
"""

from alembic import op
import sqlalchemy as sa


revision = "20260715_000005"
down_revision = "20260715_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("photos", "quality_score", existing_type=sa.Integer(), type_=sa.Float(), existing_nullable=True)
    op.add_column("photos", sa.Column("content_sha256", sa.String(length=64), nullable=True))
    op.add_column("photos", sa.Column("perceptual_hash", sa.String(length=16), nullable=True))
    op.add_column("photos", sa.Column("cleaning_analysis_version", sa.String(length=64), nullable=True))
    op.add_column("photos", sa.Column("cleaning_task_id", sa.String(length=36), nullable=True))
    op.add_column("photos", sa.Column("cleaning_features", sa.JSON(), nullable=True))
    op.add_column("photos", sa.Column("cleaning_suggestion", sa.String(length=32), nullable=True))
    op.add_column("photos", sa.Column("cleaning_confidence", sa.Float(), nullable=True))
    op.add_column("photos", sa.Column("cleaning_decision", sa.String(length=32), nullable=True))
    op.add_column("photos", sa.Column("cleaning_decision_source", sa.String(length=64), nullable=True))
    op.add_column("photos", sa.Column("cleaning_decided_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_photos_cleaning_task", "photos", "tasks", ["cleaning_task_id"], ["id"], ondelete="SET NULL")
    op.execute("UPDATE photos SET cleaning_suggestion = cleaning_recommendation WHERE cleaning_recommendation IS NOT NULL")
    op.execute("UPDATE photos SET cleaning_recommendation = NULL")

    op.create_table(
        "cleaning_duplicate_groups",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("album_id", sa.String(length=36), sa.ForeignKey("albums.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("analysis_version", sa.String(length=64), nullable=False),
        sa.Column("group_type", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("preferred_photo_id", sa.String(length=36), sa.ForeignKey("photos.id", ondelete="SET NULL"), nullable=True),
        sa.Column("thresholds_json", sa.JSON(), nullable=True),
        sa.Column("explanation_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cleaning_duplicate_groups_album_id", "cleaning_duplicate_groups", ["album_id"])

    op.create_table(
        "cleaning_duplicate_members",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("group_id", sa.String(length=36), sa.ForeignKey("cleaning_duplicate_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("photo_id", sa.String(length=36), sa.ForeignKey("photos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(length=32), nullable=False),
        sa.Column("hamming_distance", sa.Integer(), nullable=True),
        sa.Column("burst_time_delta_ms", sa.Integer(), nullable=True),
        sa.Column("preferred_score", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("is_preferred", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("auto_excluded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("factors_json", sa.JSON(), nullable=True),
        sa.UniqueConstraint("group_id", "photo_id", name="uq_cleaning_group_photo"),
    )
    op.create_index("ix_cleaning_duplicate_members_group_id", "cleaning_duplicate_members", ["group_id"])
    op.create_index("ix_cleaning_duplicate_members_photo_id", "cleaning_duplicate_members", ["photo_id"])

    op.create_table(
        "photo_cleaning_decision_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("album_id", sa.String(length=36), sa.ForeignKey("albums.id", ondelete="CASCADE"), nullable=False),
        sa.Column("photo_id", sa.String(length=36), sa.ForeignKey("photos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("group_id", sa.String(length=36), sa.ForeignKey("cleaning_duplicate_groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("previous_decision", sa.String(length=32), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_photo_cleaning_decision_events_album_id", "photo_cleaning_decision_events", ["album_id"])
    op.create_index("ix_photo_cleaning_decision_events_photo_id", "photo_cleaning_decision_events", ["photo_id"])


def downgrade() -> None:
    op.drop_table("photo_cleaning_decision_events")
    op.drop_table("cleaning_duplicate_members")
    op.drop_table("cleaning_duplicate_groups")
    op.drop_constraint("fk_photos_cleaning_task", "photos", type_="foreignkey")
    op.drop_column("photos", "cleaning_decided_at")
    op.drop_column("photos", "cleaning_decision_source")
    op.drop_column("photos", "cleaning_decision")
    op.drop_column("photos", "cleaning_confidence")
    op.drop_column("photos", "cleaning_suggestion")
    op.drop_column("photos", "cleaning_features")
    op.drop_column("photos", "cleaning_task_id")
    op.drop_column("photos", "cleaning_analysis_version")
    op.drop_column("photos", "perceptual_hash")
    op.drop_column("photos", "content_sha256")
    op.alter_column("photos", "quality_score", existing_type=sa.Float(), type_=sa.Integer(), existing_nullable=True)
