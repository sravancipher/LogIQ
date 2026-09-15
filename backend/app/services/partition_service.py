from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

_PARTITION_NAME_RE = re.compile(r"^logs_(\d{4})_(\d{2})_(\d{2})$")


def _partition_name(day: date) -> str:
    return f"logs_{day:%Y_%m_%d}"


def ensure_future_partitions(db: Session, days_ahead: int | None = None) -> list[str]:
    """Create (if missing) a daily partition of `logs` for today through
    `today + days_ahead`. Idempotent - safe to call on every worker cycle or
    maintenance request.
    """
    days_ahead = settings.partition_lookahead_days if days_ahead is None else days_ahead
    today = date.today()
    ensured: list[str] = []
    for offset in range(days_ahead + 1):
        day = today + timedelta(days=offset)
        next_day = day + timedelta(days=1)
        name = _partition_name(day)
        if not _PARTITION_NAME_RE.match(name):
            continue
        db.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF logs "
                f"FOR VALUES FROM ('{day.isoformat()}') TO ('{next_day.isoformat()}')"
            )
        )
        ensured.append(name)
    return ensured


def drop_expired_partitions(db: Session, retention_days: int | None = None) -> list[str]:
    """Drop daily `logs` partitions older than the retention window. Only ever
    touches child tables matching the `logs_YYYY_MM_DD` naming convention - the
    `logs_default` safety-net partition (and anything else) is never a candidate.
    """
    retention_days = settings.log_retention_days if retention_days is None else retention_days
    cutoff = date.today() - timedelta(days=retention_days)

    rows = db.execute(
        text(
            "SELECT c.relname FROM pg_inherits i "
            "JOIN pg_class c ON c.oid = i.inhrelid "
            "JOIN pg_class p ON p.oid = i.inhparent "
            "WHERE p.relname = 'logs'"
        )
    ).fetchall()

    dropped: list[str] = []
    for (relname,) in rows:
        match = _PARTITION_NAME_RE.match(relname)
        if not match:
            continue
        partition_date = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if partition_date < cutoff:
            db.execute(text(f"DROP TABLE IF EXISTS {relname}"))
            dropped.append(relname)
    return dropped


def run_partition_maintenance(db: Session) -> dict[str, list[str]]:
    ensured = ensure_future_partitions(db)
    dropped = drop_expired_partitions(db)
    return {"partitions_ensured": ensured, "partitions_dropped": dropped}
