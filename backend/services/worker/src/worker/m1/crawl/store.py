"""Nơi lưu markdown của trang. Supabase Storage làm sau (T-Storage), cắm vào `PageStore`."""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple, Protocol
from urllib.parse import urlsplit


class StoredPaths(NamedTuple):
    fit_path: str
    raw_path: str


class PageStore(Protocol):
    def save_page(
        self,
        *,
        source_id: str,
        url: str,
        page_type: str,
        fetched_at: str,
        raw_md: str,
        fit_md: str,
        title: str = "",
        site_name: str = "",
    ) -> StoredPaths:
        """Ghi markdown raw và fit, trả đường dẫn trong store."""
        ...


def header_value(s: str) -> str:
    """Giá trị an toàn cho header `<!-- … -->`: 1 dòng, không `|`, không `-->`, ≤ 200 ký tự."""
    s = s.replace("-->", " ").replace("|", " ")
    return re.sub(r"\s+", " ", s).strip()[:200]


def page_header(
    source_id: str, url: str, page_type: str, fetched_at: str, title: str = "", site_name: str = ""
) -> str:
    """Header đầu file markdown. `title` (<title>) và `site_name` (og:site_name) nằm trong file
    để evidence lấy từ đó vẫn kiểm được trên chính `markdown_path`."""
    parts = [f"source_id: {source_id}", f"url: {url}", f"page_type: {page_type}"]
    parts.append(f"fetched_at: {fetched_at}")
    if t := header_value(title):
        parts.append(f"title: {t}")
    if n := header_value(site_name):
        parts.append(f"site_name: {n}")
    return f"<!-- {' | '.join(parts)} -->\n\n"


def slugify(url: str) -> str:
    path = urlsplit(url).path.strip("/") or "home"
    return re.sub(r"[^a-zA-Z0-9]+", "-", path).strip("-")[:60] or "home"


class LocalPageStore:
    """Ghi vào thư mục `<root>/pages/`. Không xoá file cũ: trang `unchanged` không được ghi lại."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._pages_dir = root / "pages"
        self._pages_dir.mkdir(parents=True, exist_ok=True)

    def read_page(self, path: str) -> str:
        """Đọc lại markdown theo đường dẫn đã trả ở `save_page` (dùng cho extract)."""
        return (self._root / path).read_text(encoding="utf-8")

    def save_page(
        self,
        *,
        source_id: str,
        url: str,
        page_type: str,
        fetched_at: str,
        raw_md: str,
        fit_md: str,
        title: str = "",
        site_name: str = "",
    ) -> StoredPaths:
        name = f"{source_id}-{page_type}-{slugify(url)}"
        header = page_header(source_id, url, page_type, fetched_at, title, site_name)
        (self._pages_dir / f"{name}.md").write_text(header + fit_md, encoding="utf-8")
        (self._pages_dir / f"{name}.raw.md").write_text(header + raw_md, encoding="utf-8")
        return StoredPaths(fit_path=f"pages/{name}.md", raw_path=f"pages/{name}.raw.md")
