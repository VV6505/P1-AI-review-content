"""Request/response của API P1. Hình dạng theo `docs/specs/p1-pipeline-db-contract.md`."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

IdempotencyKey = Field(min_length=1, max_length=200)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductCreate(Strict):
    website_url: str = Field(min_length=1, max_length=2048)
    name: str | None = Field(default=None, max_length=200)


class ProductOut(BaseModel):
    id: UUID
    website_url: str
    name: str | None = None
    status: str


class CrawlRequest(Strict):
    idempotency_key: str = IdempotencyKey
    n8n_execution_id: str | None = Field(default=None, min_length=1, max_length=100)
    # Hai vùng này chỉ là dữ liệu đầu vào. `owner_context` không trở thành fact nếu chưa được
    # đưa vào PKB với origin=owner và được duyệt; creative_preferences chỉ đi tới M2.
    owner_context: str | None = Field(default=None, max_length=4000)
    creative_preferences: str | None = Field(default=None, max_length=4000)
    # Chỉ dùng trong demo local. Đây là id phiên cookie Playwright, không phải tài khoản/mật khẩu.
    auth_session_id: UUID | None = None


class LoginOpen(Strict):
    login_url: str = Field(min_length=1, max_length=2048)


class DiscoveryPreflightOut(BaseModel):
    requires_login: bool
    login_url: str | None = None
    reason: str | None = None


class LoginStatusOut(BaseModel):
    status: Literal["none", "browser_open", "closed", "timeout"]


class LoginFinishOut(BaseModel):
    authenticated: bool
    auth_session_id: UUID | None = None
    final_url: str | None = None


class VideoRequest(Strict):
    pkb_version: int = Field(gt=0)
    script_revision: int = Field(gt=0)
    idempotency_key: str = IdempotencyKey
    render_profile: str | None = Field(default=None, min_length=1, max_length=100)
    n8n_execution_id: str | None = Field(default=None, min_length=1, max_length=100)
    # Tham số render (preset, tỉ lệ, template). Chưa chốt cách chia job, nên để tự do.
    options: dict[str, Any] = {}


class JobCreated(BaseModel):
    job_id: UUID


class JobPatch(Strict):
    """Worker/n8n cập nhật job. Chuyển trạng thái sai bị DB từ chối (409)."""

    status: Literal["queued", "running", "completed", "failed"] | None = None
    error: str | None = Field(default=None, max_length=2000)
    attempts: int | None = Field(default=None, ge=0)
    pkb_version: int | None = Field(default=None, gt=0)
    result_manifest: dict[str, Any] | None = None
    n8n_execution_id: str | None = Field(default=None, min_length=1, max_length=100)
    cost_breakdown: dict[str, Any] | None = None


class PkbCreate(Strict):
    data: dict[str, Any]
    sources: list[dict[str, Any]]


class PkbRevise(Strict):
    """Hai trường identity mà owner được sửa an toàn trong PKB v0.3."""

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)


class VersionCreated(BaseModel):
    version: int


class ScriptCreate(Strict):
    knowledge_version: int = Field(gt=0)
    content: dict[str, Any]
    idempotency_key: str = IdempotencyKey
    parent_revision: int | None = Field(default=None, gt=0)
    report: dict[str, Any] = {}
    cost_breakdown: dict[str, Any] = {}


class ScriptGenerate(Strict):
    """Yêu cầu sinh script từ PKB đã duyệt. Tư liệu (`permitted_assets`) do BE/n8n truyền vào."""

    knowledge_version: int = Field(gt=0)
    idempotency_key: str = IdempotencyKey
    parent_revision: int | None = Field(default=None, gt=0)
    # Tư liệu có quyền dùng (asset_id, product_id, kind, allowed_use, rights_basis). Bảng assets
    # chưa có, nên tạm truyền trong request; M2 chỉ được trả về asset_id có trong danh sách này.
    permitted_assets: list[dict[str, Any]] = []
    # Tuỳ chọn: video_description, platform, intent, audience, approved/forbidden_claims, cta.
    content_context: dict[str, Any] | None = None


class RevisionCreated(BaseModel):
    revision: int


class Review(Strict):
    decision: Literal["submit", "approve", "reject"]
    note: str | None = Field(default=None, max_length=1000)


class ReviewOut(BaseModel):
    status: str


class DesignSuggestRequest(Strict):
    template: str = Field(default="offset-shadow", min_length=1, max_length=60)
    crawl_job_id: UUID | None = None

