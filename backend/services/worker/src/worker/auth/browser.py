"""Phát hiện login wall và mở Chromium thật để owner tự đăng nhập.

Mật khẩu không đi qua API/AI. API chỉ lưu Playwright storage state sau khi owner xác nhận.
Manager dùng một thread vì Playwright sync API phải được tạo và dùng trên cùng thread.
"""

from __future__ import annotations

import queue
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

LOGIN_PATH = re.compile(
    r"(^|/)(log-?in|sign-?in|signin|auth|account/login|dang-?nhap|đăng-?nhập)(/|$|\.)",
    re.IGNORECASE,
)
TIMEOUT_S = 600


def is_login_url(url: str) -> bool:
    return bool(LOGIN_PATH.search(urlparse(url).path or "/"))


def page_has_login(page: Page) -> bool:
    try:
        if page.locator("input[type=password]:visible").count() > 0:
            return True
    except Exception:
        pass
    return is_login_url(page.url)


@dataclass(frozen=True)
class LoginProbe:
    requires_login: bool
    login_url: str | None = None
    reason: str | None = None


@dataclass
class _Window:
    browser: Browser
    context: BrowserContext
    page: Page
    opened: float = field(default_factory=time.monotonic)


class LoginWindows:
    def __init__(self, timeout_s: float = TIMEOUT_S) -> None:
        self.timeout_s = timeout_s
        self._commands: queue.Queue[tuple[Callable[[Playwright], Any], Future[Any]] | None] = (
            queue.Queue()
        )
        self._windows: dict[str, _Window] = {}
        self._status: dict[str, str] = {}
        self._thread = threading.Thread(target=self._loop, name="p1-login-windows", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        with sync_playwright() as playwright:
            while True:
                try:
                    item = self._commands.get(timeout=0.2)
                except queue.Empty:
                    self._expire()
                    continue
                if item is None:
                    break
                call, future = item
                try:
                    future.set_result(call(playwright))
                except Exception as exc:  # noqa: BLE001 - chuyển lỗi về request API
                    future.set_exception(exc)
            for key in list(self._windows):
                self._close(key, "closed")

    def _submit(self, call: Callable[[Playwright], Any]) -> Any:
        future: Future[Any] = Future()
        self._commands.put((call, future))
        return future.result(timeout=90)

    def _close(self, key: str, status: str) -> None:
        window = self._windows.pop(key, None)
        if window is not None:
            try:
                window.context.close()
            finally:
                window.browser.close()
        self._status[key] = status

    def _expire(self) -> None:
        for key, window in list(self._windows.items()):
            if time.monotonic() - window.opened >= self.timeout_s:
                self._close(key, "timeout")

    def probe(self, url: str) -> LoginProbe:
        def call(playwright: Playwright) -> LoginProbe:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                response = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                status = response.status if response is not None else None
                if status in {401, 403}:
                    return LoginProbe(True, page.url, f"http_{status}")
                if page_has_login(page):
                    reason = "password_field" if not is_login_url(url) else "login_page"
                    return LoginProbe(True, page.url, reason)
                return LoginProbe(False)
            finally:
                browser.close()

        return self._submit(call)  # type: ignore[no-any-return]

    def open(self, key: str, url: str) -> None:
        def call(playwright: Playwright) -> None:
            self._close(key, "closed")
            try:
                # Ưu tiên Chrome cài trên máy để tương thích JS/SSO tốt hơn Chromium đóng gói.
                browser = playwright.chromium.launch(channel="chrome", headless=False)
            except Exception:  # noqa: BLE001 - máy không có Chrome thì dùng Chromium Playwright
                browser = playwright.chromium.launch(headless=False)
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            self._windows[key] = _Window(browser, context, page)
            self._status[key] = "browser_open"

        self._submit(call)

    def status(self, key: str) -> str:
        return "browser_open" if key in self._windows else self._status.get(key, "none")

    def finish(self, key: str, state_path: Path) -> dict[str, Any]:
        def call(_playwright: Playwright) -> dict[str, Any]:
            window = self._windows.get(key)
            if window is None:
                raise RuntimeError("cửa sổ đăng nhập không còn mở")
            page = next(
                (p for p in reversed(window.context.pages) if not p.url.startswith("about:")),
                window.page,
            )
            if page_has_login(page):
                return {"ok": False, "final_url": page.url}
            state_path.parent.mkdir(parents=True, exist_ok=True)
            window.context.storage_state(path=str(state_path), indexed_db=True)
            # Một số SPA demo chỉ ẩn login trong DOM, không tạo cookie/localStorage. Lưu lại
            # chính DOM đã được owner mở khóa để runner vẫn đọc/chụp được nội dung đã xác nhận.
            body_text = page.locator("body").inner_text().strip()
            if body_text:
                (state_path.parent / "authenticated-page.txt").write_text(
                    body_text, encoding="utf-8"
                )
                (state_path.parent / "authenticated-page.html").write_text(
                    page.content(), encoding="utf-8"
                )
            page.add_style_tag(
                content=(
                    "input, textarea, [data-private], [class*='avatar'], [class*='email']"
                    "{filter:blur(10px)!important}"
                )
            )
            capture_dir = state_path.parent / "captured-media"
            capture_dir.mkdir(parents=True, exist_ok=True)
            height = int(page.evaluate("Math.max(document.body.scrollHeight, 720)"))
            positions = {
                "top": 0,
                "middle": max(0, height // 2 - 360),
                "bottom": max(0, height - 720),
            }
            for name, y in positions.items():
                page.evaluate("y => window.scrollTo(0, y)", y)
                page.wait_for_timeout(500)
                page.screenshot(path=str(capture_dir / f"owner-{name}.png"), full_page=False)
            final_url = page.url
            self._close(key, "closed")
            return {"ok": True, "final_url": final_url}

        return self._submit(call)  # type: ignore[no-any-return]

    def close(self, key: str) -> None:
        self._submit(lambda _playwright: self._close(key, "closed"))

    def shutdown(self) -> None:
        self._commands.put(None)
        self._thread.join(timeout=15)
