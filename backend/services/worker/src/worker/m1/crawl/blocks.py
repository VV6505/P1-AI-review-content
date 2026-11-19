"""Nhận diện trang bị chặn bot (WAF / challenge) và trang đăng nhập. Không vượt chặn."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from worker.m1.crawl.fetcher import FetchResult
from worker.m1.crawl.http import HttpResponse

LOGIN_URL = re.compile(r"login|signin|sign-in|signup|auth|accounts?\.", re.IGNORECASE)
# HTML: chỉ dò marker đặc thù của trang thử thách (chữ "captcha" có thể nằm trong CSS của form
# thường). Nội dung hiển thị: dò câu thông báo chặn.
BLOCK_HTML_MARKERS = re.compile(r"cf-chl|challenge-platform|cf_chl_opt|_cf_chl", re.IGNORECASE)
BLOCK_TEXT_MARKERS = re.compile(
    r"just a moment|attention required|access denied|verify you are human|unusual traffic|"
    r"checking your browser|enable javascript and cookies",
    re.IGNORECASE,
)
# Crawl4AI tự gắn nhãn khi nghi bị chặn và trả success=False với thông báo kiểu này.
ANTIBOT_ERROR = re.compile(r"Blocked by anti-bot protection", re.IGNORECASE)


def waf_challenge_response(resp: HttpResponse) -> str:
    """Trả mô tả nếu response là trang thử thách của WAF (Cloudflare...), không thì chuỗi rỗng."""
    text = resp.body.decode("utf-8", errors="replace")
    if (
        resp.headers.get("cf-mitigated", "").lower() == "challenge"
        or BLOCK_HTML_MARKERS.search(text)
        or BLOCK_TEXT_MARKERS.search(text)
    ):
        return (
            f"status={resp.status} cf-ray={resp.headers.get('cf-ray', '-')} "
            f"server={resp.headers.get('server', '-')}"
        )
    return ""


@dataclass(frozen=True)
class Block:
    kind: Literal[
        "not_found", "crawl_failed", "http_status", "login_redirect", "bot_challenge", "too_short"
    ]
    detail: str
    status: int | None = None

    @property
    def is_waf(self) -> bool:
        """Dấu hiệu WAF / chặn bot: dừng, không retry, không đổi UA."""
        return self.kind == "bot_challenge" or (
            self.kind == "http_status" and self.status in (403, 429)
        )


def detect_block(result: FetchResult, is_home: bool, min_home_chars: int) -> Block | None:
    """Trả `Block` nếu trang có dấu hiệu chặn bot / bắt đăng nhập / lỗi, ngược lại None."""
    status = result.status_code
    if status in (404, 410):
        # Crawl4AI có thể gắn nhãn anti-bot cho trang lỗi ít chữ, nên kiểm tra 404 trước.
        return Block("not_found", f"http_{status}", status)
    if not result.success:
        message = result.error_message[:300]
        if status in (403, 429):
            return Block("http_status", f"http_{status}", status)
        if ANTIBOT_ERROR.search(message) or BLOCK_HTML_MARKERS.search(result.html[:50000]):
            return Block("bot_challenge", message)
        return Block("crawl_failed", message, status)
    if status in (401, 403, 429, 503):
        return Block("http_status", f"http_{status}", status)
    final = result.redirected_url or result.url
    if final and LOGIN_URL.search(urlsplit(final).netloc + urlsplit(final).path):
        return Block("login_redirect", final)
    raw = result.raw_markdown
    if len(raw) < 3000 and (
        BLOCK_HTML_MARKERS.search(result.html[:50000])
        or BLOCK_TEXT_MARKERS.search(f"{result.title}\n{raw}")
    ):
        return Block("bot_challenge", "bot_challenge_marker")
    if is_home and len(raw) < min_home_chars:
        return Block("too_short", f"home_too_short: {len(raw)} chars")
    return None
