"""Chọn trang gửi LLM: top-k theo điểm crawl. Trang pricing gửi raw markdown, trang khác gửi fit."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal, Protocol

from worker.m1.extract.evidence import currency_prices
from worker.m1.extract.prompt import clean_for_llm
from worker.m1.models import CrawlResult, PageRecord

HEADER_RE = re.compile(r"\A<!--(.*?)-->", re.DOTALL)


def parse_header(md: str) -> dict[str, str]:
    """Đọc header `<!-- source_id: … | title: … | site_name: … -->` do `LocalPageStore` ghi."""
    m = HEADER_RE.match(md)
    if not m:
        return {}
    out: dict[str, str] = {}
    for part in m.group(1).split(" | "):
        key, sep, value = part.strip().partition(": ")
        if sep:
            out[key] = value.strip()
    return out


class PageReader(Protocol):
    """Đọc markdown đã lưu lúc crawl. `LocalPageStore` có sẵn; Supabase Storage cắm vào sau."""

    def read_page(self, path: str) -> str: ...


@dataclass
class SourceDoc:
    source_id: str
    url: str
    page_type: str
    score: int
    fetched_at: str
    region: str
    locale: str
    variant: Literal["raw", "fit"]
    content_hash: str
    path: str
    text: str  # đã qua clean_for_llm; evidence được kiểm trên text này và `meta`
    meta: dict[str, str] = field(default_factory=dict)  # header của file (title, site_name…)

    @property
    def index_text(self) -> str:
        """Text dùng kiểm evidence: nội dung + `title` / `site_name` trong header của file."""
        extra = [self.meta[k] for k in ("title", "site_name") if self.meta.get(k)]
        return "\n".join([self.text, *extra])

    def source(self) -> dict[str, object]:
        """1 phần tử `sources[]` của PKB."""
        return {
            "id": self.source_id,
            "url": self.url,
            "page_type": self.page_type,
            "fetched_at": self.fetched_at,
            "content_hash": self.content_hash,
            "region": self.region,
            "locale": self.locale,
            "variant": self.variant,
            "markdown_path": self.path,
            "image_paths": [],
        }


def _prices(text: str) -> set[float]:
    return {t.value for t in currency_prices(text)}


def load_doc(
    p: PageRecord, reader: PageReader, raw_page_types: tuple[str, ...]
) -> tuple[SourceDoc | None, str | None]:
    """Đọc 1 trang thành `SourceDoc`. Không đọc được: (None, warning)."""
    variant: Literal["raw", "fit"] = "raw" if p.page_type in raw_page_types else "fit"
    path = p.raw_path if variant == "raw" else p.fit_path
    if path is None:  # unchanged: lần crawl này không ghi lại markdown
        return None, f"page_not_stored:{p.source_id}"
    try:
        md = reader.read_page(path)
    except OSError as e:
        return None, f"page_read_failed:{p.source_id}:{type(e).__name__}"
    text = clean_for_llm(md)
    if variant == "fit" and p.raw_path and p.raw_path != path:
        # Trang một trang (mục giá nằm trên trang chủ, page_type `other`): fit làm rơi dòng giá và
        # tiêu đề plan (AISoEasy 29/10). Raw có giá mà fit không có thì gửi raw.
        try:
            raw_md = reader.read_page(p.raw_path)
        except OSError:
            raw_md = ""
        raw_text = clean_for_llm(raw_md)
        if _prices(raw_text) - _prices(text):
            variant, path, md, text = "raw", p.raw_path, raw_md, raw_text
    if not text.strip():
        return None, f"page_empty:{p.source_id}"
    doc = SourceDoc(
        source_id=p.source_id,
        url=p.url,
        page_type=p.page_type,
        score=p.score,
        fetched_at=p.fetched_at,
        region=p.region,
        locale=p.locale,
        variant=variant,
        content_hash=p.raw_hash if variant == "raw" else p.fit_hash,
        path=path,
        text=text,
        meta=parse_header(md),
    )
    return doc, None


def by_score(crawl: CrawlResult) -> list[PageRecord]:
    return sorted(crawl.pages, key=lambda p: (-p.score, p.source_id))


def select_docs(
    crawl: CrawlResult, reader: PageReader, top_k: int, raw_page_types: tuple[str, ...]
) -> tuple[list[SourceDoc], list[str]]:
    """Trả (tối đa `top_k` trang điểm cao nhất, warnings). Trang không đọc được: bỏ, cảnh báo."""
    warnings: list[str] = []
    docs: list[SourceDoc] = []
    for p in by_score(crawl):
        if len(docs) >= top_k:
            break
        doc, warning = load_doc(p, reader, raw_page_types)
        if doc is None:
            warnings.append(warning or "")
            continue
        docs.append(doc)
    return docs, warnings


def iter_all_docs(
    docs: list[SourceDoc], crawl: CrawlResult, reader: PageReader, raw_page_types: tuple[str, ...]
) -> Iterator[SourceDoc]:
    """Trang đã gửi LLM trước, rồi các trang crawl còn lại theo điểm (đọc khi cần)."""
    yield from docs
    sent = {d.source_id for d in docs}
    for p in by_score(crawl):
        if p.source_id not in sent:
            doc, _ = load_doc(p, reader, raw_page_types)
            if doc is not None:
                yield doc
