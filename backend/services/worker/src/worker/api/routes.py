"""Endpoint P1: Product → PKB → script → job. Hợp đồng: `docs/specs/p1-pipeline-db-contract.md`.

Quyền:
- Owner (token Supabase): tạo product, tạo job crawl, đọc dữ liệu của mình (RLS), duyệt PKB/script.
- Service (X-Service-Token, n8n/worker): tạo PKB version, script revision, job video, cập nhật job.
Ghi luôn đi qua RPC `service_role`; quyền sở hữu khi duyệt do RPC kiểm bằng `p_actor`.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
import shutil
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from worker.api.db import Database, Row
from worker.api.deps import (
    Owner,
    Service,
    current_owner,
    get_db,
    get_script_generator,
    get_settings,
    owner_or_service,
    require_service,
)
from worker.api.errors import ApiError, DatabaseError
from worker.api.local_db import LocalDatabase
from worker.api.generator import ScriptGenerationError, ScriptGenerator
from worker.api.schemas import (
    CrawlRequest,
    DesignSuggestRequest,
    DiscoveryPreflightOut,
    JobCreated,
    JobPatch,
    LoginFinishOut,
    LoginOpen,
    LoginStatusOut,
    PkbCreate,
    PkbRevise,
    ProductCreate,
    ProductOut,
    Review,
    ReviewOut,
    RevisionCreated,
    ScriptCreate,
    ScriptGenerate,
    VersionCreated,
    VideoRequest,
)
from worker.auth.browser import LoginWindows
from worker.m1.pkb.validate import validate_pkb
from worker.m1.url import InvalidUrlError, normalize_product_url
from worker.settings import Settings

router = APIRouter()

Db = Annotated[Database, Depends(get_db)]
OwnerDep = Annotated[Owner, Depends(current_owner)]
ServiceDep = Annotated[Service, Depends(require_service)]
AnyoneDep = Annotated[Owner | Service, Depends(owner_or_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _db_call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Gọi database và đổi `DatabaseError` thành `ApiError` theo SQLSTATE."""
    try:
        return fn(*args, **kwargs)
    except DatabaseError as e:
        raise e.to_api_error() from e


def _read(db: Database, who: Owner | Service, table: str, filters: dict[str, str]) -> list[Row]:
    """Owner đọc bằng token của họ (RLS); service đọc toàn bộ."""
    jwt = who.jwt if isinstance(who, Owner) else None
    return _db_call(db.select, table, filters, jwt)


def _one(rows: list[Row], what: str) -> Row:
    if not rows:
        raise ApiError(404, f"không thấy {what}")
    return rows[0]


def _product(db: Database, who: Owner | Service, product_id: UUID) -> Row:
    return _one(_read(db, who, "products", {"id": f"eq.{product_id}"}), "product")


@router.delete("/products/{product_id}", status_code=204)
def delete_local_product(product_id: UUID, owner: OwnerDep, db: Db, settings: SettingsDep) -> Response:
    if not settings.local_p1_mode or not isinstance(db, LocalDatabase):
        raise ApiError(404, "xóa dự án chỉ hỗ trợ demo local")
    _product(db, owner, product_id)
    job_ids = _db_call(db.delete_product, str(product_id))
    video_root = Path(settings.video_output_dir).resolve()
    for job_id in job_ids:
        target = (video_root / str(UUID(job_id))).resolve()
        if target.parent == video_root and target.is_dir():
            shutil.rmtree(target)
    auth_root = Path(settings.local_auth_dir).resolve()
    auth_target = (auth_root / str(product_id)).resolve()
    if auth_target.parent == auth_root and auth_target.is_dir():
        shutil.rmtree(auth_target)
    return Response(status_code=204)


@lru_cache
def _login_windows() -> LoginWindows:
    return LoginWindows()


def _local_auth_path(settings: Settings, product_id: UUID) -> Path:
    return Path(settings.local_auth_dir).resolve() / str(product_id) / "storage_state.json"


