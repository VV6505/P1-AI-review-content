"""Chạy bộ nhận job: `uv run python -m worker.runner` (tiến trình riêng, tách khỏi API).

Cần `.env`: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (và SUPABASE_ANON_KEY cho client DB dùng chung).
`--once`: xử lý mọi job đang chờ rồi thoát (dùng khi chạy tay/cron).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from worker.api.db import Database, PostgrestDatabase
from worker.api.local_db import LocalDatabase
from worker.m1.extract.__main__ import load_env
from worker.runner.runner import JobRunner
from worker.runner.steps import Crawl4AICrawlStep, GeminiExtractStep, HomepageCaptureStep
from worker.runner.video import VideoJobRunner
from worker.settings import MissingConfigError, Settings


async def _loop(runner: JobRunner, video: VideoJobRunner, interval_s: float, once: bool) -> None:
    while True:
        if await runner.run_once():
            continue  # còn việc thì nhận tiếp ngay
        # Video renderer chứa I/O đồng bộ (FFmpeg, TTS, Playwright sync API). Chạy ngoài
        # event loop để Playwright không bị lỗi "Sync API inside asyncio loop".
        if await asyncio.to_thread(video.run_once):
            continue
        if once:
            return
        await asyncio.sleep(interval_s)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m worker.runner", description=__doc__)
    parser.add_argument("--once", action="store_true", help="Hết job thì thoát")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    load_env(Path(".env"))
    settings = Settings.from_env()
    try:
        settings.require("api", "runner")
        provider = os.environ.get("LLM_PROVIDER", "gemini").strip().lower()
        if provider == "freemodel":
            if not settings.freemodel_api_key.get_secret_value():
                raise MissingConfigError(("FREEMODEL_API_KEY",))
        elif provider != "fixture":
            settings.require("extract")
    except MissingConfigError as e:
        print(e, file=sys.stderr)
        return 2
    db: Database = (
        LocalDatabase(settings.local_data_dir, settings.local_owner_id)
        if settings.local_p1_mode
        else PostgrestDatabase(settings)
    )
    runner = JobRunner(
        db, settings, Crawl4AICrawlStep(), GeminiExtractStep(), HomepageCaptureStep()
    )
    video = VideoJobRunner(db, settings)
    try:
        asyncio.run(_loop(runner, video, settings.runner_poll_interval_s, args.once))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
