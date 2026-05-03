"""add last_used_at to api_keys

Revision ID: 20260426_0002
Revises: 20260426_0001
Create Date: 2026-04-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260426_0002"
down_revision: Union[str, None] = "20260426_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("idx_api_keys_last_used_at", "api_keys", ["last_used_at"])


def downgrade() -> None:
    op.drop_index("idx_api_keys_last_used_at", table_name="api_keys")
    op.drop_column("api_keys", "last_used_at")
