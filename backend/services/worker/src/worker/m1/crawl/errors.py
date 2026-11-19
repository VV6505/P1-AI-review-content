"""Mã lỗi crawl: cấp job (job `failed`) và lý do bỏ qua trang (job vẫn chạy tiếp).

Module này chỉ báo `retryable`. Retry tối đa 3 lần với exponential backoff (AC của #42)
là việc của hàng đợi `generation_jobs`, không làm ở đây.
"""

from __future__ import annotations

from enum import StrEnum


class CrawlErrorCode(StrEnum):
    """Mã lỗi cấp job. `generation_jobs.error` bắt đầu bằng mã (xem `CrawlError.message`)."""

    INVALID_URL = "invalid_url"
    WAF_CHALLENGE = "waf_challenge"
    ROBOTS_DISALLOW = "robots_disallow"
    ROBOTS_UNAVAILABLE = "robots_unavailable"
    LOGIN_REDIRECT = "login_redirect"
    HOME_UNREACHABLE = "home_unreachable"
    NO_CONTENT = "no_content"

    @property
    def retryable(self) -> bool:
        return self in _RETRYABLE


# Lỗi tạm thời (mạng, robots chưa tải được) thì thử lại được. WAF, robots cấm, đăng nhập: không.
_RETRYABLE = frozenset({CrawlErrorCode.ROBOTS_UNAVAILABLE, CrawlErrorCode.HOME_UNREACHABLE})


class CrawlError(Exception):
    """Lỗi cấp job. Service bắt lại và đóng gói vào `CrawlResult`."""

    def __init__(self, code: CrawlErrorCode, detail: str = "") -> None:
        super().__init__(f"{code.value}: {detail}" if detail else code.value)
        self.code = code
        self.detail = detail

    @property
    def message(self) -> str:
        return str(self)


class SkipReason(StrEnum):
    """Lý do bỏ qua một trang. Tên khác spike: xem bảng đối chiếu ở đặc tả M1, mục Mã lỗi crawl."""

    ROBOTS_DISALLOWED = "robots_disallowed"  # spike: robots_disallow
    LOGIN_REDIRECT = "login_redirect"
    OVER_LIMIT = "over_limit"
    DUPLICATE = "duplicate"  # spike: duplicate_of
    # Thay `not_english` (không giữ alias). Ngôn ngữ dò theo tiền tố path, xem discover.py.
    LANGUAGE_NOT_ALLOWED = "language_not_allowed"  # ngôn ngữ ngoài M1_CRAWL_LANGUAGES
    TRANSLATION_DUPLICATE = "translation_duplicate"  # spike: locale_duplicate
    NON_HTML = "non_html"  # spike: asset
    FETCH_ERROR = "fetch_error"  # spike: not_found, crawl_failed
    UNCHANGED = "unchanged"  # NFR-04: content_hash không đổi
    BLOCKED = "blocked"  # bị chặn giữa chừng, hoặc chưa crawl vì đã dừng
    # Giữ tên spike
    OUT_OF_SCOPE = "out_of_scope"
    EXCLUDED_PATH = "excluded_path"
    LOW_SCORE = "low_score"
    REDIRECT_OUT_OF_SCOPE = "redirect_out_of_scope"
