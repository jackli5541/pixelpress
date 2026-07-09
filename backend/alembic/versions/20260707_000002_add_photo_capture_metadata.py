"""add photo capture metadata

Revision ID: 20260707_000002
Revises: 20260704_000001
Create Date: 2026-07-07 00:00:02
"""

from alembic import op
import sqlalchemy as sa


revision = "20260707_000002"
down_revision = "20260706_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("photos", sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("photos", sa.Column("taken_timezone", sa.String(length=64), nullable=True))
    op.add_column("photos", sa.Column("gps_latitude", sa.Float(), nullable=True))
    op.add_column("photos", sa.Column("gps_longitude", sa.Float(), nullable=True))
    op.add_column("photos", sa.Column("device_model", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("photos", "device_model")
    op.drop_column("photos", "gps_longitude")
    op.drop_column("photos", "gps_latitude")
    op.drop_column("photos", "taken_timezone")
    op.drop_column("photos", "taken_at")
