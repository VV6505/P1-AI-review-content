"""Ngữ cảnh khối nguồn cho evidence của `usp`, `use_cases`, `audiences`.

LLM hay chép đúng dòng chứa số (`2.58M+ Views`) mà bỏ heading của khối (`### TikTok`), nên fact mất
nền tảng / phòng ban. Hàm ở đây nối heading gần nhất phía trên vào evidence, bằng code và không gọi
LLM: evidence mới là đoạn liền từ dòng heading tới hết evidence cũ, cắt thẳng từ markdown nguồn
(vẫn nguyên văn, ≤ `EVIDENCE_MAX`). Quá dài thì giữ evidence cũ và cảnh báo.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from worker.m1.extract.coverage import FENCE, HEADING, heading_title
from worker.m1.extract.evidence import has_word, norm
from worker.m1.extract.pages import SourceDoc
from worker.m1.pkb.models import EVIDENCE_MAX

CONTEXT_GROUPS = ("usp", "use_cases", "audiences")
# Heading + tối đa 3 dòng thân. Xa hơn thì dòng đó thường là dòng thống kê chung của cả trang đứng
# sau khối cuối (AISoEasy: `87.6%audience in Vietnam` sau `### Facebook Group`), không của khối.
MAX_LINES = 4
# Heading tối đa chừng này từ mới là tên khối (TikTok, Facebook Group); dài hơn là câu, không
# thêm vào `text`.
NAME_MAX_WORDS = 4
# Nhãn (kicker) là dòng ngắn ngay trên heading (`Sales` trên `### Close deals…`, `For individuals`
# trên `## Free AI videos?`): tối đa chừng này từ, không chữ số, không câu, không danh sách / trích.
KICKER_MAX_WORDS = 6
_KICKER_SKIP = re.compile(r"^(?:[*\-+>|`]|\d+[.)]\s)")


@dataclass(frozen=True)
class _Heading:
    start: int  # vị trí đầu dòng heading trong text gốc
    end: int  # hết dòng (không gồm ký tự xuống dòng)
    title: str


@dataclass(frozen=True)
class _Page:
    text: str
    norm: str  # `norm(text)`
    raw_at: list[int]  # raw_at[i] = vị trí trong `text` của ký tự thứ i của `norm`
    headings: list[_Heading]


def _mapped_norm(raw: str) -> tuple[str, list[int]] | None:
    """`norm(raw)` kèm vị trí gốc của từng ký tự. Làm theo từng cụm (ký tự + dấu tổ hợp) để NFC
    ghép đúng chữ Việt dựng sẵn / tổ hợp. Kết quả khác `norm(raw)` (ký tự hiếm) thì trả None."""
    out: list[str] = []
    at: list[int] = []
    i, n = 0, len(raw)
    while i < n:
        j = i + 1
        while j < n and unicodedata.combining(raw[j]):
            j += 1
        for ch in unicodedata.normalize("NFC", raw[i:j]).lower():
            if ch in "*_`":
                continue
            if ch in "#|>\\" or ch.isspace():
                ch = " "
            if ch == " " and (not out or out[-1] == " "):
                continue
            out.append(ch)
            at.append(i)
        i = j
    if out and out[-1] == " ":
        out.pop()
        at.pop()
    text = "".join(out)
    return (text, at) if text == norm(raw) else None


def _headings(text: str) -> list[_Heading]:
    out: list[_Heading] = []
    fenced = False
    pos = 0
    for ln in text.splitlines(keepends=True):
        body = ln.rstrip("\r\n")
        if FENCE.match(body):
            fenced = not fenced
        m = None if fenced else HEADING.match(body)
        if m:
            out.append(_Heading(pos, pos + len(body), heading_title(m.group(1))))
        pos += len(ln)
    return out


def _kicker(text: str, heading: _Heading) -> int | None:
    """Vị trí đầu dòng nhãn nằm ngay trên `heading`, hoặc None nếu dòng đó không phải nhãn."""
    before = text[: heading.start].rstrip("\r\n")
    if not before:
        return None
    start = max(before.rfind("\n"), before.rfind("\r")) + 1
    line = before[start:].strip()
    if not line or len(line.split()) > KICKER_MAX_WORDS:
        return None
    if re.search(r"\d", line) or line[-1] in ".!?" or _KICKER_SKIP.match(line):
        return None
    return None if HEADING.match(before[start:]) else start


def _page(text: str) -> _Page | None:
    mapped = _mapped_norm(text)
    return _Page(text, mapped[0], mapped[1], _headings(text)) if mapped else None


def _expand(page: _Page, evidence: str) -> tuple[_Heading, str] | None:
    """(heading gần nhất phía trên, evidence mở rộng). None khi không có gì để nối: evidence
    không có trong trang, đã chạm dòng heading (nằm trong hoặc vắt qua) hoặc không có heading."""
    target = norm(evidence)
    a = page.norm.find(target) if target else -1
    if a == -1:
        return None
    start = page.raw_at[a]
    end = page.raw_at[a + len(target) - 1] + 1
    above: _Heading | None = None
    for h in page.headings:
        if h.start < end and h.end > start:
            # Evidence chính là dòng heading: không có heading nào phía trên để nối, nhưng dòng nhãn
            # ngay trên nó là ngữ cảnh của khối.
            if h.start <= start and (k := _kicker(page.text, h)) is not None:
                return h, page.text[k:end].strip()
            return None
        if h.start < start:
            above = h
    if above is None:
        return None
    return above, page.text[above.start : end].strip()


def add_block_context(pkb: dict[str, Any], docs: Sequence[SourceDoc]) -> list[str]:
    """Nối heading của khối nguồn vào evidence của `usp`, `use_cases`, `audiences` (sửa tại chỗ).
    `usp` thêm tên khối (`2.58M+ Views (TikTok)`) vào `text` nếu text chưa có. Evidence mở rộng
    vượt `EVIDENCE_MAX` thì giữ evidence cũ, trả warning `evidence_context_missing:<path>`."""
    texts = {d.source_id: d.text for d in docs}
    pages: dict[str, _Page | None] = {}
    warnings: list[str] = []
    for group in CONTEXT_GROUPS:
        for i, f in enumerate(pkb.get(group) or []):
            sid, ev = f.get("source_id"), f.get("evidence")
            if not (isinstance(sid, str) and sid in texts and isinstance(ev, str)):
                continue
            if sid not in pages:
                pages[sid] = _page(texts[sid])
            path = f"{group}[{i}]"
            if (page := pages[sid]) is None:
                warnings.append(f"evidence_context_missing:{path}")
                continue
            if (found := _expand(page, ev)) is None:
                continue
            heading, expanded = found
            if len(expanded) > EVIDENCE_MAX or expanded.count("\n") + 1 > MAX_LINES:
                warnings.append(f"evidence_context_missing:{path}")
                continue
            f["evidence"] = expanded
            text, name = f.get("text"), heading.title
            if group == "usp" and isinstance(text, str) and 0 < len(name.split()) <= NAME_MAX_WORDS:
                if not has_word(name, text):
                    f["text"] = f"{text} ({name})"
    return warnings
