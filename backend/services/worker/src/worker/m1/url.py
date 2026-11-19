"""Chuẩn hoá URL cho M1.

- `normalize_product_url`: khoá duy nhất của `products.website_url` (T1, ERD gate 2).
- `normalize_page_url`: định danh trang trong một lần crawl (bỏ hết query).
"""

from __future__ import annotations

import re
from urllib.parse import unquote_plus, urlsplit, urlunsplit

# Tham số theo dõi, bỏ khi chuẩn hoá URL product.
TRACKING_PARAMS = frozenset({"ref", "fbclid", "gclid"})
TRACKING_PREFIXES = ("utm_",)
DEFAULT_PORTS = {"http": 80, "https": 443}


class InvalidUrlError(ValueError):
    """URL sai dạng. `str(e)` là lý do ngắn, API trả về theo trường (AC của #41)."""


def normalize_product_url(url: str) -> str:
    """Chuẩn hoá `website_url` của product. Hai URL ra cùng chuỗi thì coi là cùng product.

    Quy tắc:
    1. Cắt khoảng trắng hai đầu; trong URL không được có khoảng trắng hay ký tự điều khiển.
    2. Chỉ nhận `http` / `https` (hạ chữ thường). `http` đổi thành `https`.
    3. Từ chối URL có `user:pass@`.
    4. Host hạ chữ thường; tên miền IDN đổi sang punycode. Giữ `www.`.
    5. Bỏ port mặc định của scheme gốc (http:80, https:443); port khác giữ.
    6. Bỏ fragment (`#...`).
    7. Bỏ tham số theo dõi (`utm_*`, `ref`, `fbclid`, `gclid`); các query còn lại giữ nguyên
       giá trị và sắp theo tên tham số.
    8. Giữ path và chữ hoa/thường của path (Copilot, Notion là product theo path, qa-log #10);
       bỏ `/` cuối. URL gốc ra dạng `https://example.com` (không có `/`).

    Raise `InvalidUrlError` nếu URL không hợp lệ.
    """
    url = (url or "").strip()
    if not url:
        raise InvalidUrlError("URL trống")
    if re.search(r"[\s\x00-\x1f\x7f]", url):
        raise InvalidUrlError("URL chứa khoảng trắng hoặc ký tự điều khiển")
    try:
        parts = urlsplit(url)
        port = parts.port
        host = parts.hostname
    except ValueError as e:
        raise InvalidUrlError(f"URL sai dạng: {e}") from e

    scheme = parts.scheme.lower()
    if scheme not in DEFAULT_PORTS:
        raise InvalidUrlError("chỉ nhận URL http hoặc https")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise InvalidUrlError("URL không được chứa user:pass@")
    if not host:
        raise InvalidUrlError("URL thiếu host")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as e:
        raise InvalidUrlError("host không hợp lệ") from e
    if ":" in host:  # IPv6: hostname đã bỏ ngoặc vuông
        host = f"[{host}]"

    netloc = host if port is None or port == DEFAULT_PORTS[scheme] else f"{host}:{port}"
    path = parts.path.rstrip("/")
    return urlunsplit(("https", netloc, path, _clean_query(parts.query), ""))


def _clean_query(query: str) -> str:
    kept: list[tuple[str, str]] = []
    for segment in query.split("&"):
        if not segment:
            continue
        name = unquote_plus(segment.split("=", 1)[0]).lower()
        if name in TRACKING_PARAMS or name.startswith(TRACKING_PREFIXES):
            continue
        kept.append((name, segment))
    kept.sort(key=lambda item: item[0])  # sort ổn định: cùng tên giữ thứ tự gốc
    return "&".join(segment for _, segment in kept)


def normalize_page_url(url: str) -> str:
    """Định danh trang trong một lần crawl: bỏ query, fragment, `/` cuối; scheme, host chữ thường.

    Có thể raise `ValueError` nếu URL sai dạng (link rác trên trang); nơi gọi tự bỏ qua.
    """
    parts = urlsplit(url)
    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))
