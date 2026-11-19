"""Giữ khoảng cách ≥ 1 giây giữa 2 request tới cùng host (NFR-05)."""

from __future__ import annotations

import asyncio
import itertools
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

from worker.m1.models import RequestLogEntry


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class Throttle:
    """Mọi request (mở trang, tải robots, tải sitemap) đều phải gọi `wait` trước.

    interval của host = max(min_interval, Crawl-delay trong robots.txt nếu có).
    `clock` và `sleep` truyền được để test chạy không cần chờ thật.
    """

    def __init__(
        self,
        min_interval: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._interval: dict[str, float] = {}
        self._last: dict[str, float] = {}
        self.log: list[RequestLogEntry] = []

    def set_interval(self, host: str, seconds: float) -> None:
        self._interval[host] = max(self.min_interval, seconds)

    async def wait(self, url: str, kind: Literal["page", "robots", "sitemap"]) -> RequestLogEntry:
        host = urlsplit(url).netloc
        interval = self._interval.get(host, self.min_interval)
        last = self._last.get(host)
        # Lặp vì trên Windows asyncio.sleep có thể dậy sớm ~15 ms
        while last is not None and (gap := self._clock() - last) < interval:
            await self._sleep(interval - gap + 0.005)
        t = self._clock()
        entry = RequestLogEntry(url=url, kind=kind, host=host, t=round(t, 3), fetched_at=now_iso())
        self._last[host] = t
        self.log.append(entry)
        return entry

    def min_observed_interval(self) -> dict[str, float | None]:
        by_host: dict[str, list[float]] = {}
        for e in self.log:
            by_host.setdefault(e.host, []).append(e.t)
        result: dict[str, float | None] = {}
        for host, ts in by_host.items():
            gaps = [b - a for a, b in itertools.pairwise(ts)]
            result[host] = round(min(gaps), 3) if gaps else None
        return result
