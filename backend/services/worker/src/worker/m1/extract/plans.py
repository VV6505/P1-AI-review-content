"""Sửa plan sau LLM bằng code: evidence thiếu tên plan, giá khuyến mãi bị bỏ. Không đổi prompt.

Ca thật AISoEasy 29/10: trang ghi `### Individual Pro` / `$9$18` / `/ month — 50% off, limited
spots`; LLM ghi plan "Pro", `list_price` 9, không có `promo_price`, evidence "Join now — $9/month".
"""

from __future__ import annotations

import re
from typing import Any

from worker.m1.extract.evidence import (
    PriceToken,
    currency_prices,
    free_only,
    has_promo_marker,
    has_word,
    norm,
    price_in_evidence,
)
from worker.m1.extract.pages import SourceDoc
from worker.m1.pkb.models import EVIDENCE_MAX

HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$")
BULLET = re.compile(r"^\s*(?:[*+-]|\d+[.)])\s")
# Điều kiện của giá khuyến mãi, chép nguyên văn từ evidence.
TERMS = re.compile(
    r"limited\s+(?:spots?|time|seats?|offer)|first\s+(?:month|year|\d+\s+months?)|"
    r"(?:tháng|năm)\s+đầu|số lượng\s+(?:có hạn|giới hạn)|for\s+new\s+(?:users|customers)",
    re.IGNORECASE,
)
BLOCK_MAX_LINES = 15


def _locate(text: str, evidence: str, max_span: int = 6) -> tuple[list[str], int, int] | None:
    """Dòng đầu / cuối (trong `text`) của đoạn ngắn nhất chứa evidence. Khớp sau chuẩn hoá."""
    target = norm(evidence)
    if not target:
        return None
    lines = text.splitlines()
    for span in range(1, max_span + 1):
        for i in range(len(lines) - span + 1):
            if target in norm("\n".join(lines[i : i + span])):
                return lines, i, i + span - 1
    return None


def _has_price(plan: dict[str, Any], text: str) -> bool:
    lp = plan.get("list_price")
    return lp is None or price_in_evidence(float(lp), text)


def _name_span(plan: dict[str, Any], doc: SourceDoc) -> str | None:
    """Đoạn ≤ 200 ký tự bắt đầu từ heading gần nhất phía trên khối giá, chứa cả tên plan và giá.
    Heading gần nhất không có tên plan (hoặc không có heading) thì None."""
    loc = _locate(doc.text, plan["evidence"])
    if loc is None:
        return None
    lines, first, last = loc
    h = next((k for k in range(first - 1, -1, -1) if HEADING.match(lines[k])), None)
    if h is None or not has_word(plan["name"], HEADING.match(lines[h]).group(1)):  # type: ignore[union-attr]
        return None
    run: list[str] = []
    size = 0
    for ln in lines[h + 1 :]:
        if not ln.strip() or BULLET.match(ln) or HEADING.match(ln):
            break
        if size + len(ln) + 1 > EVIDENCE_MAX:
            break
        run.append(ln)
        size += len(ln) + 1
    candidates = ["\n".join(lines[h : last + 1]), "\n".join([lines[h], *run])]
    for cand in candidates:
        if len(cand) <= EVIDENCE_MAX and has_word(plan["name"], cand) and _has_price(plan, cand):
            return cand
    return None


def fix_plan_names(plans: list[dict[str, Any]], docs: list[SourceDoc]) -> list[int]:
    """Evidence của plan không chứa tên plan: thay bằng đoạn từ heading phía trên (`value` giữ
    nguyên, như `identity.name`). Không thấy thì để `value_not_in_evidence`. Trả chỉ số đã sửa."""
    by_id = {d.source_id: d for d in docs}
    fixed: list[int] = []
    for i, p in enumerate(plans):
        ev, name, doc = p.get("evidence"), p.get("name"), by_id.get(str(p.get("source_id")))
        if not (isinstance(ev, str) and isinstance(name, str) and doc) or has_word(name, ev):
            continue
        if span := _name_span(p, doc):
            p["evidence"] = span
            fixed.append(i)
    return fixed


