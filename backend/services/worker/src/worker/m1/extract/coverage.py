"""Độ phủ của trang nguồn: section nào có nội dung mà không fact nào lấy evidence từ đó.

Không gọi LLM, không đoán nghĩa: chỉ tách markdown theo heading và hỏi "có evidence nào nằm trong
section này không". Dùng để người xác nhận PKB biết LLM đã bỏ qua khối nào của trang (ca AISoEasy
30/10: 4 lộ trình theo phòng ban, số liệu traction, jobs board bị bỏ hoàn toàn).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from worker.m1.extract.evidence import Fact, iter_facts, norm
from worker.m1.extract.pages import SourceDoc

HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$")
FENCE = re.compile(r"^\s*(?:```|~~~)")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_WORD = re.compile(r"\w+", re.UNICODE)

# Section "đáng kể": đủ chữ để chứa fact. Nút, nhãn và menu ngắn không đạt. Đo trên 3 trang chủ
# (AISoEasy, PDFCraft, ElevenLabs): 15 từ bắt được khối traction và jobs board của AISoEasy mà
# trang chủ PDFCraft chỉ có 1 cảnh báo.
MIN_WORDS = 15
MIN_OVERLAP = (
    20  # ký tự evidence phải nằm trong section để tính là phủ (evidence ngắn hơn: cả đoạn)
)
TOP = "(đầu trang)"  # phần trước heading đầu tiên
HEADING_MAX = 80


@dataclass(frozen=True)
class Section:
    source_id: str
    heading: str
    body: str  # chữ dưới heading tới heading kế (không gồm heading)
    start: int  # vị trí trong `page_text` (text đã chuẩn hoá của cả trang)
    end: int

    @property
    def words(self) -> int:
        """Số từ của nội dung dưới heading. `SourceDoc.text` đã bỏ ảnh và URL của link."""
        return len(_WORD.findall(self.body))

    @property
    def significant(self) -> bool:
        return self.words >= MIN_WORDS


def heading_title(raw: str) -> str:
    """Tên của heading (phần sau `###`): bỏ ảnh, giữ chữ của link."""
    return _LINK.sub(r"\1", _IMAGE.sub("", raw)).strip()


def split_sections(source_id: str, text: str) -> tuple[list[Section], str]:
    """Tách theo mọi heading (`#`…`######`), trả (sections, `page_text`). Mỗi section chạy từ
    heading tới heading kế (kể cả heading con), nên section cha chỉ giữ chữ trước heading con đầu.
    Heading mang link `### [Tên](url)` lấy `Tên`. Dòng trong khối code không tính là heading.
    `page_text` là các section đã chuẩn hoá nối bằng 1 dấu cách, bằng `norm(text)`."""
    parts: list[tuple[str, list[str], list[str]]] = [(TOP, [], [])]  # heading, dòng thân, mọi dòng
    fenced = False
    for ln in text.splitlines():
        if FENCE.match(ln):
            fenced = not fenced
        m = None if fenced else HEADING.match(ln)
        if m:
            parts.append((heading_title(m.group(1))[:HEADING_MAX], [], [ln]))
        else:
            parts[-1][1].append(ln)
            parts[-1][2].append(ln)
    sections: list[Section] = []
    chunks: list[str] = []
    pos = 0
    for heading, body, lines in parts:
        n = norm("\n".join(lines))
        if not n:
            continue
        sections.append(Section(source_id, heading, "\n".join(body), pos, pos + len(n)))
        chunks.append(n)
        pos += len(n) + 1
    return sections, " ".join(chunks)


def _span(page_text: str, evidence: str) -> tuple[int, int] | None:
    """Vị trí đầu tiên của evidence (đã chuẩn hoá) trong `page_text`. Chỉ tính lần xuất hiện đầu:
    evidence ngắn lặp ở nhiều section (tên sản phẩm "AI So Easy" có ở menu, hero, footer) mà tính
    hết thì một fact phủ cả trang và che mất các khối bị bỏ. Chấp nhận bỏ sót khi LLM trích lần
    sau (hiếm: evidence dài thì duy nhất)."""
    target = norm(evidence)
    i = page_text.find(target) if target else -1
    return None if i == -1 else (i, i + len(target))


def uncovered_sections(
    docs: Sequence[SourceDoc], facts: Sequence[tuple[str, Fact]]
) -> list[Section]:
    """Section đáng kể của các trang đã gửi LLM mà không fact nào có evidence chồng lên. Evidence
    nằm vắt qua 2 section thì tính phủ cả hai. Trả theo thứ tự trang."""
    out: list[Section] = []
    for doc in docs:
        sections, page_text = split_sections(doc.source_id, doc.text)
        hits = [
            span
            for _, f in facts
            if f.get("source_id") == doc.source_id and isinstance(f.get("evidence"), str)
            if (span := _span(page_text, f["evidence"]))
        ]
        out += [
            s
            for s in sections
            if s.significant
            and not any(_overlap(a, b, s) >= min(b - a, MIN_OVERLAP) for a, b in hits)
        ]
    return out


def _overlap(a: int, b: int, s: Section) -> int:
    """Số ký tự của evidence [a, b) nằm trong section. Evidence vắt qua ranh giới chỉ phủ section
    kia khi lấn vào đủ `MIN_OVERLAP` ký tự: một dòng nhãn cuối section ("Membership" ngay trước
    heading kế) không tính là phủ section đó."""
    return max(0, min(b, s.end) - max(a, s.start))


def coverage_warnings(docs: Sequence[SourceDoc], data: dict[str, Any]) -> list[str]:
    """`section_not_covered:<heading>` cho mỗi section đáng kể không được fact nào dùng."""
    missed = uncovered_sections(docs, list(iter_facts(data)))
    return [f"section_not_covered:{s.heading}" for s in missed]
