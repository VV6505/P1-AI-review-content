"""CLI chạy tay: `uv run python -m worker.m1.crawl <url> --out <thư mục>`.

Ghi `<out>/pages/*.md` và `<out>/crawl.json`. Cần trình duyệt: `uv run playwright install chromium`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from worker.m1.config import CrawlOptions, CrawlSettings
from worker.m1.crawl.fetcher import Crawl4AIFetcher
from worker.m1.crawl.service import crawl_product
from worker.m1.crawl.store import LocalPageStore
from worker.m1.models import CrawlResult


def _print_summary(result: CrawlResult) -> None:
    print(f"\n=== {result.root_url} ===")
    if result.status == "failed":
        print(f"!! FAILED: {result.error_message} (retryable={result.retryable})")
    if result.partial:
        print(f"!! PARTIAL: {result.warning}")
    print(
        f"status={result.status} found={result.pages_found} used={result.pages_used} "
        f"crawl_seconds={result.crawl_seconds} min_interval={result.min_observed_interval_s}"
    )
    print("robots:", {h: f"{r.status}/{r.policy}" for h, r in result.robots.items()})
    print("skipped:", result.skipped_counts)
    print(f"{'id':7} {'page_type':9} {'raw':>7} {'fit':>7}  url")
    for p in result.pages:
        flag = " (unchanged)" if p.unchanged else ""
        print(f"{p.source_id:7} {p.page_type:9} {p.raw_chars:7} {p.fit_chars:7}  {p.url}{flag}")


async def _main(args: argparse.Namespace) -> CrawlResult:
    out = Path(args.out)
    previous: dict[str, str] = {}
    if args.previous:
        previous = json.loads(Path(args.previous).read_text(encoding="utf-8"))
    options = CrawlOptions(allow_subdomains=args.allow_subdomains, extra_hosts=args.extra_host)
    settings = CrawlSettings.from_env()
    async with Crawl4AIFetcher(settings) as fetcher:
        result = await crawl_product(
            args.url,
            options,
            fetcher,
            LocalPageStore(out),
            previous_hashes=previous,
            settings=settings,
        )
    (out / "crawl.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m worker.m1.crawl", description=__doc__)
    parser.add_argument("url", help="Website URL của product")
    parser.add_argument("--out", required=True, help="Thư mục ghi kết quả (nên đặt ngoài repo)")
    parser.add_argument(
        "--allow-subdomains", action="store_true", help="Crawl host phụ cùng domain gốc (FR-02)"
    )
    parser.add_argument("--extra-host", action="append", default=[], help="Host phụ cụ thể")
    parser.add_argument(
        "--previous", help="File JSON {url: content_hash} của lần crawl trước (NFR-04)"
    )
    args = parser.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]  # Windows cp1252
    _print_summary(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
