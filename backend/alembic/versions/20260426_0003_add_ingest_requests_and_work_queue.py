"""add ingest_requests and work_queue_items tables (no-op, see upgrade())

Revision ID: 20260426_0003
Revises: 20260426_0002
Create Date: 2026-04-26
"""

from typing import Sequence, Union

revision: str = "20260426_0003"
down_revision: Union[str, None] = "20260426_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ingest_requests and work_queue_items are already created by 20260426_0001;
    # this revision is kept as a no-op merge point so the chain (...->0002->0003->0004->...)
    # stays intact without re-creating tables that already exist.
    pass


def downgrade() -> None:
    pass
