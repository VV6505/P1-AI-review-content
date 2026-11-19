"""CLI chạy tay: `uv run python -m worker.m1.extract <crawl_dir> --out <thư mục>`.

`<crawl_dir>` là thư mục `--out` của `python -m worker.m1.crawl` (có `crawl.json` và `pages/`).
Ghi `<out>/pkb.json` ({data, sources}), `<out>/cost_breakdown.json`, `<out>/extract.json` (warnings,
số đo hoặc lỗi). Gọi Gemini thật cần `GEMINI_API_KEY` trong `.env`; `LLM_PROVIDER=fixture` thì không
gọi mạng. Mỗi lần chạy = 1 lời gọi generate (trừ retry), tính vào quota 500 RPD của project.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from worker.m1.crawl.store import LocalPageStore
from worker.m1.extract.service import ExtractError, ExtractResult, extract_product
from worker.m1.llm import make_llm
from worker.m1.models import CrawlResult


def load_env(path: Path) -> None:
    """Đọc KEY=VALUE từ .env vào os.environ (không ghi đè biến đã có)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _write(path: Path, doc: Any) -> None:
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _summary(res: ExtractResult) -> None:
    data = res.data
    plans = (data.get("pricing") or {}).get("plans") or []
    items = res.cost_breakdown["items"]
    n_features = len(data.get("features") or [])
    print(f"name={data['identity']['name']['value']!r} facts={res.facts} plans={len(plans)} "
          f"features={n_features} evidence_in_source={res.evidence_in_source}")  # fmt: skip
    for p in plans:
        price = f"{p.get('list_price')} {p.get('currency')}/{p.get('price_unit')}"
        print(f"  plan {p['name']!r}: {price} {p.get('billing_cycle')} [{p['source_id']}] "
              f"{p['price_text']!r}")  # fmt: skip
    for c in (data.get("quality") or {}).get("conflicts") or []:
        print(f"  conflict {c['field']}: {c['values']} {c['source_ids']}")
    tok_in = sum(i["tokens_in"] for i in items)
    tok_out = sum(i["tokens_out"] for i in items)
    cost = sum(i["cost_usd"] for i in items)
    print(f"llm_calls={len(items)} tokens_in={tok_in} tokens_out={tok_out} "
          f"cost_usd(giá niêm yết)={cost:.6f}")  # fmt: skip
    print(f"warnings ({len(res.warnings)}):")
    for w in res.warnings:
        print(f"  {w}")


async def _main(args: argparse.Namespace) -> int:
    crawl_dir, out = Path(args.crawl_dir), Path(args.out)
    crawl = CrawlResult.model_validate_json((crawl_dir / "crawl.json").read_text(encoding="utf-8"))
    llm = make_llm()
    try:
        res = await extract_product(crawl, LocalPageStore(crawl_dir), llm)
    except ExtractError as e:
        _write(out / "cost_breakdown.json", e.cost_breakdown)
        retry_after = e.retry_after.isoformat() if e.retry_after else None
        _write(out / "extract.json", {"status": "failed", "error_code": e.code.value,
               "error_message": e.message, "retryable": e.retryable, "retry_after": retry_after,
               "warnings": e.warnings})  # fmt: skip
        print(f"!! FAILED: {e.message} (retryable={e.retryable}, retry_after={retry_after})")
        return 1
    _write(out / "pkb.json", {"data": res.data, "sources": res.sources})
    _write(out / "cost_breakdown.json", res.cost_breakdown)
    _write(out / "extract.json", {"status": "completed", "model": llm.model, "facts": res.facts,
           "evidence_in_source": res.evidence_in_source, "warnings": res.warnings})  # fmt: skip
    _summary(res)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m worker.m1.extract", description=__doc__)
    parser.add_argument("crawl_dir", help="Thư mục kết quả crawl (có crawl.json)")
    parser.add_argument("--out", required=True, help="Thư mục ghi kết quả (nên đặt ngoài repo)")
    parser.add_argument("--env", default=".env", help="File .env (mặc định ./.env)")
    args = parser.parse_args()
    load_env(Path(args.env))
    Path(args.out).mkdir(parents=True, exist_ok=True)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]  # Windows cp1252
    sys.exit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
