"""Phụ thuộc FastAPI: cấu hình, database, xác thực.

Hai loại người gọi:
- `Owner`: người dùng đăng nhập (`Authorization: Bearer <access_token>` của Supabase Auth). Token
được Supabase Auth
  xác minh (không tự giải mã JWT). Quyền sở hữu do RLS (khi đọc) và RPC (khi ghi) kiểm.
- `Service`: n8n / worker, gửi `X-Service-Token` khớp `N8N_SERVICE_TOKEN`. Endpoint dịch vụ tắt hẳn
nếu chưa đặt token.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header

from worker.api.db import Database, PostgrestDatabase
from worker.api.errors import ApiError
from worker.api.generator import GeminiScriptGenerator, ScriptGenerator
from worker.api.local_db import LocalDatabase
from worker.settings import MissingConfigError, Settings


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()


@lru_cache
def _local_db(directory: str, owner_id: str) -> LocalDatabase:
    return LocalDatabase(directory, owner_id)


def get_db(settings: Annotated[Settings, Depends(get_settings)]) -> Database:
    if settings.local_p1_mode:
        return _local_db(settings.local_data_dir, settings.local_owner_id)
    try:
        return PostgrestDatabase(settings)
    except MissingConfigError as e:
        raise ApiError(503, str(e)) from e


def get_script_generator(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScriptGenerator | None:
    """Bộ sinh script M2; kiểm đúng secret của provider đang được chọn."""
    provider = os.environ.get("LLM_PROVIDER", "gemini").strip().lower()
    if provider == "freemodel":
        if not settings.freemodel_api_key.get_secret_value():
            return None
    elif provider != "fixture" and settings.missing("script"):
        return None
    return GeminiScriptGenerator()


@dataclass(frozen=True)
class Owner:
    id: str
    jwt: str


@dataclass(frozen=True)
class Service:
    pass


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def current_owner(
    db: Annotated[Database, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> Owner:
    token = _bearer(authorization)
    if token is None:
        raise ApiError(401, "thiếu access token (Authorization: Bearer ...)")
    user_id = db.get_user_id(token)
    if user_id is None:
        raise ApiError(401, "access token không hợp lệ hoặc đã hết hạn")
    return Owner(id=user_id, jwt=token)


def require_service(
    settings: Annotated[Settings, Depends(get_settings)],
    x_service_token: Annotated[str | None, Header()] = None,
) -> Service:
    expected = settings.n8n_service_token.get_secret_value()
    if not expected:
        raise ApiError(503, "endpoint dịch vụ chưa bật: thiếu cấu hình: N8N_SERVICE_TOKEN")
    if not x_service_token or not hmac.compare_digest(x_service_token, expected):
        raise ApiError(401, "X-Service-Token không hợp lệ")
    return Service()


def owner_or_service(
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Database, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
    x_service_token: Annotated[str | None, Header()] = None,
) -> Owner | Service:
    if x_service_token is not None:
        return require_service(settings, x_service_token)
    return current_owner(db, authorization)