def _require_local_login(settings: Settings) -> None:
    if not settings.local_p1_mode:
        raise ApiError(404, "đăng nhập qua cửa sổ chỉ được bật cho demo local")


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(body: ProductCreate, response: Response, owner: OwnerDep, db: Db) -> Any:
    try:
        url = normalize_product_url(body.website_url)
    except InvalidUrlError as e:
        raise ApiError(422, f"website_url: {e}") from e
    merchants = _db_call(db.select, "merchants", {"user_id": f"eq.{owner.id}", "select": "id"})
    merchant = _one(merchants, "hồ sơ merchant của tài khoản này (đăng ký merchant trước)")
    row = {"merchant_id": merchant["id"], "website_url": url}
    if body.name:
        row["name"] = body.name.strip()
    try:
        return _db_call(db.insert, "products", row)
    except ApiError as e:
        if e.status == 409:
            try:
                existing = _read(
                    db,
                    owner,
                    "products",
                    {
                        "merchant_id": f"eq.{merchant['id']}",
                        "website_url": f"eq.{url}",
                    },
                )
            except ApiError:
                existing = []
            if existing:
                response.status_code = 200
                return existing[0]
            raise ApiError(409, "website_url đã tồn tại") from e
        raise


@router.get("/products/by-url", response_model=ProductOut)
def get_product_by_url(
    website_url: Annotated[str, Query(min_length=1, max_length=2048)],
    owner: OwnerDep,
    db: Db,
) -> Any:
    """Tiếp tục Product của cùng owner khi FE nhập lại URL đã có."""
    try:
        url = normalize_product_url(website_url)
    except InvalidUrlError as exc:
        raise ApiError(422, f"website_url: {exc}") from exc
    merchants = _read(db, owner, "merchants", {"user_id": f"eq.{owner.id}", "select": "id"})
    merchant = _one(merchants, "hồ sơ merchant của tài khoản này (đăng ký merchant trước)")
    rows = _read(
        db,
        owner,
        "products",
        {"merchant_id": f"eq.{merchant['id']}", "website_url": f"eq.{url}"},
    )
    return _one(rows, "product theo website_url")


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: UUID, who: AnyoneDep, db: Db) -> Any:
    return _product(db, who, product_id)


@router.post("/products/{product_id}/crawl", response_model=JobCreated, status_code=202)
def create_crawl_job(
    product_id: UUID, body: CrawlRequest, who: AnyoneDep, db: Db, settings: SettingsDep
) -> Any:
    product = _product(db, who, product_id)
    snapshot = {"website_url": product["website_url"]}
    if body.owner_context:
        snapshot["owner_context"] = body.owner_context
    if body.creative_preferences:
        snapshot["creative_preferences"] = body.creative_preferences
    if body.auth_session_id is not None:
        if (
            body.auth_session_id != product_id
            or not _local_auth_path(settings, product_id).is_file()
        ):
            raise ApiError(422, "phiên đăng nhập không hợp lệ hoặc đã bị xóa")
        snapshot["auth_session_id"] = str(body.auth_session_id)
    job_id = _db_call(
        db.rpc,
        "create_generation_job",
        {
            "p_product_id": str(product_id),
            "p_job_type": "crawl",
            "p_idempotency_key": body.idempotency_key,
            "p_input_snapshot": snapshot,
            "p_n8n_execution_id": body.n8n_execution_id,
        },
    )
    return {"job_id": job_id}


@router.post("/products/{product_id}/discovery/preflight", response_model=DiscoveryPreflightOut)
async def discovery_preflight(
    product_id: UUID, owner: OwnerDep, db: Db, settings: SettingsDep
) -> Any:
    """Mở thử URL bằng Chromium; không gửi nội dung hay thông tin đăng nhập cho AI."""
    _require_local_login(settings)
    product = _product(db, owner, product_id)
    try:
        result = await run_in_threadpool(_login_windows().probe, str(product["website_url"]))
    except Exception as exc:  # noqa: BLE001 - lỗi trình duyệt được đổi thành lỗi API ngắn gọn
        raise ApiError(502, f"không kiểm tra được trang sản phẩm: {type(exc).__name__}") from exc
    return {
        "requires_login": result.requires_login,
        "login_url": result.login_url,
        "reason": result.reason,
    }


