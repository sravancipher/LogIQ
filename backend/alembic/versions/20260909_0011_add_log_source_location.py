"""add source_file/source_line to logs (chat assistant "where did this come from")

Revision ID: 20260909_0011
Revises: 20260907_0010
Create Date: 2026-09-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260909_0011"
down_revision: Union[str, None] = "20260907_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("logs", sa.Column("source_file", sa.String(length=500), nullable=True))
    op.add_column("logs", sa.Column("source_line", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("logs", "source_line")
    op.drop_column("logs", "source_file")
