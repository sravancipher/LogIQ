"""20260426_0004 — add cloud_integrations table

Revision ID: 20260426_0004
Revises: 20260426_0003
Create Date: 2026-04-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision: str = "20260426_0004"
down_revision: str = "20260426_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cloud_integrations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("webhook_token", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_cloud_integrations_project",
        "cloud_integrations",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_cloud_integrations_project", table_name="cloud_integrations")
    op.drop_table("cloud_integrations")
