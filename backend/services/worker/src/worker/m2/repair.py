"""Prompt sửa (một lượt) và feedback. Template của Định: `contract/…-script-vi-repair.prompt.md`.

Feedback là danh sách `{source, message, scene_id?, segment_id?, path?}` với `source` thuộc
`schema | content_validator | qa | syllable_advisory`. Worker chỉ tự sinh `schema`,
`content_validator` và `syllable_advisory`; `qa` chỉ đến từ người/QA bên ngoài, worker không tự gán
nhãn QA đạt cho model.
"""

from __future__ import annotations

import json
import re
from functools import cache
from typing import Any

from worker.m2.prompt import build_system_prompt
from worker.m2.validate import CONTRACT_DIR, SCRIPT_SCHEMA, load_contract

REPAIR_FILE = "p1-ac-03-script-vi-repair.prompt.md"
_BLOCK_RE = re.compile(r"```text\n(.*?)\n```", re.DOTALL)
_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")
REPAIR_PLACEHOLDERS = (
    "original_generation_prompt",
    "output_schema_json",
    "candidate_script_json",
    "feedback_json",
)
SOURCES = ("schema", "content_validator", "qa", "syllable_advisory")
SYLLABLE_RANGE = (150, 170)  # khuyến nghị của prompt, không phải lỗi contract


@cache
def repair_template() -> str:
    text = (CONTRACT_DIR / REPAIR_FILE).read_text(encoding="utf-8")
    blocks = _BLOCK_RE.findall(text)
    if len(blocks) != 1:
        raise ValueError(f"{REPAIR_FILE}: cần đúng 1 khối ```text, có {len(blocks)}")
    return blocks[0]


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def build_repair_prompt(
    inp: dict[str, Any],
    candidate: dict[str, Any],
    feedback: list[dict[str, Any]],
    narration_range: tuple[int, int] | None = None,
) -> str:
    """Render đủ biến, không để lại placeholder. Dữ liệu được đóng gói JSON (chuỗi đã escape)."""
    values = {
        "original_generation_prompt": build_system_prompt(inp, narration_range),
        "output_schema_json": _dump(load_contract(SCRIPT_SCHEMA)),
        "candidate_script_json": _dump(candidate),
        "feedback_json": _dump(feedback),
    }
    template = repair_template()
    found = set(_PLACEHOLDER_RE.findall(template))
    if found != set(REPAIR_PLACEHOLDERS):
        raise ValueError(f"placeholder trong prompt sửa {sorted(found)} khác {REPAIR_PLACEHOLDERS}")
    return _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], template)


def build_repair_user_prompt() -> str:
    return "Sửa kịch bản theo hướng dẫn trong system prompt. Chỉ trả JSON."


def _locate(message: str) -> dict[str, str]:
    where: dict[str, str] = {}
    seg = re.search(r"\b(s\d+-u\d+)\b", message)
    if seg:
        where["segment_id"] = seg.group(1)
    scene = re.search(r"cảnh '(s\d+)'|\b(s\d+)(?:-u\d+)?\b", message)
    if scene:
        where["scene_id"] = scene.group(1) or scene.group(2)
    return where


def validator_feedback(schema: list[str], content: list[str]) -> list[dict[str, Any]]:
    """Lỗi schema/content của validator → feedback. `schema` hoặc `content` rỗng thì bỏ."""
    out: list[dict[str, Any]] = []
    for msg in schema:
        path = msg.split(":", 1)[0]
        out.append({"source": "schema", "message": msg, "path": path})
    for msg in content:
        out.append({"source": "content_validator", "message": msg, **_locate(msg)})
    return out


def syllable_feedback(
    syllables: int, target_range: tuple[int, int] = SYLLABLE_RANGE
) -> list[dict[str, Any]]:
    low, high = target_range
    if low <= syllables <= high:
        return []
    side = "ít hơn" if syllables < low else "nhiều hơn"
    return [
        {
            "source": "syllable_advisory",
            "message": (
                f"Lời đọc hiện có {syllables} âm tiết, {side} mốc khuyến nghị {low}–{high}. "
                "Chỉ là khuyến nghị: bổ sung/rút gọn bằng nội dung có căn cứ trong fact, không "
                "thêm claim hay kéo dài câu chỉ để đủ số."
            ),
            "syllables": syllables,
        }
    ]
