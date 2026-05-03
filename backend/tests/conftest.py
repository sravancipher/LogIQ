import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import AuthContext, require_api_key
from app.db.session import get_db
from app.main import app


@pytest.fixture
def override_auth():
    app.dependency_overrides[require_api_key] = lambda: AuthContext(project_id=uuid.uuid4())
    yield
    app.dependency_overrides.pop(require_api_key, None)


@pytest.fixture
def client(override_auth):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def override_db():
    def _set(fake_db):
        app.dependency_overrides[get_db] = lambda: fake_db

    yield _set
    app.dependency_overrides.pop(get_db, None)
