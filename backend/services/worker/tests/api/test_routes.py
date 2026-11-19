from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.api.conftest import OWNER, SERVICE
from tests.api.fakes import JOB_ID, OWNER_ID, OWNER_JWT, PRODUCT_ID, FakeDb
from worker.api.deps import get_db, get_settings
from worker.api.errors import DatabaseError
from worker.main import app
from worker.settings import Settings

PRODUCT = {"id": PRODUCT_ID, "website_url": "https://pdfcraft.devtoolcafe.com", "status": "draft"}


# --- xác thực -----------------------------------------------------------------------------------


def test_health_khong_can_dang_nhap(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_owner_thieu_token_401(client: TestClient) -> None:
    r = client.post("/products", json={"website_url": "https://example.com"})
    assert r.status_code == 401
    assert "Bearer" in r.json()["detail"]


def test_owner_token_sai_401(client: TestClient) -> None:
    r = client.post(
        "/products",
        json={"website_url": "https://example.com"},
        headers={"Authorization": "Bearer x"},
    )
    assert r.status_code == 401


def test_service_token_sai_401(client: TestClient) -> None:
    r = client.post(
        f"/products/{PRODUCT_ID}/pkb",
        json={"data": {}, "sources": []},
        headers={"X-Service-Token": "sai"},
    )
    assert r.status_code == 401


def test_owner_khong_goi_duoc_endpoint_dich_vu(client: TestClient, db: FakeDb) -> None:
    r = client.post(f"/products/{PRODUCT_ID}/pkb", json={"data": {}, "sources": []}, headers=OWNER)
    assert r.status_code == 401
    assert not any(k.startswith("rpc:") for k, _ in db.calls)


def test_endpoint_dich_vu_tat_khi_chua_dat_token(db: FakeDb) -> None:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: Settings()
    try:
        r = TestClient(app).post(
            f"/products/{PRODUCT_ID}/pkb",
            json={"data": {}, "sources": []},
            headers={"X-Service-Token": "bat-ky"},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503
    assert "N8N_SERVICE_TOKEN" in r.json()["detail"]


def test_thieu_cau_hinh_supabase_503_chi_co_ten_bien() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        supabase_service_role_key=SecretStr("khong-duoc-lo")
    )
    try:
        r = TestClient(app).post(
            "/products", json={"website_url": "https://example.com"}, headers=OWNER
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503
    assert "SUPABASE_URL" in r.json()["detail"]
    assert "khong-duoc-lo" not in r.text


# --- product ------------------------------------------------------------------------------------


def test_tao_product_chuan_hoa_url_va_lay_merchant(client: TestClient, db: FakeDb) -> None:
    db.tables["merchants"] = [{"id": "m-1"}]
    r = client.post(
        "/products",
        json={"website_url": "HTTP://PDFCraft.devtoolcafe.com/?utm_source=x", "name": " PDFCraft "},
        headers=OWNER,
    )
    assert r.status_code == 201
    assert db.last("insert:products") == {
        "merchant_id": "m-1",
        "website_url": "https://pdfcraft.devtoolcafe.com",
        "name": "PDFCraft",
    }
    assert db.last("select:merchants")["filters"]["user_id"] == f"eq.{OWNER_ID}"


def test_tao_product_url_sai_422(client: TestClient) -> None:
    r = client.post("/products", json={"website_url": "ftp://x"}, headers=OWNER)
    assert r.status_code == 422
    assert r.json()["detail"].startswith("website_url:")


def test_tao_product_khong_co_merchant_404(client: TestClient) -> None:
    r = client.post("/products", json={"website_url": "https://example.com"}, headers=OWNER)
    assert r.status_code == 404
    assert "merchant" in r.json()["detail"]


def test_tao_product_trung_url_409(client: TestClient, db: FakeDb) -> None:
    db.tables["merchants"] = [{"id": "m-1"}]
    db.errors["table:products"] = DatabaseError(409, "23505", "duplicate key")
    r = client.post("/products", json={"website_url": "https://example.com"}, headers=OWNER)
    assert r.status_code == 409
    assert r.json()["detail"] == "website_url đã tồn tại"


def test_lay_lai_product_cu_theo_url(client: TestClient, db: FakeDb) -> None:
    db.tables["merchants"] = [{"id": "m-1"}]
    db.tables["products"] = [PRODUCT]
    r = client.get(
        "/products/by-url",
        params={"website_url": PRODUCT["website_url"]},
        headers=OWNER,
    )
    assert r.status_code == 200
    assert r.json()["id"] == PRODUCT_ID
    filters = db.last("select:products")["filters"]
    assert filters["merchant_id"] == "eq.m-1"
    assert filters["website_url"] == f"eq.{PRODUCT['website_url']}"


def test_body_thua_truong_422_khong_lo_gia_tri(client: TestClient) -> None:
    r = client.post(
        "/products", json={"website_url": "https://example.com", "x": "bi-mat-123"}, headers=OWNER
    )
    assert r.status_code == 422
    assert "bi-mat-123" not in r.text


# --- job ----------------------------------------------------------------------------------------


def test_crawl_job_owner_doc_product_bang_rls_va_goi_rpc(client: TestClient, db: FakeDb) -> None:
    db.tables["products"] = [PRODUCT]
    db.rpc_results["create_generation_job"] = JOB_ID
    r = client.post(
        f"/products/{PRODUCT_ID}/crawl",
        json={"idempotency_key": "exec-9:crawl", "n8n_execution_id": "9"},
        headers=OWNER,
    )
    assert r.status_code == 202
    assert r.json() == {"job_id": JOB_ID}
    assert db.last("select:products")["jwt"] == OWNER_JWT  # đọc thay mặt người dùng
    args = db.last("rpc:create_generation_job")
    assert args["p_job_type"] == "crawl"
    assert args["p_idempotency_key"] == "exec-9:crawl"
    assert args["p_n8n_execution_id"] == "9"
    assert args["p_input_snapshot"] == {"website_url": PRODUCT["website_url"]}


def test_crawl_giu_owner_context_va_creative_preferences_o_input(
    client: TestClient, db: FakeDb
) -> None:
    db.tables["products"] = [PRODUCT]
    db.rpc_results["create_generation_job"] = JOB_ID
    r = client.post(
        f"/products/{PRODUCT_ID}/crawl",
        json={
            "idempotency_key": "crawl-with-context",
            "owner_context": "Thông tin do chủ sở hữu cung cấp.",
            "creative_preferences": "Giọng thân thiện.",
        },
        headers=OWNER,
    )
    assert r.status_code == 202
    assert db.last("rpc:create_generation_job")["p_input_snapshot"] == {
        "website_url": PRODUCT["website_url"],
        "owner_context": "Thông tin do chủ sở hữu cung cấp.",
        "creative_preferences": "Giọng thân thiện.",
    }


def test_crawl_job_product_cua_nguoi_khac_404(client: TestClient) -> None:
    # RLS trả rỗng cho product không thuộc owner
    r = client.post(f"/products/{PRODUCT_ID}/crawl", json={"idempotency_key": "k"}, headers=OWNER)
    assert r.status_code == 404


def test_crawl_job_service_doc_khong_dung_jwt(client: TestClient, db: FakeDb) -> None:
    db.tables["products"] = [PRODUCT]
    db.rpc_results["create_generation_job"] = JOB_ID
    r = client.post(f"/products/{PRODUCT_ID}/crawl", json={"idempotency_key": "k"}, headers=SERVICE)
    assert r.status_code == 202
    assert db.last("select:products")["jwt"] is None


def test_crawl_job_thieu_idempotency_key_422(client: TestClient) -> None:
    r = client.post(f"/products/{PRODUCT_ID}/crawl", json={}, headers=OWNER)
    assert r.status_code == 422


def test_video_job_truyen_pkb_script_va_render_profile(client: TestClient, db: FakeDb) -> None:
    db.rpc_results["create_generation_job"] = JOB_ID
    r = client.post(
        f"/products/{PRODUCT_ID}/videos",
        json={
            "pkb_version": 1,
            "script_revision": 2,
            "idempotency_key": "exec-9:video:16x9",
            "render_profile": "16:9",
            "n8n_execution_id": "9",
        },
        headers=SERVICE,
    )
    assert r.status_code == 202
    args = db.last("rpc:create_generation_job")
    assert (args["p_pkb_version"], args["p_script_revision"], args["p_render_profile"]) == (
        1,
        2,
        "16:9",
    )
    assert args["p_job_type"] == "video"


def test_video_job_script_chua_duyet_422(client: TestClient, db: FakeDb) -> None:
    db.errors["create_generation_job"] = DatabaseError(
        400, "23514", "video job requires an approved script revision of the same PKB version"
    )
    r = client.post(
        f"/products/{PRODUCT_ID}/videos",
        json={"pkb_version": 1, "script_revision": 2, "idempotency_key": "k"},
        headers=SERVICE,
    )
    assert r.status_code == 422
    assert "approved script revision" in r.json()["detail"]


def test_get_job_owner_dung_rls(client: TestClient, db: FakeDb) -> None:
    db.tables["generation_jobs"] = [{"id": JOB_ID, "status": "running", "n8n_execution_id": "9"}]
    r = client.get(f"/jobs/{JOB_ID}", headers=OWNER)
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    assert db.last("select:generation_jobs")["jwt"] == OWNER_JWT


def test_get_job_khong_thay_404(client: TestClient) -> None:
    assert client.get(f"/jobs/{JOB_ID}", headers=OWNER).status_code == 404


def test_patch_job_chi_service_va_chi_truong_da_gui(client: TestClient, db: FakeDb) -> None:
    db.tables["generation_jobs"] = [{"id": JOB_ID, "status": "failed"}]
    assert (
        client.patch(f"/jobs/{JOB_ID}", json={"status": "running"}, headers=OWNER).status_code
        == 401
    )
    r = client.patch(
        f"/jobs/{JOB_ID}", json={"status": "failed", "error": "tts_unavailable"}, headers=SERVICE
    )
    assert r.status_code == 200
    assert db.last("update:generation_jobs")["patch"] == {
        "status": "failed",
        "error": "tts_unavailable",
    }


def test_patch_job_rong_422_va_trang_thai_la_422(client: TestClient) -> None:
    assert client.patch(f"/jobs/{JOB_ID}", json={}, headers=SERVICE).status_code == 422
    r = client.patch(f"/jobs/{JOB_ID}", json={"status": "done"}, headers=SERVICE)
    assert r.status_code == 422


def test_patch_job_chuyen_trang_thai_sai_409(client: TestClient, db: FakeDb) -> None:
    db.errors["table:generation_jobs"] = DatabaseError(
        400, "23001", "job x is completed, state is final"
    )
    r = client.patch(f"/jobs/{JOB_ID}", json={"status": "running"}, headers=SERVICE)
    assert r.status_code == 409


# --- PKB và script ------------------------------------------------------------------------------


def test_tao_pkb_version_qua_rpc(client: TestClient, db: FakeDb) -> None:
    db.rpc_results["create_pkb_version"] = 1
    r = client.post(
        f"/products/{PRODUCT_ID}/pkb",
        json={"data": {"schema_version": "0.3"}, "sources": []},
        headers=SERVICE,
    )
    assert r.status_code == 201
    assert r.json() == {"version": 1}
    assert db.last("rpc:create_pkb_version")["p_product_id"] == PRODUCT_ID


def test_owner_sua_pkb_tao_version_moi_va_giu_bang_chung(client: TestClient, db: FakeDb) -> None:
    fixture_path = Path(__file__).parents[4] / "docs/specs/pkb/examples/valid-v03-software.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    db.tables["products"] = [PRODUCT]
    db.tables["product_knowledge"] = [
        {"product_id": PRODUCT_ID, "version": 1, "status": "draft", **fixture}
    ]
    db.rpc_results["create_pkb_version"] = 2
    r = client.post(
        f"/products/{PRODUCT_ID}/pkb/1/revise",
        json={"name": "Tên chủ sở hữu xác nhận", "description": "Mô tả đã kiểm tra."},
        headers=OWNER,
    )
    assert r.status_code == 200
    assert r.json() == {"version": 2}
    data = db.last("rpc:create_pkb_version")["p_data"]
    assert data["identity"]["name"]["origin"] == "owner"
    assert data["identity"]["name"]["previous"]["source_id"] == "src_01"
    assert data["identity"]["description"]["origin"] == "owner"


def test_duyet_pkb_truyen_actor_tu_token_khong_tu_body(client: TestClient, db: FakeDb) -> None:
    db.tables["product_knowledge"] = [{"status": "approved"}]
    r = client.post(
        f"/products/{PRODUCT_ID}/pkb/1/review",
        json={"decision": "approve", "note": "ok"},
        headers=OWNER,
    )
    assert r.status_code == 200
    assert r.json() == {"status": "approved"}
    args = db.last("rpc:review_pkb")
    assert args["p_actor"] == OWNER_ID
    assert args["p_decision"] == "approve"


def test_duyet_pkb_actor_khong_so_huu_403(client: TestClient, db: FakeDb) -> None:
    db.errors["review_pkb"] = DatabaseError(403, "42501", "actor does not own product")
    r = client.post(
        f"/products/{PRODUCT_ID}/pkb/1/review", json={"decision": "approve"}, headers=OWNER
    )
    assert r.status_code == 403


def test_duyet_pkb_quyet_dinh_la_422(client: TestClient) -> None:
    r = client.post(
        f"/products/{PRODUCT_ID}/pkb/1/review", json={"decision": "merge"}, headers=OWNER
    )
    assert r.status_code == 422


def test_tao_script_idempotent_qua_rpc(client: TestClient, db: FakeDb) -> None:
    db.rpc_results["create_script_revision"] = 3
    r = client.post(
        f"/products/{PRODUCT_ID}/scripts",
        json={
            "knowledge_version": 1,
            "content": {"scenes": []},
            "idempotency_key": "exec-9:script",
            "parent_revision": 2,
        },
        headers=SERVICE,
    )
    assert r.status_code == 201
    assert r.json() == {"revision": 3}
    args = db.last("rpc:create_script_revision")
    assert args["p_idempotency_key"] == "exec-9:script"
    assert args["p_parent_revision"] == 2


def test_tao_script_pkb_chua_duyet_422(client: TestClient, db: FakeDb) -> None:
    db.errors["create_script_revision"] = DatabaseError(
        400, "23514", "script revision requires an approved PKB"
    )
    r = client.post(
        f"/products/{PRODUCT_ID}/scripts",
        json={"knowledge_version": 1, "content": {}, "idempotency_key": "k"},
        headers=SERVICE,
    )
    assert r.status_code == 422


def test_duyet_script(client: TestClient, db: FakeDb) -> None:
    db.tables["script_revisions"] = [{"status": "in_review"}]
    r = client.post(
        f"/products/{PRODUCT_ID}/scripts/2/review", json={"decision": "submit"}, headers=OWNER
    )
    assert r.status_code == 200
    assert db.last("rpc:review_script_revision")["p_revision"] == 2


@pytest.mark.parametrize(
    ("status", "code", "expected"),
    [
        (400, "42501", 403),
        (400, "23503", 404),
        (400, "23505", 409),
        (400, "23001", 409),
        (400, "23514", 422),
        (400, "XX000", 422),
        (500, "XX000", 502),
    ],
)
def test_anh_xa_loi_database(
    client: TestClient, db: FakeDb, status: int, code: str, expected: int
) -> None:
    db.errors["create_pkb_version"] = DatabaseError(status, code, "msg")
    r = client.post(
        f"/products/{PRODUCT_ID}/pkb", json={"data": {}, "sources": []}, headers=SERVICE
    )
    assert r.status_code == expected
