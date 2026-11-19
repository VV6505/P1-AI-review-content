"""HTTP đơn giản cho robots.txt và sitemap (không render JS). Adapter để test thay bằng fake."""

from __future__ import annotations

import asyncio
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class HttpResponse:
    status: int | None  # None = không nhận được response (DNS, kết nối, timeout)
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)  # tên header viết thường
    error: str = ""
    timed_out: bool = False


class HttpClient(Protocol):
    async def get(self, url: str) -> HttpResponse: ...


class UrllibHttpClient:
    """GET bằng urllib với UA dự án (RobotFileParser.read() dùng UA Python-urllib nên bỏ)."""

    def __init__(self, user_agent: str, timeout_s: float) -> None:
        self._user_agent = user_agent
        self._timeout_s = timeout_s

    async def get(self, url: str) -> HttpResponse:
        return await asyncio.to_thread(self._get_sync, url)

    def _get_sync(self, url: str) -> HttpResponse:
        req = urllib.request.Request(
            url, headers={"User-Agent": self._user_agent, "Accept-Encoding": "identity"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                return HttpResponse(resp.status, resp.read(), headers)
        except urllib.error.HTTPError as e:
            # Đọc ít byte để dò trang challenge; lỗi HTTP không cần cả body
            headers = {k.lower(): v for k, v in e.headers.items()}
            return HttpResponse(e.code, e.read(4096), headers, str(e))
        except Exception as e:  # noqa: BLE001 — mọi lỗi mạng đều thành response status=None
            reason = getattr(e, "reason", e)
            timed_out = isinstance(e, TimeoutError | socket.timeout) or isinstance(
                reason, TimeoutError | socket.timeout
            )
            return HttpResponse(None, b"", {}, f"{type(e).__name__}: {e}", timed_out)
