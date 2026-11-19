from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.api.fakes import FakeDb
from worker.api.deps import get_db, get_settings
from worker.main import app
from worker.settings import Settings

SERVICE_TOKEN = "service-secret"


@pytest.fixture
def db() -> FakeDb:
    return FakeDb()


@pytest.fixture
def client(db: FakeDb) -> Iterator[TestClient]:
    settings = Settings(n8n_service_token=SecretStr(SERVICE_TOKEN))
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app)
    app.dependency_overrides.clear()


OWNER = {"Authorization": "Bearer owner-jwt"}
SERVICE = {"X-Service-Token": SERVICE_TOKEN}
