"""Dựng các lớp đồ họa RGBA cho template `social-media` (phong cách flat vector pastel + bong bóng icon mạng xã hội bay nổi)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from worker.render.canvas import (
    _domain_label,
    _extract_highlights,
    _hex_rgb,
    _load_font,
    _mix,
    _rgba,
    _wrap_text,
)
from worker.render.design import contrast_text_for, relative_luminance


@dataclass(frozen=True)
class SocialCanvasLayers:
    bg_path: Path
    float_a_path: Path
    float_b_path: Path
    title_path: Path | None
    card_path: Path | None
    info_path: Path | None
    cta_btn_path: Path | None
    progress_path: Path | None
    progress_box: tuple[int, int, int, int] | None
    media_box: tuple[int, int, int, int] | None


def _draw_soft_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int],
    shadow_rgba: tuple[int, int, int, int],
    outline_rgba: tuple[int, int, int, int],
    radius: int,
    shadow_dy: int,
    outline_w: int = 2,
) -> None:
    x, y, w, h = box
    # 2 lớp bóng mềm pastel thay vì viền đen cứng kiểu brutalist.
    draw.rounded_rectangle(
        (x - 2, y + shadow_dy, x + w + 2, y + h + shadow_dy + 4),
        radius=radius + 2,
        fill=(shadow_rgba[0], shadow_rgba[1], shadow_rgba[2], max(18, shadow_rgba[3] // 2)),
    )
    draw.rounded_rectangle(
        (x + 2, y + max(2, shadow_dy // 2), x + w + 2, y + h + max(2, shadow_dy // 2) + 2),
        radius=radius,
        fill=shadow_rgba,
    )
    draw.rounded_rectangle(
        (x, y, x + w, y + h),
        radius=radius,
        fill=_rgba(fill),
        outline=outline_rgba,
        width=outline_w,
    )


def _draw_teardrop(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    r: int,
    angle_deg: float,
    *,
    fill: tuple[int, int, int, int] | None = None,
    outline: tuple[int, int, int, int] | None = None,
    width: int = 3,
) -> None:
    """Vẽ giọt nước / lá vector mềm kiểu minh họa editorial trong ảnh mẫu."""
    pts: list[tuple[float, float]] = []
    rad = math.radians(angle_deg)
    ca, sa = math.cos(rad), math.sin(rad)
    for i in range(36):
        t = (i / 36.0) * 2 * math.pi
        # Phương trình giọt nước mảnh nhọn một đầu
        lx = r * 0.72 * math.sin(t) * (1.0 - 0.35 * math.cos(t))
        ly = -r * math.cos(t)
        rx = cx + lx * ca - ly * sa
        ry = cy + lx * sa + ly * ca
        pts.append((rx, ry))
    draw.polygon(pts, fill=fill, outline=outline)
    if outline and width > 1:
        draw.line(pts + [pts[0]], fill=outline, width=width, joint="curve")


def _draw_social_badge_play(draw: ImageDraw.ImageDraw, cx: int, cy: int, s: int) -> None:
    """Nút Play đỏ (kiểu YouTube)."""
    w, h = round(s * 1.28), round(s * 0.90)
    x0, y0 = cx - w // 2, cy - h // 2
    draw.rounded_rectangle(
        (x0 + 3, y0 + 5, x0 + w + 3, y0 + h + 5), radius=round(h * 0.28), fill=(30, 32, 48, 36)
    )
    draw.rounded_rectangle(
        (x0, y0, x0 + w, y0 + h), radius=round(h * 0.28), fill=(239, 68, 68, 255)
    )
    tri_r = round(h * 0.26)
    draw.polygon(
        [(cx - tri_r * 0.55, cy - tri_r), (cx - tri_r * 0.55, cy + tri_r), (cx + tri_r * 1.05, cy)],
        fill=(255, 255, 255, 255),
    )


def _draw_social_badge_circle(
    draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: tuple[int, int, int], glyph: str
) -> None:
    """Huy hiệu tròn mạng xã hội (kiểu Facebook / Share / Verified)."""
    draw.ellipse((cx - r + 3, cy - r + 6, cx + r + 3, cy + r + 6), fill=(30, 32, 48, 36))
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_rgba(color))
    font = _load_font(round(r * 1.15), bold=True)
    draw.text((cx, cy + round(r * 0.04)), glyph, font=font, fill=(255, 255, 255, 255), anchor="mm")


def _draw_social_badge_camera(draw: ImageDraw.ImageDraw, cx: int, cy: int, s: int) -> None:
    """Huy hiệu vuông bo tròn kiểu Instagram (chuyển sắc san hô–tím gọn trong khung)."""
    half = s // 2
    x0, y0 = cx - half, cy - half
    rad = round(s * 0.28)
    draw.rounded_rectangle(
        (x0 + 3, y0 + 6, x0 + s + 3, y0 + s + 6), radius=rad, fill=(30, 32, 48, 36)
    )
    draw.rounded_rectangle((x0, y0, x0 + s, y0 + s), radius=rad, fill=(225, 48, 108, 255))
    draw.rounded_rectangle(
        (x0 + 3, y0 + round(s * 0.52), x0 + round(s * 0.56), y0 + s - 3),
        radius=round(s * 0.22),
        fill=(249, 115, 22, 165),
    )
    draw.rounded_rectangle(
        (x0, y0, x0 + s, y0 + s), radius=rad, outline=(255, 255, 255, 55), width=2
    )
    # Khung camera trắng bên trong
    in_m = round(s * 0.21)
    lw = max(3, round(s * 0.075))
    draw.rounded_rectangle(
        (x0 + in_m, y0 + in_m, x0 + s - in_m, y0 + s - in_m),
        radius=round(s * 0.16),
        outline=(255, 255, 255, 255),
        width=lw,
    )
    lr = round(s * 0.15)
    draw.ellipse((cx - lr, cy - lr, cx + lr, cy + lr), outline=(255, 255, 255, 255), width=lw)
    dr = max(2, round(s * 0.045))
    draw.ellipse(
        (x0 + s - in_m - dr * 3, y0 + in_m + dr, x0 + s - in_m - dr, y0 + in_m + dr * 3),
        fill=(255, 255, 255, 255),
    )


def _draw_social_badge_in(draw: ImageDraw.ImageDraw, cx: int, cy: int, s: int) -> None:
    """Huy hiệu vuông bo nhẹ màu xanh dương đậm (kiểu LinkedIn)."""
    half = s // 2
    x0, y0 = cx - half, cy - half
    rad = round(s * 0.18)
    draw.rounded_rectangle(
        (x0 + 3, y0 + 6, x0 + s + 3, y0 + s + 6), radius=rad, fill=(30, 32, 48, 36)
    )
    draw.rounded_rectangle((x0, y0, x0 + s, y0 + s), radius=rad, fill=(10, 102, 194, 255))
    font = _load_font(round(s * 0.56), bold=True)
    draw.text((cx, cy + round(s * 0.02)), "in", font=font, fill=(255, 255, 255, 255), anchor="mm")


def _draw_social_badge_heart(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int) -> None:
    """Bong bóng reaction tim san hô."""
    draw.ellipse((cx - r + 3, cy - r + 5, cx + r + 3, cy + r + 5), fill=(30, 32, 48, 30))
    draw.ellipse(
        (cx - r, cy - r, cx + r, cy + r),
        fill=(255, 255, 255, 255),
        outline=(255, 159, 137, 160),
        width=3,
    )
    hr = round(r * 0.34)
    # Trái tim vector gồm 2 hình tròn + 1 tam giác
    draw.ellipse(
        (cx - hr * 1.15, cy - hr * 0.85, cx + hr * 0.15, cy + hr * 0.45), fill=(244, 63, 94, 255)
    )
    draw.ellipse(
        (cx - hr * 0.15, cy - hr * 0.85, cx + hr * 1.15, cy + hr * 0.45), fill=(244, 63, 94, 255)
    )
    draw.polygon(
        [(cx - hr * 1.12, cy - hr * 0.05), (cx + hr * 1.12, cy - hr * 0.05), (cx, cy + hr * 1.15)],
        fill=(244, 63, 94, 255),
    )


def _draw_social_badge_spark(
    draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: tuple[int, int, int]
) -> None:
    """Huy hiệu tròn pastel có ngôi sao 4 cánh vector."""
    draw.ellipse((cx - r + 3, cy - r + 5, cx + r + 3, cy + r + 5), fill=(30, 32, 48, 28))
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_rgba(color))
    sr = round(r * 0.48)
    ir = round(sr * 0.32)
    pts = [
        (cx, cy - sr),
        (cx + ir, cy - ir),
        (cx + sr, cy),
        (cx + ir, cy + ir),
        (cx, cy + sr),
        (cx - ir, cy + ir),
        (cx - sr, cy),
        (cx - ir, cy - ir),
    ]
    draw.polygon(pts, fill=(255, 255, 255, 255))


def _draw_desk_accent(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    peach: tuple[int, int, int],
    indigo: tuple[int, int, int],
) -> None:
    """Đường nền bàn pastel + quả cầu indigo + chậu cây coral tối giản gợi đúng tinh thần ảnh mẫu."""
    # Đường sàn mảnh
    floor_y = y + h
    draw.line(
        (x, floor_y, x + w, floor_y), fill=(203, 213, 225, 190), width=max(2, round(h * 0.04))
    )
    # Quả cầu gradient xanh tím nhỏ bên trái
    orb_r = round(h * 0.28)
    orb_cx = x + round(w * 0.12)
    orb_cy = floor_y - orb_r - 2
    draw.ellipse(
        (orb_cx - orb_r, orb_cy - orb_r, orb_cx + orb_r, orb_cy + orb_r), fill=_rgba(indigo)
    )
    draw.chord(
        (orb_cx - orb_r, orb_cy - orb_r, orb_cx + orb_r, orb_cy + orb_r),
        start=25,
        end=155,
        fill=(30, 32, 64, 210),
    )
    # Chậu cây đỏ cam tối giản bên phải
    pot_w = round(h * 0.56)
    pot_h = round(h * 0.26)
    pot_x = x + round(w * 0.80)
    pot_y = floor_y - pot_h
    draw.rounded_rectangle(
        (pot_x, pot_y, pot_x + pot_w, floor_y), radius=round(pot_h * 0.35), fill=_rgba(peach)
    )
    stem_x = pot_x + pot_w // 2
    draw.line(
        (stem_x, pot_y, stem_x, pot_y - round(h * 0.52)),
        fill=(220, 38, 38, 220),
        width=max(3, round(h * 0.035)),
    )
    _draw_teardrop(
        draw,
        stem_x - round(h * 0.14),
        pot_y - round(h * 0.28),
        round(h * 0.16),
        -42,
        fill=(239, 68, 68, 240),
    )
    _draw_teardrop(
        draw,
        stem_x + round(h * 0.13),
        pot_y - round(h * 0.44),
        round(h * 0.15),
        38,
        fill=(220, 38, 38, 240),
    )


def build_social_media_layers(
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
) -> SocialCanvasLayers:
    """Sinh các lớp RGBA phong cách Social Media Flat Illustration (pastel, bóng mềm, icon bay nổi)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    is_portrait = height > width
    scale = (width / 1080.0) if is_portrait else (height / 1080.0)

    bg_rgb = _hex_rgb(bg_hex, "#F9F7F4")
    accent_rgb = _hex_rgb(accent_hex, "#5B5CE6")
    card_rgb = _hex_rgb(card_hex, "#FFFFFF")
    is_light_bg = relative_luminance(f"#{bg_hex}") > 0.42
    is_light_card = relative_luminance(f"#{card_hex}") > 0.42

    lavender_rgb = _mix(accent_rgb, (196, 192, 255), 0.58)
    peach_rgb = (255, 166, 146)
    ink_rgb = (30, 32, 48) if is_light_bg else (248, 250, 252)
    card_ink = (30, 32, 48) if is_light_card else (248, 250, 252)
    card_muted = _mix(card_ink, card_rgb, 0.42)
    soft_shadow = (*_mix(accent_rgb, (30, 32, 48), 0.55), 34 if is_light_bg else 90)
    soft_outline = (*_mix(accent_rgb, ink_rgb, 0.25), 42 if is_light_bg else 75)

    badge_bg_hex = accent_hex if relative_luminance(f"#{accent_hex}") < 0.65 else "5B5CE6"
    badge_bg_rgb = _hex_rgb(badge_bg_hex)
    badge_fg_rgb = _hex_rgb(contrast_text_for(f"#{badge_bg_hex}"))

    domain = _domain_label(website_url, product_name)
    highlights = _extract_highlights(scene, override, narration, headline)

    bg_path = output_dir / f"{scene_id}_sm_bg.png"
    float_a_path = output_dir / f"{scene_id}_sm_fa.png"
    float_b_path = output_dir / f"{scene_id}_sm_fb.png"
    title_path = output_dir / f"{scene_id}_sm_title.png"
    card_path = output_dir / f"{scene_id}_sm_card.png"
    info_path = output_dir / f"{scene_id}_sm_info.png"
    cta_btn_path = output_dir / f"{scene_id}_sm_ctabtn.png"
    progress_path = output_dir / f"{scene_id}_sm_prog.png"

    # 1. NỀN PASTEL + HỌA TIẾT GIỌT NƯỚC / BLOB MỀM (kiểu ảnh minh họa)
    bg_img = Image.new("RGB", (width, height), bg_rgb)
    bg_draw = ImageDraw.Draw(bg_img, "RGBA")

    # Vòng pastel lớn cực mềm ở nền sau
    bg_draw.ellipse(
        (-round(180 * scale), round(380 * scale), round(460 * scale), round(1020 * scale)),
        fill=(*lavender_rgb, 56 if is_light_bg else 34),
    )
    bg_draw.ellipse(
        (
            width - round(420 * scale),
            round(860 * scale),
            width + round(180 * scale),
            round(1460 * scale),
        ),
        fill=(*peach_rgb, 52 if is_light_bg else 32),
    )
    # Giọt nước đặc màu lavender góc trên trái & cụm 2 giọt góc dưới phải + giọt viền coral góc dưới trái (giống ảnh mẫu!)
    _draw_teardrop(
        bg_draw,
        round(92 * scale),
        round(220 * scale),
        round(42 * scale),
        135,
        fill=(*lavender_rgb, 175),
    )
    _draw_teardrop(
        bg_draw,
        round(86 * scale),
        height - round(155 * scale),
        round(42 * scale),
        0,
        fill=None,
        outline=(*peach_rgb, 210),
        width=max(2, round(3.5 * scale)),
    )
    _draw_teardrop(
        bg_draw,
        width - round(92 * scale),
        height - round(130 * scale),
        round(40 * scale),
        -48,
        fill=(*lavender_rgb, 185),
    )
    _draw_teardrop(
        bg_draw,
        width - round(112 * scale),
        height - round(136 * scale),
        round(40 * scale),
        -48,
        fill=None,
        outline=(*accent_rgb, 145),
        width=max(2, round(3 * scale)),
    )

    # 2. LỚP BONG BÓNG MẠNG XÃ HỘI BAY NỔI (2 lớp A/B bob lệch pha mượt 30fps!)
    fa_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    fa_draw = ImageDraw.Draw(fa_img)
    fb_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    fb_draw = ImageDraw.Draw(fb_img)

    if is_portrait:
        # Cụm icon bay quanh vùng tiêu đề & khung web (đặt thoáng ở mép, không đè chữ/chip)
        _draw_social_badge_circle(
            fa_draw,
            width - round(112 * scale),
            round(224 * scale),
            round(38 * scale),
            (24, 119, 242),
            "f",
        )
        _draw_social_badge_play(fb_draw, round(98 * scale), round(456 * scale), round(52 * scale))
        _draw_social_badge_camera(
            fa_draw, width - round(94 * scale), round(454 * scale), round(64 * scale)
        )
        _draw_social_badge_in(
            fb_draw, width - round(94 * scale), round(1130 * scale), round(58 * scale)
        )
        _draw_social_badge_heart(
            fa_draw, round(106 * scale), round(1542 * scale), round(34 * scale)
        )
        _draw_social_badge_spark(
            fb_draw,
            width - round(108 * scale),
            round(1545 * scale),
            round(28 * scale),
            (245, 158, 11),
        )
    else:
        _draw_social_badge_circle(
            fa_draw,
            width - round(115 * scale),
            round(170 * scale),
            round(34 * scale),
            (24, 119, 242),
            "f",
        )
        _draw_social_badge_camera(
            fb_draw, width - round(190 * scale), round(130 * scale), round(54 * scale)
        )
        _draw_social_badge_in(
            fa_draw, width - round(95 * scale), round(860 * scale), round(52 * scale)
        )
        _draw_social_badge_play(fb_draw, round(92 * scale), round(860 * scale), round(48 * scale))
        _draw_social_badge_heart(fa_draw, round(170 * scale), round(140 * scale), round(28 * scale))

    fa_img.save(float_a_path, format="PNG")
    fb_img.save(float_b_path, format="PNG")

    if is_portrait:
        pad_x = round(58 * scale)
        content_w = width - pad_x * 2

        # Thanh Stories Progress trên cùng
        seg_y = round(48 * scale)
        seg_h = max(7, round(10 * scale))
        seg_gap = round(10 * scale)
        seg_w = (content_w - seg_gap * max(0, scene_total - 1)) // max(1, scene_total)
        active_seg_box: tuple[int, int, int, int] | None = None
        for i in range(scene_total):
            sx = pad_x + i * (seg_w + seg_gap)
            completed = i < scene_index - 1
            seg_fill = _rgba(accent_rgb) if completed else (*ink_rgb, 34)
            bg_draw.rounded_rectangle(
                (sx, seg_y, sx + seg_w, seg_y + seg_h), radius=seg_h // 2, fill=seg_fill
            )
            if i == scene_index - 1:
                active_seg_box = (sx, seg_y, seg_w, seg_h)

        # Header kiểu Social Story: Avatar vòng tròn + @domain + Verified + Step pill
        head_y = seg_y + seg_h + round(24 * scale)
        av_r = round(30 * scale)
        av_cx = pad_x + av_r
        av_cy = head_y + av_r
        bg_draw.ellipse(
            (av_cx - av_r - 3, av_cy - av_r - 3, av_cx + av_r + 3, av_cy + av_r + 3),
            fill=_rgba(peach_rgb),
        )
        bg_draw.ellipse(
            (av_cx - av_r, av_cy - av_r, av_cx + av_r, av_cy + av_r), fill=_rgba(badge_bg_rgb)
        )
        font_av = _load_font(round(28 * scale), bold=True)
        initial = (product_name or domain or "R")[0].upper()
        bg_draw.text((av_cx, av_cy), initial, font=font_av, fill=_rgba(badge_fg_rgb), anchor="mm")

        font_handle = _load_font(round(26 * scale), bold=True)
        handle_text = f"@{domain}"
        hx = av_cx + av_r + round(16 * scale)
        bg_draw.text(
            (hx, av_cy - round(10 * scale)),
            handle_text,
            font=font_handle,
            fill=_rgba(ink_rgb),
            anchor="lm",
        )
        font_sub_h = _load_font(round(19 * scale), bold=False)
        bg_draw.text(
            (hx, av_cy + round(16 * scale)),
            "Social Review · Đã xác minh",
            font=font_sub_h,
            fill=(*ink_rgb, 155),
            anchor="lm",
        )

        # Tick xanh verified cạnh handle
        vx = hx + int(bg_draw.textlength(handle_text, font=font_handle)) + round(18 * scale)
        vy = av_cy - round(10 * scale)
        vr = round(12 * scale)
        bg_draw.ellipse((vx - vr, vy - vr, vx + vr, vy + vr), fill=(29, 155, 240, 255))
        bg_draw.line(
            [(vx - 5, vy), (vx - 1, vy + 4), (vx + 6, vy - 4)],
            fill=(255, 255, 255, 255),
            width=max(2, round(2.8 * scale)),
        )

        step_label = f"{scene_index:02d} / {scene_total:02d}"
        font_step = _load_font(round(22 * scale), bold=True)
        st_w = int(bg_draw.textlength(step_label, font=font_step)) + round(34 * scale)
        st_h = round(44 * scale)
        bg_draw.rounded_rectangle(
            (width - pad_x - st_w, av_cy - st_h // 2, width - pad_x, av_cy + st_h // 2),
            radius=st_h // 2,
            fill=(*lavender_rgb, 130),
        )
        bg_draw.text(
            (width - pad_x - st_w // 2, av_cy),
            step_label,
            font=font_step,
            fill=_rgba(ink_rgb),
            anchor="mm",
        )
        bg_img.save(bg_path, format="PNG")

        # Active progress fill
        prog_img = Image.new("RGBA", (seg_w, seg_h), (0, 0, 0, 0))
        p_draw = ImageDraw.Draw(prog_img)
        p_draw.rounded_rectangle(
            (0, 0, seg_w - 1, seg_h - 1), radius=seg_h // 2, fill=_rgba(accent_rgb)
        )
        prog_img.save(progress_path, format="PNG")

        if media_size is None:
            # CTA Card mềm kiểu minh họa Social Media
            cta_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            c_draw = ImageDraw.Draw(cta_img)
            cta_y = round(420 * scale)
            cta_h = round(760 * scale)
            _draw_soft_card(
                c_draw,
                (pad_x, cta_y, content_w, cta_h),
                fill=card_rgb,
                shadow_rgba=soft_shadow,
                outline_rgba=soft_outline,
                radius=round(30 * scale),
                shadow_dy=round(18 * scale),
            )
            # Dải trang trí bàn pastel + chậu cây mini ở đáy thẻ CTA
            _draw_desk_accent(
                c_draw,
                pad_x + round(44 * scale),
                cta_y + cta_h - round(155 * scale),
                content_w - round(88 * scale),
                round(120 * scale),
                peach_rgb,
                accent_rgb,
            )

            font_badge = _load_font(round(24 * scale), bold=True)
            b_text = f"#  {(badge or 'TRẢI NGHIỆM').upper()}"
            b_w = int(c_draw.textlength(b_text, font=font_badge)) + round(44 * scale)
            b_h = round(48 * scale)
            b_x = (width - b_w) // 2
            b_y = cta_y + round(56 * scale)
            c_draw.rounded_rectangle(
                (b_x, b_y, b_x + b_w, b_y + b_h), radius=b_h // 2, fill=(*lavender_rgb, 145)
            )
            c_draw.text(
                (b_x + b_w // 2, b_y + b_h // 2),
                b_text,
                font=font_badge,
                fill=_rgba(accent_rgb if is_light_card else badge_fg_rgb),
                anchor="mm",
            )

            font_cta = _load_font(round(54 * scale), bold=True)
            cta_lines = _wrap_text(c_draw, headline, font_cta, content_w - round(96 * scale), 3)
            line_h = round(70 * scale)
            text_top = b_y + b_h + round(44 * scale)
            for idx, line in enumerate(cta_lines):
                c_draw.text(
                    (width // 2, text_top + idx * line_h),
                    line,
                    font=font_cta,
                    fill=_rgba(card_ink),
                    anchor="ma",
                )

            font_sub = _load_font(round(28 * scale), bold=False)
            sub_y = text_top + len(cta_lines) * line_h + round(22 * scale)
            for idx, line in enumerate(
                _wrap_text(c_draw, highlights[0], font_sub, content_w - round(110 * scale), 2)
            ):
                c_draw.text(
                    (width // 2, sub_y + idx * round(38 * scale)),
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
                content_w - round(120 * scale),
                int(b_draw.textlength(btn_text, font=btn_font)) + round(88 * scale),
            )
            btn_h = round(84 * scale)
            btn_x = (width - btn_w) // 2
            btn_y = cta_y + cta_h - round(235 * scale)
            _draw_soft_card(
                b_draw,
                (btn_x, btn_y, btn_w, btn_h),
                fill=badge_bg_rgb,
                shadow_rgba=(*badge_bg_rgb, 80),
                outline_rgba=(255, 255, 255, 40),
                radius=btn_h // 2,
                shadow_dy=round(10 * scale),
            )
            b_draw.text(
                (btn_x + btn_w // 2, btn_y + btn_h // 2),
                btn_text,
                font=btn_font,
                fill=_rgba(badge_fg_rgb),
                anchor="mm",
            )
            btn_img.save(cta_btn_path, format="PNG")

            return SocialCanvasLayers(
                bg_path=bg_path,
                float_a_path=float_a_path,
                float_b_path=float_b_path,
                title_path=None,
                card_path=None,
                info_path=info_path,
                cta_btn_path=cta_btn_path,
                progress_path=progress_path,
                progress_box=active_seg_box,
                media_box=None,
            )

        # Layer Title (nhẹ nhàng, không viền cứng, pill badge pastel + nét nhấn san hô mềm)
        title_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        t_draw = ImageDraw.Draw(title_img)
        badge_y = round(200 * scale)
        font_badge = _load_font(round(23 * scale), bold=True)
        b_text = f"#  {(badge or 'ĐIỂM NỔI BẬT').upper()}"
        b_w = int(t_draw.textlength(b_text, font=font_badge)) + round(44 * scale)
        b_h = round(46 * scale)
        b_x = pad_x
        t_draw.rounded_rectangle(
            (b_x, badge_y, b_x + b_w, badge_y + b_h), radius=b_h // 2, fill=_rgba(badge_bg_rgb)
        )
        t_draw.text(
            (b_x + b_w // 2, badge_y + b_h // 2),
            b_text,
            font=font_badge,
            fill=_rgba(badge_fg_rgb),
            anchor="mm",
        )

        hl_max_w = content_w - round(90 * scale)
        font_hl = _load_font(round(52 * scale), bold=True)
        hl_lines = _wrap_text(t_draw, headline, font_hl, hl_max_w, 2)
        if len(hl_lines) == 2 and t_draw.textlength(hl_lines[1], font=font_hl) > hl_max_w * 0.94:
            font_hl = _load_font(round(45 * scale), bold=True)
            hl_lines = _wrap_text(t_draw, headline, font_hl, hl_max_w, 2)
        hl_y = badge_y + b_h + round(22 * scale)
        hl_lh = round(64 * scale)
        # Vệt highlight màu đào mềm phía sau dòng chữ cuối
        if hl_lines:
            last_w = min(hl_max_w, int(t_draw.textlength(hl_lines[-1], font=font_hl)))
            ly_bar = hl_y + (len(hl_lines) - 1) * hl_lh + round(36 * scale)
            t_draw.rounded_rectangle(
                (
                    pad_x - round(4 * scale),
                    ly_bar,
                    pad_x + last_w + round(8 * scale),
                    ly_bar + round(22 * scale),
                ),
                radius=round(11 * scale),
                fill=(*peach_rgb, 145 if is_light_bg else 95),
            )
        for idx, line in enumerate(hl_lines):
            t_draw.text(
                (pad_x, hl_y + idx * hl_lh), line, font=font_hl, fill=_rgba(ink_rgb), anchor="la"
            )
        title_img.save(title_path, format="PNG")

        # Layer Card trình chiếu sản phẩm bo góc mềm + bóng lavender
        card_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        cd_draw = ImageDraw.Draw(card_img)
        src_w, src_h = media_size
        pad_in = round(14 * scale)
        bar_h = round(50 * scale)
        max_media_w = content_w - pad_in * 2
        max_media_h = round(540 * scale)
        fit_scale = min(max_media_w / max(1, src_w), max_media_h / max(1, src_h))
        fit_w = max(2, int(round(src_w * fit_scale)) // 2 * 2)
        fit_h = max(2, int(round(src_h * fit_scale)) // 2 * 2)
        card_w = fit_w + pad_in * 2
        card_h = bar_h + fit_h + pad_in * 2
        card_x = (width - card_w) // 2
        card_y = round(486 * scale) + max(0, (round(608 * scale) - card_h) // 2)

        # Khối màu đào/lavender lệch nhẹ phía sau tạo tầng chiều sâu
        cd_draw.rounded_rectangle(
            (
                card_x + round(18 * scale),
                card_y - round(16 * scale),
                card_x + card_w + round(14 * scale),
                card_y + round(120 * scale),
            ),
            radius=round(26 * scale),
            fill=(*peach_rgb, 125 if is_light_bg else 70),
        )
        _draw_soft_card(
            cd_draw,
            (card_x, card_y, card_w, card_h),
            fill=card_rgb,
            shadow_rgba=soft_shadow,
            outline_rgba=soft_outline,
            radius=round(24 * scale),
            shadow_dy=round(16 * scale),
            outline_w=max(2, round(2.5 * scale)),
        )
        # Header app mềm mại
        dot_d = round(13 * scale)
        dot_y = card_y + (bar_h - dot_d) // 2 + round(4 * scale)
        for di, dcol in enumerate((peach_rgb, (251, 191, 36), lavender_rgb)):
            dx = card_x + round(24 * scale) + di * (dot_d + round(9 * scale))
            cd_draw.ellipse((dx, dot_y, dx + dot_d, dot_y + dot_d), fill=_rgba(dcol))
        font_url = _load_font(round(19 * scale), bold=True)
        cd_draw.text(
            (card_x + card_w // 2, card_y + bar_h // 2 + round(4 * scale)),
            domain,
            font=font_url,
            fill=_rgba(card_muted),
            anchor="mm",
        )
        tag_text = "LIVE DEMO" if is_video_media else "SOCIAL VIEW"
        font_tag = _load_font(round(16 * scale), bold=True)
        tw = int(cd_draw.textlength(tag_text, font=font_tag)) + round(22 * scale)
        th = round(28 * scale)
        tx = card_x + card_w - tw - round(20 * scale)
        ty = card_y + (bar_h - th) // 2 + round(4 * scale)
        cd_draw.rounded_rectangle(
            (tx, ty, tx + tw, ty + th), radius=th // 2, fill=(*lavender_rgb, 125)
        )
        cd_draw.text(
            (tx + tw // 2, ty + th // 2),
            tag_text,
            font=font_tag,
            fill=_rgba(accent_rgb if is_light_card else badge_fg_rgb),
            anchor="mm",
        )

        media_x = card_x + pad_in
        media_y = card_y + bar_h + pad_in // 2
        card_img.save(card_path, format="PNG")

        # Layer Thẻ Social Highlights phía dưới khung web (bo tròn mềm + reaction chips + 2 điểm nổi bật)
        info_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        i_draw = ImageDraw.Draw(info_img)
        info_y = card_y + card_h + round(40 * scale)
        font_pt = _load_font(round(28 * scale), bold=True)
        wrapped_pts = [
            _wrap_text(i_draw, pt, font_pt, content_w - round(118 * scale), 2)
            for pt in highlights[:2]
        ]
        rows_h = sum(
            max(round(56 * scale), len(lines) * round(37 * scale) + round(14 * scale))
            for lines in wrapped_pts
        )
        info_h = min(round(118 * scale) + rows_h + round(24 * scale), round(1525 * scale) - info_y)
        _draw_soft_card(
            i_draw,
            (pad_x, info_y, content_w, info_h),
            fill=card_rgb,
            shadow_rgba=soft_shadow,
            outline_rgba=soft_outline,
            radius=round(24 * scale),
            shadow_dy=round(14 * scale),
        )
        # Hàng chip tương tác kiểu Social Media (pastel pills)
        chip_y = info_y + round(24 * scale)
        chip_x = pad_x + round(26 * scale)
        font_chip = _load_font(round(19 * scale), bold=True)
        for label, cbg, cfg in (
            ("NỔI BẬT", (*lavender_rgb, 130), accent_rgb if is_light_card else card_ink),
            ("DỄ DÙNG", (*peach_rgb, 125), (185, 28, 28) if is_light_card else card_ink),
            ("CHIA SẺ NGAY", (219, 234, 254, 180), (29, 78, 216) if is_light_card else card_ink),
        ):
            cw = int(i_draw.textlength(label, font=font_chip)) + round(30 * scale)
            ch = round(36 * scale)
            i_draw.rounded_rectangle(
                (chip_x, chip_y, chip_x + cw, chip_y + ch), radius=ch // 2, fill=cbg
            )
            i_draw.text(
                (chip_x + cw // 2, chip_y + ch // 2),
                label,
                font=font_chip,
                fill=_rgba(cfg),
                anchor="mm",
            )
            chip_x += cw + round(12 * scale)

        pt_y = chip_y + round(56 * scale)
        chk_r = round(18 * scale)
        chk_w = max(3, round(3.8 * scale))
        for idx, pt_lines in enumerate(wrapped_pts):
            ccx = pad_x + round(44 * scale)
            ccy = pt_y + round(18 * scale)
            dot_col = badge_bg_rgb if idx == 0 else (239, 68, 68)
            i_draw.ellipse(
                (ccx - chk_r, ccy - chk_r, ccx + chk_r, ccy + chk_r), fill=_rgba(dot_col)
            )
            i_draw.line(
                [
                    (ccx - round(chk_r * 0.45), ccy),
                    (ccx - round(chk_r * 0.1), ccy + round(chk_r * 0.36)),
                    (ccx + round(chk_r * 0.48), ccy - round(chk_r * 0.34)),
                ],
                fill=(255, 255, 255, 255),
                width=chk_w,
                joint="curve",
            )
            for li, pl in enumerate(pt_lines):
                i_draw.text(
                    (ccx + chk_r + round(18 * scale), pt_y + li * round(36 * scale)),
                    pl,
                    font=font_pt,
                    fill=_rgba(card_ink),
                    anchor="la",
                )
            pt_y += max(round(56 * scale), len(pt_lines) * round(37 * scale) + round(14 * scale))
        info_img.save(info_path, format="PNG")

        return SocialCanvasLayers(
            bg_path=bg_path,
            float_a_path=float_a_path,
            float_b_path=float_b_path,
            title_path=title_path,
            card_path=card_path,
            info_path=info_path,
            cta_btn_path=None,
            progress_path=progress_path,
            progress_box=active_seg_box,
            media_box=(media_x, media_y, fit_w, fit_h),
        )

    # --- LANDSCAPE 16:9 ---
    pad_x = round(56 * scale)
    av_r = round(24 * scale)
    av_cx, av_cy = pad_x + av_r, round(54 * scale)
    bg_draw.ellipse(
        (av_cx - av_r, av_cy - av_r, av_cx + av_r, av_cy + av_r), fill=_rgba(badge_bg_rgb)
    )
    bg_draw.text(
        (av_cx, av_cy),
        (product_name or domain or "R")[0].upper(),
        font=_load_font(round(22 * scale), bold=True),
        fill=_rgba(badge_fg_rgb),
        anchor="mm",
    )
    bg_draw.text(
        (av_cx + av_r + round(14 * scale), av_cy),
        f"@{domain}",
        font=_load_font(round(22 * scale), bold=True),
        fill=_rgba(ink_rgb),
        anchor="lm",
    )
    step_label = f"{scene_index:02d} / {scene_total:02d}"
    font_st = _load_font(round(20 * scale), bold=True)
    st_w = int(bg_draw.textlength(step_label, font=font_st)) + round(32 * scale)
    bg_draw.rounded_rectangle(
        (width - pad_x - st_w, av_cy - round(19 * scale), width - pad_x, av_cy + round(19 * scale)),
        radius=round(19 * scale),
        fill=(*lavender_rgb, 145),
    )
    bg_draw.text(
        (width - pad_x - st_w // 2, av_cy),
        step_label,
        font=font_st,
        fill=_rgba(ink_rgb),
        anchor="mm",
    )
    bg_img.save(bg_path, format="PNG")

    if media_size is None:
        cta_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        c_draw = ImageDraw.Draw(cta_img)
        cta_w, cta_h = round(width * 0.64), round(height * 0.58)
        cta_x, cta_y = (width - cta_w) // 2, round(height * 0.16)
        _draw_soft_card(
            c_draw,
            (cta_x, cta_y, cta_w, cta_h),
            fill=card_rgb,
            shadow_rgba=soft_shadow,
            outline_rgba=soft_outline,
            radius=round(28 * scale),
            shadow_dy=round(16 * scale),
        )
        _draw_desk_accent(
            c_draw,
            cta_x + round(40 * scale),
            cta_y + cta_h - round(120 * scale),
            cta_w - round(80 * scale),
            round(92 * scale),
            peach_rgb,
            accent_rgb,
        )
        font_cta = _load_font(round(48 * scale), bold=True)
        for idx, line in enumerate(
            _wrap_text(c_draw, headline, font_cta, cta_w - round(100 * scale), 2)
        ):
            c_draw.text(
                (width // 2, cta_y + round(105 * scale) + idx * round(62 * scale)),
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
        btn_w = int(b_draw.textlength(btn_text, font=btn_font)) + round(76 * scale)
        btn_h = round(72 * scale)
        btn_x, btn_y = (width - btn_w) // 2, cta_y + cta_h - round(185 * scale)
        _draw_soft_card(
            b_draw,
            (btn_x, btn_y, btn_w, btn_h),
            fill=badge_bg_rgb,
            shadow_rgba=(*badge_bg_rgb, 80),
            outline_rgba=(255, 255, 255, 40),
            radius=btn_h // 2,
            shadow_dy=round(10 * scale),
        )
        b_draw.text(
            (btn_x + btn_w // 2, btn_y + btn_h // 2),
            btn_text,
            font=btn_font,
            fill=_rgba(badge_fg_rgb),
            anchor="mm",
        )
        btn_img.save(cta_btn_path, format="PNG")
        return SocialCanvasLayers(
            bg_path=bg_path,
            float_a_path=float_a_path,
            float_b_path=float_b_path,
            title_path=None,
            card_path=None,
            info_path=info_path,
            cta_btn_path=cta_btn_path,
            progress_path=None,
            progress_box=None,
            media_box=None,
        )

    card_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    cd_draw = ImageDraw.Draw(card_img)
    src_w, src_h = media_size
    pad_in, bar_h = round(12 * scale), round(42 * scale)
    fit_scale = min(round(width * 0.56) / max(1, src_w), round(height * 0.62) / max(1, src_h))
    fit_w = max(2, int(round(src_w * fit_scale)) // 2 * 2)
    fit_h = max(2, int(round(src_h * fit_scale)) // 2 * 2)
    card_w, card_h = fit_w + pad_in * 2, bar_h + fit_h + pad_in * 2
    card_x = pad_x
    card_y = round(135 * scale) + max(0, (round(height * 0.68) - card_h) // 2)
    _draw_soft_card(
        cd_draw,
        (card_x, card_y, card_w, card_h),
        fill=card_rgb,
        shadow_rgba=soft_shadow,
        outline_rgba=soft_outline,
        radius=round(22 * scale),
        shadow_dy=round(14 * scale),
    )
    media_x, media_y = card_x + pad_in, card_y + bar_h + pad_in // 2
    card_img.save(card_path, format="PNG")

    right_x = card_x + card_w + round(44 * scale)
    right_w = width - pad_x - right_x
    title_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    t_draw = ImageDraw.Draw(title_img)
    font_b = _load_font(round(20 * scale), bold=True)
    b_text = f"#  {(badge or 'ĐIỂM NỔI BẬT').upper()}"
    bw = int(t_draw.textlength(b_text, font=font_b)) + round(36 * scale)
    t_draw.rounded_rectangle(
        (right_x, card_y, right_x + bw, card_y + round(40 * scale)),
        radius=round(20 * scale),
        fill=_rgba(badge_bg_rgb),
    )
    t_draw.text(
        (right_x + bw // 2, card_y + round(20 * scale)),
        b_text,
        font=font_b,
        fill=_rgba(badge_fg_rgb),
        anchor="mm",
    )
    font_hl = _load_font(round(40 * scale), bold=True)
    for idx, line in enumerate(_wrap_text(t_draw, headline, font_hl, right_w, 3)):
        t_draw.text(
            (right_x, card_y + round(58 * scale) + idx * round(50 * scale)),
            line,
            font=font_hl,
            fill=_rgba(ink_rgb),
            anchor="la",
        )
    title_img.save(title_path, format="PNG")

    info_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    i_draw = ImageDraw.Draw(info_img)
    i_y = card_y + round(235 * scale)
    i_h = max(round(210 * scale), card_y + card_h - i_y)
    _draw_soft_card(
        i_draw,
        (right_x, i_y, right_w, i_h),
        fill=card_rgb,
        shadow_rgba=soft_shadow,
        outline_rgba=soft_outline,
        radius=round(20 * scale),
        shadow_dy=round(12 * scale),
    )
    font_pt = _load_font(round(23 * scale), bold=True)
    py = i_y + round(28 * scale)
    for idx, pt in enumerate(highlights[:2]):
        ccx, ccy = right_x + round(34 * scale), py + round(14 * scale)
        i_draw.ellipse(
            (ccx - 13, ccy - 13, ccx + 13, ccy + 13),
            fill=_rgba(badge_bg_rgb if idx == 0 else (239, 68, 68)),
        )
        i_draw.line(
            [(ccx - 6, ccy), (ccx - 1, ccy + 5), (ccx + 6, ccy - 5)],
            fill=(255, 255, 255, 255),
            width=3,
        )
        pt_lines = _wrap_text(i_draw, pt, font_pt, right_w - round(76 * scale), 2)
        for li, pl in enumerate(pt_lines):
            i_draw.text(
                (ccx + 24, py + li * round(31 * scale)),
                pl,
                font=font_pt,
                fill=_rgba(card_ink),
                anchor="la",
            )
        py += max(round(56 * scale), len(pt_lines) * round(33 * scale) + round(14 * scale))
    info_img.save(info_path, format="PNG")

    return SocialCanvasLayers(
        bg_path=bg_path,
        float_a_path=float_a_path,
        float_b_path=float_b_path,
        title_path=title_path,
        card_path=card_path,
        info_path=info_path,
        cta_btn_path=None,
        progress_path=None,
        progress_box=None,
        media_box=(media_x, media_y, fit_w, fit_h),
    )
