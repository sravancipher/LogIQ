"""20260426_0005 — add insight_feedback table

Revision ID: 20260426_0005
Revises: 20260426_0004
Create Date: 2026-04-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260426_0005"
down_revision: str = "20260426_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "insight_feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.String(length=10), nullable=False),
        sa.Column("lookback_minutes", sa.Integer(), nullable=False),
        sa.Column("analysis_mode", sa.String(length=20), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("root_cause", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=False),
        sa.Column("incident_summary", sa.Text(), nullable=True),
        sa.Column("correction", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_insight_feedback_project_created",
        "insight_feedback",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_insight_feedback_project_created", table_name="insight_feedback")
    op.drop_table("insight_feedback")
