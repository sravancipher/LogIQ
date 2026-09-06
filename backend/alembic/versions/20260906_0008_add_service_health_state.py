"""add service_health_state table

Revision ID: 20260906_0008
Revises: 20260906_0007
Create Date: 2026-09-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0008"
down_revision: Union[str, None] = "20260906_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_health_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_name", sa.String(length=255), nullable=False),
        sa.Column("last_status", sa.String(length=20), nullable=False),
        sa.Column("last_alerted_status", sa.String(length=20), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "service_name", name="uq_service_health_state_project_service"),
    )
    op.create_index("idx_service_health_state_project", "service_health_state", ["project_id"])


def downgrade() -> None:
    op.drop_index("idx_service_health_state_project", table_name="service_health_state")
    op.drop_table("service_health_state")
