"""Claim và render job ``video`` từ đúng script revision đã duyệt."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from worker.api.db import Database, Row
from worker.render.ffmpeg import RenderError, render_video
from worker.render.tts import TtsError, make_tts
from worker.settings import Settings

log = logging.getLogger("worker.video")


class VideoJobRunner:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def _claim(self) -> Row | None:
        rows = self.db.select(
            "generation_jobs",
            {
                "status": "eq.queued",
                "job_type": "eq.video",
                "order": "created_at.asc",
                "limit": "1",
            },
        )
        if not rows:
            return None
        row = rows[0]
        claimed = self.db.update(
            "generation_jobs",
            {"id": f"eq.{row['id']}", "status": "eq.queued"},
            {"status": "running", "attempts": int(row.get("attempts") or 0) + 1, "error": None},
        )
        return {**row, **claimed[0]} if claimed else None

    def run_once(self) -> bool:
        job = self._claim()
        if job is None:
            return False
        job_id = str(job["id"])
        try:
            script_rows = self.db.select(
                "script_revisions",
                {
                    "product_id": f"eq.{job['product_id']}",
                    "revision": f"eq.{job['script_revision']}",
                },
            )
            if not script_rows or script_rows[0].get("status") != "approved":
                raise RenderError("video job không trỏ tới script đã duyệt")
            options = dict((job.get("input_snapshot") or {}).get("options") or {})
            profile = job.get("render_profile")
            if profile and "template" not in options:
                options["template"] = profile
            product_rows = self.db.select("products", {"id": f"eq.{job['product_id']}"})
            if product_rows:
                prod = product_rows[0]
                options.setdefault("website_url", str(prod.get("website_url") or ""))
                if prod.get("name"):
                    options.setdefault("product_name", str(prod["name"]))
            if not options.get("asset_paths"):
                crawl_rows = self.db.select(
                    "generation_jobs",
                    {
                        "product_id": f"eq.{job['product_id']}",
                        "job_type": "eq.crawl",
                        "status": "eq.completed",
                    },
                )
                if crawl_rows:
                    crawl_assets = (crawl_rows[-1].get("result_manifest") or {}).get("assets") or []
                    options["asset_paths"] = {
                        str(a["asset_id"]): str(a["path"])
                        for a in crawl_assets
                        if isinstance(a, dict) and a.get("asset_id") and a.get("path")
                    }
            output = Path(self.settings.video_output_dir) / job_id
            result = render_video(
                script_rows[0]["content"], options, output, self.settings, make_tts(self.settings)
            )
            manifest: dict[str, Any] = {
                **result.manifest,
                "product_id": job["product_id"],
                "pkb_version": job["pkb_version"],
                "script_revision": job["script_revision"],
                "download_url": f"/jobs/{job_id}/video",
            }
            self.db.update(
                "generation_jobs",
                {"id": f"eq.{job_id}"},
                {"status": "completed", "error": None, "result_manifest": manifest},
            )
            log.info("video job %s completed (qa=%s)", job_id, manifest["qa"]["passed"])
        except (RenderError, TtsError) as exc:
            self.db.update(
                "generation_jobs",
                {"id": f"eq.{job_id}"},
                {"status": "failed", "error": str(exc)[:2000]},
            )
            log.error("video job %s failed: %s", job_id, exc)
        return True
