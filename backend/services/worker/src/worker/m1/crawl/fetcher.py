"""Adapter render trang bằng Crawl4AI (thư viện, không dùng Docker server). ADR-0001.

Chỉ file này dùng `crawl4ai`, và import trong `Crawl4AIFetcher.__init__` để test (dùng fake
`PageFetcher`) không phải nạp thư viện nặng.
Không bật stealth, không đổi UA, không proxy: bị chặn thì dừng (quy tắc crawl số 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol

from worker.m1.config import CrawlSettings


@dataclass
class FetchResult:
    """Kết quả render 1 trang, tách khỏi kiểu của Crawl4AI."""

    url: str
    success: bool = True
    error_message: str = ""
    status_code: int | None = None
    redirected_url: str | None = None
    html: str = ""
    title: str = ""
    site_name: str = ""  # og:site_name
    raw_markdown: str = ""
    fit_markdown: str = ""
    internal_links: list[tuple[str, str]] = field(default_factory=list)  # (href, anchor text)


class PageFetcher(Protocol):
    async def fetch(self, url: str) -> FetchResult: ...


class Crawl4AIFetcher:
    """Dùng: `async with Crawl4AIFetcher(settings) as fetcher: ...`.

    Cần trình duyệt: `uv run playwright install chromium` (một lần trên máy chạy thật).
    """

    def __init__(self, settings: CrawlSettings, storage_state: Path | None = None) -> None:
        from crawl4ai import (
            AsyncWebCrawler,
            BrowserConfig,
            CacheMode,
            CrawlerRunConfig,
            PruningContentFilterLXML,
        )
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

        self._run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,  # không dùng cache: log request phải thật
            user_agent=settings.user_agent,
            wait_until="domcontentloaded",  # networkidle hay treo ở SPA
            delay_before_return_html=settings.render_delay_s,
            scan_full_page=True,  # cuộn hết trang để nội dung lazy-load hiện ra
            page_timeout=settings.page_timeout_ms,
            word_count_threshold=3,  # mặc định cao làm rơi thẻ giá (ít chữ)
            markdown_generator=DefaultMarkdownGenerator(
                content_filter=PruningContentFilterLXML(
                    threshold=0.45, threshold_type="dynamic", min_word_threshold=3
                ),
            ),
            verbose=False,
        )
        browser_config = BrowserConfig(
            headless=True,
            user_agent=settings.user_agent,
            storage_state=str(storage_state) if storage_state is not None else None,
            verbose=False,
        )
        self._crawler = AsyncWebCrawler(config=browser_config)

    async def __aenter__(self) -> Crawl4AIFetcher:
        await self._crawler.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._crawler.__aexit__(exc_type, exc, tb)

    async def fetch(self, url: str) -> FetchResult:
        result: Any = await self._crawler.arun(url, config=self._run_config)
        markdown = result.markdown
        links = (result.links or {}).get("internal", [])
        return FetchResult(
            url=result.url or url,
            success=bool(result.success),
            error_message=str(result.error_message or ""),
            status_code=getattr(result, "status_code", None),
            redirected_url=getattr(result, "redirected_url", None),
            html=result.html or "",
            title=str((result.metadata or {}).get("title") or ""),
            site_name=str((result.metadata or {}).get("og:site_name") or ""),
            raw_markdown=(markdown.raw_markdown if markdown else "") or "",
            fit_markdown=(markdown.fit_markdown if markdown else "") or "",
            internal_links=[(link.get("href", ""), link.get("text", "")) for link in links],
        )
