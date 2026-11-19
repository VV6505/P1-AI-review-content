"""Lớp truy cập database của API: gọi Supabase PostgREST (RPC và bảng) và Supabase Auth.

Không thêm thư viện: dùng `urllib` của stdlib như `worker.m1.crawl`. Mọi lời gọi database đi qua
`Database`
để test thay bằng fake và để đổi provider chỉ sửa file này (ADR-0005).

Hai chế độ:
- service (`jwt=None`): khoá service_role, bỏ qua RLS. Chỉ dùng cho thao tác backend đã tự kiểm
quyền.
- thay mặt người dùng (`jwt=<access token>`): khoá anon + token người dùng, RLS giới hạn trong dữ
liệu của họ.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, Protocol
from urllib.parse import quote, urlencode

from worker.api.errors import DatabaseError
from worker.settings import Settings

# (method, url, headers, body) -> (status, JSON đã parse hoặc None)
Transport = Callable[[str, str, Mapping[str, str], bytes | None], tuple[int, Any]]

Row = dict[str, Any]


class Database(Protocol):
    def rpc(self, name: str, args: Mapping[str, Any]) -> Any: ...
    def select(
        self, table: str, filters: Mapping[str, str], jwt: str | None = None
    ) -> list[Row]: ...
    def insert(self, table: str, row: Mapping[str, Any]) -> Row: ...
    def update(
        self, table: str, filters: Mapping[str, str], patch: Mapping[str, Any]
    ) -> list[Row]: ...
    def get_user_id(self, jwt: str) -> str | None: ...


def urllib_transport(timeout_s: float) -> Transport:
    def send(
        method: str, url: str, headers: Mapping[str, str], body: bytes | None
    ) -> tuple[int, Any]:
        request = urllib.request.Request(url, data=body, method=method, headers=dict(headers))
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise DatabaseError(503, "unreachable", "không kết nối được database") from e
        try:
            return status, (json.loads(raw) if raw else None)
        except ValueError:
            return status, None

    return send


class PostgrestDatabase:
    def __init__(self, settings: Settings, transport: Transport | None = None) -> None:
        settings.require("api")
        self._base = settings.supabase_url
        self._anon = settings.supabase_anon_key.get_secret_value()
        self._service = settings.supabase_service_role_key.get_secret_value()
        self._send = transport or urllib_transport(settings.http_timeout_s)

    def _headers(self, jwt: str | None, *, returning: bool = False) -> dict[str, str]:
        apikey, bearer = (self._service, self._service) if jwt is None else (self._anon, jwt)
        headers = {
            "apikey": apikey,
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if returning:
            headers["Prefer"] = "return=representation"
        return headers

    def _call(self, method: str, path: str, headers: Mapping[str, str], body: Any = None) -> Any:
        payload = None if body is None else json.dumps(body).encode()
        status, data = self._send(method, self._base + path, headers, payload)
        if status >= 400:
            code = str(data.get("code", "")) if isinstance(data, dict) else ""
            message = str(data.get("message", "")) if isinstance(data, dict) else ""
            raise DatabaseError(status, code, message or f"HTTP {status}")
        return data

    @staticmethod
    def _query(filters: Mapping[str, str]) -> str:
        return ("?" + urlencode(filters, quote_via=quote)) if filters else ""

    def rpc(self, name: str, args: Mapping[str, Any]) -> Any:
        return self._call("POST", f"/rest/v1/rpc/{name}", self._headers(None), dict(args))

    def select(self, table: str, filters: Mapping[str, str], jwt: str | None = None) -> list[Row]:
        data = self._call("GET", f"/rest/v1/{table}{self._query(filters)}", self._headers(jwt))
        return data if isinstance(data, list) else []

    def insert(self, table: str, row: Mapping[str, Any]) -> Row:
        data = self._call(
            "POST", f"/rest/v1/{table}", self._headers(None, returning=True), dict(row)
        )
        return data[0] if isinstance(data, list) and data else {}

    def update(self, table: str, filters: Mapping[str, str], patch: Mapping[str, Any]) -> list[Row]:
        data = self._call(
            "PATCH",
            f"/rest/v1/{table}{self._query(filters)}",
            self._headers(None, returning=True),
            dict(patch),
        )
        return data if isinstance(data, list) else []

    def get_user_id(self, jwt: str) -> str | None:
        """Hỏi Supabase Auth ai là chủ token. Token sai/hết hạn trả None. Không tự giải mã JWT."""
        headers = {
            "apikey": self._anon,
            "Authorization": f"Bearer {jwt}",
            "Accept": "application/json",
        }
        status, data = self._send("GET", self._base + "/auth/v1/user", headers, None)
        if status == 200 and isinstance(data, dict) and isinstance(data.get("id"), str):
            return data["id"]
        return None