@router.post("/products/{product_id}/login/browser", response_model=LoginStatusOut)
async def open_login_browser(
    product_id: UUID, body: LoginOpen, owner: OwnerDep, db: Db, settings: SettingsDep
) -> Any:
    _require_local_login(settings)
    _product(db, owner, product_id)
    try:
        login_url = normalize_product_url(body.login_url)
        await run_in_threadpool(_login_windows().open, str(product_id), login_url)
    except InvalidUrlError as exc:
        raise ApiError(422, f"login_url: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ApiError(502, f"không mở được cửa sổ đăng nhập: {type(exc).__name__}") from exc
    return {"status": "browser_open"}


@router.get("/products/{product_id}/login/browser", response_model=LoginStatusOut)
def login_browser_status(product_id: UUID, owner: OwnerDep, db: Db, settings: SettingsDep) -> Any:
    _require_local_login(settings)
    _product(db, owner, product_id)
    return {"status": _login_windows().status(str(product_id))}


@router.post("/products/{product_id}/login/finish", response_model=LoginFinishOut)
async def finish_login(product_id: UUID, owner: OwnerDep, db: Db, settings: SettingsDep) -> Any:
    _require_local_login(settings)
    _product(db, owner, product_id)
    try:
        result = await run_in_threadpool(
            _login_windows().finish, str(product_id), _local_auth_path(settings, product_id)
        )
    except Exception as exc:  # noqa: BLE001
        raise ApiError(409, str(exc)) from exc
    if not result["ok"]:
        return {"authenticated": False, "final_url": result["final_url"]}
    return {
        "authenticated": True,
        "auth_session_id": product_id,
        "final_url": result["final_url"],
    }


@router.post("/products/{product_id}/videos", response_model=JobCreated, status_code=202)
def create_video_job(product_id: UUID, body: VideoRequest, _: ServiceDep, db: Db) -> Any:
    job_id = _db_call(
        db.rpc,
        "create_generation_job",
        {
            "p_product_id": str(product_id),
            "p_job_type": "video",
            "p_idempotency_key": body.idempotency_key,
            "p_input_snapshot": {
                "pkb_version": body.pkb_version,
                "script_revision": body.script_revision,
                "render_profile": body.render_profile,
                "options": body.options,
            },
            "p_pkb_version": body.pkb_version,
            "p_script_revision": body.script_revision,
            "p_n8n_execution_id": body.n8n_execution_id,
            "p_render_profile": body.render_profile,
        },
    )
    return {"job_id": job_id}


JOB_COLUMNS = (
    "id,product_id,job_type,status,error,attempts,pkb_version,script_revision,render_profile,"
    "n8n_execution_id,result_manifest,cost_usd,cost_breakdown,created_at,finished_at"
)


@router.get("/jobs/{job_id}")
def get_job(job_id: UUID, who: AnyoneDep, db: Db) -> Any:
    return _one(
        _read(db, who, "generation_jobs", {"id": f"eq.{job_id}", "select": JOB_COLUMNS}), "job"
    )


@router.get("/jobs/{job_id}/video")
def download_video(job_id: UUID, who: AnyoneDep, db: Db, settings: SettingsDep) -> FileResponse:
    """Chỉ trả MP4 đã render và qua QA; không nhận đường dẫn từ request."""
    job = _one(
        _read(db, who, "generation_jobs", {"id": f"eq.{job_id}", "select": JOB_COLUMNS}),
        "job",
    )
    manifest = job.get("result_manifest") or {}
    if job.get("status") != "completed" or not (manifest.get("qa") or {}).get("passed"):
        raise ApiError(409, "video chưa hoàn tất QA")
    root = Path(settings.video_output_dir).resolve()
    target = Path(str(manifest.get("video_path", ""))).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ApiError(404, "không thấy file video")
    return FileResponse(target, media_type="video/mp4", filename=f"p1-{job_id}.mp4")


@router.get("/jobs/{job_id}/assets/{index}")
def get_job_asset(
    job_id: UUID, index: int, who: AnyoneDep, db: Db, settings: SettingsDep
) -> FileResponse:
    """Xem trước asset đã thu; chỉ cho file nằm dưới page store của worker."""
    job = _one(
        _read(db, who, "generation_jobs", {"id": f"eq.{job_id}", "select": JOB_COLUMNS}),
        "job",
    )
    assets = (job.get("result_manifest") or {}).get("assets") or []
    if index < 0 or index >= len(assets):
        raise ApiError(404, "không thấy tư liệu")
    root = Path(settings.page_store_dir).resolve()
    target = Path(str(assets[index].get("path", ""))).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ApiError(404, "không thấy file tư liệu")
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
    }
    media_type = media_types.get(target.suffix.lower(), "application/octet-stream")
    return FileResponse(target, media_type=media_type)


@router.patch("/jobs/{job_id}")
def patch_job(job_id: UUID, body: JobPatch, _: ServiceDep, db: Db) -> Any:
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise ApiError(422, "không có trường nào để cập nhật")
    rows = _db_call(db.update, "generation_jobs", {"id": f"eq.{job_id}"}, patch)
    return _one(rows, "job")


@router.post("/products/{product_id}/pkb", response_model=VersionCreated, status_code=201)
def create_pkb(product_id: UUID, body: PkbCreate, _: ServiceDep, db: Db) -> Any:
    version = _db_call(
        db.rpc,
        "create_pkb_version",
        {"p_product_id": str(product_id), "p_data": body.data, "p_sources": body.sources},
    )
    return {"version": version}


