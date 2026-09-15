from datetime import date

from app.services import partition_service
from app.services.partition_service import drop_expired_partitions, ensure_future_partitions


class _FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetchall(self):
        return self._rows


class _FakeDb:
    def __init__(self, partition_rows=None):
        self.executed: list[str] = []
        self._partition_rows = partition_rows or []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.executed.append(sql)
        if "pg_inherits" in sql:
            return _FakeResult(self._partition_rows)
        return _FakeResult()


class _FixedDate(date):
    @classmethod
    def today(cls):
        return date(2026, 9, 15)


def test_ensure_future_partitions_creates_expected_date_range(monkeypatch):
    monkeypatch.setattr(partition_service, "date", _FixedDate)
    db = _FakeDb()

    created = ensure_future_partitions(db, days_ahead=2)

    assert created == ["logs_2026_09_15", "logs_2026_09_16", "logs_2026_09_17"]
    assert any("FOR VALUES FROM ('2026-09-15') TO ('2026-09-16')" in s for s in db.executed)
    assert all("CREATE TABLE IF NOT EXISTS" in s for s in db.executed)


def test_drop_expired_partitions_only_drops_dated_partitions_past_retention(monkeypatch):
    monkeypatch.setattr(partition_service, "date", _FixedDate)
    db = _FakeDb(
        partition_rows=[
            ("logs_2026_09_01",),  # 14 days old -> expired
            ("logs_2026_09_10",),  # 5 days old -> kept
            ("logs_default",),  # never a candidate
            ("some_unrelated_table",),  # doesn't match naming convention
        ]
    )

    dropped = drop_expired_partitions(db, retention_days=7)

    assert dropped == ["logs_2026_09_01"]
    assert any("DROP TABLE IF EXISTS logs_2026_09_01" in s for s in db.executed)
    assert not any("logs_2026_09_10" in s for s in db.executed if "DROP" in s)
    assert not any("logs_default" in s for s in db.executed if "DROP" in s)
