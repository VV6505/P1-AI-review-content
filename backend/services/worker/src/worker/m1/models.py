"""Kiểu dữ liệu ra của crawl M1 (Pydantic v2, ≈ DTO trong C#)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from worker.m1.crawl.errors import CrawlErrorCode, SkipReason


class PageRecord(BaseModel):
    """Một trang đã lấy. Các trường đầu khớp `sources[]` của contract PKB (`variant` do T3 chọn)."""

    source_id: str  # src_NN
    url: str
    page_type: str
    content_hash: str  # = raw_hash; dùng cho idempotent (NFR-04)
    fetched_at: str
    region: str
    locale: str
    raw_path: str | None  # đường dẫn trong store; None nếu unchanged (không ghi lại)
    fit_path: str | None
    # Chi tiết thêm (spike)
    raw_hash: str
    fit_hash: str
    final_url: str
    score: int
    found_via: str
    anchor_text: str = ""
    http_status: int | None = None
    robots_rule: str = ""
    render_seconds: float = 0.0
    raw_chars: int = 0
    fit_chars: int = 0
    unchanged: bool = False
    title: str | None = None  # <title>, đã làm sạch như trong header markdown
    site_name: str | None = None  # og:site_name


class SkippedPage(BaseModel):
    url: str
    reason: SkipReason
    detail: str = ""
    page_type: str = "other"
    score: int = 0
    found_via: str = ""


class RobotsSummary(BaseModel):
    host: str
    url: str
    status: int | None
    policy: Literal["parsed", "allow_all", "unavailable", "waf_challenge"]
    group: str = ""  # nhóm User-agent áp dụng: own | * | none
    crawl_delay: float | None = None
    sitemaps: list[str] = []
    fetched_at: str
    error: str = ""


class RequestLogEntry(BaseModel):
    """Một request tới host (trang, robots, sitemap). `t` là giây theo đồng hồ monotonic."""

    url: str
    kind: Literal["page", "robots", "sitemap"]
    host: str
    t: float
    fetched_at: str
    status: int | None = None


class CrawlResult(BaseModel):
    status: Literal["completed", "failed"]
    # Chỉ có khi failed. Chuỗi `error` ghi vào generation_jobs.error là `error_message`.
    error_code: CrawlErrorCode | None = None
    error_message: str = ""
    retryable: bool | None = None
    # completed nhưng dừng sớm vì bị chặn ở trang con; warning = "blocked_mid_crawl:<lý do>"
    partial: bool = False
    warning: str | None = None
    root_url: str
    pages: list[PageRecord] = []
    skipped: list[SkippedPage] = []
    skipped_counts: dict[str, int] = {}
    robots: dict[str, RobotsSummary] = {}
    pages_found: int = 0
    pages_used: int = 0
    started_at: str
    finished_at: str
    crawl_seconds: float = 0.0
    min_observed_interval_s: dict[str, float | None] = {}
    requests: list[RequestLogEntry] = []
