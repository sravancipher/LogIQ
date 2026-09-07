"""add api_version to llm_settings (multi-provider LLM support)

Revision ID: 20260907_0009
Revises: 20260906_0008
Create Date: 2026-09-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260907_0009"
down_revision: Union[str, None] = "20260906_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("llm_settings", sa.Column("api_version", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("llm_settings", "api_version")
