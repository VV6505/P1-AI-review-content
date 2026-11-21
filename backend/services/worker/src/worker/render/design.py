"""AI nhận diện ngữ cảnh trang web để gợi ý tiêu đề cảnh & bảng màu template phù hợp."""

from __future__ import annotations

import colorsys
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

from worker.m1.llm import make_llm

log = logging.getLogger("worker.render.design")

HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")

DESIGN_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["site_summary", "scenes", "palettes", "recommended_palette_id"],
    "properties": {
        "site_summary": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["scene_id", "headline", "badge", "highlights"],
                "properties": {
                    "scene_id": {"type": "string"},
                    "headline": {"type": "string"},
                    "badge": {"type": "string"},
                    "highlights": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "palettes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "name", "reason", "bg_color", "accent_color", "card_color"],
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "reason": {"type": "string"},
                    "bg_color": {"type": "string"},
                    "accent_color": {"type": "string"},
                    "card_color": {"type": "string"},
                },
            },
        },
        "recommended_palette_id": {"type": "string"},
    },
}


def normalize_hex(value: Any, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    match = HEX_RE.match(value.strip())
    if not match:
        return fallback
    return f"#{match.group(1).upper()}"


def relative_luminance(hex_color: str) -> float:
    clean = normalize_hex(hex_color, "#111827")[1:]
    rgb = [int(clean[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]

    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (_lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_text_for(bg_hex: str) -> str:
    """Trả màu chữ tương phản cao (#111827 trên nền sáng, #FFFFFF trên nền tối)."""
    return "#111827" if relative_luminance(bg_hex) > 0.42 else "#FFFFFF"


def extract_brand_colors(image_paths: list[Path]) -> dict[str, Any]:
    """Trích xuất màu nhấn và tông nền thật từ ảnh chụp màn hình sản phẩm."""
    accent_buckets: Counter[tuple[int, int, int]] = Counter()
    bg_buckets: Counter[tuple[int, int, int]] = Counter()
    for path in image_paths[:4]:
        if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        try:
            with Image.open(path) as img:
                small = img.convert("RGB").resize((80, 45))
                pixels = list(small.getdata())
        except OSError:
            continue
        for r, g, b in pixels:
            qr, qg, qb = (r // 16) * 16 + 8, (g // 16) * 16 + 8, (b // 16) * 16 + 8
            _, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            if s >= 0.35 and 0.22 <= v <= 0.96:
                accent_buckets[(qr, qg, qb)] += 1
            else:
                bg_buckets[(qr, qg, qb)] += 1

    def _to_hex(rgb: tuple[int, int, int]) -> str:
        return f"#{min(255, rgb[0]):02X}{min(255, rgb[1]):02X}{min(255, rgb[2]):02X}"

    accents = [_to_hex(rgb) for rgb, _ in accent_buckets.most_common(4)]
    backgrounds = [_to_hex(rgb) for rgb, _ in bg_buckets.most_common(3)]
    primary_accent = accents[0] if accents else "#E44332"
    primary_bg = backgrounds[0] if backgrounds else "#FAF3EC"
    return {
        "detected_accents": accents,
        "detected_backgrounds": backgrounds,
        "primary_accent": primary_accent,
        "primary_bg": primary_bg,
    }


def _tint_from_accent(accent_hex: str) -> str:
    clean = normalize_hex(accent_hex, "#E44332")[1:]
    r, g, b = (int(clean[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    h, s, _ = colorsys.rgb_to_hsv(r, g, b)
    lr, lg, lb = colorsys.hsv_to_rgb(h, min(0.14, s * 0.25), 0.97)
    return f"#{round(lr * 255):02X}{round(lg * 255):02X}{round(lb * 255):02X}"


def _dark_from_accent(accent_hex: str) -> str:
    clean = normalize_hex(accent_hex, "#E44332")[1:]
    r, g, b = (int(clean[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    h, s, _ = colorsys.rgb_to_hsv(r, g, b)
    dr, dg, db = colorsys.hsv_to_rgb(h, min(0.45, max(0.18, s * 0.5)), 0.13)
    return f"#{round(dr * 255):02X}{round(dg * 255):02X}{round(db * 255):02X}"


def _fallback_headline(
    scene: dict[str, Any], product_name: str, concept_title: str
) -> tuple[str, str]:
    role = str(scene.get("role") or "feature").lower()
    claims = scene.get("claims") or []
    first_claim = (
        str(claims[0].get("text") or "").strip() if claims and isinstance(claims[0], dict) else ""
    )
    segments = scene.get("narration_segments") or []
    narration = " ".join(str(seg.get("text") or "").strip() for seg in segments).strip()
    source = first_claim or narration
    words = [w.strip(".,:;!?") for w in source.split() if w.strip(".,:;!?")]
    short = " ".join(words[:7]) if words else product_name
    if role == "hook":
        return (concept_title[:48] or f"Khám phá {product_name}"), "MỞ ĐẦU"
    if role == "cta":
        return f"Trải nghiệm {product_name} ngay", "TRẢI NGHIỆM"
    badge_map = {
        "problem": "VẤN ĐỀ",
        "demo": "THAO TÁC",
        "feature": "TÍNH NĂNG",
        "result": "HIỆU QUẢ",
        "proof": "BẰNG CHỨNG",
    }
    return short[:52], badge_map.get(role, "ĐIỂM NỔI BẬT")


def _default_palettes(product_name: str, color_info: dict[str, Any]) -> list[dict[str, str]]:
    accent = normalize_hex(color_info.get("primary_accent"), "#E44332")
    soft_bg = _tint_from_accent(accent)
    dark_bg = _dark_from_accent(accent)
    return [
        {
            "id": "brand-soft",
            "name": f"Nền sáng {product_name}",
            "reason": "Tông nền sáng êm mắt khớp màu nhấn lấy trực tiếp từ trang web, nổi bật viền Offset Shadow.",
            "bg_color": soft_bg,
            "accent_color": accent,
            "card_color": "#FFFFFF",
            "text_color": contrast_text_for(soft_bg),
        },
        {
            "id": "editorial-cream",
            "name": "Giấy kem Editorial",
            "reason": "Tông giấy kem ấm tạo cảm giác tạp chí hiện đại, làm nổi ảnh giao diện sáng.",
            "bg_color": "#F5EFE6",
            "accent_color": accent,
            "card_color": "#FFFFFF",
            "text_color": "#111827",
        },
        {
            "id": "brand-dark",
            "name": f"Tối hiện đại {product_name}",
            "reason": "Nền tối độ tương phản cao giúp khung sản phẩm sáng bật lên rõ ràng trên điện thoại.",
            "bg_color": dark_bg,
            "accent_color": accent,
            "card_color": "#18181B",
            "text_color": "#FFFFFF",
        },
        {
            "id": "neo-pop",
            "name": "Vàng năng động Pop",
            "reason": "Phong cách Neo-brutalist mạnh mẽ, hút mắt trong 3 giây đầu trên TikTok/Reels.",
            "bg_color": "#FDE047",
            "accent_color": "#111827",
            "card_color": "#FFFFFF",
            "text_color": "#111827",
        },
    ]


async def suggest_template_design(
    *,
    product: dict[str, Any],
    pkb: dict[str, Any],
    script: dict[str, Any],
    template: str,
    asset_paths: list[Path],
) -> dict[str, Any]:
    """Gọi LLM + màu trích xuất từ ảnh chụp web để gợi ý tiêu đề cảnh & bảng màu template."""
    pkb_data = pkb.get("data") if isinstance(pkb.get("data"), dict) else {}
    identity = pkb_data.get("identity") if isinstance(pkb_data.get("identity"), dict) else {}
    raw_name = identity.get("name")
    product_name = (
        str(raw_name.get("value") if isinstance(raw_name, dict) else raw_name or "").strip()
        or str(product.get("name") or "").strip()
        or "Sản phẩm"
    )
    raw_desc = identity.get("description")
    product_desc = str(
        raw_desc.get("value") if isinstance(raw_desc, dict) else raw_desc or ""
    ).strip()
    website_url = str(product.get("website_url") or "").strip()
    concept = script.get("concept") if isinstance(script.get("concept"), dict) else {}
    concept_title = str(concept.get("title") or "").strip()
    scenes = script.get("scenes") if isinstance(script.get("scenes"), list) else []

    color_info = extract_brand_colors(asset_paths)
    fallback_palettes = _default_palettes(product_name, color_info)

    scene_summaries = []
    for idx, scene in enumerate(scenes, start=1):
        sid = str(scene.get("scene_id") or f"s{idx:02}")
        role = str(scene.get("role") or "feature")
        narration = " ".join(
            str(seg.get("text") or "").strip() for seg in (scene.get("narration_segments") or [])
        ).strip()
        visual = scene.get("visual_plan") if isinstance(scene.get("visual_plan"), dict) else {}
        scene_summaries.append(
            {
                "scene_id": sid,
                "role": role,
                "asset_id": visual.get("asset_id"),
                "narration": narration,
            }
        )

    system_prompt = (
        "Bạn là Art Director & Copywriter cho video ngắn giới thiệu sản phẩm web/SaaS tiếng Việt. "
        "Dựa vào thông tin website, màu chủ đạo đo từ ảnh chụp giao diện và từng cảnh trong kịch bản, hãy:\n"
        "1. Đặt lại TIÊU ĐỀ NGẮN (headline) bằng tiếng Việt có dấu cho TỪNG cảnh (4–7 từ, tối đa 46 ký tự), "
        "bám sát đúng nội dung trang web và lời đọc của cảnh đó. TUYỆT ĐỐI KHÔNG dùng nhãn kỹ thuật như "
        "'HOOK', 'PROBLEM', 'DEMO', 'RESULT', 'CTA'.\n"
        "2. Đặt NHÃN BADGE siêu ngắn (1–3 từ tiếng Việt viết hoa, tối đa 18 ký tự) mô tả chủ đề cảnh "
        "(ví dụ: '50M+ NGƯỜI DÙNG', 'GOM VIỆC AI', 'CHIA VIỆC NHÓM', 'BẢNG GIÁ', 'DÙNG THỬ FREE').\n"
        "3. Đặt đúng 2 ĐIỂM NỔI BẬT NGẮN (highlights: mảng 2 chuỗi tiếng Việt, mỗi chuỗi 5–10 từ, tối đa 54 ký tự) "
        "chắt lọc đúng dữ kiện thật của cảnh đó để hiển thị trong thẻ Điểm Nổi Bật dưới khung web (không bịa số liệu).\n"
        "4. Gợi ý 4 bảng màu nền template (palettes) phù hợp với màu nhận diện của trang web và phong cách "
        f"template '{template}' (ưu tiên độ tương phản tốt để khung giao diện sản phẩm + chữ/phụ đề nổi rõ, "
        "không chói lóa, có cả lựa chọn nền sáng nhẹ theo brand và nền tối sang trọng). "
        "Mọi màu phải là mã HEX 6 ký tự dạng #RRGGBB."
    )
    user_prompt = (
        f"Website: {website_url}\n"
        f"Tên sản phẩm: {product_name}\n"
        f"Mô tả sản phẩm: {product_desc[:500]}\n"
        f"Concept video: {concept_title}\n"
        f"Template đang chọn: {template}\n"
        f"Màu nhấn đo từ ảnh chụp trang web: {color_info['detected_accents']}\n"
        f"Màu nền đo từ ảnh chụp trang web: {color_info['detected_backgrounds']}\n"
        f"Danh sách các cảnh:\n{scene_summaries}\n\n"
        "Trả về JSON theo đúng schema."
    )

    ai_data: dict[str, Any] | None = None
    try:
        llm = make_llm()
        result = await llm.generate_json(
            step="design_suggest",
            system=system_prompt,
            prompt=user_prompt,
            response_schema=DESIGN_RESPONSE_SCHEMA,
        )
        ai_data = result.data
    except Exception as exc:  # noqa: BLE001
        log.warning("design_suggest LLM fallback: %s", exc)

    ai_scenes: dict[str, dict[str, Any]] = {}
    if isinstance(ai_data, dict) and isinstance(ai_data.get("scenes"), list):
        for item in ai_data["scenes"]:
            if isinstance(item, dict) and isinstance(item.get("scene_id"), str):
                ai_scenes[item["scene_id"]] = item

    resolved_scenes: list[dict[str, Any]] = []
    for idx, scene in enumerate(scenes, start=1):
        sid = str(scene.get("scene_id") or f"s{idx:02}")
        fb_headline, fb_badge = _fallback_headline(scene, product_name, concept_title)
        cand = ai_scenes.get(sid) or {}
        headline = str(cand.get("headline") or "").strip()
        badge = str(cand.get("badge") or "").strip()
        if not headline or headline.upper() in {
            "HOOK",
            "PROBLEM",
            "DEMO",
            "RESULT",
            "CTA",
            "FEATURE",
        }:
            headline = fb_headline
        if not badge or badge.upper() in {"HOOK", "PROBLEM", "DEMO", "RESULT", "CTA"}:
            badge = fb_badge
        raw_hl = cand.get("highlights")
        highlights = [
            str(h).strip()[:64]
            for h in (raw_hl if isinstance(raw_hl, list) else [])
            if isinstance(h, str) and h.strip()
        ][:2]
        if not highlights:
            claims = scene.get("claims") or []
            highlights = [
                str(c.get("text") or "").strip()[:64]
                for c in claims[:2]
                if isinstance(c, dict) and str(c.get("text") or "").strip()
            ]
        if not highlights:
            highlights = [headline[:64]]
        resolved_scenes.append(
            {
                "scene_id": sid,
                "headline": headline[:56],
                "badge": badge.upper()[:22],
                "highlights": highlights,
            }
        )

    resolved_palettes: list[dict[str, str]] = []
    if isinstance(ai_data, dict) and isinstance(ai_data.get("palettes"), list):
        seen_ids: set[str] = set()
        for idx, item in enumerate(ai_data["palettes"][:4], start=1):
            if not isinstance(item, dict):
                continue
            pid = re.sub(
                r"[^a-z0-9_-]+", "-", str(item.get("id") or f"palette-{idx}").lower()
            ).strip("-")
            if not pid or pid in seen_ids:
                pid = f"palette-{idx}"
            seen_ids.add(pid)
            bg = normalize_hex(item.get("bg_color"), fallback_palettes[min(idx - 1, 3)]["bg_color"])
            accent = normalize_hex(
                item.get("accent_color"), fallback_palettes[min(idx - 1, 3)]["accent_color"]
            )
            card = normalize_hex(item.get("card_color"), "#FFFFFF")
            resolved_palettes.append(
                {
                    "id": pid,
                    "name": str(item.get("name") or f"Bảng màu {idx}").strip()[:42],
                    "reason": str(
                        item.get("reason") or "Phù hợp màu thương hiệu trang web."
                    ).strip()[:140],
                    "bg_color": bg,
                    "accent_color": accent,
                    "card_color": card,
                    "text_color": contrast_text_for(bg),
                }
            )
    if len(resolved_palettes) < 2:
        resolved_palettes = fallback_palettes

    rec_id = str(ai_data.get("recommended_palette_id") or "") if isinstance(ai_data, dict) else ""
    if not any(p["id"] == rec_id for p in resolved_palettes):
        rec_id = resolved_palettes[0]["id"]

    site_summary = (
        str(ai_data.get("site_summary") or "").strip() if isinstance(ai_data, dict) else ""
    ) or f"Nhận diện màu thương hiệu và tiêu đề theo trang {product_name} ({website_url})."

    return {
        "site_summary": site_summary[:220],
        "detected_colors": color_info,
        "scenes": resolved_scenes,
        "palettes": resolved_palettes,
        "recommended_palette_id": rec_id,
    }
