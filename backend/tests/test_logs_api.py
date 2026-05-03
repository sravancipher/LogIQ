from datetime import datetime, timezone, timedelta


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self):
        self.added = []
        self.saved = []
        self.committed = False
        self._scalar_return = None
        self._query_rows = []

    def scalar(self, *_args, **_kwargs):
        return self._scalar_return

    def set_scalar(self, value):
        self._scalar_return = value

    def set_rows(self, rows):
        self._query_rows = rows

    def bulk_save_objects(self, rows):
        self.saved.extend(rows)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def scalars(self, *_args, **_kwargs):
        return _ScalarResult(self._query_rows)


def test_ingest_logs_accepts_batch(client, override_db):
    db = _FakeDb()
    override_db(db)

    payload = {
        "logs": [
            {
                "service_name": "svc-a",
                "operation": "op-a",
                "level": "error",
                "status": "error",
                "message": "timeout",
                "error_type": "TimeoutError",
                "correlation_id": "corr-1",
                "metadata": {"k": "v"},
                "source": "sdk",
            }
        ]
    }

    response = client.post("/api/v1/logs", json=payload)

    assert response.status_code == 202
    assert response.json()["accepted"] == 1
    assert len(db.saved) == 1
    assert db.committed is True


def test_get_logs_returns_cursor_page(client, override_db):
    db = _FakeDb()
    now = datetime.now(timezone.utc)

    class _Row:
        def __init__(self, idx, created_at, msg):
            self.id = idx
            self.service_name = "svc"
            self.operation = "op"
            self.level = "ERROR"
            self.status = "error"
            self.message = msg
            self.error_type = "TimeoutError"
            self.correlation_id = f"corr-{idx}"
            self.metadata_json = {"i": idx}
            self.source = "sdk"
            self.created_at = created_at

    db.set_rows([
        _Row(3, now, "m3"),
        _Row(2, now - timedelta(seconds=1), "m2"),
    ])
    override_db(db)

    response = client.get("/api/v1/logs?limit=1")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["message"] == "m3"
    assert body["next_cursor"] is not None