def _price_text(evidence: str) -> str:
    """Dòng giá trong evidence (nối dòng kế nếu bắt đầu bằng `/` hoặc `per`)."""
    lines = evidence.splitlines()
    for k, ln in enumerate(lines):
        if currency_prices(ln):
            nxt = lines[k + 1].strip() if k + 1 < len(lines) else ""
            if nxt.startswith(("/", "per ")):
                return f"{ln.strip()} {nxt}"
            return ln.strip()
    return evidence


def _compatible(a: PriceToken, b: PriceToken) -> bool:
    """Cùng tiền; đơn vị (month / year) không xung đột. Một bên không ghi đơn vị thì chấp nhận."""
    return a.currency == b.currency and (a.unit is None or b.unit is None or a.unit == b.unit)


def split_promo(plan: dict[str, Any]) -> str:
    """Evidence có đúng 2 giá cùng tiền / đơn vị và (giá liền nhau như `$9$18`, hoặc có dấu hiệu
    "% off" / "giảm") thì giá lớn là `list_price`, giá nhỏ là `promo_price`. Dấu hiệu đứng riêng
    không đủ: "$17/mo (…$200 billed up front), $20 if billed monthly" có 3 giá khác chu kỳ.
    Trả `split` | `unparsed` (có dấu hiệu nhưng không chắc) | `none`."""
    ev, lp = plan.get("evidence"), plan.get("list_price")
    if plan.get("promo_price") is not None or lp is None or not isinstance(ev, str):
        return "none"
    prices = currency_prices(ev)
    values = {t.value for t in prices}
    marker = has_promo_marker(ev)
    if len(values) == 2:
        a, b = prices[0], prices[-1]
        adjacent = len(prices) == 2 and not ev[a.end : b.start].strip()
        if _compatible(a, b) and (marker or adjacent):
            hi, lo = max(values), min(values)
            if not any(abs(lp - v) < 1e-9 for v in (hi, lo)):
                return "unparsed"
            plan["list_price"], plan["promo_price"] = (
                int(v) if v == int(v) else v for v in (hi, lo)
            )
            if plan.get("promo_terms") is None and (m := TERMS.search(ev)):
                plan["promo_terms"] = m.group(0)
            if not price_in_evidence(hi, plan.get("price_text") or ""):
                plan["price_text"] = _price_text(ev)
            return "split"
        return "unparsed" if marker else "none"
    return "unparsed" if marker and len(values) <= 1 else "none"


def _block_text(doc: SourceDoc, evidence: str) -> str:
    """Khối quanh evidence: từ heading gần nhất phía trên tới heading kế (tối đa 15 dòng)."""
    loc = _locate(doc.text, evidence)
    if loc is None:
        return ""
    lines, first, last = loc
    start = next((k for k in range(first, -1, -1) if HEADING.match(lines[k])), first)
    end = next((k for k in range(last + 1, len(lines)) if HEADING.match(lines[k])), len(lines))
    return "\n".join(lines[start : min(end, start + BLOCK_MAX_LINES)])


def fix_plans(pkb: dict[str, Any], docs: list[SourceDoc]) -> list[str]:
    """Chạy sau LLM, trước kiểm evidence. Trả warnings."""
    pricing = pkb["pricing"]
    plans: list[dict[str, Any]] = pricing.get("plans") or []
    warnings: list[str] = []
    if not plans or free_only(plans):
        return warnings
    fix_plan_names(plans, docs)
    by_id = {d.source_id: d for d in docs}
    statuses = [split_promo(p) for p in plans]
    shown = {
        float(p[k]) for p in plans for k in ("list_price", "promo_price") if p.get(k) is not None
    } | {float(u["price"]) for u in pricing.get("usage_prices") or [] if u.get("price") is not None}
    for i, (p, status) in enumerate(zip(plans, statuses, strict=True)):
        path = f"pricing.plans[{i}]"
        if status != "none":
            warnings.append(f"promo_{status}:{path}")
            continue
        ev, doc = p.get("evidence"), by_id.get(str(p.get("source_id")))
        if p.get("promo_price") is not None or p.get("list_price") is None or not ev:
            continue
        seen = {t.value for t in currency_prices(f"{ev}\n{_block_text(doc, ev) if doc else ''}")}
        # PKB mới có 1 giá của plan, nguồn có ≥ 2 giá và có giá chưa plan nào ghi
        if len(seen) >= 2 and seen - shown:
            warnings.append(f"promo_missing:{path}")
    return warnings
