"""Fake cho test crawl: không mạng, không trình duyệt, không chờ thật."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit

from worker.m1.config import CrawlOptions, CrawlSettings
from worker.m1.crawl.fetcher import FetchResult
from worker.m1.crawl.http import HttpResponse
from worker.m1.crawl.service import crawl_product
from worker.m1.crawl.store import StoredPaths
from worker.m1.crawl.throttle import Throttle
from worker.m1.models import CrawlResult

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeClock:
    """Đồng hồ giả: `sleep` chỉ đẩy giờ lên, test chạy tức thì nhưng vẫn kiểm được khoảng cách."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeHttp:
    """GET giả cho robots.txt và sitemap. URL không khai báo → 404."""

    def __init__(self, responses: dict[str, HttpResponse] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[str] = []

    async def get(self, url: str) -> HttpResponse:
        self.calls.append(url)
        return self.responses.get(url, HttpResponse(404, b"", {}, "404"))


def text_response(body: str, status: int = 200, **headers: str) -> HttpResponse:
    return HttpResponse(
        status, body.encode("utf-8"), {k.replace("_", "-"): v for k, v in headers.items()}
    )


class FakeFetcher:
    """Trả `FetchResult` khai báo sẵn theo URL; URL lạ → 404. `fail` là URL sẽ raise."""

    def __init__(self, pages: dict[str, FetchResult], fail: Iterable[str] = ()) -> None:
        self.pages = pages
        self.fail = set(fail)
        self.calls: list[str] = []

    async def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        if url in self.fail:
            raise RuntimeError("browser crashed")
        return self.pages.get(url) or FetchResult(url=url, status_code=404, success=True)


class MemoryStore:
    def __init__(self) -> None:
        self.saved: dict[str, dict[str, str]] = {}

    def save_page(
        self,
        *,
        source_id: str,
        url: str,
        page_type: str,
        fetched_at: str,
        raw_md: str,
        fit_md: str,
        title: str = "",
        site_name: str = "",
    ) -> StoredPaths:
        self.saved[url] = {
            "source_id": source_id,
            "raw": raw_md,
            "fit": fit_md,
            "title": title,
            "site_name": site_name,
        }
        return StoredPaths(fit_path=f"pages/{source_id}.md", raw_path=f"pages/{source_id}.raw.md")


def page(
    url: str,
    links: Iterable[str | tuple[str, str]] = (),
    *,
    body: str | None = None,
    status: int = 200,
    **kwargs: object,
) -> FetchResult:
    """Trang render được. Mặc định mỗi URL có nội dung riêng (để không bị coi là trùng)."""
    body = body if body is not None else fixture("page.md") + f"\nSource page: {url}\n"
    link_pairs = [(link, "") if isinstance(link, str) else link for link in links]
    fields: dict[str, object] = {"title": "Example", **kwargs}
    return FetchResult(
        url=url,
        status_code=status,
        html="<html></html>",
        raw_markdown=body,
        fit_markdown=body,
        internal_links=link_pairs,
        **fields,  # type: ignore[arg-type]
    )


def challenge_page(url: str, status: int = 403) -> FetchResult:
    return FetchResult(
        url=url,
        status_code=status,
        html=fixture("cloudflare_challenge.html"),
        title="Just a moment...",
        raw_markdown="Enable JavaScript and cookies to continue",
    )


def run_crawl(
    url: str,
    pages: dict[str, FetchResult],
    *,
    http: FakeHttp | None = None,
    options: CrawlOptions | None = None,
    previous_hashes: dict[str, str] | None = None,
    settings: CrawlSettings | None = None,
    store: MemoryStore | None = None,
    fetcher: FakeFetcher | None = None,
    robots: str | None = "",
) -> tuple[CrawlResult, FakeFetcher, MemoryStore, FakeHttp]:
    """Chạy `crawl_product` với fake. `robots=""` là robots.txt rỗng (cho phép hết)."""
    http = http or FakeHttp()
    if robots is not None:
        host = urlsplit(url).netloc
        http.responses.setdefault(f"https://{host}/robots.txt", text_response(robots))
    fetcher = fetcher or FakeFetcher(pages)
    store = store or MemoryStore()
    settings = settings or CrawlSettings()
    clock = FakeClock()
    result = asyncio.run(
        crawl_product(
            url,
            options or CrawlOptions(),
            fetcher,
            store,
            previous_hashes=previous_hashes,
            settings=settings,
            http=http,
            throttle=Throttle(settings.min_interval_s, clock=clock, sleep=clock.sleep),
        )
    )
    return result, fetcher, store, http
