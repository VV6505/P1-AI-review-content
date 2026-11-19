"""Gộp, bỏ trùng và tìm mâu thuẫn trong kết quả LLM. Port `merge` từ spike (extract.py)."""

from __future__ import annotations

import re
from typing import Any

from worker.m1.extract.evidence import norm


def _key(*vals: object) -> str:
    return "|".join(norm(str(v or "")) for v in vals)


def _has_digit(plan: dict[str, Any]) -> bool:
    return bool(re.search(r"\d", plan.get("price_text") or ""))


def merge(parts: list[dict[str, Any]]) -> dict[str, Any]:
    """Gộp các kết quả (thứ tự = ưu tiên). Trường đơn: lấy giá trị đầu tiên khác null.
    Danh sách: nối và bỏ trùng theo tên / giá trị. Mode batch có 1 phần: vẫn bỏ trùng trong đó."""
    out: dict[str, Any] = {
        "identity": {"models": []},
        "pricing": {"plans": [], "usage_prices": [], "other_views": []},
        "features": [],
        "use_cases": [],
        "limitations": [],
        "audiences": [],
        "usp": [],
        "conflicts": [],
    }
    seen: dict[str, set[str]] = {}

    def add(lst: list[Any], item: Any, group: str, key: str) -> None:
        bucket = seen.setdefault(group, set())
        if key not in bucket:
            bucket.add(key)
            lst.append(item)

    for p in parts:
        for field, value in (p.get("identity") or {}).items():
            if field == "models":
                for m in value or []:
                    add(out["identity"]["models"], m, "models", _key(m.get("name")))
            elif value and not out["identity"].get(field):
                out["identity"][field] = value
        for field, value in (p.get("pricing") or {}).items():
            if field == "plans":
                for pl in value or []:
                    key = _key(pl.get("name"), pl.get("price_text"), pl.get("billing_cycle"))
                    add(out["pricing"]["plans"], pl, "plans", key)
            elif field == "usage_prices":
                for up in value or []:
                    key = _key(up.get("name"), up.get("unit"), up.get("price"))
                    add(out["pricing"]["usage_prices"], up, "usage_prices", key)
            elif field == "other_views":
                for v in value or []:
                    add(out["pricing"]["other_views"], v, "other_views", _key(v))
            elif value and not out["pricing"].get(field):
                out["pricing"][field] = value
        for f in p.get("features") or []:
            add(out["features"], f, "features", _key(f.get("name")))
        for group, text_key in (
            ("use_cases", "title"),
            ("limitations", "text"),
            ("audiences", "segment"),
            ("usp", "text"),
        ):
            for f in p.get(group) or []:
                add(out[group], f, group, _key(f.get(text_key)))
        out["conflicts"].extend(p.get("conflicts") or [])
    # Trang không phải pricing hay nhắc tên plan mà không có giá ("Pro and Max plans"):
    # bỏ mục không có số nếu đã có mục cùng tên kèm giá.
    plans = out["pricing"]["plans"]
    priced = {_key(pl.get("name")) for pl in plans if _has_digit(pl)}
    out["pricing"]["plans"] = [
        pl for pl in plans if _has_digit(pl) or _key(pl.get("name")) not in priced
    ]
    return out


def price_conflicts(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Mâu thuẫn giá do code phát hiện: cùng plan + chu kỳ + đơn vị (hoặc cùng giá dùng theo
    tên + đơn vị) mà giá khác nhau. Giữ mọi dòng, không chọn. Gọi sau khi đã lọc và đánh lại id,
    để chỉ số trong `field` trỏ đúng phần tử."""
    out: list[dict[str, Any]] = []
    pricing = data.get("pricing") or {}
    groups = (
        ("plans", "list_price", ("name", "billing_cycle", "price_unit")),
        ("usage_prices", "price", ("name", "unit")),
    )
    for group, value_key, key_fields in groups:
        by_key: dict[str, list[int]] = {}
        items = pricing.get(group) or []
        for i, it in enumerate(items):
            if it.get(value_key) is not None:
                by_key.setdefault(_key(*(it.get(k) for k in key_fields)), []).append(i)
        for idxs in by_key.values():
            values = [items[i][value_key] for i in idxs]
            if len(set(values)) < 2:
                continue
            out.append(
                {
                    "field": f"pricing.{group}[{idxs[0]}].{value_key}",
                    "values": values,
                    "source_ids": [items[i]["source_id"] for i in idxs],
                }
            )
    return out
