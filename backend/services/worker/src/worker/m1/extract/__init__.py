"""Bước 1.4 của M1: trích fact từ trang đã crawl thành PKB v0.3. Interface: `extract_product`."""

from __future__ import annotations

from worker.m1.extract.service import (
    ExtractError,
    ExtractErrorCode,
    ExtractResult,
    ExtractSettings,
    extract_product,
)

__all__ = [
    "ExtractError",
    "ExtractErrorCode",
    "ExtractResult",
    "ExtractSettings",
    "extract_product",
]
