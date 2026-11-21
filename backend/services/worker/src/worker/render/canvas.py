"""Dựng các lớp đồ họa Offset Shadow tách rời (RGBA) bằng Pillow để FFmpeg tạo animation mượt 30fps."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont

from worker.render.design import contrast_text_for, normalize_hex, relative_luminance

FONT_BOLD_CANDIDATES = (
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\tahomabd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
FONT_REG_CANDIDATES = (
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


@dataclass(frozen=True)
class CanvasLayers:
    bg_path: Path
    title_path: Path | None
    browser_path: Path | None
    info_path: Path | None
    cta_btn_path: Path | None
    progress_path: Path | None
    progress_box: tuple[int, int, int, int] | None  # (x, y, w, h)
    media_box: tuple[int, int, int, int] | None  # (x, y, w, h)
    card_box: tuple[int, int, int, int] | None  # (x, y, w, h)
    border_px: int


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = FONT_BOLD_CANDIDATES if bold else FONT_REG_CANDIDATES
    for candidate in candidates:
        if Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, size=max(10, size))
            except OSError:
                continue
    return ImageFont.load_default()


def _hex_rgb(hex_color: str, fallback: str = "#111827") -> tuple[int, int, int]:
    clean = normalize_hex(hex_color, fallback)[1:]
    return (int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16))


def _rgba(rgb: tuple[int, int, int], alpha: int = 255) -> tuple[int, int, int, int]:
    return (rgb[0], rgb[1], rgb[2], alpha)


def _mix(c1: tuple[int, int, int], c2: tuple[int, int, int], weight: float) -> tuple[int, int, int]:
    return (
        round(c1[0] * (1 - weight) + c2[0] * weight),
        round(c1[1] * (1 - weight) + c2[1] * weight),
        round(c1[2] * (1 - weight) + c2[2] * weight),
    )


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    words = text.strip().split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines - 1:
                break
    remaining_idx = sum(len(line.split()) for line in lines)
    tail = " ".join(words[remaining_idx:])
    if tail:
        while draw.textlength(tail, font=font) > max_width and len(tail) > 4:
            tail = tail[:-2].rstrip() + "…"
        lines.append(tail)
    return lines[:max_lines]


def _draw_offset_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int],
    border: tuple[int, int, int],
    shadow: tuple[int, int, int],
    border_w: int,
    shadow_dx: int,
    shadow_dy: int,
    radius: int = 0,
) -> None:
    x, y, w, h = box
    s_box = (x + shadow_dx, y + shadow_dy, x + w + shadow_dx, y + h + shadow_dy)
    m_box = (x, y, x + w, y + h)
    if radius > 0:
        draw.rounded_rectangle(s_box, radius=radius, fill=_rgba(shadow))
        draw.rounded_rectangle(
            m_box, radius=radius, fill=_rgba(fill), outline=_rgba(border), width=border_w
        )
    else:
        draw.rectangle(s_box, fill=_rgba(shadow))
        draw.rectangle(m_box, fill=_rgba(fill), outline=_rgba(border), width=border_w)


def _domain_label(url: str, fallback: str) -> str:
    if url:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host:
            return host[:28]
    return (fallback or "reviewlab").strip()[:28]


def _extract_highlights(
    scene: dict[str, Any], override: dict[str, Any], narration: str, headline: str
) -> list[str]:
    raw = override.get("highlights")
    points: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            text = str(item or "").strip()
            if text:
                points.append(text[:68])
    if not points:
        claims = scene.get("claims")
        if isinstance(claims, list):
            for claim in claims:
                if isinstance(claim, dict):
                    t = str(claim.get("text") or "").strip()
                    if t:
                        points.append(t[:74])
    if not points:
        parts = [p.strip() for p in narration.replace(";", ".").split(".") if len(p.strip()) > 8]
        for part in parts[:2]:
            if part.lower() != headline.lower():
                points.append(part[:74])
    if not points:
        points = [headline[:68]]
    return points[:2]


def _draw_background(
    img: Image.Image,
    *,
    accent_rgb: tuple[int, int, int],
    ink_rgb: tuple[int, int, int],
    is_light: bool,
    scale: float,
) -> None:
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")

    step = max(24, round(40 * scale))
    dot_r = max(1, round(2.1 * scale))
    dot_color = (*ink_rgb, 34 if is_light else 42)
    for y in range(step // 2, h, step):
        for x in range(step // 2, w, step):
            draw.ellipse((x - dot_r, y - dot_r, x + dot_r, y + dot_r), fill=dot_color)

    soft_accent = (*accent_rgb, 36 if is_light else 46)
    soft_ink = (*ink_rgb, 18 if is_light else 28)
    draw.rounded_rectangle(
        (w - round(260 * scale), -round(40 * scale), w + round(60 * scale), round(220 * scale)),
        radius=round(28 * scale),
        fill=soft_accent,
    )
    draw.rounded_rectangle(
        (-round(70 * scale), h - round(270 * scale), round(220 * scale), h + round(50 * scale)),
        radius=round(28 * scale),
        fill=soft_accent,
    )
    m = round(34 * scale)
    plus_s = round(14 * scale)
    plus_w = max(2, round(3.5 * scale))
    for px, py in (
        (w - m - round(36 * scale), h - m - round(44 * scale)),
        (m + round(24 * scale), h - round(310 * scale)),
    ):
        draw.line((px - plus_s, py, px + plus_s, py), fill=(*accent_rgb, 150), width=plus_w)
        draw.line((px, py - plus_s, px, py + plus_s), fill=(*accent_rgb, 150), width=plus_w)

    frame_m = round(20 * scale)
    draw.rectangle(
        (frame_m, frame_m, w - frame_m, h - frame_m),
        outline=soft_ink,
        width=max(2, round(2.5 * scale)),
    )


def build_offset_shadow_layers(
    *,
    output_dir: Path,
    scene_id: str,
    width: int,
    height: int,
    scene: dict[str, Any],
    override: dict[str, Any],
    headline: str,
    badge: str,
    narration: str,
    scene_index: int,
    scene_total: int,
    product_name: str,
    website_url: str,
    bg_hex: str,
    accent_hex: str,
    card_hex: str,
    media_size: tuple[int, int] | None,
    is_video_media: bool,
) -> CanvasLayers:
    """Sinh các lớp RGBA tách rời để FFmpeg tạo animation vào cảnh & thanh tiến độ chạy sống."""
    output_dir.mkdir(parents=True, exist_ok=True)
    is_portrait = height > width
    scale = (width / 1080.0) if is_portrait else (height / 1080.0)

    bg_rgb = _hex_rgb(bg_hex, "#FAF3EC")
    accent_rgb = _hex_rgb(accent_hex, "#E44332")
    card_rgb = _hex_rgb(card_hex, "#FFFFFF")
    is_light_bg = relative_luminance(f"#{bg_hex}") > 0.42
    is_light_card = relative_luminance(f"#{card_hex}") > 0.42
    ink_rgb = (17, 24, 39) if is_light_bg else (248, 250, 252)
    border_rgb = (17, 24, 39) if is_light_bg else (241, 245, 249)
    shadow_rgb = (17, 24, 39) if is_light_bg else (5, 7, 13)
    card_ink = (17, 24, 39) if is_light_card else (248, 250, 252)
    card_muted = _mix(card_ink, card_rgb, 0.35)

    badge_bg_hex = accent_hex if relative_luminance(f"#{accent_hex}") < 0.65 else "111827"
    badge_bg_rgb = _hex_rgb(badge_bg_hex)
    badge_fg_rgb = _hex_rgb(contrast_text_for(f"#{badge_bg_hex}"))

    border_px = max(3, round(5 * scale))
    card_border_px = max(4, round(6 * scale))
    shadow_sm = max(4, round(7 * scale))
    shadow_md = max(7, round(12 * scale))
    shadow_lg = max(10, round(16 * scale))

    domain = _domain_label(website_url, product_name)
    highlights = _extract_highlights(scene, override, narration, headline)

    # Layer 1: Background + Top Bar + Progress Track
    bg_img = Image.new("RGB", (width, height), bg_rgb)
    _draw_background(
        bg_img, accent_rgb=accent_rgb, ink_rgb=ink_rgb, is_light=is_light_bg, scale=scale
    )
    bg_draw = ImageDraw.Draw(bg_img)

    bg_path = output_dir / f"{scene_id}_bg.png"
    title_path = output_dir / f"{scene_id}_title.png"
    browser_path = output_dir / f"{scene_id}_browser.png"
    info_path = output_dir / f"{scene_id}_info.png"
    cta_btn_path = output_dir / f"{scene_id}_ctabtn.png"
    progress_path = output_dir / f"{scene_id}_prog.png"

    if is_portrait:
        pad_x = round(58 * scale)
        content_w = width - pad_x * 2

        # Top Meta Bar trên nền
        top_y = round(54 * scale)
        pill_h = round(58 * scale)
        font_pill = _load_font(round(24 * scale), bold=True)
        brand_w = min(
            round(content_w * 0.62),
            int(bg_draw.textlength(f"  {domain}", font=font_pill)) + round(66 * scale),
        )
        _draw_offset_box(
            bg_draw,
            (pad_x, top_y, brand_w, pill_h),
            fill=card_rgb,
            border=border_rgb,
            shadow=shadow_rgb,
            border_w=max(2, round(3.5 * scale)),
            shadow_dx=shadow_sm,
            shadow_dy=shadow_sm,
            radius=round(10 * scale),
        )
        dot_r = round(8 * scale)
        dot_cx = pad_x + round(24 * scale)
        dot_cy = top_y + pill_h // 2
        bg_draw.ellipse(
            (dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r), fill=accent_rgb
        )
        bg_draw.text(
            (dot_cx + round(14 * scale), dot_cy), domain, font=font_pill, fill=card_ink, anchor="lm"
        )

        step_label = f"{scene_index:02d} / {scene_total:02d}"
        step_w = int(bg_draw.textlength(step_label, font=font_pill)) + round(44 * scale)
        step_x = width - pad_x - step_w
        _draw_offset_box(
            bg_draw,
            (step_x, top_y, step_w, pill_h),
            fill=badge_bg_rgb,
            border=border_rgb,
            shadow=shadow_rgb,
            border_w=max(2, round(3.5 * scale)),
            shadow_dx=shadow_sm,
            shadow_dy=shadow_sm,
            radius=round(10 * scale),
        )
        bg_draw.text(
            (step_x + step_w // 2, top_y + pill_h // 2),
            step_label,
            font=font_pill,
            fill=badge_fg_rgb,
            anchor="mm",
        )

        # Thanh tiến độ: các cảnh trước tô đầy, cảnh hiện tại để trống track cho FFmpeg chạy live 0% → 100%
        seg_y = top_y + pill_h + round(22 * scale)
        seg_h = max(8, round(12 * scale))
        seg_gap = round(10 * scale)
        seg_w = (content_w - seg_gap * max(0, scene_total - 1)) // max(1, scene_total)
        active_seg_box: tuple[int, int, int, int] | None = None
        for i in range(scene_total):
            sx = pad_x + i * (seg_w + seg_gap)
            completed = i < scene_index - 1
            seg_fill = accent_rgb if completed else _mix(bg_rgb, ink_rgb, 0.14)
            bg_draw.rounded_rectangle(
                (sx, seg_y, sx + seg_w, seg_y + seg_h),
                radius=seg_h // 2,
                fill=seg_fill,
                outline=border_rgb if completed else None,
                width=max(1, round(2 * scale)),
            )
            if i == scene_index - 1:
                active_seg_box = (sx, seg_y, seg_w, seg_h)
        bg_img.save(bg_path, format="PNG")

        # Ảnh thanh tiến độ sống (RGBA) cho phân đoạn hiện tại
        prog_img = Image.new("RGBA", (seg_w, seg_h), (0, 0, 0, 0))
        p_draw = ImageDraw.Draw(prog_img)
        p_draw.rounded_rectangle(
            (0, 0, seg_w - 1, seg_h - 1),
            radius=seg_h // 2,
            fill=_rgba(accent_rgb),
            outline=_rgba(border_rgb),
            width=max(1, round(2 * scale)),
        )
        prog_img.save(progress_path, format="PNG")

        if media_size is None:
            # CTA Scene: tách Thẻ CTA (info_path) và Nút hành động (cta_btn_path) để bật nhịp liên tiếp
            cta_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            c_draw = ImageDraw.Draw(cta_img)
            cta_y = round(430 * scale)
            cta_h = round(760 * scale)
            _draw_offset_box(
                c_draw,
                (pad_x, cta_y, content_w, cta_h),
                fill=card_rgb,
                border=border_rgb,
                shadow=shadow_rgb,
                border_w=card_border_px,
                shadow_dx=shadow_lg,
                shadow_dy=shadow_lg,
                radius=round(16 * scale),
            )
            ribbon_h = round(24 * scale)
            c_draw.rectangle(
                (
                    pad_x + card_border_px,
                    cta_y + card_border_px,
                    pad_x + content_w - card_border_px,
                    cta_y + card_border_px + ribbon_h,
                ),
                fill=_rgba(accent_rgb),
            )
            font_badge = _load_font(round(28 * scale), bold=True)
            b_text = (badge or "TRẢI NGHIỆM").upper()
            b_w = int(c_draw.textlength(b_text, font=font_badge)) + round(52 * scale)
            b_h = round(54 * scale)
            b_x = (width - b_w) // 2
            b_y = cta_y - b_h // 2
            _draw_offset_box(
                c_draw,
                (b_x, b_y, b_w, b_h),
                fill=badge_bg_rgb,
                border=border_rgb,
                shadow=shadow_rgb,
                border_w=border_px,
                shadow_dx=shadow_sm,
                shadow_dy=shadow_sm,
                radius=round(8 * scale),
            )
            c_draw.text(
                (b_x + b_w // 2, b_y + b_h // 2),
                b_text,
                font=font_badge,
                fill=_rgba(badge_fg_rgb),
                anchor="mm",
            )

            font_cta = _load_font(round(56 * scale), bold=True)
            cta_lines = _wrap_text(c_draw, headline, font_cta, content_w - round(96 * scale), 3)
            line_h = round(72 * scale)
            text_top = cta_y + round(140 * scale)
            for idx, line in enumerate(cta_lines):
                c_draw.text(
                    (width // 2, text_top + idx * line_h),
                    line,
                    font=font_cta,
                    fill=_rgba(card_ink),
                    anchor="ma",
                )

            font_sub = _load_font(round(30 * scale), bold=False)
            sub_lines = _wrap_text(
                c_draw, highlights[0], font_sub, content_w - round(110 * scale), 2
            )
            sub_y = text_top + len(cta_lines) * line_h + round(26 * scale)
            for idx, line in enumerate(sub_lines):
                c_draw.text(
                    (width // 2, sub_y + idx * round(42 * scale)),
                    line,
                    font=font_sub,
                    fill=_rgba(card_muted),
                    anchor="ma",
                )
            cta_img.save(info_path, format="PNG")

            btn_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            b_draw = ImageDraw.Draw(btn_img)
            btn_font = _load_font(round(32 * scale), bold=True)
            btn_text = f"Khám phá {product_name[:18]}  →"
            btn_w = min(
                content_w - round(100 * scale),
                int(b_draw.textlength(btn_text, font=btn_font)) + round(84 * scale),
            )
            btn_h = round(84 * scale)
            btn_x = (width - btn_w) // 2
            btn_y = cta_y + cta_h - round(170 * scale)
            _draw_offset_box(
                b_draw,
                (btn_x, btn_y, btn_w, btn_h),
                fill=badge_bg_rgb,
                border=border_rgb,
                shadow=shadow_rgb,
                border_w=border_px,
                shadow_dx=shadow_sm,
                shadow_dy=shadow_sm,
                radius=round(12 * scale),
            )
            b_draw.text(
                (btn_x + btn_w // 2, btn_y + btn_h // 2),
                btn_text,
                font=btn_font,
                fill=_rgba(badge_fg_rgb),
                anchor="mm",
            )
            font_dom = _load_font(round(24 * scale), bold=True)
            b_draw.text(
                (width // 2, cta_y + cta_h - round(46 * scale)),
                domain,
                font=font_dom,
                fill=_rgba(card_muted),
                anchor="mm",
            )
            btn_img.save(cta_btn_path, format="PNG")

            return CanvasLayers(
                bg_path=bg_path,
                title_path=None,
                browser_path=None,
                info_path=info_path,
                cta_btn_path=cta_btn_path,
                progress_path=progress_path,
                progress_box=active_seg_box,
                media_box=None,
                card_box=None,
                border_px=card_border_px,
            )

        # Layer 2: Title Card + Floating Badge (trượt từ trên xuống)
        title_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        t_draw = ImageDraw.Draw(title_img)
        title_card_y = round(218 * scale)
        title_card_h = round(220 * scale)
        _draw_offset_box(
            t_draw,
            (pad_x, title_card_y, content_w, title_card_h),
            fill=card_rgb,
            border=border_rgb,
            shadow=shadow_rgb,
            border_w=border_px,
            shadow_dx=shadow_md,
            shadow_dy=shadow_md,
            radius=round(12 * scale),
        )
        stripe_w = round(16 * scale)
        t_draw.rectangle(
            (
                pad_x + border_px,
                title_card_y + border_px,
                pad_x + border_px + stripe_w,
                title_card_y + title_card_h - border_px,
            ),
            fill=_rgba(accent_rgb),
        )
        font_badge = _load_font(round(24 * scale), bold=True)
        b_text = (badge or "ĐIỂM NỔI BẬT").upper()
        b_w = int(t_draw.textlength(b_text, font=font_badge)) + round(44 * scale)
        b_h = round(48 * scale)
        b_x = pad_x + round(32 * scale)
        b_y = title_card_y - round(26 * scale)
        _draw_offset_box(
            t_draw,
            (b_x, b_y, b_w, b_h),
            fill=badge_bg_rgb,
            border=border_rgb,
            shadow=shadow_rgb,
            border_w=max(2, round(3.5 * scale)),
            shadow_dx=max(3, round(5 * scale)),
            shadow_dy=max(3, round(5 * scale)),
            radius=round(8 * scale),
        )
        t_draw.text(
            (b_x + b_w // 2, b_y + b_h // 2),
            b_text,
            font=font_badge,
            fill=_rgba(badge_fg_rgb),
            anchor="mm",
        )

        hl_max_w = content_w - round(76 * scale)
        font_hl = _load_font(round(48 * scale), bold=True)
        hl_lines = _wrap_text(t_draw, headline, font_hl, hl_max_w, 2)
        if len(hl_lines) == 2 and t_draw.textlength(hl_lines[1], font=font_hl) > hl_max_w * 0.94:
            font_hl = _load_font(round(42 * scale), bold=True)
            hl_lines = _wrap_text(t_draw, headline, font_hl, hl_max_w, 2)
        hl_lh = round(58 * scale)
        hl_total_h = len(hl_lines) * hl_lh
        hl_start_y = (
            title_card_y
            + round(22 * scale)
            + max(0, (title_card_h - round(32 * scale) - hl_total_h) // 2)
        )
        for idx, line in enumerate(hl_lines):
            t_draw.text(
                (pad_x + border_px + stripe_w + round(28 * scale), hl_start_y + idx * hl_lh),
                line,
                font=font_hl,
                fill=_rgba(card_ink),
                anchor="la",
            )
        title_img.save(title_path, format="PNG")

        # Layer 3: Browser Card Shell (trượt từ dưới lên đồng bộ cùng video/ảnh web)
        browser_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        br_draw = ImageDraw.Draw(browser_img)
        src_w, src_h = media_size
        bar_h = round(54 * scale)
        max_media_w = content_w - card_border_px * 2
        max_media_h = round(556 * scale)
        fit_scale = min(max_media_w / max(1, src_w), max_media_h / max(1, src_h))
        fit_w = max(2, int(round(src_w * fit_scale)) // 2 * 2)
        fit_h = max(2, int(round(src_h * fit_scale)) // 2 * 2)
        card_w = fit_w + card_border_px * 2
        card_h = bar_h + fit_h + card_border_px * 2
        card_x = (width - card_w) // 2
        card_y = round(488 * scale) + max(0, (round(616 * scale) - card_h) // 2)

        _draw_offset_box(
            br_draw,
            (card_x, card_y, card_w, card_h),
            fill=card_rgb,
            border=border_rgb,
            shadow=shadow_rgb,
            border_w=card_border_px,
            shadow_dx=shadow_lg,
            shadow_dy=shadow_lg,
            radius=0,
        )
        bar_bg = (
            _mix(card_rgb, border_rgb, 0.05)
            if is_light_card
            else _mix(card_rgb, (255, 255, 255), 0.06)
        )
        br_draw.rectangle(
            (
                card_x + card_border_px,
                card_y + card_border_px,
                card_x + card_w - card_border_px,
                card_y + card_border_px + bar_h,
            ),
            fill=_rgba(bar_bg),
        )
        dot_d = round(14 * scale)
        dot_y = card_y + card_border_px + (bar_h - dot_d) // 2
        for di, dcol in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
            dx = card_x + card_border_px + round(22 * scale) + di * (dot_d + round(10 * scale))
            br_draw.ellipse((dx, dot_y, dx + dot_d, dot_y + dot_d), fill=_rgba(dcol))
        url_w = round(card_w * 0.48)
        url_h = round(32 * scale)
        url_x = card_x + (card_w - url_w) // 2
        url_y = card_y + card_border_px + (bar_h - url_h) // 2
        br_draw.rounded_rectangle(
            (url_x, url_y, url_x + url_w, url_y + url_h),
            radius=url_h // 2,
            fill=_rgba(card_rgb),
            outline=_rgba(_mix(border_rgb, card_rgb, 0.72)),
            width=max(1, round(2 * scale)),
        )
        font_url = _load_font(round(19 * scale), bold=False)
        br_draw.text(
            (url_x + url_w // 2, url_y + url_h // 2),
            domain,
            font=font_url,
            fill=_rgba(card_muted),
            anchor="mm",
        )
        tag_text = "DEMO CLIP" if is_video_media else "TRANG THẬT"
        font_tag = _load_font(round(17 * scale), bold=True)
        tag_w = int(br_draw.textlength(tag_text, font=font_tag)) + round(24 * scale)
        tag_h = round(28 * scale)
        tag_x = card_x + card_w - card_border_px - tag_w - round(16 * scale)
        tag_y = card_y + card_border_px + (bar_h - tag_h) // 2
        br_draw.rounded_rectangle(
            (tag_x, tag_y, tag_x + tag_w, tag_y + tag_h),
            radius=round(6 * scale),
            fill=_rgba(badge_bg_rgb),
        )
        br_draw.text(
            (tag_x + tag_w // 2, tag_y + tag_h // 2),
            tag_text,
            font=font_tag,
            fill=_rgba(badge_fg_rgb),
            anchor="mm",
        )
        media_x = card_x + card_border_px
        media_y = card_y + card_border_px + bar_h
        br_draw.rectangle(
            (card_x, media_y - max(2, round(3 * scale)), card_x + card_w, media_y),
            fill=_rgba(border_rgb),
        )
        browser_img.save(browser_path, format="PNG")

        # Layer 4: Key Takeaways Card (bật trễ nhịp từ dưới lên)
        info_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        i_draw = ImageDraw.Draw(info_img)
        info_y = card_y + card_h + round(44 * scale)
        font_pt = _load_font(round(29 * scale), bold=True)
        wrapped_pts = [
            _wrap_text(i_draw, pt, font_pt, content_w - round(118 * scale), 2)
            for pt in highlights[:2]
        ]
        rows_h = sum(
            max(round(56 * scale), len(lines) * round(38 * scale) + round(16 * scale))
            for lines in wrapped_pts
        )
        info_h = min(round(106 * scale) + rows_h + round(22 * scale), round(1525 * scale) - info_y)
        info_fill = (
            _mix(card_rgb, accent_rgb, 0.06) if is_light_card else _mix(card_rgb, accent_rgb, 0.12)
        )
        _draw_offset_box(
            i_draw,
            (pad_x, info_y, content_w, info_h),
            fill=info_fill,
            border=border_rgb,
            shadow=shadow_rgb,
            border_w=border_px,
            shadow_dx=shadow_md,
            shadow_dy=shadow_md,
            radius=round(12 * scale),
        )
        font_kicker = _load_font(round(21 * scale), bold=True)
        kicker_y = info_y + round(26 * scale)
        dm_cx = pad_x + round(38 * scale)
        dm_cy = kicker_y + round(12 * scale)
        dm_r = round(9 * scale)
        i_draw.polygon(
            [
                (dm_cx, dm_cy - dm_r),
                (dm_cx + dm_r, dm_cy),
                (dm_cx, dm_cy + dm_r),
                (dm_cx - dm_r, dm_cy),
            ],
            fill=_rgba(accent_rgb),
        )
        i_draw.text(
            (dm_cx + round(20 * scale), kicker_y),
            "ĐIỂM NỔI BẬT",
            font=font_kicker,
            fill=_rgba(accent_rgb),
            anchor="la",
        )
        div_y = kicker_y + round(36 * scale)
        i_draw.line(
            (pad_x + round(28 * scale), div_y, pad_x + content_w - round(28 * scale), div_y),
            fill=_rgba(_mix(border_rgb, info_fill, 0.78)),
            width=max(1, round(2 * scale)),
        )

        pt_y = div_y + round(24 * scale)
        check_size = round(36 * scale)
        chk_w = max(3, round(4.2 * scale))
        for pt_lines in wrapped_pts:
            cx = pad_x + round(28 * scale)
            cy = pt_y + round(2 * scale)
            i_draw.rounded_rectangle(
                (cx, cy, cx + check_size, cy + check_size),
                radius=round(7 * scale),
                fill=_rgba(badge_bg_rgb),
                outline=_rgba(border_rgb),
                width=max(2, round(2.5 * scale)),
            )
            i_draw.line(
                [
                    (cx + round(check_size * 0.24), cy + round(check_size * 0.52)),
                    (cx + round(check_size * 0.44), cy + round(check_size * 0.72)),
                    (cx + round(check_size * 0.78), cy + round(check_size * 0.30)),
                ],
                fill=_rgba(badge_fg_rgb),
                width=chk_w,
                joint="curve",
            )
            for li, pl in enumerate(pt_lines):
                i_draw.text(
                    (cx + check_size + round(18 * scale), pt_y + li * round(37 * scale)),
                    pl,
                    font=font_pt,
                    fill=_rgba(card_ink),
                    anchor="la",
                )
            pt_y += max(round(56 * scale), len(pt_lines) * round(38 * scale) + round(16 * scale))
        info_img.save(info_path, format="PNG")

        return CanvasLayers(
            bg_path=bg_path,
            title_path=title_path,
            browser_path=browser_path,
            info_path=info_path,
            cta_btn_path=None,
            progress_path=progress_path,
            progress_box=active_seg_box,
            media_box=(media_x, media_y, fit_w, fit_h),
            card_box=(card_x, card_y, card_w, card_h),
            border_px=card_border_px,
        )

    # --- LANDSCAPE 16:9 ---
    pad_x = round(54 * scale)
    top_y = round(38 * scale)
    pill_h = round(48 * scale)
    font_pill = _load_font(round(22 * scale), bold=True)
    brand_w = int(bg_draw.textlength(domain, font=font_pill)) + round(64 * scale)
    _draw_offset_box(
        bg_draw,
        (pad_x, top_y, brand_w, pill_h),
        fill=card_rgb,
        border=border_rgb,
        shadow=shadow_rgb,
        border_w=max(2, round(3 * scale)),
        shadow_dx=shadow_sm,
        shadow_dy=shadow_sm,
        radius=round(9 * scale),
    )
    dot_r = round(7 * scale)
    bg_draw.ellipse(
        (
            pad_x + round(20 * scale) - dot_r,
            top_y + pill_h // 2 - dot_r,
            pad_x + round(20 * scale) + dot_r,
            top_y + pill_h // 2 + dot_r,
        ),
        fill=accent_rgb,
    )
    bg_draw.text(
        (pad_x + round(36 * scale), top_y + pill_h // 2),
        domain,
        font=font_pill,
        fill=card_ink,
        anchor="lm",
    )

    step_label = f"{scene_index:02d} / {scene_total:02d}"
    step_w = int(bg_draw.textlength(step_label, font=font_pill)) + round(40 * scale)
    step_x = width - pad_x - step_w
    _draw_offset_box(
        bg_draw,
        (step_x, top_y, step_w, pill_h),
        fill=badge_bg_rgb,
        border=border_rgb,
        shadow=shadow_rgb,
        border_w=max(2, round(3 * scale)),
        shadow_dx=shadow_sm,
        shadow_dy=shadow_sm,
        radius=round(9 * scale),
    )
    bg_draw.text(
        (step_x + step_w // 2, top_y + pill_h // 2),
        step_label,
        font=font_pill,
        fill=badge_fg_rgb,
        anchor="mm",
    )
    bg_img.save(bg_path, format="PNG")

    if media_size is None:
        cta_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        c_draw = ImageDraw.Draw(cta_img)
        cta_w = round(width * 0.66)
        cta_h = round(height * 0.56)
        cta_x = (width - cta_w) // 2
        cta_y = round(height * 0.18)
        _draw_offset_box(
            c_draw,
            (cta_x, cta_y, cta_w, cta_h),
            fill=card_rgb,
            border=border_rgb,
            shadow=shadow_rgb,
            border_w=card_border_px,
            shadow_dx=shadow_lg,
            shadow_dy=shadow_lg,
            radius=round(14 * scale),
        )
        c_draw.rectangle(
            (
                cta_x + card_border_px,
                cta_y + card_border_px,
                cta_x + cta_w - card_border_px,
                cta_y + card_border_px + round(20 * scale),
            ),
            fill=_rgba(accent_rgb),
        )
        font_cta = _load_font(round(52 * scale), bold=True)
        for idx, line in enumerate(
            _wrap_text(c_draw, headline, font_cta, cta_w - round(100 * scale), 2)
        ):
            c_draw.text(
                (width // 2, cta_y + round(140 * scale) + idx * round(64 * scale)),
                line,
                font=font_cta,
                fill=_rgba(card_ink),
                anchor="ma",
            )
        cta_img.save(info_path, format="PNG")

        btn_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        b_draw = ImageDraw.Draw(btn_img)
        btn_font = _load_font(round(28 * scale), bold=True)
        btn_text = f"Khám phá {product_name[:20]}  →"
        btn_w = int(b_draw.textlength(btn_text, font=btn_font)) + round(72 * scale)
        btn_h = round(72 * scale)
        btn_x = (width - btn_w) // 2
        btn_y = cta_y + cta_h - round(130 * scale)
        _draw_offset_box(
            b_draw,
            (btn_x, btn_y, btn_w, btn_h),
            fill=badge_bg_rgb,
            border=border_rgb,
            shadow=shadow_rgb,
            border_w=border_px,
            shadow_dx=shadow_sm,
            shadow_dy=shadow_sm,
            radius=round(10 * scale),
        )
        b_draw.text(
            (btn_x + btn_w // 2, btn_y + btn_h // 2),
            btn_text,
            font=btn_font,
            fill=_rgba(badge_fg_rgb),
            anchor="mm",
        )
        btn_img.save(cta_btn_path, format="PNG")
        return CanvasLayers(
            bg_path=bg_path,
            title_path=None,
            browser_path=None,
            info_path=info_path,
            cta_btn_path=cta_btn_path,
            progress_path=None,
            progress_box=None,
            media_box=None,
            card_box=None,
            border_px=card_border_px,
        )

    browser_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    br_draw = ImageDraw.Draw(browser_img)
    src_w, src_h = media_size
    bar_h = round(46 * scale)
    fit_scale = min(round(width * 0.56) / max(1, src_w), round(height * 0.62) / max(1, src_h))
    fit_w = max(2, int(round(src_w * fit_scale)) // 2 * 2)
    fit_h = max(2, int(round(src_h * fit_scale)) // 2 * 2)
    card_w = fit_w + card_border_px * 2
    card_h = bar_h + fit_h + card_border_px * 2
    card_x = pad_x
    card_y = round(145 * scale) + max(0, (round(height * 0.68) - card_h) // 2)
    _draw_offset_box(
        br_draw,
        (card_x, card_y, card_w, card_h),
        fill=card_rgb,
        border=border_rgb,
        shadow=shadow_rgb,
        border_w=card_border_px,
        shadow_dx=shadow_lg,
        shadow_dy=shadow_lg,
    )
    dot_d = round(12 * scale)
    dot_y = card_y + card_border_px + (bar_h - dot_d) // 2
    for di, dcol in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        dx = card_x + card_border_px + round(18 * scale) + di * (dot_d + round(8 * scale))
        br_draw.ellipse((dx, dot_y, dx + dot_d, dot_y + dot_d), fill=_rgba(dcol))
    media_x = card_x + card_border_px
    media_y = card_y + card_border_px + bar_h
    br_draw.rectangle(
        (card_x, media_y - max(2, round(3 * scale)), card_x + card_w, media_y),
        fill=_rgba(border_rgb),
    )
    browser_img.save(browser_path, format="PNG")

    right_x = card_x + card_w + round(44 * scale)
    right_w = width - pad_x - right_x
    title_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    t_draw = ImageDraw.Draw(title_img)
    t_y = card_y
    t_h = round(260 * scale)
    _draw_offset_box(
        t_draw,
        (right_x, t_y, right_w, t_h),
        fill=card_rgb,
        border=border_rgb,
        shadow=shadow_rgb,
        border_w=border_px,
        shadow_dx=shadow_md,
        shadow_dy=shadow_md,
        radius=round(12 * scale),
    )
    font_badge = _load_font(round(22 * scale), bold=True)
    b_text = (badge or "ĐIỂM NỔI BẬT").upper()
    b_w = int(t_draw.textlength(b_text, font=font_badge)) + round(36 * scale)
    b_h = round(42 * scale)
    _draw_offset_box(
        t_draw,
        (right_x + round(24 * scale), t_y - round(22 * scale), b_w, b_h),
        fill=badge_bg_rgb,
        border=border_rgb,
        shadow=shadow_rgb,
        border_w=max(2, round(3 * scale)),
        shadow_dx=4,
        shadow_dy=4,
        radius=round(7 * scale),
    )
    t_draw.text(
        (right_x + round(24 * scale) + b_w // 2, t_y - round(22 * scale) + b_h // 2),
        b_text,
        font=font_badge,
        fill=_rgba(badge_fg_rgb),
        anchor="mm",
    )
    font_hl = _load_font(round(40 * scale), bold=True)
    for idx, line in enumerate(
        _wrap_text(t_draw, headline, font_hl, right_w - round(52 * scale), 3)
    ):
        t_draw.text(
            (right_x + round(26 * scale), t_y + round(54 * scale) + idx * round(50 * scale)),
            line,
            font=font_hl,
            fill=_rgba(card_ink),
            anchor="la",
        )
    title_img.save(title_path, format="PNG")

    info_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    i_draw = ImageDraw.Draw(info_img)
    i_y = t_y + t_h + round(34 * scale)
    i_h = max(round(220 * scale), card_y + card_h - i_y)
    info_fill = (
        _mix(card_rgb, accent_rgb, 0.06) if is_light_card else _mix(card_rgb, accent_rgb, 0.12)
    )
    _draw_offset_box(
        i_draw,
        (right_x, i_y, right_w, i_h),
        fill=info_fill,
        border=border_rgb,
        shadow=shadow_rgb,
        border_w=border_px,
        shadow_dx=shadow_md,
        shadow_dy=shadow_md,
        radius=round(12 * scale),
    )
    font_pt = _load_font(round(24 * scale), bold=True)
    py = i_y + round(28 * scale)
    cs = round(26 * scale)
    for pt in highlights[:2]:
        cx = right_x + round(22 * scale)
        i_draw.rounded_rectangle(
            (cx, py + 2, cx + cs, py + 2 + cs),
            radius=round(5 * scale),
            fill=_rgba(badge_bg_rgb),
            outline=_rgba(border_rgb),
            width=2,
        )
        i_draw.line(
            [
                (cx + round(cs * 0.24), py + 2 + round(cs * 0.52)),
                (cx + round(cs * 0.44), py + 2 + round(cs * 0.72)),
                (cx + round(cs * 0.78), py + 2 + round(cs * 0.30)),
            ],
            fill=_rgba(badge_fg_rgb),
            width=3,
        )
        pt_lines = _wrap_text(i_draw, pt, font_pt, right_w - round(76 * scale), 2)
        for li, pl in enumerate(pt_lines):
            i_draw.text(
                (cx + cs + round(14 * scale), py + li * round(32 * scale)),
                pl,
                font=font_pt,
                fill=_rgba(card_ink),
                anchor="la",
            )
        py += max(round(56 * scale), len(pt_lines) * round(34 * scale) + round(14 * scale))
    info_img.save(info_path, format="PNG")

    return CanvasLayers(
        bg_path=bg_path,
        title_path=title_path,
        browser_path=browser_path,
        info_path=info_path,
        cta_btn_path=None,
        progress_path=None,
        progress_box=None,
        media_box=(media_x, media_y, fit_w, fit_h),
        card_box=(card_x, card_y, card_w, card_h),
        border_px=card_border_px,
    )
