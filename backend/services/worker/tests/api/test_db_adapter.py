import json
from typing import Any

import pytest

from worker.api.db import PostgrestDatabase
from worker.api.errors import DatabaseError
from worker.settings import MissingConfigError, Settings

SETTINGS = Settings.from_env(
    {
        "SUPABASE_URL": "http://sb",
        "SUPABASE_ANON_KEY": "anon",
        "SUPABASE_SERVICE_ROLE_KEY": "service",
    }
)


class Recorder:
    def __init__(self, status: int = 200, data: Any = None) -> None:
        self.status, self.data = status, data
        self.sent: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def __call__(self, method: str, url: str, headers: Any, body: bytes | None):
        self.sent.append((method, url, dict(headers), body))
        return self.status, self.data


def test_requires_config() -> None:
    with pytest.raises(MissingConfigError):
        PostgrestDatabase(Settings())


def test_rpc_uses_service_key() -> None:
    t = Recorder(data=3)
    assert PostgrestDatabase(SETTINGS, t).rpc("create_pkb_version", {"p_product_id": "x"}) == 3
    method, url, headers, body = t.sent[0]
    assert (method, url) == ("POST", "http://sb/rest/v1/rpc/create_pkb_version")
    assert headers["apikey"] == "service" and headers["Authorization"] == "Bearer service"
    assert json.loads(body or b"") == {"p_product_id": "x"}


def test_select_with_jwt_uses_anon_and_user_token() -> None:
    t = Recorder(data=[{"id": "1"}])
    rows = PostgrestDatabase(SETTINGS, t).select("products", {"id": "eq.1"}, jwt="user")
    assert rows == [{"id": "1"}]
    _, url, headers, _ = t.sent[0]
    assert url == "http://sb/rest/v1/products?id=eq.1"
    assert headers["apikey"] == "anon" and headers["Authorization"] == "Bearer user"


def test_insert_and_update_return_representation() -> None:
    t = Recorder(data=[{"id": "9"}])
    db = PostgrestDatabase(SETTINGS, t)
    assert db.insert("products", {"name": "n"}) == {"id": "9"}
    assert db.update("generation_jobs", {"id": "eq.9"}, {"status": "running"}) == [{"id": "9"}]
    assert t.sent[0][2]["Prefer"] == "return=representation"
    assert t.sent[1][0] == "PATCH"


def test_error_carries_sqlstate() -> None:
    t = Recorder(status=400, data={"code": "23514", "message": "PKB chưa approved"})
    with pytest.raises(DatabaseError) as e:
        PostgrestDatabase(SETTINGS, t).rpc("create_script_revision", {})
    assert e.value.code == "23514"
    assert e.value.to_api_error().status == 422


def test_get_user_id() -> None:
    db = PostgrestDatabase(SETTINGS, Recorder(data={"id": "u1"}))
    assert db.get_user_id("jwt") == "u1"
    assert PostgrestDatabase(SETTINGS, Recorder(status=401, data={})).get_user_id("bad") is None
