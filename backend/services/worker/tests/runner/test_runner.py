import asyncio

from tests.runner.fakes import (
    FakeCrawl,
    FakeExtract,
    JobsDb,
    crawl_failed,
    crawl_ok,
    job,
)
from worker.runner.runner import JobRunner
from worker.runner.steps import StepError
from worker.settings import Settings


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def make(db: JobsDb, crawl: FakeCrawl, extract: FakeExtract | None = None, **s: object):
    settings = Settings(page_store_dir="/tmp/pages", runner_retry_backoff_s=30.0, **s)  # type: ignore[arg-type]
    clock = Clock()
    return JobRunner(db, settings, crawl, extract, clock=clock), clock


def run(runner: JobRunner) -> bool:
    return asyncio.run(runner.run_once())


def test_no_job_returns_false() -> None:
    runner, _ = make(JobsDb(), FakeCrawl())
    assert run(runner) is False


def test_happy_path_creates_pkb_and_completes() -> None:
    db = JobsDb(job())
    crawl, extract = FakeCrawl(crawl_ok(2)), FakeExtract()
    runner, _ = make(db, crawl, extract)
    assert run(runner) is True
    j = db.by_id("j1")
    assert j["status"] == "completed" and j["attempts"] == 1 and j["error"] is None
    assert j["pkb_version"] == 1
    assert j["cost_breakdown"]["schema_version"] == "cost-breakdown.v1"
    m = j["result_manifest"]
    assert m["pages_used"] == 2 and [p["content_hash"] for p in m["pages"]] == ["hash1", "hash2"]
    assert m["extract"] == {"status": "completed", "warnings": ["w1"]}
    assert db.pkb_calls[0]["p_product_id"] == j["product_id"]
    assert crawl.calls == [("https://example.com", crawl.calls[0][1])]
    assert crawl.calls[0][1].name == "j1"  # thư mục theo job id


def test_without_extract_completes_without_pkb() -> None:
    db = JobsDb(job())
    runner, _ = make(db, FakeCrawl(crawl_ok()))
    run(runner)
    j = db.by_id("j1")
    assert j["status"] == "completed" and j["pkb_version"] is None
    assert j["result_manifest"]["extract"] == {"status": "skipped"}
    assert db.pkb_calls == []


def test_existing_pkb_version_is_not_recreated() -> None:
    db = JobsDb(job(pkb_version=7))
    extract = FakeExtract()
    runner, _ = make(db, FakeCrawl(crawl_ok()), extract)
    run(runner)
    assert extract.calls == 0 and db.pkb_calls == []
    assert db.by_id("j1")["status"] == "completed"


def test_claim_lost_returns_false() -> None:
    db = JobsDb(job())
    runner, _ = make(db, FakeCrawl())
    # runner khác nhận trước giữa lúc select và update
    original = db.select

    def select_then_steal(*a, **k):  # type: ignore[no-untyped-def]
        rows = original(*a, **k)
        db.by_id("j1")["status"] = "running"
        return rows

    db.select = select_then_steal  # type: ignore[method-assign]
    assert run(runner) is False
    assert db.by_id("j1")["attempts"] == 0


def test_non_retryable_crawl_failure_marks_failed() -> None:
    db = JobsDb(job())
    runner, _ = make(db, FakeCrawl(crawl_failed(retryable=False)))
    run(runner)
    j = db.by_id("j1")
    assert j["status"] == "failed" and "trang chủ" in j["error"]


def test_retryable_requeues_with_backoff_then_fails_at_limit() -> None:
    db = JobsDb(job())
    crawl = FakeCrawl(*[crawl_failed(retryable=True)] * 3)
    runner, clock = make(db, crawl, runner_max_attempts=3)
    run(runner)
    j = db.by_id("j1")
    assert j["status"] == "queued" and j["attempts"] == 1 and j["error"]
    assert run(runner) is False  # đang backoff 30s
    clock.t = 31
    run(runner)
    assert db.by_id("j1")["status"] == "queued" and db.by_id("j1")["attempts"] == 2
    clock.t = 31 + 61  # backoff lần 2 = 60s
    run(runner)
    j = db.by_id("j1")
    assert j["status"] == "failed" and j["attempts"] == 3 and j["error"]


def test_extract_error_records_cost_and_fails() -> None:
    db = JobsDb(job())
    err = StepError("llm_quota", retryable=False, cost_breakdown={"items": [1]})
    runner, _ = make(db, FakeCrawl(crawl_ok()), FakeExtract(err))
    run(runner)
    j = db.by_id("j1")
    assert j["status"] == "failed" and j["error"] == "llm_quota"
    assert j["cost_breakdown"] == {"items": [1]}
    assert db.pkb_calls == []


def test_unexpected_exception_fails_job_and_loop_survives() -> None:
    db = JobsDb(job("j1"), job("j2"))
    runner, _ = make(db, FakeCrawl(RuntimeError("boom"), crawl_ok()), FakeExtract())
    assert run(runner) and run(runner)
    assert db.by_id("j1")["status"] == "failed" and "RuntimeError: boom" in db.by_id("j1")["error"]
    assert db.by_id("j2")["status"] == "completed"


def test_missing_url_fails_job() -> None:
    db = JobsDb(job(input_snapshot={}))
    runner, _ = make(db, FakeCrawl())
    run(runner)
    assert db.by_id("j1")["status"] == "failed"


def test_long_error_is_clipped() -> None:
    db = JobsDb(job())
    runner, _ = make(db, FakeCrawl(RuntimeError("x" * 5000)))
    run(runner)
    assert len(db.by_id("j1")["error"]) <= 2000


def test_oldest_job_first() -> None:
    db = JobsDb(job("j2"), job("j1"))
    runner, _ = make(db, FakeCrawl(crawl_ok()))
    run(runner)
    assert db.by_id("j1")["status"] == "completed" and db.by_id("j2")["status"] == "queued"
