"""Cổng (port) của các bước nặng và adapter mặc định cho crawl.

Runner chỉ biết các Protocol này nên test bằng fake, không cần trình duyệt hay LLM. Provider đổi
chỉ sửa adapter (ADR-0005).
"""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

from worker.m1.config import CrawlOptions, CrawlSettings
from worker.m1.crawl.fetcher import Crawl4AIFetcher, FetchResult
from worker.m1.crawl.service import crawl_product
from worker.m1.crawl.store import LocalPageStore
from worker.m1.extract.service import ExtractError, extract_product
from worker.m1.llm import make_llm
from worker.m1.models import CrawlResult


class StepError(Exception):
    """Lỗi của một bước. `retryable` quyết định runner xếp lại hàng hay đánh `failed`."""

    def __init__(
        self, message: str, *, retryable: bool = False, cost_breakdown: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.cost_breakdown = cost_breakdown or {}


@dataclass
class ExtractOutcome:
    data: dict[str, Any]  # product_knowledge.data (PKB v0.3)
    sources: list[dict[str, Any]]  # product_knowledge.sources
    cost_breakdown: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class CrawlStep(Protocol):
    async def __call__(
        self, url: str, out_dir: Path, storage_state: Path | None = None
    ) -> CrawlResult:
        """Crawl `url`, ghi markdown vào `out_dir`. Lỗi crawl nằm trong `CrawlResult`."""
        ...


class ExtractStep(Protocol):
    async def __call__(self, crawl: CrawlResult, out_dir: Path) -> ExtractOutcome:
        """Dựng PKB v0.3 từ kết quả crawl. Lỗi thì raise `StepError`."""
        ...


class MediaStep(Protocol):
    async def __call__(
        self, url: str, out_dir: Path, storage_state: Path | None = None
    ) -> list[dict[str, Any]]:
        """Thu tư liệu có nguồn/quyền rõ; lỗi không được làm mất PKB đã crawl."""
        ...


class Crawl4AICrawlStep:
    """Adapter mặc định: `crawl_product` của M1 với Crawl4AI. Cần `playwright install chromium`."""

    def __init__(self, settings: CrawlSettings | None = None) -> None:
        self._settings = settings or CrawlSettings.from_env()

    async def __call__(
        self, url: str, out_dir: Path, storage_state: Path | None = None
    ) -> CrawlResult:
        captured_text = storage_state.parent / "authenticated-page.txt" if storage_state else None
        if captured_text is not None and captured_text.is_file():
            text = captured_text.read_text(encoding="utf-8")

            class CapturedPageFetcher:
                async def fetch(self, url: str) -> FetchResult:
                    return FetchResult(
                        url=url,
                        success=True,
                        status_code=200,
                        title="Trang sản phẩm sau đăng nhập",
                        raw_markdown=text,
                        fit_markdown=text,
                    )

            return await crawl_product(
                url,
                CrawlOptions(),
                CapturedPageFetcher(),
                LocalPageStore(out_dir),
                settings=self._settings,
            )
        async with Crawl4AIFetcher(self._settings, storage_state) as fetcher:
            return await crawl_product(
                url,
                CrawlOptions(),
                fetcher,
                LocalPageStore(out_dir),
                settings=self._settings,
            )


class GeminiExtractStep:
    """Adapter mặc định: `extract_product` của M1 (1 lời gọi LLM), provider theo `LLM_PROVIDER`."""

    async def __call__(self, crawl: CrawlResult, out_dir: Path) -> ExtractOutcome:
        try:
            llm = make_llm()
        except ValueError as e:  # cấu hình LLM sai (vd. fixture thiếu đường dẫn): không retry
            raise StepError(f"cấu hình LLM không hợp lệ: {e}") from e
        try:
            res = await extract_product(crawl, LocalPageStore(out_dir), llm)
        except ExtractError as e:
            raise StepError(
                e.message, retryable=e.retryable, cost_breakdown=e.cost_breakdown
            ) from e
        return ExtractOutcome(
            data=res.data,
            sources=res.sources,
            cost_breakdown=res.cost_breakdown,
            warnings=res.warnings,
        )


class HomepageCaptureStep:
    """Thu ảnh và một clip thao tác đọc-only để renderer không chỉ dựng slideshow tĩnh."""

    async def __call__(
        self, url: str, out_dir: Path, storage_state: Path | None = None
    ) -> list[dict[str, Any]]:
        from PIL import Image, ImageStat
        from playwright.async_api import async_playwright

        media = out_dir / "media"
        media.mkdir(parents=True, exist_ok=True)
        captured: list[tuple[str, Path]] = []
        recordings: list[tuple[str, Path]] = []
        seen: set[str] = set()
        captured_dir = storage_state.parent / "captured-media" if storage_state else None
        if captured_dir is not None and captured_dir.is_dir():
            for source in sorted(captured_dir.glob("*.png")):
                target = media / f"homepage-{source.stem}.png"
                shutil.copy2(source, target)
                with Image.open(target) as image:
                    stat = ImageStat.Stat(image.convert("RGB"))
                variance = sum(stat.var) / len(stat.var)
                digest = hashlib.sha256(target.read_bytes()).hexdigest()
                if variance < 4 or digest in seen:
                    target.unlink(missing_ok=True)
                    continue
                seen.add(digest)
                captured.append((source.stem, target))
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                video_dir = media / "browser-agent-video"
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    storage_state=str(storage_state) if storage_state is not None else None,
                )
                page = await context.new_page()
                response = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                if response is not None and response.status in {401, 403}:
                    raise RuntimeError(f"trang yêu cầu đăng nhập (HTTP {response.status})")
                try:
                    await page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:
                    pass
                await page.wait_for_timeout(2_000)
                if await page.locator("input[type=password]:visible").count() > 0:
                    raise RuntimeError("phiên đăng nhập chưa hợp lệ hoặc đã hết hạn")
                body_text = (await page.locator("body").inner_text()).strip()
                if len(body_text) < 20:
                    raise RuntimeError("trang không hiển thị đủ nội dung để làm tư liệu")
                # Không đưa giá trị input/avatar phổ biến vào ảnh demo sau đăng nhập.
                await page.add_style_tag(
                    content=(
                        "input:not([type=search]), textarea, [data-private], [class*='avatar'], [class*='email']"
                        "{filter:blur(10px)!important}"
                    )
                )
                # Con trỏ trong clip đi theo các tọa độ mouse thật; không mô phỏng click giả.
                cursor_script = """() => {
                      const cursor = document.createElement('div');
                      cursor.id = '__p1_agent_cursor';
                      cursor.style.cssText = 'position:fixed;z-index:2147483647;width:32px;height:40px;'
                        + 'pointer-events:none;left:20px;top:20px;transition:left .08s linear,top .08s linear;'
                        + 'filter:drop-shadow(0 3px 3px #0009);'
                        + 'background: url("data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%2732%27 height=%2740%27 viewBox=%270 0 32 40%27%3E%3Cpath d=%27M3 2v30l8-8 5 13 6-3-5-12h12z%27 fill=%27white%27 stroke=%27%23111827%27 stroke-width=%272.5%27/%3E%3C/svg%3E") center / contain no-repeat';
                      document.documentElement.appendChild(cursor);
                      window.addEventListener('mousemove', e => {
                        cursor.style.left = e.clientX + 'px'; cursor.style.top = e.clientY + 'px';
                      });
                      window.addEventListener('mousedown', () => {
                        cursor.style.filter = 'drop-shadow(0 0 12px #a78bfa)';
                        cursor.style.transform = 'scale(.82)';
                      });
                      window.addEventListener('mouseup', () => {
                        cursor.style.filter = 'drop-shadow(0 3px 3px #0009)';
                        cursor.style.transform = 'scale(1)';
                      });
                    }"""
                await page.evaluate(cursor_script)
                await context.add_init_script(
                    f"document.addEventListener('DOMContentLoaded', {cursor_script});"
                )
                height = int(await page.evaluate("Math.max(document.body.scrollHeight, 720)"))
                positions = [
                    ("top", 0),
                    ("middle", max(0, height // 2 - 360)),
                    ("bottom", max(0, height - 720)),
                ]
                for name, y in positions:
                    await page.evaluate("y => window.scrollTo(0, y)", y)
                    await page.wait_for_timeout(700)
                    target = media / f"homepage-{name}.png"
                    await page.screenshot(path=str(target), full_page=False)
                    with Image.open(target) as image:
                        stat = ImageStat.Stat(image.convert("RGB"))
                    variance = sum(stat.var) / len(stat.var)
                    digest = hashlib.sha256(target.read_bytes()).hexdigest()
                    if variance < 4 or digest in seen:
                        target.unlink(missing_ok=True)
                        continue
                    seen.add(digest)
                    captured.append((name, target))
                # Lập bản đồ điều hướng và thu thêm tối đa bốn trang/tab nội bộ an toàn.
                # Đây là discovery có giới hạn, không phải crawler bấm mọi thứ trên website.
                raw_links = await page.locator("a[href]:visible").evaluate_all(
                    """els => els.slice(0, 120).map(el => ({
                      href: el.getAttribute('href') || '',
                      label: (el.innerText || el.getAttribute('aria-label') || '').trim()
                    }))"""
                )
                base_host = urlparse(page.url).netloc
                blocked_tokens = (
                    "logout", "sign out", "delete", "remove", "checkout", "payment",
                    "purchase", "buy", "cart", "đăng xuất", "xóa", "mua", "thanh toán",
                )
                priority_tokens = (
                    "feature", "product", "demo", "tool", "pricing", "dashboard",
                    "lesson", "course", "tính năng", "sản phẩm", "bảng giá",
                )
                navigation: list[tuple[int, str, str]] = []
                visited_urls = {page.url.rstrip("/")}
                for item in raw_links:
                    href = str(item.get("href") or "").strip()
                    label = str(item.get("label") or "").strip()
                    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                        continue
                    absolute = urljoin(page.url, href)
                    parsed = urlparse(absolute)
                    haystack = f"{parsed.path} {label}".lower()
                    if (
                        parsed.scheme not in {"http", "https"}
                        or parsed.netloc != base_host
                        or any(token in haystack for token in blocked_tokens)
                        or absolute.rstrip("/") in visited_urls
                    ):
                        continue
                    score = sum(1 for token in priority_tokens if token in haystack)
                    navigation.append((score, absolute, label))
                    visited_urls.add(absolute.rstrip("/"))
                navigation.sort(key=lambda item: (-item[0], len(urlparse(item[1]).path)))
                for nav_index, (_score, target_url, label) in enumerate(navigation[:4], start=1):
                    try:
                        response = await page.goto(
                            target_url, wait_until="domcontentloaded", timeout=20_000
                        )
                        if response is not None and response.status >= 400:
                            continue
                        await page.wait_for_timeout(900)
                        if await page.locator("input[type=password]:visible").count() > 0:
                            continue
                        body = (await page.locator("body").inner_text()).strip()
                        if len(body) < 40:
                            continue
                        await page.add_style_tag(
                            content=(
                                "input:not([type=search]), textarea, [data-private], [class*='avatar'], [class*='email']"
                                "{filter:blur(10px)!important}"
                            )
                        )
                        slug = re.sub(r"[^a-z0-9]+", "-", (label or urlparse(target_url).path).lower())
                        slug = slug.strip("-")[:36] or f"page-{nav_index}"
                        target = media / f"navigation-{nav_index}-{slug}.png"
                        await page.screenshot(path=str(target), full_page=False)
                        with Image.open(target) as image:
                            stat = ImageStat.Stat(image.convert("RGB"))
                        variance = sum(stat.var) / len(stat.var)
                        digest = hashlib.sha256(target.read_bytes()).hexdigest()
                        if variance < 4 or digest in seen:
                            target.unlink(missing_ok=True)
                            continue
                        seen.add(digest)
                        captured.append((f"tab-{nav_index}-{slug}", target))
                    except Exception:
                        continue
                # Giai đoạn lập bản đồ/chụp ảnh không nằm trong video demo.
                await context.close()
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    storage_state=str(storage_state) if storage_state is not None else None,
                    record_video_dir=str(video_dir),
                    record_video_size={"width": 1280, "height": 720},
                )
                await context.add_init_script(
                    f"document.addEventListener('DOMContentLoaded', {cursor_script});"
                )
                page = await context.new_page()
                response = await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                if response is not None and response.status in {401, 403}:
                    raise RuntimeError(f"trang yêu cầu đăng nhập (HTTP {response.status})")
                await page.add_style_tag(
                    content=(
                        "input:not([type=search]), textarea, [data-private], "
                        "[class*='avatar'], [class*='email']{filter:blur(10px)!important}"
                    )
                )
                await page.wait_for_timeout(700)
                # Quay một demo đọc-only: cuộn qua nội dung, hover và mở tối đa một liên kết
                # nội bộ an toàn. Không đụng form, logout, thanh toán hay liên kết ngoài domain.
                await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
                await page.wait_for_timeout(900)
                await page.mouse.move(230, 200, steps=18)
                await page.wait_for_timeout(700)
                await page.mouse.wheel(0, max(480, min(1100, height // 3)))
                await page.mouse.move(920, 420, steps=24)
                await page.wait_for_timeout(1100)
                # Chỉ gõ vào ô tìm kiếm công khai; không gửi form hay chạm dữ liệu tài khoản.
                search = page.locator('input[type="search"]:visible').first
                if storage_state is None and await search.count() > 0:
                    try:
                        query = re.sub(r"\s+", " ", (await page.title()).split("|")[0]).strip()[:32]
                        if query:
                            await search.scroll_into_view_if_needed()
                            box = await search.bounding_box()
                            if box:
                                await page.mouse.move(
                                    box["x"] + min(100, box["width"] / 2),
                                    box["y"] + box["height"] / 2,
                                    steps=20,
                                )
                                await search.click()
                                await page.keyboard.type(query, delay=85)
                                await page.wait_for_timeout(900)
                    except Exception:
                        pass
                for score, target_url, _label in navigation:
                    if score <= 0:
                        break
                    link = page.locator("a[href]:visible")
                    matches = await link.evaluate_all(
                        "(els, target) => els.filter(el => el.href === target).map(el => els.indexOf(el))",
                        target_url,
                    )
                    if not matches:
                        continue
                    link = link.nth(matches[0])
                    await link.scroll_into_view_if_needed()
                    box = await link.bounding_box()
                    if not box:
                        continue
                    x = min(1240, max(10, box["x"] + box["width"] / 2))
                    y = min(680, max(10, box["y"] + box["height"] / 2))
                    await page.mouse.move(x, y, steps=24)
                    await link.hover()
                    await page.wait_for_timeout(800)
                    try:
                        await link.click(timeout=3_000, delay=180)
                        await page.wait_for_load_state("domcontentloaded", timeout=8_000)
                        await page.wait_for_timeout(1_100)
                    except Exception:
                        pass
                    break
                video = page.video
                await context.close()
                if video is not None:
                    recorded = Path(await video.path())
                    if recorded.is_file() and recorded.stat().st_size > 10_000:
                        target = media / "browser-agent-guided.webm"
                        shutil.move(str(recorded), target)
                        recordings.append(("guided", target))
            finally:
                await browser.close()
        if not captured and not recordings:
            raise RuntimeError("ảnh chụp trang sản phẩm bị trắng hoặc trùng hoàn toàn")
        return self._assets(captured, recordings)

    @staticmethod
    def _assets(
        captured: list[tuple[str, Path]], recordings: list[tuple[str, Path]] | None = None
    ) -> list[dict[str, Any]]:
        assets = [
            {
                "asset_id": f"crawl:screenshot:{name}",
                "kind": "screenshot",
                "path": str(target.resolve()),
                "allowed_use": ["internal_demo"],
                "rights_basis": (
                    "Ảnh chụp từ URL do owner cung cấp; chỉ dùng demo nội bộ, "
                    "phát hành công khai cần xác nhận quyền."
                ),
            }
            for name, target in captured
        ]
        assets.extend(
            {
                "asset_id": f"crawl:screen-recording:{name}",
                "kind": "screen_recording",
                "path": str(target.resolve()),
                "allowed_use": ["internal_demo"],
                "rights_basis": (
                    "Clip thao tác đọc-only trên URL do owner cung cấp; không chứa thao tác ghi, "
                    "phát hành công khai cần owner xác nhận quyền và kiểm tra dữ liệu riêng tư."
                ),
            }
            for name, target in (recordings or [])
        )
        return assets
