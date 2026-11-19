"""Fake cho test runner: DB trong bộ nhớ (có claim nguyên tử như PostgREST) và các bước giả."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from worker.api.db import Row
from worker.m1.models import CrawlResult, PageRecord
from worker.runner.steps import ExtractOutcome, StepError

PRODUCT = "00000000-0000-4000-8000-0000000000c1"


def job(job_id: str = "j1", **over: Any) -> Row:
    row: Row = {
        "id": job_id,
        "product_id": PRODUCT,
        "job_type": "crawl",
        "status": "queued",
        "attempts": 0,
        "error": None,
        "pkb_version": None,
        "result_manifest": None,
        "cost_breakdown": {},
        "created_at": job_id,
        "input_snapshot": {"website_url": "https://example.com"},
    }
    row.update(over)
    return row


class JobsDb:
    def __init__(self, *jobs: Row) -> None:
        self.jobs = list(jobs)
        self.pkb_calls: list[dict[str, Any]] = []
        self.next_version = 1

    def by_id(self, job_id: str) -> Row:
        return next(j for j in self.jobs if j["id"] == job_id)

    @staticmethod
    def _match(row: Row, filters: Mapping[str, str]) -> bool:
        for key, cond in filters.items():
            if key in ("order", "limit", "select"):
                continue
            if cond.startswith("eq.") and str(row.get(key)) != cond[3:]:
                return False
        return True

    def select(self, table: str, filters: Mapping[str, str], jwt: str | None = None) -> list[Row]:
        assert table == "generation_jobs"
        rows = sorted(
            (r for r in self.jobs if self._match(r, filters)), key=lambda r: r["created_at"]
        )
        return [dict(r) for r in rows[: int(filters.get("limit", "100"))]]

    def update(self, table: str, filters: Mapping[str, str], patch: Mapping[str, Any]) -> list[Row]:
        assert table == "generation_jobs"
        hit = [r for r in self.jobs if self._match(r, filters)]
        for r in hit:
            r.update(patch)
        return [dict(r) for r in hit]

    def rpc(self, name: str, args: Mapping[str, Any]) -> Any:
        assert name == "create_pkb_version"
        self.pkb_calls.append(dict(args))
        version, self.next_version = self.next_version, self.next_version + 1
        return version

    def insert(self, table: str, row: Mapping[str, Any]) -> Row:  # pragma: no cover
        raise NotImplementedError

    def get_user_id(self, jwt: str) -> str | None:  # pragma: no cover
        return None


def page(n: int = 1) -> PageRecord:
    return PageRecord(
        source_id=f"src_{n:02d}",
        url=f"https://example.com/p{n}",
        page_type="other",
        content_hash=f"hash{n}",
        fetched_at="2026-11-18T00:00:00Z",
        region="VN",
        locale="vi",
        raw_path=f"pages/{n}.raw.md",
        fit_path=f"pages/{n}.md",
        raw_hash=f"hash{n}",
        fit_hash=f"fit{n}",
        final_url=f"https://example.com/p{n}",
        score=1,
        found_via="home",
    )


def crawl_ok(pages: int = 2) -> CrawlResult:
    return CrawlResult(
        status="completed",
        root_url="https://example.com",
        pages=[page(i + 1) for i in range(pages)],
        pages_found=10,
        pages_used=pages,
        started_at="2026-11-18T00:00:00Z",
        finished_at="2026-11-18T00:00:05Z",
        crawl_seconds=5.0,
    )


def crawl_failed(*, retryable: bool) -> CrawlResult:
    return CrawlResult.model_validate(
        {
            "status": "failed",
            "error_code": None,
            "error_message": "không tải được trang chủ",
            "retryable": retryable,
            "root_url": "https://example.com",
            "started_at": "2026-11-18T00:00:00Z",
            "finished_at": "2026-11-18T00:00:01Z",
        }
    )


class FakeCrawl:
    def __init__(self, *results: CrawlResult | Exception) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, Path]] = []

    async def __call__(self, url: str, out_dir: Path) -> CrawlResult:
        self.calls.append((url, out_dir))
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class FakeExtract:
    def __init__(self, error: StepError | None = None) -> None:
        self.error = error
        self.calls = 0

    async def __call__(self, crawl: CrawlResult, out_dir: Path) -> ExtractOutcome:
        self.calls += 1
        if self.error:
            raise self.error
        return ExtractOutcome(
            data={"identity": {"name": "X"}},
            sources=[{"source_id": p.source_id, "url": p.url} for p in crawl.pages],
            cost_breakdown={"schema_version": "cost-breakdown.v1", "items": []},
            warnings=["w1"],
        )