@router.get("/products/{product_id}/pkb/{version}")
def get_pkb(product_id: UUID, version: int, who: AnyoneDep, db: Db) -> Any:
    filters = {"product_id": f"eq.{product_id}", "version": f"eq.{version}"}
    return _one(_read(db, who, "product_knowledge", filters), "PKB version")


@router.post("/products/{product_id}/pkb/{version}/revise", response_model=VersionCreated)
def revise_pkb(product_id: UUID, version: int, body: PkbRevise, owner: OwnerDep, db: Db) -> Any:
    """Tạo PKB version mới; không sửa bản cũ và không biến creative brief thành fact."""
    _product(db, owner, product_id)
    current = _one(
        _read(
            db,
            owner,
            "product_knowledge",
            {"product_id": f"eq.{product_id}", "version": f"eq.{version}"},
        ),
        "PKB version",
    )
    data, sources = deepcopy(current["data"]), deepcopy(current["sources"])
    if data.get("schema_version") != "0.3":
        raise ApiError(422, "chỉ sửa owner field trên PKB v0.3")
    edited_at = datetime.now(UTC).isoformat()
    identity = data["identity"]
    for field, value in (("name", body.name.strip()), ("description", body.description.strip())):
        previous = identity.get(field)
        owner_fact: dict[str, Any] = {
            "value": value,
            "origin": "owner",
            "edited_by": owner.id,
            "edited_at": edited_at,
        }
        if isinstance(previous, dict) and previous.get("origin") == "crawled":
            owner_fact["previous"] = {
                "value": previous.get("value", ""),
                "source_id": previous["source_id"],
                "evidence": previous["evidence"],
            }
        identity[field] = owner_fact
    try:
        validate_pkb(data, sources)
    except ValueError as exc:
        raise ApiError(422, f"PKB owner edit không hợp lệ: {exc}") from exc
    new_version = _db_call(
        db.rpc,
        "create_pkb_version",
        {"p_product_id": str(product_id), "p_data": data, "p_sources": sources},
    )
    return {"version": new_version}


@router.post("/products/{product_id}/pkb/{version}/review", response_model=ReviewOut)
def review_pkb(product_id: UUID, version: int, body: Review, owner: OwnerDep, db: Db) -> Any:
    _db_call(
        db.rpc,
        "review_pkb",
        {
            "p_product_id": str(product_id),
            "p_version": version,
            "p_actor": owner.id,
            "p_decision": body.decision,
            "p_note": body.note,
        },
    )
    filters = {"product_id": f"eq.{product_id}", "version": f"eq.{version}", "select": "status"}
    return _one(_db_call(db.select, "product_knowledge", filters, owner.jwt), "PKB version")


@router.post("/products/{product_id}/scripts", response_model=RevisionCreated, status_code=201)
def create_script(product_id: UUID, body: ScriptCreate, _: ServiceDep, db: Db) -> Any:
    revision = _db_call(
        db.rpc,
        "create_script_revision",
        {
            "p_product_id": str(product_id),
            "p_knowledge_version": body.knowledge_version,
            "p_content": body.content,
            "p_idempotency_key": body.idempotency_key,
            "p_parent_revision": body.parent_revision,
            "p_report": body.report,
            "p_cost_breakdown": body.cost_breakdown,
        },
    )
    return {"revision": revision}


M2_INPUT_VERSION = "p1-ac-03-input.v1-draft"


