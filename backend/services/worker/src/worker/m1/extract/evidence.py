"""Duyệt fact, sửa evidence quá dài, kiểm evidence có nguyên văn trong trang nguồn."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from worker.m1.pkb.models import EVIDENCE_MAX

Fact = dict[str, Any]


def norm(s: str) -> str:
    """Chuẩn hoá để so khớp: NFC (dấu tiếng Việt dựng sẵn / tổ hợp), chữ thường, bỏ markdown.

    Ký tự nhấn mạnh (`*`, `_`, backtick) bị xoá hẳn, để `**90+ tools**.` khớp `90+ tools.`.
    Ký tự cấu trúc (`#`, `|`, `>`, `\\`) thành khoảng trắng, để ô bảng không dính nhau.
    """
    s = unicodedata.normalize("NFC", s).lower()
    s = re.sub(r"[*_`]", "", s)
    s = re.sub(r"[#|>\\]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def iter_facts(obj: Any, path: str = "") -> Iterator[tuple[str, Fact]]:
    """Duyệt mọi dict có khoá `source_id` (tức là 1 fact), kèm đường dẫn kiểu `features[2]`."""
    if isinstance(obj, dict):
        if "source_id" in obj:
            yield path, obj
        for k, v in obj.items():
            yield from iter_facts(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_facts(v, f"{path}[{i}]")


def repair_evidence(data: Any) -> int:
    """Gemini không luôn tuân maxLength. Cắt evidence > 200 ký tự tại ranh giới từ (vẫn là trích
    nguyên văn, nên vẫn kiểm được trong nguồn). Trả số evidence đã cắt."""
    n = 0
    for _, f in iter_facts(data):
        ev = f.get("evidence")
        if isinstance(ev, str) and len(ev) > EVIDENCE_MAX:
            f["evidence"] = ev[:EVIDENCE_MAX].rsplit(" ", 1)[0]
            n += 1
    return n


# Giá 0 thường in bằng chữ, không có số
FREE_WORDS = ("free", "miễn phí")


def numbers_in(text: str) -> set[float]:
    """Mọi cách đọc được của các số trong `text`: `1,000` / `1.000` → 1000, `9,99` → 9.99.

    Dấu `.` / `,` mơ hồ (`1.500`) thì lấy cả 2 cách đọc, vì không biết trang dùng kiểu nào.
    """
    out: set[float] = set()
    for tok in re.findall(r"\d+(?:[.,]\d+)*", text):
        seps = set(re.findall(r"[.,]", tok))
        if len(seps) == 2:  # `1,234.56` / `1.234,56`: dấu đứng sau cùng là dấu thập phân
            dec = tok[max(tok.rfind("."), tok.rfind(","))]
            grp = "," if dec == "." else "."
            out.add(float(tok.replace(grp, "").replace(dec, ".")))
            continue
        if not seps:
            out.add(float(tok))
            continue
        sep = seps.pop()
        head, *groups = tok.split(sep)
        if all(len(g) == 3 for g in groups):  # nhóm nghìn
            out.add(float(head + "".join(groups)))
        if len(groups) == 1:  # dấu thập phân
            out.add(float(f"{head}.{groups[0]}"))
    return out


def price_in_evidence(price: float, evidence: str) -> bool:
    if price == 0 and has_free_word(evidence):
        return True
    return any(abs(price - n) < 1e-9 for n in numbers_in(norm(evidence)))


@dataclass(frozen=True)
class PriceToken:
    value: float
    currency: str
    unit: str | None  # month | year, nếu ngay sau số có ghi
    start: int
    end: int


_AMOUNT = r"\d+(?:[.,]\d+)*"
_PRICE_RE = re.compile(
    rf"(?P<pre>US\$|[$€£₫])\s?(?P<a>{_AMOUNT})"
    rf"|(?P<b>{_AMOUNT})\s?(?P<suf>[$€£₫đ]|vn[dđ]|usd|eur)(?!\w)",
    re.IGNORECASE,
)
_UNIT_RE = re.compile(
    r"\s*(?:/|per\s+|mỗi\s+)?\s*(month|mo|monthly|tháng|year|yr|yearly|năm)(?!\w)", re.IGNORECASE
)
_CURRENCY = {"us$": "$", "usd": "$", "eur": "€", "đ": "₫", "vnd": "₫", "vnđ": "₫"}


def currency_prices(text: str) -> list[PriceToken]:
    """Giá có ký hiệu tiền (`$9`, `9 USD`, `100.000đ`), theo thứ tự xuất hiện. Số trần như `50%`
    hay `10 seats` không tính: đọc nhầm chúng thành giá sẽ đảo list / promo."""
    text = re.sub(r"[*_`]", "", text)
    out: list[PriceToken] = []
    for m in _PRICE_RE.finditer(text):
        cur = (m["pre"] or m["suf"]).lower()
        amounts = numbers_in(m["a"] or m["b"])
        unit_m = _UNIT_RE.match(text, m.end())
        unit = None
        if unit_m:
            unit = "month" if unit_m[1].lower() in ("month", "mo", "monthly", "tháng") else "year"
        out.append(PriceToken(max(amounts), _CURRENCY.get(cur, cur), unit, m.start(), m.end()))
    return out


# Dấu hiệu khuyến mãi (đã norm). "sales" của "Contact sales" không khớp \bsale\b.
_PROMO_MARKER = re.compile(
    r"\d+\s*%\s*(?:off|discount|giảm)|%\s*off|\bsale\b|\bdiscount|\bpromo|giảm giá|giảm \d|"
    r"ưu đãi|khuyến mãi"
)


def has_promo_marker(text: str) -> bool:
    return _PROMO_MARKER.search(norm(text)) is not None


def has_free_word(text: str) -> bool:
    return any(w in norm(text) for w in FREE_WORDS)


def free_only(plans: list[dict[str, Any]]) -> bool:
    """Đúng 1 plan, giá 0, evidence có chữ miễn phí."""
    if len(plans) != 1:
        return False
    p = plans[0]
    ev = p.get("evidence")
    return p.get("list_price") == 0 and isinstance(ev, str) and has_free_word(ev)


def has_word(value: str, text: str) -> bool:
    """`value` có trong `text` như 1 cụm từ riêng (sau chuẩn hoá): `ElevenLabsClient` không tính."""
    v = norm(value)
    return bool(v) and re.search(rf"(?<!\w){re.escape(v)}(?!\w)", norm(text)) is not None


def name_candidates(meta: dict[str, str], text: str) -> list[tuple[str, str | None]]:
    """(đoạn có thể chứa tên sản phẩm, `extracted_via`): og:site_name, <title>, rồi các dòng h1."""
    out: list[tuple[str, str | None]] = []
    if v := meta.get("site_name"):
        out.append((v, "og"))
    if v := meta.get("title"):
        out.append((v, "dom"))
    out += [(ln[2:].strip(), None) for ln in text.splitlines() if ln.startswith("# ")]
    return [(t, via) for t, via in out if t and len(t) <= EVIDENCE_MAX]


def value_warnings(pkb: dict[str, Any]) -> list[str]:
    """Evidence có trong nguồn nhưng không chứa giá trị (vd. `name`="PDFCraft", evidence "Công cụ
    PDF…"). Chỉ kiểm tên sản phẩm, tên plan và giá. Không bắt được giá bị đảo khi cả 2 số đều nằm
    trong evidence (ca Creator 22/11): cái đó do `promo_above_list` bắt."""
    out: list[str] = []

    def check(path: str, f: Any, key: str) -> None:
        if not isinstance(f, dict):
            return
        ev, v = f.get("evidence"), f.get(key)
        if not isinstance(ev, str) or v is None:
            return
        ok = has_word(v, ev) if isinstance(v, str) else price_in_evidence(float(v), ev)
        if not ok:
            out.append(f"value_not_in_evidence:{path}")

    check("identity.name", pkb["identity"].get("name"), "value")
    pricing = pkb["pricing"]
    plans = pricing.get("plans") or []
    for i, p in enumerate(plans):
        # Ngoại lệ free-only: sản phẩm không có bảng giá, 1 plan "Free" giá 0 lấy từ câu khẳng
        # định miễn phí. Evidence chỉ cần ý miễn phí, không cần tên plan.
        keys = ("list_price",) if free_only(plans) else ("name", "list_price", "promo_price")
        for key in keys:
            check(f"pricing.plans[{i}].{key}", p, key)
    for i, u in enumerate(pricing.get("usage_prices") or []):
        check(f"pricing.usage_prices[{i}].price", u, "price")
    return out


# Số liệu trang tự nêu: `5.06M+`, `33,973+`, `+35%`, `+720 in H1`, `5x`, `12 hours`,
# `1,867 members`. Số có dấu `+` đứng trước là mức tăng, tự nó đủ là số liệu (nhãn đi sau có thể là
# bất kỳ chữ nào). Giá (`$9`) không tính: có ký hiệu tiền thì thuộc pricing.
_METRIC = re.compile(
    r"(?<![\w$€£.,+])(?:\+\d|\d[\d.,]*\s?(?:[kmb]\b\+?|\+|%|[x×](?!\w)|"
    r"(?:\w+\s)?(?:hours?|hrs?|days?|giờ|ngày|views?|lượt|followers?|users?|customers?|"
    r"clients?|members?|downloads?|reach)\b))",
    re.IGNORECASE,
)
METRIC_GROUPS = ("usp", "use_cases")


def has_metric(text: str) -> bool:
    return _METRIC.search(re.sub(r"[*_`]", "", text)) is not None


_NUMBER = re.compile(r"(?<![\w.,])\+?\d[\d.,]*(?:[kmb](?![a-z0-9]))?[+%]?", re.IGNORECASE)
_NEXT_WORD = re.compile(r"\s+([^\s,;.:()\[\]]+)")


def label_mismatch(text: str, evidence: str) -> bool:
    """Số trong `text` đi với nhãn khác so với evidence. Với mỗi số của `text` có từ ngay sau nó
    (`33,973+ AI content views` → `ai`): nếu số đó có trong evidence và từ nhãn cũng có trong
    evidence, mà không lần nào số đứng liền trước từ nhãn đó (cùng dòng hoặc dòng kế) thì lệch.
    Ca thật AISoEasy 30/10: nguồn `5.06M+ / AI content views 33,973+ / new followers`, LLM ghép
    `33,973+ AI content views`. Nhãn không có trong evidence (LLM dịch nhãn) thì bỏ qua."""
    ev = norm(evidence)
    for m in _NUMBER.finditer(text):
        nxt = _NEXT_WORD.match(text, m.end())
        number = norm(m.group(0))
        if not nxt or not number.strip("+"):
            continue
        label = norm(nxt.group(1))
        at = [x.end() for x in re.finditer(re.escape(number) + r"(?![\w])", ev)]
        if not at or not re.search(rf"(?<!\w){re.escape(label)}(?!\w)", ev):
            continue
        if not any(re.match(rf"\s*{re.escape(label)}(?!\w)", ev[end:]) for end in at):
            return True
    return False


def metric_warnings(pkb: dict[str, Any]) -> list[str]:
    """`self_reported_metric:<path>` cho usp / use_case có số liệu (lượt xem, %, 5x, số giờ…).
    Đó là số do website tự công bố, không phải số đã kiểm. Người dùng video nói "theo website"
    chứ không khẳng định. Số trong `text` / `title` hay trong evidence đều tính.
    `metric_label_mismatch:<path>` thêm khi số trong `text` / `title` đi với nhãn khác evidence."""
    out: list[str] = []
    for group in METRIC_GROUPS:
        for i, f in enumerate(pkb.get(group) or []):
            fields = {k: str(f.get(k) or "") for k in ("text", "title", "evidence")}
            if has_metric(" ".join(fields.values())):
                out.append(f"self_reported_metric:{group}[{i}]")
                claim = fields["text"] or fields["title"]
                if label_mismatch(claim, fields["evidence"]):
                    out.append(f"metric_label_mismatch:{group}[{i}]")
    return out


class EvidenceIndex:
    """Text đã chuẩn hoá của từng trang, để kiểm evidence nhanh."""

    def __init__(self, texts: dict[str, str]) -> None:
        self._norm = {sid: norm(t) for sid, t in texts.items()}

    def add(self, source_id: str, text: str) -> None:
        self._norm[source_id] = norm(text)

    def known(self, source_id: object) -> bool:
        return isinstance(source_id, str) and source_id in self._norm

    def found(self, source_id: object, evidence: object) -> bool:
        if not (self.known(source_id) and isinstance(evidence, str) and evidence.strip()):
            return False
        return norm(evidence) in self._norm[str(source_id)]
