from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import OWNER, SERVICE
from tests.api.fakes import PRODUCT_ID, FakeDb
from worker.api.deps import get_script_generator
from worker.api.generator import GeneratedScript, ScriptGenerationError
from worker.main import app

URL = f"/products/{PRODUCT_ID}/scripts/generate"
BODY = {"knowledge_version": 1, "idempotency_key": "exec1:script"}
PKB = {
    "status": "approved",
    "data": {"schema_version": "0.3", "identity": {}},
    "sources": [{"source_id": "src_01"}],
}


class FakeGenerator:
    def __init__(self, result: GeneratedScript | Exception | None = None) -> None:
        self.result = result or GeneratedScript(
            content={"scenes": []}, report={"ok": True}, cost_breakdown={"items": []}
        )
        self.inputs: list[dict[str, Any]] = []

    async def __call__(self, m2_input: dict[str, Any]) -> GeneratedScript:
        self.inputs.append(m2_input)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def gen(client: TestClient) -> FakeGenerator:
    g = FakeGenerator()
    app.dependency_overrides[get_script_generator] = lambda: g
    return g


def test_generates_and_stores_revision(client: TestClient, db: FakeDb, gen: FakeGenerator) -> None:
    db.tables["product_knowledge"] = [PKB]
    db.rpc_results["create_script_revision"] = 3
    body = {
        **BODY,
        "parent_revision": 2,
        "permitted_assets": [{"asset_id": "a1"}],
        "content_context": {"platform": "tiktok"},
    }
    r = client.post(URL, json=body, headers=SERVICE)
    assert r.status_code == 201 and r.json() == {"revision": 3}
    m2 = gen.inputs[0]
    assert m2["approved_pkb"] == {
        "status": "approved",
        "schema_version": "0.3",
        "data": PKB["data"],
        "sources": PKB["sources"],
    }
    assert m2["permitted_assets"] == [{"asset_id": "a1"}]
    assert m2["content_context"] == {"platform": "tiktok"}
    assert m2["product_id"] == PRODUCT_ID and m2["knowledge_version"] == 1
    args = db.last("rpc:create_script_revision")
    assert args["p_content"] == {"scenes": []} and args["p_report"] == {"ok": True}
    assert args["p_parent_revision"] == 2 and args["p_idempotency_key"] == "exec1:script"


def test_content_context_omitted_when_absent(
    client: TestClient, db: FakeDb, gen: FakeGenerator
) -> None:
    db.tables["product_knowledge"] = [PKB]
    db.rpc_results["create_script_revision"] = 1
    client.post(URL, json=BODY, headers=SERVICE)
    assert "content_context" not in gen.inputs[0]


def test_same_key_returns_existing_without_calling_llm(
    client: TestClient, db: FakeDb, gen: FakeGenerator
) -> None:
    db.tables["script_revisions"] = [{"revision": 5}]
    r = client.post(URL, json=BODY, headers=SERVICE)
    assert r.status_code == 200 and r.json() == {"revision": 5}
    assert gen.inputs == []
    filters = db.last("select:script_revisions")["filters"]
    assert filters == {"product_id": f"eq.{PRODUCT_ID}", "idempotency_key": "eq.exec1:script"}


def test_unapproved_pkb_is_422(client: TestClient, db: FakeDb, gen: FakeGenerator) -> None:
    db.tables["product_knowledge"] = [{**PKB, "status": "draft"}]
    r = client.post(URL, json=BODY, headers=SERVICE)
    assert r.status_code == 422 and gen.inputs == []


def test_missing_pkb_is_404(client: TestClient, gen: FakeGenerator) -> None:
    assert client.post(URL, json=BODY, headers=SERVICE).status_code == 404


def test_generator_not_configured_is_503(client: TestClient, db: FakeDb) -> None:
    app.dependency_overrides.pop(get_script_generator, None)
    r = client.post(URL, json=BODY, headers=SERVICE)
    assert r.status_code == 503 and "M2" in r.json()["detail"]


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (ScriptGenerationError("llm_quota", retryable=True), 502),
        (ScriptGenerationError("validator: thiếu fact_refs", invalid=True), 422),
    ],
)
def test_generator_errors_map_to_http(
    client: TestClient, db: FakeDb, gen: FakeGenerator, error: Exception, status: int
) -> None:
    db.tables["product_knowledge"] = [PKB]
    gen.result = error
    r = client.post(URL, json=BODY, headers=SERVICE)
    assert r.status_code == status and "sinh script thất bại" in r.json()["detail"]
    assert not [k for k, _ in db.calls if k == "rpc:create_script_revision"]


def test_requires_service_token(client: TestClient, gen: FakeGenerator) -> None:
    assert client.post(URL, json=BODY).status_code == 401
    assert client.post(URL, json=BODY, headers=OWNER).status_code == 401


def test_rejects_unknown_fields(client: TestClient, gen: FakeGenerator) -> None:
    r = client.post(URL, json={**BODY, "approved_pkb": {}}, headers=SERVICE)
    assert r.status_code == 422