@router.post(
    "/products/{product_id}/scripts/generate", response_model=RevisionCreated, status_code=201
)
async def generate_script(
    product_id: UUID,
    body: ScriptGenerate,
    response: Response,
    _: ServiceDep,
    db: Db,
    generator: Annotated[ScriptGenerator | None, Depends(get_script_generator)],
) -> Any:
    """Sinh script (M2) từ PKB `approved` rồi lưu thành revision `draft`. Chạy đồng bộ (LLM)."""
    pid = str(product_id)
    # Cùng key trả revision cũ, không gọi LLM lần nữa (idempotent, tiết kiệm quota).
    prior = await run_in_threadpool(
        _db_call,
        db.select,
        "script_revisions",
        {"product_id": f"eq.{pid}", "idempotency_key": f"eq.{body.idempotency_key}"},
    )
    if prior:
        response.status_code = 200
        return {"revision": prior[0]["revision"]}
    if generator is None:
        raise ApiError(503, "bộ sinh script (M2) chưa được cấu hình")

    rows = await run_in_threadpool(
        _db_call,
        db.select,
        "product_knowledge",
        {"product_id": f"eq.{pid}", "version": f"eq.{body.knowledge_version}"},
    )
    pkb = _one(rows, "PKB version")
    if pkb["status"] != "approved":
        raise ApiError(422, f"PKB version {body.knowledge_version} chưa được duyệt")
    m2_input: dict[str, Any] = {
        "schema_version": M2_INPUT_VERSION,
        "product_id": pid,
        "knowledge_version": body.knowledge_version,
        "approved_pkb": {
            "status": "approved",
            "schema_version": pkb["data"]["schema_version"],
            "data": pkb["data"],
            "sources": pkb["sources"],
        },
        "permitted_assets": body.permitted_assets,
    }
    if body.content_context is not None:
        m2_input["content_context"] = body.content_context
    try:
        script = await generator(m2_input)
    except ScriptGenerationError as e:
        status = 422 if e.invalid else 502
        suffix = " (có thể thử lại)" if e.retryable else ""
        raise ApiError(status, f"sinh script thất bại: {e.message}{suffix}") from e

    revision = await run_in_threadpool(
        _db_call,
        db.rpc,
        "create_script_revision",
        {
            "p_product_id": pid,
            "p_knowledge_version": body.knowledge_version,
            "p_content": script.content,
            "p_idempotency_key": body.idempotency_key,
            "p_parent_revision": body.parent_revision,
            "p_report": script.report,
            "p_cost_breakdown": script.cost_breakdown,
        },
    )
    return {"revision": revision}


@router.get("/products/{product_id}/scripts/{revision}")
def get_script(product_id: UUID, revision: int, who: AnyoneDep, db: Db) -> Any:
    filters = {"product_id": f"eq.{product_id}", "revision": f"eq.{revision}"}
    return _one(_read(db, who, "script_revisions", filters), "script revision")


@router.post("/products/{product_id}/scripts/{revision}/review", response_model=ReviewOut)
def review_script(product_id: UUID, revision: int, body: Review, owner: OwnerDep, db: Db) -> Any:
    _db_call(
        db.rpc,
        "review_script_revision",
        {
            "p_product_id": str(product_id),
            "p_revision": revision,
            "p_actor": owner.id,
            "p_decision": body.decision,
            "p_note": body.note,
        },
    )
    filters = {"product_id": f"eq.{product_id}", "revision": f"eq.{revision}", "select": "status"}
    return _one(_db_call(db.select, "script_revisions", filters, owner.jwt), "script revision")


@router.post("/products/{product_id}/scripts/{revision}/design-suggest")
async def design_suggest(
    product_id: UUID,
    revision: int,
    body: DesignSuggestRequest,
    who: AnyoneDep,
    db: Db,
    settings: SettingsDep,
) -> Any:
    """AI phân tích website, ảnh chụp và kịch bản để gợi ý tiêu đề cảnh + bảng màu template."""
    from worker.render.design import suggest_template_design

    product = await run_in_threadpool(_product, db, who, product_id)
    script_rows = await run_in_threadpool(
        _read,
        db,
        who,
        "script_revisions",
        {"product_id": f"eq.{product_id}", "revision": f"eq.{revision}"},
    )
    script_row = _one(script_rows, "script revision")
    pkb_version = script_row.get("knowledge_version")
    pkb_rows = await run_in_threadpool(
        _read,
        db,
        who,
        "product_knowledge",
        {"product_id": f"eq.{product_id}", "version": f"eq.{pkb_version}"},
    )
    pkb_row = _one(pkb_rows, "PKB version")

    asset_paths: list[Path] = []
    asset_root = Path(settings.page_store_dir).resolve()
    job_filters: dict[str, str] = (
        {"id": f"eq.{body.crawl_job_id}"}
        if body.crawl_job_id
        else {"product_id": f"eq.{product_id}", "job_type": "eq.crawl", "status": "eq.completed"}
    )
    crawl_jobs = await run_in_threadpool(_read, db, who, "generation_jobs", job_filters)
    if crawl_jobs:
        manifest = crawl_jobs[-1].get("result_manifest") or {}
        for asset in manifest.get("assets") or []:
            raw_path = asset.get("path") if isinstance(asset, dict) else None
            if not isinstance(raw_path, str) or not raw_path:
                continue
            resolved = Path(raw_path).resolve()
            if resolved.is_relative_to(asset_root) and resolved.is_file():
                asset_paths.append(resolved)

    return await suggest_template_design(
        product=product,
        pkb=pkb_row,
        script=script_row.get("content") or {},
        template=body.template,
        asset_paths=asset_paths,
    )
