"""convert logs to native RANGE partitioning by day, apply retention now

Revision ID: 20260915_0012
Revises: 20260909_0011
Create Date: 2026-09-15

Converts the flat `logs` table into a Postgres RANGE-partitioned-by-day table
(partition key `created_at`). Rows older than RETENTION_DAYS are permanently
dropped as part of this one-time cutover (confirmed with the project owner);
going forward, retention is enforced by app.services.partition_service, driven
by the runtime `settings.log_retention_days` setting - RETENTION_DAYS below is
a fixed, local constant only for this migration's own cutover point, and does
not change if that setting is edited later.

Postgres requires every unique constraint on a partitioned table (including the
primary key) to include the partition key, so `id` alone can no longer be the
sole primary key - it becomes a composite (id, created_at). Nothing in this
schema has a foreign key into logs.id, so this is safe.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260915_0012"
down_revision: Union[str, None] = "20260909_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RETENTION_DAYS = 7
LOOKAHEAD_DAYS = 3

_COLUMNS = (
    "id, project_id, service_name, operation, level, status, message, "
    "error_type, correlation_id, metadata_json, source, source_file, "
    "source_line, created_at"
)


def _partition_name(day: date) -> str:
    return f"logs_{day:%Y_%m_%d}"


def upgrade() -> None:
    op.execute("ALTER SEQUENCE logs_id_seq OWNED BY NONE")

    op.execute(
        """
        CREATE TABLE logs_new (
            id integer NOT NULL DEFAULT nextval('logs_id_seq'),
            project_id uuid NOT NULL,
            service_name varchar(255),
            operation varchar(255),
            level varchar(20) NOT NULL,
            status varchar(50),
            message text NOT NULL,
            error_type varchar(255),
            correlation_id varchar(255),
            metadata_json json,
            source varchar(50) NOT NULL,
            source_file varchar(500),
            source_line integer,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
        """
    )
    op.execute(
        "ALTER TABLE logs_new ADD CONSTRAINT logs_project_id_fkey "
        "FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE"
    )
    # Temporary index names: the old `logs` table (still present until the DROP
    # TABLE below) already holds indexes named idx_logs_*, and Postgres index
    # names must be unique per-schema, not per-table - collide now, rename after.
    op.execute("CREATE INDEX tmp_new_idx_logs_project ON logs_new (project_id)")
    op.execute("CREATE INDEX tmp_new_idx_logs_service ON logs_new (service_name)")
    op.execute("CREATE INDEX tmp_new_idx_logs_level ON logs_new (level)")
    op.execute("CREATE INDEX tmp_new_idx_logs_correlation ON logs_new (correlation_id)")
    op.execute("CREATE INDEX tmp_new_idx_logs_time ON logs_new (created_at)")
    op.execute("CREATE INDEX tmp_new_idx_logs_project_created ON logs_new (project_id, created_at)")

    op.execute("CREATE TABLE logs_default PARTITION OF logs_new DEFAULT")

    today = date.today()
    cutoff = today - timedelta(days=RETENTION_DAYS)
    day = cutoff
    while day <= today + timedelta(days=LOOKAHEAD_DAYS):
        next_day = day + timedelta(days=1)
        op.execute(
            f"CREATE TABLE {_partition_name(day)} PARTITION OF logs_new "
            f"FOR VALUES FROM ('{day.isoformat()}') TO ('{next_day.isoformat()}')"
        )
        day = next_day

    op.execute(
        f"INSERT INTO logs_new ({_COLUMNS}) "
        f"SELECT {_COLUMNS} FROM logs WHERE created_at >= '{cutoff.isoformat()}'"
    )
    op.execute("SELECT setval('logs_id_seq', COALESCE((SELECT MAX(id) FROM logs_new), 1))")

    op.execute("DROP TABLE logs")
    op.execute("ALTER TABLE logs_new RENAME TO logs")
    op.execute("ALTER SEQUENCE logs_id_seq OWNED BY logs.id")

    op.execute("ALTER INDEX tmp_new_idx_logs_project RENAME TO idx_logs_project")
    op.execute("ALTER INDEX tmp_new_idx_logs_service RENAME TO idx_logs_service")
    op.execute("ALTER INDEX tmp_new_idx_logs_level RENAME TO idx_logs_level")
    op.execute("ALTER INDEX tmp_new_idx_logs_correlation RENAME TO idx_logs_correlation")
    op.execute("ALTER INDEX tmp_new_idx_logs_time RENAME TO idx_logs_time")
    op.execute("ALTER INDEX tmp_new_idx_logs_project_created RENAME TO idx_logs_project_created")
    op.execute("ALTER TABLE logs RENAME CONSTRAINT logs_new_pkey TO logs_pkey")


def downgrade() -> None:
    op.execute("ALTER SEQUENCE logs_id_seq OWNED BY NONE")

    op.create_table(
        "logs_flat",
        sa.Column("id", sa.Integer(), server_default=sa.text("nextval('logs_id_seq')"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_name", sa.String(length=255), nullable=True),
        sa.Column("operation", sa.String(length=255), nullable=True),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("error_type", sa.String(length=255), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_file", sa.String(length=500), nullable=True),
        sa.Column("source_line", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.execute(f"INSERT INTO logs_flat ({_COLUMNS}) SELECT {_COLUMNS} FROM logs")
    op.execute("SELECT setval('logs_id_seq', COALESCE((SELECT MAX(id) FROM logs_flat), 1))")

    op.execute("DROP TABLE logs")
    op.execute("ALTER TABLE logs_flat RENAME TO logs")
    op.execute("ALTER SEQUENCE logs_id_seq OWNED BY logs.id")

    op.create_index("idx_logs_project", "logs", ["project_id"])
    op.create_index("idx_logs_service", "logs", ["service_name"])
    op.create_index("idx_logs_level", "logs", ["level"])
    op.create_index("idx_logs_correlation", "logs", ["correlation_id"])
    op.create_index("idx_logs_time", "logs", ["created_at"])
