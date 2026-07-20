"""add stage to project AI configurations

Revision ID: 20260720_000014
Revises: 20260719_000013
"""

from alembic import op
import sqlalchemy as sa

revision = "20260720_000014"
down_revision = "20260719_000013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_provider_configs", sa.Column("stage", sa.String(length=32), nullable=True))
    op.create_index("ix_ai_provider_configs_project_stage", "ai_provider_configs", ["project_id", "stage"])


def downgrade() -> None:
    op.drop_index("ix_ai_provider_configs_project_stage", table_name="ai_provider_configs")
    op.drop_column("ai_provider_configs", "stage")
