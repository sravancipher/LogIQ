"""add llm_settings table

Revision ID: 20260906_0006
Revises: 20260426_0005
Create Date: 2026-09-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0006"
down_revision: Union[str, None] = "20260426_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("api_key", sa.String(length=500), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", name="uq_llm_settings_project"),
    )


def downgrade() -> None:
    op.drop_table("llm_settings")
