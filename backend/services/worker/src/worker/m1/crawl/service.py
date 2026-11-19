"""Crawl 1 product: robots → sitemap → trang chủ → các trang điểm cao nhất (≤ max_pages).

Module này không biết DB, hàng đợi hay API. Hàng đợi gọi `crawl_product`, đọc `CrawlResult`:
- `failed` + `error_code` + `retryable`: ghi `error_message` vào `generation_jobs.error`.
  Retry (tối đa 3 lần, exponential backoff, AC của #42) là việc của hàng đợi.
- `completed`: danh sách `pages` đủ trường `sources[]` của contract PKB.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urlsplit

from worker.m1.config import CrawlOptions, CrawlSettings
from worker.m1.crawl.blocks import Block, detect_block
from worker.m1.crawl.content import content_hash, normalize_text
from worker.m1.crawl.discover import Candidate, Frontier, fetch_sitemap_urls
from worker.m1.crawl.errors import CrawlError, CrawlErrorCode, SkipReason
from worker.m1.crawl.fetcher import FetchResult, PageFetcher
from worker.m1.crawl.http import HttpClient, UrllibHttpClient
from worker.m1.crawl.robots import Robots, fetch_robots
from worker.m1.crawl.store import PageStore, header_value
from worker.m1.crawl.throttle import Throttle
from worker.m1.models import CrawlResult, PageRecord, SkippedPage
from worker.m1.url import InvalidUrlError, normalize_page_url, normalize_product_url

SKIPPED_DETAIL_LIMIT = 50  # số trang over_limit điểm cao nhất được ghi chi tiết
# Trang bị bỏ vì các lý do này luôn ghi chi tiết (bằng chứng cho AC); lý do còn lại chỉ đếm.
_ALWAYS_DETAILED = frozenset(
    {
        SkipReason.ROBOTS_DISALLOWED,
        SkipReason.BLOCKED,
        SkipReason.LOGIN_REDIRECT,
        SkipReason.FETCH_ERROR,
        SkipReason.DUPLICATE,
        SkipReason.REDIRECT_OUT_OF_SCOPE,
    }
)


async def crawl_product(
    url: str,
    options: CrawlOptions,
    fetcher: PageFetcher,
    store: PageStore,
    *,
    previous_hashes: Mapping[str, str] | None = None,
    settings: CrawlSettings | None = None,
    http: HttpClient | None = None,
    throttle: Throttle | None = None,
) -> CrawlResult:
    """Crawl 1 product. Không raise vì lỗi crawl: lỗi cấp job nằm trong `CrawlResult`.

    `previous_hashes`: {url trang → content_hash} của lần crawl trước (rỗng ở lần đầu).
    Trang có hash không đổi không ghi lại vào store; vẫn nằm trong `pages` với `unchanged=True`.
    """
    settings = settings or CrawlSettings.from_env()
    run = _Crawl(
        url,
        options,
        fetcher,
        store,
        previous_hashes or {},
        settings,
        http or UrllibHttpClient(settings.user_agent, settings.http_timeout_s),
        throttle or Throttle(settings.min_interval_s),
    )
    return await run.execute()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _home_error(block: Block) -> CrawlError:
    """Trang chủ bị chặn / lỗi → lỗi cấp job."""
    if block.is_waf:
        return CrawlError(CrawlErrorCode.WAF_CHALLENGE, block.detail)
    if block.kind == "login_redirect" or block.status == 401:
        return CrawlError(CrawlErrorCode.LOGIN_REDIRECT, block.detail)
    if block.kind == "too_short":
        return CrawlError(CrawlErrorCode.NO_CONTENT, block.detail)
    if block.kind == "not_found":  # 404 / 410: URL không trỏ tới trang nào
        return CrawlError(CrawlErrorCode.INVALID_URL, block.detail)
    return CrawlError(CrawlErrorCode.HOME_UNREACHABLE, block.detail)  # 503, lỗi mạng...


class _Crawl:
    def __init__(
        self,
        url: str,
        options: CrawlOptions,
        fetcher: PageFetcher,
        store: PageStore,
        previous_hashes: Mapping[str, str],
        settings: CrawlSettings,
        http: HttpClient,
        throttle: Throttle,
    ) -> None:
        self.url = url
        self.options = options
        self.fetcher = fetcher
        self.store = store
        self.settings = settings
        self.http = http
        self.throttle = throttle
        self.previous: dict[str, str] = {}
        for page_url, digest in previous_hashes.items():
            try:
                self.previous[normalize_page_url(page_url)] = digest
            except ValueError:
                continue
        self.root_url = url
        self.pages: list[PageRecord] = []
        self.robots_by_host: dict[str, Robots] = {}
        self.frontier: Frontier | None = None
        self.blocked_hosts: set[str] = set()
        self.stopped = False  # bị chặn ở host gốc: dừng toàn bộ crawl
        self.block_detail: str | None = None  # lý do chặn đầu tiên ở trang con

    async def execute(self) -> CrawlResult:
        started_at, t0 = _now_iso(), time.monotonic()
        error: CrawlError | None = None
        try:
            await self._run()
            error = self._final_error()
        except CrawlError as e:
            error = e
        return self._result(error, started_at, time.monotonic() - t0)

    # ------------------------------------------------------------------ chạy
    async def _run(self) -> None:
        try:
            self.root_url = normalize_product_url(self.url)
        except InvalidUrlError as e:
            raise CrawlError(CrawlErrorCode.INVALID_URL, str(e)) from e
        s = self.settings
        root_host = urlsplit(self.root_url).netloc.lower()
        allowed = {root_host, *(h.lower() for h in self.options.extra_hosts)}
        suffix = "." + root_host.removeprefix("www.") if self.options.allow_subdomains else None

        def host_ok(host: str) -> bool:
            return host in allowed or bool(suffix and host.endswith(suffix))

        frontier = self.frontier = Frontier(root_host, host_ok, s)

        home_robots = await self._robots_for(root_host)
        self._check_home_robots(home_robots)

        sitemap_urls = await fetch_sitemap_urls(
            home_robots.sitemaps, self.root_url, self.throttle, self.http, s
        )
        frontier.add(self.root_url, "home")
        for sitemap_url in sitemap_urls:
            frontier.add(sitemap_url, "sitemap")

        tried: set[str] = set()
        used_by_type: Counter[str] = Counter()
        seen_hashes: dict[str, str] = {}
        # `tried` đếm cả lần mở trang lỗi/trùng → max_pages giới hạn số request trang
        while len(tried) < s.max_pages and not self.stopped:
            cand = frontier.pick_next(tried, used_by_type, self.blocked_hosts)
            if cand is None:
                break
            tried.add(cand.url)
            is_home = cand.source == "home"
            host = urlsplit(cand.url).netloc

            robots = await self._robots_for(host)
            allowed_by_robots, rule = robots.decide(cand.url)
            if not allowed_by_robots:
                frontier.skip(cand, SkipReason.ROBOTS_DISALLOWED, rule)
                tried.discard(cand.url)  # chưa gửi request trang nào
                continue

            log = await self.throttle.wait(cand.url, "page")
            t_page = time.monotonic()
            result = await self._fetch(cand.url)
            render_seconds = round(time.monotonic() - t_page, 2)
            log.status = result.status_code

            block = detect_block(result, is_home, s.min_home_chars)
            if block:
                if is_home:
                    raise _home_error(block)
                self._skip_blocked(cand, block, host)
                continue

            final_url = normalize_page_url(result.redirected_url or result.url)
            if not host_ok(urlsplit(final_url).netloc):
                frontier.skip(cand, SkipReason.REDIRECT_OUT_OF_SCOPE, final_url)
                continue

            raw_md, fit_md = (
                normalize_text(result.raw_markdown),
                normalize_text(result.fit_markdown),
            )
            # Khử trùng theo raw. Lưu cả raw_hash và fit_hash: bước 2 chọn gửi bản nào cho LLM.
            raw_hash, fit_hash = content_hash(raw_md), content_hash(fit_md)
            if raw_hash in seen_hashes:
                frontier.skip(cand, SkipReason.DUPLICATE, seen_hashes[raw_hash])
                continue
            seen_hashes[raw_hash] = cand.url

            # Link mới từ trang này vào frontier (không tốn request thêm)
            for href, text in result.internal_links:
                frontier.add(href, f"link:{cand.url}", text)

            source_id = f"src_{len(self.pages) + 1:02d}"
            unchanged = self.previous.get(cand.url) == raw_hash
            if unchanged:
                fit_path = raw_path = None
            else:
                stored = self.store.save_page(
                    source_id=source_id,
                    url=cand.url,
                    page_type=cand.page_type,
                    fetched_at=log.fetched_at,
                    raw_md=raw_md,
                    fit_md=fit_md,
                    title=result.title,
                    site_name=result.site_name,
                )
                fit_path, raw_path = stored.fit_path, stored.raw_path
            self.pages.append(
                PageRecord(
                    source_id=source_id,
                    url=cand.url,
                    page_type=cand.page_type,
                    content_hash=raw_hash,
                    fetched_at=log.fetched_at,
                    region=s.region,
                    locale=s.locale,
                    raw_path=raw_path,
                    fit_path=fit_path,
                    raw_hash=raw_hash,
                    fit_hash=fit_hash,
                    final_url=final_url,
                    score=cand.score,
                    found_via=cand.source,
                    anchor_text=cand.text,
                    http_status=result.status_code,
                    robots_rule=rule,
                    render_seconds=render_seconds,
                    raw_chars=len(raw_md),
                    fit_chars=len(fit_md),
                    unchanged=unchanged,
                    title=header_value(result.title) or None,
                    site_name=header_value(result.site_name) or None,
                )
            )
            used_by_type[cand.page_type] += 1

        # Còn trong frontier mà không crawl: bị chặn giữa chừng, vượt giới hạn, hoặc điểm 0
        for cand in list(frontier.candidates.values()):
            if cand.url in tried:
                continue
            if self.stopped or urlsplit(cand.url).netloc in self.blocked_hosts:
                frontier.skip(cand, SkipReason.BLOCKED, self.block_detail or "")
            else:
                frontier.skip(
                    cand, SkipReason.OVER_LIMIT if cand.score > 0 else SkipReason.LOW_SCORE
                )

    async def _fetch(self, url: str) -> FetchResult:
        try:
            return await self.fetcher.fetch(url)
        except Exception as e:  # lỗi của trình duyệt / Crawl4AI: coi như trang lỗi, không sập job
            return FetchResult(url=url, success=False, error_message=f"{type(e).__name__}: {e}")

    async def _robots_for(self, host: str) -> Robots:
        host = host.lower()
        if host not in self.robots_by_host:
            self.robots_by_host[host] = await fetch_robots(
                f"https://{host}", self.throttle, self.http, self.settings
            )
        return self.robots_by_host[host]

    def _check_home_robots(self, robots: Robots) -> None:
        """robots.txt của host trang chủ quyết định job có chạy tiếp không."""
        if robots.policy == "waf_challenge":
            raise CrawlError(CrawlErrorCode.WAF_CHALLENGE, robots.error)
        if robots.policy == "unavailable":
            if robots.status is None and not robots.timed_out:
                # DNS / kết nối lỗi: chưa tới được site, không phải robots chặn
                raise CrawlError(CrawlErrorCode.HOME_UNREACHABLE, robots.error)
            reason = "timeout" if robots.timed_out else f"status {robots.status}"
            raise CrawlError(CrawlErrorCode.ROBOTS_UNAVAILABLE, f"robots.txt {reason}")
        allowed, rule = robots.decide(self.root_url)
        if not allowed:
            raise CrawlError(CrawlErrorCode.ROBOTS_DISALLOW, f"{self.root_url} ({rule})")

    def _skip_blocked(self, cand: Candidate, block: Block, host: str) -> None:
        """Trang con bị chặn / lỗi. Chặn bot (403, 429, challenge): dừng, không gửi thêm request."""
        assert self.frontier is not None
        if block.is_waf:
            self.frontier.skip(cand, SkipReason.BLOCKED, block.detail)
            if self.block_detail is None:
                self.block_detail = block.detail
            if host == self.frontier.root_host:
                self.stopped = True
            else:
                self.blocked_hosts.add(host)  # host phụ bị chặn: bỏ host đó, host gốc chạy tiếp
        elif block.kind == "login_redirect":
            self.frontier.skip(cand, SkipReason.LOGIN_REDIRECT, block.detail)
        else:  # not_found, crawl_failed, 401, 503
            self.frontier.skip(cand, SkipReason.FETCH_ERROR, block.detail)

    # ------------------------------------------------------------------ kết quả
    def _final_error(self) -> CrawlError | None:
        if not any(p.found_via == "home" for p in self.pages):
            return CrawlError(CrawlErrorCode.NO_CONTENT, "không lấy được trang chủ")
        if self.block_detail is not None and len(self.pages) < 2:
            # Chỉ có trang chủ, trang con bị chặn: coi như site chặn bot
            return CrawlError(CrawlErrorCode.WAF_CHALLENGE, self.block_detail)
        return None

    def _result(self, error: CrawlError | None, started_at: str, seconds: float) -> CrawlResult:
        frontier = self.frontier
        skipped_pages = list(frontier.skipped.values()) if frontier else []
        counts = Counter(c.skip_reason.value for c in skipped_pages if c.skip_reason)
        unchanged = sum(p.unchanged for p in self.pages)
        if unchanged:
            counts[SkipReason.UNCHANGED.value] = unchanged
        skipped_pages.sort(key=lambda c: (-c.score, c.url))
        details = [c for c in skipped_pages if c.skip_reason in _ALWAYS_DETAILED]
        details += [c for c in skipped_pages if c.skip_reason == SkipReason.OVER_LIMIT][
            :SKIPPED_DETAIL_LIMIT
        ]
        failed = error is not None
        return CrawlResult(
            status="failed" if failed else "completed",
            error_code=error.code if error else None,
            error_message=error.message if error else "",
            retryable=error.code.retryable if error else None,
            partial=not failed and self.block_detail is not None,
            warning=(
                f"blocked_mid_crawl:{self.block_detail}"
                if not failed and self.block_detail is not None
                else None
            ),
            root_url=self.root_url,
            pages=self.pages,
            skipped=[
                SkippedPage(
                    url=c.url,
                    reason=c.skip_reason,
                    detail=c.skip_detail,
                    page_type=c.page_type,
                    score=c.score,
                    found_via=c.source,
                )
                for c in details
                if c.skip_reason
            ],
            skipped_counts=dict(counts.most_common()),
            robots={h: r.summary() for h, r in self.robots_by_host.items()},
            pages_found=len(self.pages) + len(skipped_pages),
            pages_used=len(self.pages),
            started_at=started_at,
            finished_at=_now_iso(),
            crawl_seconds=round(seconds, 2),
            min_observed_interval_s=self.throttle.min_observed_interval(),
            requests=self.throttle.log,
        )
