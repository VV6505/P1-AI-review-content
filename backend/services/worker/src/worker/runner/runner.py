"""Nhận và chạy job `crawl`: claim → crawl → (extract) → tạo PKB `draft` → `completed`/`failed`.

Quy ước:
- **Claim không cần migration mới**: `UPDATE ... WHERE id = X AND status = 'queued'` là nguyên tử
  trong Postgres; chỉ runner nhận lại được dòng thì thắng. Hai runner song song không chạy trùng.
- Lỗi `retryable` và còn lượt (`attempts < max_attempts`) thì xếp lại `queued` (DB cho phép
  `running → queued`), chờ lũy thừa 2 trong bộ nhớ trước khi nhận lại. Hết lượt hoặc không retry
  được thì `failed` kèm `error` (bắt buộc theo DB).
- PKB được tạo xong thì ghi `pkb_version` vào job ngay (còn `running`); nếu runner chết giữa
  chừng, lượt sau thấy `pkb_version` đã có và chỉ hoàn tất job, không tạo PKB thứ hai.
- Chưa làm: job kẹt ở `running` khi runner chết (bảng chưa có `updated_at` để tự dọn); cần xếp lại
  bằng tay hoặc thêm cột ở migration sau.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from worker.api.db import Database, Row
from worker.api.errors import DatabaseError
from worker.m1.models import CrawlResult
from worker.runner.steps import CrawlStep, ExtractOutcome, ExtractStep, MediaStep, StepError
from worker.settings import Settings

log = logging.getLogger("worker.runner")

CLAIM_COLUMNS = "id,product_id,attempts,pkb_version,input_snapshot"
ERROR_LIMIT = 2000  # khớp check của generation_jobs.error


def _clip(text: str) -> str:
    return text if len(text) <= ERROR_LIMIT else text[: ERROR_LIMIT - 1] + "…"


def build_manifest(
    crawl: CrawlResult, out_dir: Path, extract: ExtractOutcome | None
) -> dict[str, Any]:
    """`result_manifest` của job crawl: đủ để kiểm ≤ 30 trang, mỗi trang có hash."""
    return {
        "root_url": crawl.root_url,
        "partial": crawl.partial,
        "warning": crawl.warning,
        "pages_found": crawl.pages_found,
        "pages_used": crawl.pages_used,
        "crawl_seconds": crawl.crawl_seconds,
        "skipped_counts": crawl.skipped_counts,
        "store_dir": str(out_dir),
        "pages": [
            {
                "source_id": p.source_id,
                "url": p.url,
                "page_type": p.page_type,
                "content_hash": p.content_hash,
                "fit_path": p.fit_path,
                "raw_path": p.raw_path,
            }
            for p in crawl.pages
        ],
        "extract": (
            {"status": "skipped"}
            if extract is None
            else {"status": "completed", "warnings": extract.warnings}
        ),
    }


class JobRunner:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        crawl: CrawlStep,
        extract: ExtractStep | None = None,
        media: MediaStep | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._db = db
        self._settings = settings
        self._crawl = crawl
        self._extract = extract
        self._media = media
        self._clock = clock
        self._not_before: dict[str, float] = {}  # job_id -> mốc được nhận lại (retry)

    # --- hàng đợi -----------------------------------------------------------------------------
    def _candidates(self) -> list[Row]:
        return self._db.select(
            "generation_jobs",
            {
                "status": "eq.queued",
                "job_type": "eq.crawl",
                "order": "created_at.asc",
                "limit": "10",
                "select": CLAIM_COLUMNS,
            },
        )

    def claim_next(self) -> Row | None:
        """Nhận job queued cũ nhất chưa chờ backoff. None nếu không có hoặc thua tranh claim."""
        now = self._clock()
        for row in self._candidates():
            if self._not_before.get(str(row["id"]), 0.0) > now:
                continue
            claimed = self._db.update(
                "generation_jobs",
                {"id": f"eq.{row['id']}", "status": "eq.queued"},
                {"status": "running", "attempts": int(row.get("attempts") or 0) + 1, "error": None},
            )
            if claimed:  # PostgREST trả dòng đã đổi; rỗng = runner khác đã nhận trước
                return {**row, **claimed[0]}
        return None

    # --- chạy một job -------------------------------------------------------------------------
    async def run_once(self) -> bool:
        """Nhận và chạy tối đa một job. Trả True nếu có job được xử lý."""
        job = self.claim_next()
        if job is None:
            return False
        job_id = str(job["id"])
        try:
            await self._run_crawl_job(job)
        except StepError as e:
            self._fail(job, e.message, retryable=e.retryable, cost=e.cost_breakdown)
        except DatabaseError as e:
            # DB lỗi: không đoán trạng thái, để job `running` và báo log (xem "Chưa làm").
            log.error("job %s: lỗi DB khi xử lý: %s", job_id, e)
        except Exception as e:  # noqa: BLE001 - mọi lỗi lạ phải kết thúc job, không giết vòng lặp
            log.exception("job %s: lỗi không lường trước", job_id)
            self._fail(job, f"lỗi nội bộ: {type(e).__name__}: {e}", retryable=False)
        return True

    async def _run_crawl_job(self, job: Row) -> None:
        job_id, product_id = str(job["id"]), str(job["product_id"])
        url = (job.get("input_snapshot") or {}).get("website_url")
        if not isinstance(url, str) or not url:
            raise StepError("input_snapshot thiếu website_url")

        out_dir = Path(self._settings.page_store_dir) / job_id
        snapshot = job.get("input_snapshot") or {}
        auth_session_id = snapshot.get("auth_session_id")
        storage_state: Path | None = None
        if isinstance(auth_session_id, str) and auth_session_id:
            storage_state = (
                Path(self._settings.local_auth_dir).resolve()
                / auth_session_id
                / "storage_state.json"
            )
            if not storage_state.is_file():
                raise StepError("phiên đăng nhập đã bị xóa; hãy đăng nhập lại")
        crawl = (
            await self._crawl(url, out_dir, storage_state)
            if storage_state is not None
            else await self._crawl(url, out_dir)
        )
        if crawl.status == "failed":
            raise StepError(
                f"{crawl.error_code}: {crawl.error_message}"
                if crawl.error_code
                else crawl.error_message,
                retryable=bool(crawl.retryable),
            )

        extract: ExtractOutcome | None = None
        pkb_version = job.get("pkb_version")
        if pkb_version is None and self._extract is not None:
            extract = await self._extract(crawl, out_dir)
            pkb_version = self._db.rpc(
                "create_pkb_version",
                {"p_product_id": product_id, "p_data": extract.data, "p_sources": extract.sources},
            )
            # Ghi ngay để lượt sau (nếu runner chết) không tạo PKB thứ hai.
            self._db.update("generation_jobs", {"id": f"eq.{job_id}"}, {"pkb_version": pkb_version})

        assets: list[dict[str, Any]] = []
        media_warning: str | None = None
        if self._media is not None:
            try:
                assets = (
                    await self._media(url, out_dir, storage_state)
                    if storage_state is not None
                    else await self._media(url, out_dir)
                )
            except Exception as exc:  # noqa: BLE001 - PKB vẫn có giá trị nếu ảnh chụp lỗi
                media_warning = f"không chụp được ảnh trang chủ: {type(exc).__name__}: {exc}"
                log.warning("job %s: %s", job_id, media_warning)
        manifest = build_manifest(crawl, out_dir, extract)
        manifest["assets"] = assets
        if media_warning:
            manifest["media_warning"] = media_warning[:500]
        manifest["intake"] = {
            "owner_context": snapshot.get("owner_context"),
            "creative_preferences": snapshot.get("creative_preferences"),
        }
        patch: dict[str, Any] = {
            "status": "completed",
            "error": None,
            "result_manifest": manifest,
        }
        if extract is not None:
            patch["cost_breakdown"] = extract.cost_breakdown
        self._db.update("generation_jobs", {"id": f"eq.{job_id}"}, patch)
        self._not_before.pop(job_id, None)
        log.info(
            "job %s: completed (pages=%s, pkb_version=%s)", job_id, crawl.pages_used, pkb_version
        )

    def _fail(
        self, job: Row, message: str, *, retryable: bool, cost: dict[str, Any] | None = None
    ) -> None:
        job_id, attempts = str(job["id"]), int(job.get("attempts") or 0)
        message = _clip(message)
        if retryable and attempts < self._settings.runner_max_attempts:
            delay = self._settings.runner_retry_backoff_s * (2 ** (attempts - 1))
            self._not_before[job_id] = self._clock() + delay
            self._db.update(
                "generation_jobs", {"id": f"eq.{job_id}"}, {"status": "queued", "error": message}
            )
            log.warning("job %s: lỗi tạm thời, xếp lại sau %.0fs: %s", job_id, delay, message)
            return
        patch: dict[str, Any] = {"status": "failed", "error": message or "lỗi không rõ"}
        if cost:
            patch["cost_breakdown"] = cost
        self._db.update("generation_jobs", {"id": f"eq.{job_id}"}, patch)
        self._not_before.pop(job_id, None)
        log.error("job %s: failed: %s", job_id, message)
