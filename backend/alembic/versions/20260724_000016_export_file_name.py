"""add user-visible export file name

Revision ID: 20260724_000016
Revises: 20260722_000015
"""

from alembic import op
import sqlalchemy as sa


revision = "20260724_000016"
down_revision = "20260722_000015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exports", sa.Column("file_name", sa.String(length=160), nullable=True))


def downgrade() -> None:
    op.drop_column("exports", "file_name")
