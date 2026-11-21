"""Renderer P1 nhẹ: một tiến trình FFmpeg mỗi cảnh, rồi nối thành MP4."""

from __future__ import annotations

import json
import re
import subprocess
import time
from html import escape
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from worker.render.canvas import build_offset_shadow_layers
from worker.render.design import contrast_text_for, normalize_hex, relative_luminance
from worker.render.social_canvas import build_social_media_layers
from worker.render.tts import FallbackTts, Synthesizer
from worker.settings import Settings


PRO_TEMPLATES = {
    "offset-shadow",
    "social-media",
    "short-countdown",
    "review-pro",
    "animation",
    "reels-aurora",
    "reels-editorial",
    "reels-neon",
    "reels-comparison",
}
SUPPORTED_TEMPLATES = {"cinematic", "animation", "vintage", *PRO_TEMPLATES}

# Các preset lấy cảm hứng từ catalog template MIT của AI-auto-generate-video.
# Renderer vẫn thuộc P1: clip/ảnh thật của sản phẩm luôn được đặt contain trong khung.
TEMPLATE_PALETTES = {
    "offset-shadow": ("faf3ec", "e44332", "ffffff"),
    "social-media": ("f9f7f4", "5b5ce6", "ffffff"),
    "short-countdown": ("facc15", "111827", "ffffff"),
    "animation": ("180d2b", "e879f9", "2c1b46"),
    "review-pro": ("07110d", "8ee8bc", "15231d"),
    "reels-aurora": ("160d35", "ff9a3d", "30205f"),
    "reels-editorial": ("efe9df", "e6372f", "28231f"),
    "reels-neon": ("070912", "22d3ee", "171b2d"),
    "reels-comparison": ("071918", "34e0c0", "123432"),
}

ICON_RULES = (
    (("lịch", "calendar", "schedule", "thời khóa"), "calendar-days", "LỊCH"),
    (("bảo mật", "secure", "security", "quyền"), "shield-check", "AN TOÀN"),
    (("tìm", "search", "tra cứu"), "search", "TÌM KIẾM"),
    (("nhanh", "tốc độ", "instant", "real-time"), "zap", "NHANH"),
    (("thống kê", "kết quả", "report", "analytics", "điểm"), "chart-no-axes-column-increasing", "KẾT QUẢ"),
    (("người dùng", "sinh viên", "đội ngũ", "team", "users"), "users-round", "NGƯỜI DÙNG"),
    (("điện thoại", "smartphone", "mobile", "hướng dẫn"), "smartphone", "HƯỚNG DẪN"),
    (("giọng", "audio", "voice", "nghe"), "headphones", "NGHE THỬ"),
    (("đối đầu", "so sánh", "versus", " vs "), "scale", "SO SÁNH"),
    (("top 3", "đếm ngược", "thứ ba", "hạng"), "trophy", "TOP 3"),
    (("video", "demo", "xem", "play"), "circle-play", "DEMO"),
)
ICON_GLYPHS = {
    "calendar-days": "▦", "shield-check": "⬡", "search": "⌕", "zap": "ϟ",
    "chart-no-axes-column-increasing": "▥", "users-round": "♙", "smartphone": "▯",
    "headphones": "♫", "scale": "⚖", "trophy": "♜", "circle-play": "▶",
    "sparkles": "✦",
}
ICON_FILES = {
    "calendar-days", "shield-check", "search", "zap",
    "chart-no-axes-column-increasing", "users-round", "smartphone",
    "headphones", "scale", "trophy", "circle-play",
}
STOPWORDS = {
    "và", "của", "cho", "trong", "trên", "một", "những", "được", "với", "các",
    "giúp", "ngay", "theo", "từ", "đến", "là", "có", "the", "and", "for", "your",
}


class RenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderResult:
    video: Path
    manifest: dict[str, Any]


def _image_has_content(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            stat = ImageStat.Stat(image.convert("RGB"))
        return sum(stat.var) / len(stat.var) >= 4
    except (OSError, ValueError):
        return False


def _run(command: list[str], timeout: int = 600) -> None:
    try:
        done = subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise RenderError(f"không tìm thấy chương trình: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderError("FFmpeg quá thời gian cho phép") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc))[-1200:]
        raise RenderError(f"FFmpeg thất bại: {detail}") from exc
    if done.returncode:
        raise RenderError("FFmpeg kết thúc bất thường")


def _ass_escape(text: str) -> str:
    return text.replace("\\", "／").replace("{", "(").replace("}", ")").replace("\n", r"\N")


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cents = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{cents:02}"


def _caption_chunks(text: str, target_words: int = 7) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    for start in range(0, len(words), target_words):
        chunks.append(" ".join(words[start : start + target_words]))
    return chunks


INTERNAL_ROLES = {"HOOK", "PROBLEM", "DEMO", "RESULT", "CTA", "FEATURE", "PROOF"}


def _display_headline(
    scene: dict[str, Any], script: dict[str, Any], override: dict[str, Any], narration: str
) -> str:
    """Dùng câu người xem hiểu được, không đưa role nội bộ lên video."""
    role = str(scene.get("role") or "").lower()
    approved = script.get("hook") if role == "hook" else script.get("cta") if role == "cta" else None
    approved_text = approved.get("text") if isinstance(approved, dict) else None
    override_headline = str(override.get("headline") or "").strip()
    if override_headline.upper() in INTERNAL_ROLES:
        override_headline = ""
    candidate = (
        override_headline
        or approved_text
        or scene.get("subtitle_text")
        or narration
    )
    words = str(candidate or "").strip().split()
    headline = " ".join(words[:11])
    if len(words) > 11:
        headline += "…"
    return headline[:90]


def _media_dimensions(asset: Path, settings: Settings) -> tuple[int, int]:
    """Đọc kích thước gốc (width, height) của ảnh hoặc video để ôm sát khung thẻ."""
    suffix = asset.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        try:
            with Image.open(asset) as img:
                w, h = img.size
                if w > 0 and h > 0:
                    return w, h
        except OSError:
            pass
    elif suffix in {".mp4", ".webm", ".mov", ".mkv"}:
        try:
            info = _probe(settings, asset)
            vs = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
            w, h = int(vs.get("width") or 0), int(vs.get("height") or 0)
            if w > 0 and h > 0:
                return w, h
        except RenderError:
            pass
    return 1280, 720


def _fit_box(src_w: int, src_h: int, max_w: int, max_h: int) -> tuple[int, int]:
    scale = min(max_w / max(1, src_w), max_h / max(1, src_h))
    fit_w = max(2, int(round(src_w * scale)) // 2 * 2)
    fit_h = max(2, int(round(src_h * scale)) // 2 * 2)
    return fit_w, fit_h


def _strip_hash(hex_color: str, fallback: str) -> str:
    return normalize_hex(hex_color, f"#{fallback}")[1:].lower()


def _safe_keyword_hex(accent_hex: str, on_dark_pill: bool) -> str:
    """Đảm bảo màu nhấn từ khóa phụ đề luôn có độ tương phản cao, không bị chìm."""
    lum = relative_luminance(f"#{accent_hex}")
    if on_dark_pill and lum < 0.22:
        return "fde047"
    if not on_dark_pill and lum > 0.72:
        return "e44332"
    return accent_hex


def _ass_color(hex_color: str) -> str:
    value = hex_color.lstrip("#").zfill(6)[-6:]
    return f"&H00{value[4:6]}{value[2:4]}{value[0:2]}"


def _graphic_cues(role: str, headline: str, narration: str) -> dict[str, Any]:
    haystack = f"{role} {headline} {narration}".lower()
    icon, badge = "sparkles", "ĐIỂM NỔI BẬT"
    for keywords, candidate_icon, candidate_badge in ICON_RULES:
        if any(keyword in haystack for keyword in keywords):
            icon, badge = candidate_icon, candidate_badge
            break
    words = [
        word.strip(".,:;!?()[]{}\"'“”").lower()
        for word in narration.split()
    ]
    keywords = sorted(
        {word for word in words if len(word) >= 5 and word not in STOPWORDS},
        key=lambda word: (-len(word), words.index(word)),
    )[:2]
    role_lower = role.lower()
    card = "hook" if "hook" in role_lower else "cta" if "cta" in role_lower else "feature"
    if "vs" in haystack or "đối đầu" in haystack or "so sánh" in haystack:
        card = "comparison"
    elif "top 3" in haystack or "đếm ngược" in haystack:
        card = "countdown"
    return {"icon": icon, "icon_glyph": ICON_GLYPHS[icon], "badge": badge, "keywords": keywords, "card": card}


def _rasterize_lucide_icons(names: set[str], output_dir: Path, accent: str) -> dict[str, Path]:
    """Raster hóa SVG Lucide đã đóng gói bằng Chromium local, không truy cập mạng."""
    selected = names & ICON_FILES
    if not selected:
        return {}
    icon_dir = Path(__file__).parent / "assets" / "lucide"
    svg_by_name: dict[str, str] = {}
    for name in selected:
        path = icon_dir / f"{name}.svg"
        if not path.is_file():
            continue
        svg = path.read_text(encoding="utf-8")
        svg = svg.replace('stroke="currentColor"', f'stroke="#{accent}"')
        svg_by_name[name] = svg
    if not svg_by_name:
        return {}
    output_dir.mkdir(parents=True, exist_ok=True)
    targets = {name: output_dir / f"{name}-{accent}.png" for name in svg_by_name}
    missing = {name: svg for name, svg in svg_by_name.items() if not targets[name].is_file()}
    if missing:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 192, "height": 192}, device_scale_factor=1)
                for name, svg in missing.items():
                    page.set_content(
                        "<html><body style='margin:0;background:transparent;display:grid;"
                        "place-items:center;width:192px;height:192px'>"
                        f"{svg}</body></html>",
                        wait_until="load",
                    )
                    page.locator("svg").evaluate(
                        "el => {el.setAttribute('width','144');el.setAttribute('height','144')}"
                    )
                    page.locator("body").screenshot(path=str(targets[name]), omit_background=True)
                browser.close()
        except Exception as exc:  # noqa: BLE001
            detail = " ".join(str(exc).split())[:300]
            suffix = f": {detail}" if detail else ""
            raise RenderError(
                f"không raster hóa được icon Lucide ({type(exc).__name__}){suffix}"
            ) from exc
    return {name: path for name, path in targets.items() if path.is_file()}


def _highlight_ass(text: str, keywords: list[str], accent: str) -> str:
    escaped = _ass_escape(text)
    for keyword in sorted(keywords, key=len, reverse=True):
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        escaped = pattern.sub(
            lambda match: f"{{\\c{accent}\\b1}}{match.group(0)}{{\\rCaption}}",
            escaped,
        )
    return escaped


def _ass(
    path: Path,
    text: str,
    headline: str,
    width: int,
    height: int,
    duration: float,
    template: str,
    graphics: dict[str, Any],
    *,
    bg_hex: str = "111827",
    accent_hex: str = "8ee8bc",
    card_hex: str = "ffffff",
    has_media: bool = True,
    captions_only: bool = False,
) -> None:
    is_portrait = height > width
    is_hd = max(width, height) >= 1600
    is_light_bg = relative_luminance(f"#{bg_hex}") > 0.42
    is_light_card = relative_luminance(f"#{card_hex}") > 0.42
    font = "Georgia" if template == "vintage" else "Arial"

    caption_margin_x = round(width * 0.08)
    caption_margin_v = (
        (210 if is_hd else 140) if is_portrait else (56 if is_hd else 38)
    )
    badge_margin_v = (128 if is_hd else 86) if is_portrait else (34 if is_hd else 24)
    headline_margin_v = (232 if is_hd else 156) if is_portrait else (96 if is_hd else 64)
    headline_margin_x = round(width * 0.08)

    style_format = (
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
    )

    # Phụ đề luôn nằm trong hộp tối tương phản cao (BorderStyle=3) với từ khóa sáng nổi bật.
    caption_size = (
        (52 if is_hd else 36) if is_portrait else (44 if is_hd else 32)
    )
    caption_pad = 14 if is_hd else 10
    caption_shadow = 7 if template == "offset-shadow" else 3
    caption_box_ass = "&H00111827" if template == "offset-shadow" or is_light_bg else "&H180B101B"
    caption_shadow_ass = _ass_color(accent_hex) if (template == "offset-shadow" and not is_light_bg) else "&H00000000"
    style = (
        f"Style: Caption,{font},{caption_size},&H00FFFFFF,&H000000FF,{caption_box_ass},"
        f"{caption_shadow_ass},-1,0,0,0,100,100,0,0,3,{caption_pad},{caption_shadow},2,"
        f"{caption_margin_x},{caption_margin_x},{caption_margin_v},1"
    )

    # Tiêu đề đặt gọn phía trên khung sản phẩm, tự tính tương phản theo màu nền.
    headline_primary = "&H00111827" if is_light_bg else "&H00FFFFFF"
    headline_outline = _ass_color(bg_hex) if is_light_bg else "&H000B101B"
    headline_size = (56 if is_hd else 38) if is_portrait else (44 if is_hd else 30)
    headline_style = (
        f"Style: Headline,{font},{headline_size},{headline_primary},"
        f"&H000000FF,{headline_outline},&H40000000,-1,0,0,0,100,100,0,0,1,"
        f"{2 if is_light_bg else 4},{0 if is_light_bg else 2},8,"
        f"{headline_margin_x},{headline_margin_x},{headline_margin_v},1"
    )

    # Badge căn giữa trên cùng, nền màu nhấn (hoặc đen đậm), chữ tương phản tuyệt đối + bóng lệch.
    badge_bg_hex = accent_hex if relative_luminance(f"#{accent_hex}") < 0.65 else "111827"
    badge_fg_hex = contrast_text_for(f"#{badge_bg_hex}")[1:]
    badge_bg_ass = _ass_color(badge_bg_hex)
    badge_fg_ass = _ass_color(badge_fg_hex)
    badge_size = (30 if is_hd else 22) if is_portrait else (26 if is_hd else 18)
    badge_pad = 12 if is_hd else 8
    badge_shadow = 6 if template == "offset-shadow" else 2
    badge_style = (
        f"Style: Badge,{font},{badge_size},{badge_fg_ass},&H000000FF,"
        f"{badge_bg_ass},&H00111827,-1,0,0,0,100,100,1,0,3,{badge_pad},{badge_shadow},8,"
        f"70,70,{badge_margin_v},1"
    )

    # Card chỉ dùng cho cảnh text-only (ví dụ CTA không có ảnh), đặt chính giữa trong khung thẻ đã vẽ.
    card_fg = "&H00111827" if is_light_card else "&H00FFFFFF"
    card_size = (58 if is_hd else 40) if is_portrait else (48 if is_hd else 34)
    card_style = (
        f"Style: Card,{font},{card_size},{card_fg},&H000000FF,"
        f"{card_fg},&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,"
        f"{round(width * 0.14)},{round(width * 0.14)},120,1"
    )

    keyword_hex = _safe_keyword_hex(accent_hex, on_dark_pill=True)
    keyword_ass = _ass_color(keyword_hex)

    events: list[str] = []
    if template in PRO_TEMPLATES:
        if not captions_only:
            countdown = str(graphics.get("countdown", ""))
            badge_label = str(graphics.get("badge", "ĐIỂM NỔI BẬT")).strip()
            badge_text = f"#{countdown}  ·  {badge_label}" if (template == "short-countdown" and countdown) else badge_label
            events.append(
                f"Dialogue: 4,0:00:00.10,{_ass_time(duration)},Badge,,0,0,0,,"
                f"{{\\fad(140,140)}}  {_ass_escape(badge_text)}  "
            )
            if not has_media:
                events.append(
                    f"Dialogue: 3,0:00:00.00,{_ass_time(duration)},Card,,0,0,0,,"
                    f"{{\\fad(160,160)}}{_ass_escape(headline)}"
                )
            else:
                events.append(
                    f"Dialogue: 2,0:00:00.00,{_ass_time(duration)},Headline,,0,0,0,,"
                    f"{{\\fad(160,160)}}{_ass_escape(headline)}"
                )
        chunks = _caption_chunks(
            text, target_words=5 if template in {"offset-shadow", "social-media", "animation", "short-countdown"} else 7
        )
        chunk_duration = duration / max(1, len(chunks))
        for index, chunk in enumerate(chunks):
            start = index * chunk_duration
            end = min(duration, (index + 1) * chunk_duration + 0.08)
            entrance = (
                r"{\fad(60,80)\fscx92\fscy92\t(0,110,\fscx100\fscy100)}"
                if template in {"offset-shadow", "social-media", "animation", "short-countdown"}
                else r"{\fad(90,90)}"
            )
            events.append(
                f"Dialogue: 3,{_ass_time(start)},{_ass_time(end)},Caption,,0,0,0,,"
                f"{entrance}{_highlight_ass(chunk, list(graphics.get('keywords', [])), keyword_ass)}"
            )
    else:
        events.append(
            f"Dialogue: 0,0:00:00.00,{_ass_time(duration)},Caption,,0,0,0,,{_ass_escape(text)}"
        )
    content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
{style_format}
{style}
{headline_style}
{badge_style}
{card_style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{chr(10).join(events)}
"""
    path.write_text(content, encoding="utf-8-sig")


def _filter_path(path: Path) -> str:
    value = str(path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    return f"'{value}'"


def _motion_filter(style: str, width: int, height: int, fps: int, duration: float) -> str:
    """Ken Burns mượt cho ảnh tĩnh (nhận 1 khung gốc, không dùng -loop 1 để `on` tăng thật)."""
    frames = max(2, round(duration * fps))
    center_x = "iw/2-(iw/zoom/2)"
    center_y = "ih/2-(ih/zoom/2)"
    progress = f"on/{frames - 1}"
    if style == "zoom_out":
        zoom = f"1.09-0.09*({progress})"
        x, y = center_x, center_y
    elif style == "pan_left":
        zoom = "1.09"
        x, y = f"(iw-iw/zoom)*(1-({progress}))", center_y
    elif style == "pan_right":
        zoom = "1.09"
        x, y = f"(iw-iw/zoom)*({progress})", center_y
    elif style == "none":
        return f",loop=loop=-1:size=1:start=0,fps={fps}"
    else:
        zoom = f"1.0+0.09*({progress})"
        x, y = center_x, center_y
    return f",zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps}"


def _ease_out_expr(start_s: float, dur_s: float, delta_px: int, base_px: int = 0) -> str:
    """Biểu thức FFmpeg trượt mượt quadratic ease-out từ `base_px + delta_px` về `base_px`."""
    end_s = start_s + dur_s
    start_val = base_px + delta_px
    return (
        f"if(lt(t\\,{start_s:.3f})\\,{start_val}\\,"
        f"if(lt(t\\,{end_s:.3f})\\,{base_px}+({delta_px})*pow(1-(t-{start_s:.3f})/{dur_s:.3f}\\,2)\\,{base_px}))"
    )


def _probe(settings: Settings, video: Path) -> dict[str, Any]:
    try:
        done = subprocess.run(
            [
                settings.ffprobe_bin,
                "-v",
                "error",
                "-show_entries",
                "stream=index,codec_type,codec_name,width,height,r_frame_rate:format=duration,size",
                "-of",
                "json",
                str(video),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return json.loads(done.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise RenderError("ffprobe không kiểm tra được MP4") from exc


def render_video(
    script: dict[str, Any],
    options: dict[str, Any],
    output_dir: Path,
    settings: Settings,
    tts: Synthesizer,
) -> RenderResult:
    started = time.monotonic()
    scenes = script.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise RenderError("script không có cảnh")
    overrides_raw = options.get("scene_overrides")
    overrides = overrides_raw if isinstance(overrides_raw, dict) else {}
    order_raw = options.get("scene_order")
    if isinstance(order_raw, list):
        rank = {str(scene_id): index for index, scene_id in enumerate(order_raw)}
        scenes = sorted(
            scenes,
            key=lambda scene: rank.get(str(scene.get("scene_id")), len(rank)),
        )
    ratio = options.get("aspect_ratio", "16:9")
    if ratio not in {"16:9", "9:16"}:
        raise RenderError("aspect_ratio chỉ nhận 16:9 hoặc 9:16")
    resolution = options.get("resolution", "720p")
    if resolution not in {"720p", "1080p"}:
        raise RenderError("resolution chỉ nhận 720p hoặc 1080p")
    if ratio == "16:9":
        width, height = (1920, 1080) if resolution == "1080p" else (1280, 720)
    else:
        width, height = (1080, 1920) if resolution == "1080p" else (720, 1280)
    template = options.get("template", "cinematic")
    if template not in SUPPORTED_TEMPLATES:
        raise RenderError("template không nằm trong catalog renderer P1")
    fps = 30 if template in PRO_TEMPLATES else 24
    transition = options.get("transition", "slide" if template in {"offset-shadow", "social-media"} else "fade")
    if transition not in {"slide", "fade", "none"}:
        raise RenderError("transition chỉ nhận slide, fade hoặc none")
    default_palette = TEMPLATE_PALETTES.get(
        template,
        {
            "cinematic": ("111827", "8ee8bc", "15231d"),
            "vintage": ("3f2d20", "e8d5b7", "2c1e14"),
        }.get(template, ("111827", "8ee8bc", "15231d")),
    )
    custom_bg = options.get("bg_color")
    custom_accent = options.get("accent_color")
    custom_card = options.get("card_color")
    base_bg = _strip_hash(str(custom_bg), default_palette[0]) if isinstance(custom_bg, str) and custom_bg.strip() else default_palette[0]
    base_accent = _strip_hash(str(custom_accent), default_palette[1]) if isinstance(custom_accent, str) and custom_accent.strip() else default_palette[1]
    base_card = _strip_hash(str(custom_card), default_palette[2]) if isinstance(custom_card, str) and custom_card.strip() else default_palette[2]
    raw_assets = options.get("asset_paths")
    assets: dict[str, Any] = raw_assets if isinstance(raw_assets, dict) else {}
    asset_root = Path(settings.page_store_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_dir, scene_dir = output_dir / "audio", output_dir / "scenes"
    scene_dir.mkdir(parents=True, exist_ok=True)
    narration_items: list[tuple[str, str]] = []
    for index, scene in enumerate(scenes, start=1):
        scene_id = str(scene.get("scene_id") or f"s{index:02}")
        segments = scene.get("narration_segments") or []
        narration = " ".join(str(item.get("text", "")).strip() for item in segments).strip()
        if not narration:
            raise RenderError(f"cảnh {scene_id} thiếu lời đọc")
        narration_items.append((scene_id, narration))
    if isinstance(tts, FallbackTts):
        audio_results = tts.synthesize_all(narration_items, audio_dir)
    else:
        audio_results = {
            scene_id: tts.synthesize(scene_id, narration, audio_dir)
            for scene_id, narration in narration_items
        }
    prepared: list[dict[str, Any]] = []
    narration_word_count = 0
    for index, scene in enumerate(scenes, start=1):
        scene_id = str(scene.get("scene_id") or f"s{index:02}")
        segments = scene.get("narration_segments") or []
        narration = " ".join(str(item.get("text", "")).strip() for item in segments).strip()
        narration_word_count += len(narration.split())
        audio, speech = audio_results[scene_id]
        visual = scene.get("visual_plan") or {}
        override_value = overrides.get(scene_id)
        override: dict[str, Any] = override_value if isinstance(override_value, dict) else {}
        asset_id = override.get("asset_id") or visual.get("asset_id")
        asset = (
            Path(str(assets.get(str(asset_id), ""))).resolve()
            if isinstance(asset_id, str) and asset_id in assets
            else None
        )
        if asset is not None:
            if not asset.is_relative_to(asset_root):
                raise RenderError(f"asset {asset_id} nằm ngoài kho tư liệu của worker")
            if not asset.is_file():
                raise RenderError(f"asset {asset_id} không tồn tại")
        prepared.append(
            {
                "id": scene_id,
                "scene": scene,
                "override": override,
                "narration": narration,
                "audio": audio,
                "speech": speech,
                "duration": max(3.0, speech + 0.22),
                "subtitle": str(
                    override.get("subtitle") or scene.get("subtitle_text") or narration
                ),
                "headline": _display_headline(scene, script, override, narration),
                "role": str(scene.get("role") or "feature"),
                "asset_id": asset_id,
                "asset": asset,
                "motion": str(
                    override.get("motion")
                    or ("zoom_in", "pan_right", "zoom_out", "pan_left")[(index - 1) % 4]
                ),
            }
        )
        graphics = _graphic_cues(prepared[-1]["role"], prepared[-1]["headline"], narration)
        custom_badge = str(override.get("badge") or "").strip()
        if custom_badge and custom_badge.upper() not in INTERNAL_ROLES:
            graphics["badge"] = custom_badge.upper()[:22]
        prepared[-1]["graphics"] = graphics
        if template == "short-countdown" and 1 < index < len(scenes):
            prepared[-1]["graphics"]["countdown"] = f"{len(scenes) - index:02}"
    total = sum(item["duration"] for item in prepared)
    tts_providers: set[str] = set()
    for item in prepared:
        meta_path = audio_dir / f"{item['id']}.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        provider = meta.get("provider")
        if isinstance(provider, str) and provider:
            tts_providers.add(provider)
    if len(tts_providers) > 1:
        raise RenderError(
            "TTS không nhất quán giữa các cảnh: " + ", ".join(sorted(tts_providers))
        )
    tts_provider = next(iter(tts_providers), type(tts).__name__)
    if total > 59.05:
        recommended_max = max(1, round(narration_word_count * 55.0 / total))
        raise RenderError(
            f"TTS dài {total:.2f}s, vượt giới hạn short video 60s; "
            f"kịch bản hiện có {narration_word_count} từ. "
            f"Hãy tạo revision tối đa khoảng {recommended_max} từ với giọng hiện tại."
        )
    real_media = 0
    unique_media: set[str] = set()
    files: list[Path] = []
    product_name = str(options.get("product_name") or "").strip()
    website_url = str(options.get("website_url") or "").strip()
    use_xfade = len(prepared) > 1 and transition in {"slide", "fade"} and template in PRO_TEMPLATES
    xfade_dur = 0.30
    scene_durations: list[float] = []
    for scene_index, item in enumerate(prepared, start=1):
        scene_path = scene_dir / f"{item['id']}.mp4"
        ass = scene_dir / f"{item['id']}.ass"
        asset: Path | None = item["asset"]
        scene_bg = base_bg
        if template == "short-countdown" and not (isinstance(custom_bg, str) and custom_bg.strip()):
            scene_bg = ("facc15", "1e293b", "0f766e", "6b21a8", "9a3412")[len(files) % 5]
        use_rich_canvas = template in {"offset-shadow", "social-media"}
        scene_dur = float(item["duration"])
        _ass(
            ass,
            item["subtitle"],
            item["headline"],
            width,
            height,
            scene_dur,
            template,
            item["graphics"],
            bg_hex=scene_bg,
            accent_hex=base_accent,
            card_hex=base_card,
            has_media=asset is not None,
            captions_only=use_rich_canvas,
        )
        command = [settings.ffmpeg_bin, "-y", "-loglevel", "error"]
        is_still = asset is not None and asset.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        is_video_media = asset is not None and asset.suffix.lower() in {".mp4", ".webm", ".mov", ".mkv"}
        template_filter = {
            "offset-shadow": "eq=contrast=1.03:saturation=1.05",
            "social-media": "eq=contrast=1.02:saturation=1.08",
            "short-countdown": "eq=contrast=1.06:saturation=1.10",
            "cinematic": "eq=contrast=1.08:saturation=1.05",
            "animation": "eq=contrast=1.04:saturation=1.16",
            "vintage": "colorchannelmixer=.393:.769:.189:.349:.686:.168:.272:.534:.131",
            "review-pro": "eq=contrast=1.05:saturation=1.06",
            "reels-aurora": "eq=contrast=1.05:saturation=1.12",
            "reels-editorial": "eq=contrast=1.03:saturation=.94:brightness=.01",
            "reels-neon": "eq=contrast=1.10:saturation=1.15",
            "reels-comparison": "eq=contrast=1.06:saturation=1.08",
        }[template]
        transition_filter = ""
        audio_fade = ""
        if transition != "none" and not use_xfade:
            fade_out = max(0.0, scene_dur - 0.30)
            transition_filter = f",fade=t=out:st={fade_out:.3f}:d=0.30"
            audio_fade = f",afade=t=in:st=0:d=0.12,afade=t=out:st={fade_out:.3f}:d=0.22"
        elif use_xfade:
            audio_fade = ",afade=t=in:st=0:d=0.08"

        if use_rich_canvas:
            media_dim: tuple[int, int] | None = None
            if asset is not None:
                if is_still and not _image_has_content(asset):
                    raise RenderError(f"asset {item['asset_id']} là ảnh trắng hoặc không đọc được")
                if not is_still and not is_video_media:
                    raise RenderError(f"asset {item['asset_id']} có loại file chưa hỗ trợ")
                real_media += 1
                unique_media.add(str(item["asset_id"]))
                media_dim = _media_dimensions(asset, settings)
            if template == "social-media":
                sm_layers = build_social_media_layers(
                    output_dir=scene_dir / "layers",
                    scene_id=str(item["id"]),
                    width=width,
                    height=height,
                    scene=item["scene"],
                    override=item["override"],
                    headline=item["headline"],
                    badge=str(item["graphics"].get("badge", "ĐIỂM NỔI BẬT")),
                    narration=item["narration"],
                    scene_index=scene_index,
                    scene_total=len(prepared),
                    product_name=product_name,
                    website_url=website_url,
                    bg_hex=scene_bg,
                    accent_hex=base_accent,
                    card_hex=base_card,
                    media_size=media_dim,
                    is_video_media=is_video_media,
                )
                bg_layer = sm_layers.bg_path
                float_a_layer: Path | None = sm_layers.float_a_path
                float_b_layer: Path | None = sm_layers.float_b_path
                title_layer = sm_layers.title_path
                browser_layer = sm_layers.card_path
                info_layer = sm_layers.info_path
                cta_btn_layer = sm_layers.cta_btn_path
                progress_layer = sm_layers.progress_path
                progress_box = sm_layers.progress_box
                media_box = sm_layers.media_box
            else:
                os_layers = build_offset_shadow_layers(
                    output_dir=scene_dir / "layers",
                    scene_id=str(item["id"]),
                    width=width,
                    height=height,
                    scene=item["scene"],
                    override=item["override"],
                    headline=item["headline"],
                    badge=str(item["graphics"].get("badge", "ĐIỂM NỔI BẬT")),
                    narration=item["narration"],
                    scene_index=scene_index,
                    scene_total=len(prepared),
                    product_name=product_name,
                    website_url=website_url,
                    bg_hex=scene_bg,
                    accent_hex=base_accent,
                    card_hex=base_card,
                    media_size=media_dim,
                    is_video_media=is_video_media,
                )
                bg_layer = os_layers.bg_path
                float_a_layer = None
                float_b_layer = None
                title_layer = os_layers.title_path
                browser_layer = os_layers.browser_path
                info_layer = os_layers.info_path
                cta_btn_layer = os_layers.cta_btn_path
                progress_layer = os_layers.progress_path
                progress_box = os_layers.progress_box
                media_box = os_layers.media_box

            # Nạp input theo đúng thứ tự: 0=bg, sau đó audio + các lớp RGBA + media.
            idx = 0
            command += ["-loop", "1", "-framerate", str(fps), "-i", str(bg_layer)]
            bg_idx = idx
            idx += 1

            command += ["-i", str(item["audio"])]
            audio_input_index = idx
            idx += 1

            prog_idx: int | None = None
            if progress_layer is not None and progress_box is not None:
                command += ["-loop", "1", "-framerate", str(fps), "-i", str(progress_layer)]
                prog_idx = idx
                idx += 1

            float_a_idx: int | None = None
            if float_a_layer is not None:
                command += ["-loop", "1", "-framerate", str(fps), "-i", str(float_a_layer)]
                float_a_idx = idx
                idx += 1

            float_b_idx: int | None = None
            if float_b_layer is not None:
                command += ["-loop", "1", "-framerate", str(fps), "-i", str(float_b_layer)]
                float_b_idx = idx
                idx += 1

            title_idx: int | None = None
            if title_layer is not None:
                command += ["-loop", "1", "-framerate", str(fps), "-i", str(title_layer)]
                title_idx = idx
                idx += 1

            browser_idx: int | None = None
            media_idx: int | None = None
            if browser_layer is not None and media_box is not None and asset is not None:
                command += ["-loop", "1", "-framerate", str(fps), "-i", str(browser_layer)]
                browser_idx = idx
                idx += 1
                if is_still:
                    command += ["-i", str(asset)]
                else:
                    command += ["-stream_loop", "-1", "-i", str(asset)]
                media_idx = idx
                idx += 1

            info_idx: int | None = None
            if info_layer is not None:
                command += ["-loop", "1", "-framerate", str(fps), "-i", str(info_layer)]
                info_idx = idx
                idx += 1

            cta_btn_idx: int | None = None
            if cta_btn_layer is not None:
                command += ["-loop", "1", "-framerate", str(fps), "-i", str(cta_btn_layer)]
                cta_btn_idx = idx
                idx += 1

            filter_parts: list[str] = [f"[{bg_idx}:v]scale={width}:{height},fps={fps},format=rgba[s0]"]
            cur = "s0"
            step = 1
            slide_scale = (width / 1080.0) if height > width else (height / 1080.0)

            # 1. Thanh tiến độ sống chạy mượt 0% → 100% suốt cảnh
            if prog_idx is not None and progress_box is not None:
                px, py, pw, ph = progress_box
                nxt = f"s{step}"
                step += 1
                filter_parts.append(
                    f"color=c=black@0.0:s={pw}x{ph}:r={fps}:d={scene_dur:.3f},format=rgba[trk];"
                    f"[{prog_idx}:v]format=rgba[pfill];"
                    f"[trk][pfill]overlay=x='-w+w*min(1\\,t/{scene_dur:.3f})':y=0:shortest=1[pbar];"
                    f"[{cur}][pbar]overlay={px}:{py}:shortest=1[{nxt}]"
                )
                cur = nxt

            # 2. Title Card trượt từ trên xuống + fade-in mượt (0.00s → 0.32s)
            if title_idx is not None:
                nxt = f"s{step}"
                step += 1
                ty_expr = _ease_out_expr(0.0, 0.32, -round(64 * slide_scale))
                filter_parts.append(
                    f"[{title_idx}:v]format=rgba,fade=t=in:st=0.0:d=0.22:alpha=1[tlay];"
                    f"[{cur}][tlay]overlay=x=0:y='{ty_expr}':shortest=1[{nxt}]"
                )
                cur = nxt

            # 3. Browser/App Card + Media trượt cùng nhau từ dưới lên (0.08s → 0.42s) + Ken Burns / 1.45x demo
            if browser_idx is not None and media_idx is not None and media_box is not None:
                mx, my, mw, mh = media_box
                by_expr = _ease_out_expr(0.08, 0.34, round(68 * slide_scale))
                my_expr = _ease_out_expr(0.08, 0.34, round(68 * slide_scale), base_px=my)
                nxt1 = f"s{step}"
                step += 1
                nxt2 = f"s{step}"
                step += 1
                if is_still:
                    media_prep = f"scale={mw}:{mh}:flags=lanczos,setsar=1{_motion_filter(item['motion'], mw, mh, fps, scene_dur)},format=rgba,fade=t=in:st=0.08:d=0.22:alpha=1"
                else:
                    media_prep = f"setpts=0.69*PTS,scale={mw}:{mh}:flags=lanczos,setsar=1,fps={fps},format=rgba,fade=t=in:st=0.08:d=0.22:alpha=1"
                filter_parts.append(
                    f"[{browser_idx}:v]format=rgba,fade=t=in:st=0.08:d=0.22:alpha=1[blay];"
                    f"[{cur}][blay]overlay=x=0:y='{by_expr}':shortest=1[{nxt1}];"
                    f"[{media_idx}:v]{media_prep}[prod];"
                    f"[{nxt1}][prod]overlay=x={mx}:y='{my_expr}':shortest=1[{nxt2}]"
                )
                cur = nxt2

            # 4. Highlights Card (hoặc CTA Card) trượt từ dưới lên trễ nhịp (0.24s → 0.60s)
            if info_idx is not None:
                nxt = f"s{step}"
                step += 1
                st_info = 0.04 if browser_layer is None else 0.24
                iy_expr = _ease_out_expr(st_info, 0.36, round(82 * slide_scale))
                filter_parts.append(
                    f"[{info_idx}:v]format=rgba,fade=t=in:st={st_info:.2f}:d=0.24:alpha=1[ilay];"
                    f"[{cur}][ilay]overlay=x=0:y='{iy_expr}':shortest=1[{nxt}]"
                )
                cur = nxt

            # 5. Nút CTA bật trượt lên tiếp nhịp (0.34s → 0.66s)
            if cta_btn_idx is not None:
                nxt = f"s{step}"
                step += 1
                cy_expr = _ease_out_expr(0.34, 0.32, round(54 * slide_scale))
                filter_parts.append(
                    f"[{cta_btn_idx}:v]format=rgba,fade=t=in:st=0.34:d=0.20:alpha=1[clay];"
                    f"[{cur}][clay]overlay=x=0:y='{cy_expr}':shortest=1[{nxt}]"
                )
                cur = nxt

            # 6. Bong bóng icon mạng xã hội bay bồng bềnh liên tục lệch pha (chỉ cho template social-media)
            if float_a_idx is not None:
                nxt = f"s{step}"
                step += 1
                amp_a = max(6, round(13 * slide_scale))
                filter_parts.append(
                    f"[{float_a_idx}:v]format=rgba,fade=t=in:st=0.12:d=0.30:alpha=1[falay];"
                    f"[{cur}][falay]overlay=x=0:y='{amp_a}*sin(t*2.4)':shortest=1[{nxt}]"
                )
                cur = nxt
            if float_b_idx is not None:
                nxt = f"s{step}"
                step += 1
                amp_b = max(6, round(11 * slide_scale))
                filter_parts.append(
                    f"[{float_b_idx}:v]format=rgba,fade=t=in:st=0.22:d=0.30:alpha=1[fblay];"
                    f"[{cur}][fblay]overlay=x=0:y='{amp_b}*cos(t*2.0)':shortest=1[{nxt}]"
                )
                cur = nxt

            filter_parts.append(
                f"[{cur}]{template_filter},format=yuv420p,subtitles={_filter_path(ass)}{transition_filter}[video]"
            )
            filter_parts.append(
                f"[{audio_input_index}:a]apad=pad_dur={scene_dur:.3f}{audio_fade}[audio]"
            )
            video_filter = ";".join(filter_parts)
        else:
            if asset is None:
                command += [
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c=0x{scene_bg}:s={width}x{height}:r={fps}:d={scene_dur}",
                ]
            elif is_still:
                if not _image_has_content(asset):
                    raise RenderError(f"asset {item['asset_id']} là ảnh trắng hoặc không đọc được")
                real_media += 1
                unique_media.add(str(item["asset_id"]))
                if template not in PRO_TEMPLATES and item["motion"] != "none":
                    command += ["-i", str(asset)]
                else:
                    command += ["-loop", "1", "-framerate", str(fps), "-i", str(asset)]
            elif is_video_media:
                real_media += 1
                unique_media.add(str(item["asset_id"]))
                command += ["-stream_loop", "-1", "-i", str(asset)]
            else:
                raise RenderError(f"asset {item['asset_id']} có loại file chưa hỗ trợ")
            review_composite = template in PRO_TEMPLATES and asset is not None
            if review_composite:
                command += [
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c=0x{scene_bg}:s={width}x{height}:r={fps}:d={scene_dur}",
                ]
            audio_input_index = 2 if review_composite else 1
            command += ["-i", str(item["audio"])]

            is_portrait = height > width
            is_hd = max(width, height) >= 1600
            border_px = 4 if is_hd else 3
            shadow_offset = 10 if is_hd else 7
            is_light_bg = relative_luminance(f"#{scene_bg}") > 0.42
            shadow_color = "111827" if is_light_bg else "05070d"
            border_color = base_accent

            if asset is None and template in PRO_TEMPLATES:
                cta_w = round(width * (0.84 if is_portrait else 0.68))
                cta_h = round(height * (0.26 if is_portrait else 0.40))
                cta_x = (width - cta_w) // 2
                cta_y = (height - cta_h) // 2
                ribbon_h = max(14, round(height * (0.012 if is_portrait else 0.018)))
                visual_filter = (
                    f"scale={width}:{height},"
                    f"drawbox=x={cta_x + shadow_offset}:y={cta_y + shadow_offset}:w={cta_w}:h={cta_h}:color=0x{shadow_color}:t=fill,"
                    f"drawbox=x={cta_x}:y={cta_y}:w={cta_w}:h={cta_h}:color=0x{base_card}:t=fill,"
                    f"drawbox=x={cta_x}:y={cta_y}:w={cta_w}:h={ribbon_h}:color=0x{base_accent}:t=fill,"
                    f"drawbox=x={cta_x}:y={cta_y}:w={cta_w}:h={cta_h}:color=0x{border_color}:t={border_px},"
                    f"fps={fps}"
                )
                motion_filter = ""
            elif asset is None:
                visual_filter = f"scale={width}:{height},fps={fps}"
                motion_filter = ""
            elif template in PRO_TEMPLATES:
                src_w, src_h = _media_dimensions(asset, settings)
                zone_top = round(height * (0.25 if is_portrait else 0.19))
                zone_bottom = round(height * (0.76 if is_portrait else 0.84))
                bar_height = max(36, round(height * (0.028 if is_portrait else 0.042)))
                max_media_w = round(width * (0.86 if is_portrait else 0.72)) - border_px * 2
                max_media_h = max(120, (zone_bottom - zone_top) - bar_height - border_px * 2 - shadow_offset)
                fit_w, fit_h = _fit_box(src_w, src_h, max_media_w, max_media_h)
                card_w = fit_w + border_px * 2
                card_h = bar_height + fit_h + border_px * 2
                card_x = (width - card_w) // 2
                card_y = zone_top + max(0, ((zone_bottom - zone_top) - card_h) // 2)
                media_x = card_x + border_px
                media_y = card_y + bar_height + border_px
                dot = max(10, round(bar_height * 0.28))
                dot_y = card_y + border_px + (bar_height - dot) // 2
                dot_gap = dot + max(8, round(dot * 0.7))
                chrome_fill = base_card
                divider_color = base_accent
                shadow_draw = (
                    f"drawbox=x={card_x + shadow_offset}:y={card_y + shadow_offset}:w={card_w}:h={card_h}:"
                    f"color=0x{shadow_color}@0.45:t=fill,"
                )
                accent_strip_w = max(80, round(card_w * 0.22))
                accent_strip_h = max(8, round(dot * 0.75))
                accent_strip_x = card_x + card_w - border_px - accent_strip_w - 22
                accent_strip_y = card_y + border_px + (bar_height - accent_strip_h) // 2
                clip_speed = "setpts=0.72*PTS," if is_video_media else ""
                visual_filter = (
                    f"{clip_speed}scale={fit_w}:{fit_h}:flags=lanczos,setsar=1[product];"
                    f"[1:v]{shadow_draw}"
                    f"drawbox=x={card_x}:y={card_y}:w={card_w}:h={card_h}:color=0x{chrome_fill}:t=fill,"
                    f"drawbox=x={card_x + border_px}:y={card_y + border_px}:w={card_w - border_px * 2}:h={bar_height}:color=0x{chrome_fill}:t=fill,"
                    f"drawbox=x={card_x + border_px + 20}:y={dot_y}:w={dot}:h={dot}:color=0xff5f56:t=fill,"
                    f"drawbox=x={card_x + border_px + 20 + dot_gap}:y={dot_y}:w={dot}:h={dot}:color=0xffbd2e:t=fill,"
                    f"drawbox=x={card_x + border_px + 20 + dot_gap * 2}:y={dot_y}:w={dot}:h={dot}:color=0x27c93f:t=fill,"
                    f"drawbox=x={accent_strip_x}:y={accent_strip_y}:w={accent_strip_w}:h={accent_strip_h}:color=0x{base_accent}:t=fill,"
                    f"drawbox=x={card_x}:y={media_y - 3}:w={card_w}:h=3:color=0x{divider_color}:t=fill[canvas];"
                    f"[canvas][product]overlay={media_x}:{media_y},"
                    f"drawbox=x={card_x}:y={card_y}:w={card_w}:h={card_h}:color=0x{border_color}:t={border_px},"
                    f"fps={fps}"
                )
                motion_filter = ""
            else:
                visual_filter = (
                    f"split=2[bg][fg];"
                    f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},gblur=sigma=24[back];"
                    f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[front];"
                    f"[back][front]overlay=(W-w)/2:(H-h)/2,fps={fps}"
                )
                motion_filter = (
                    _motion_filter(item["motion"], width, height, fps, scene_dur)
                    if is_still and item["motion"] != "none"
                    else ""
                )
            video_filter = (
                f"[0:v]{visual_filter}{motion_filter},{template_filter},format=yuv420p,"
                f"subtitles={_filter_path(ass)}{transition_filter}[video];"
                f"[{audio_input_index}:a]apad=pad_dur={scene_dur:.3f}{audio_fade}[audio]"
            )
        command += [
            "-filter_complex",
            video_filter,
            "-map",
            "[video]",
            "-map",
            "[audio]",
            "-t",
            f"{scene_dur:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "fast" if template in PRO_TEMPLATES else "veryfast",
            "-crf",
            "19" if template in PRO_TEMPLATES else "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-threads",
            "2",
            str(scene_path),
        ]
        _run(command)
        files.append(scene_path)
        scene_durations.append(scene_dur)

    video = output_dir / "video.mp4"
    if use_xfade and len(files) > 1:
        # Chuyển cảnh mượt giữa các cảnh bằng xfade + acrossfade thay vì cắt cứng / tối đen.
        xfade_style = "smoothleft" if transition == "slide" else "fade"
        stitch_cmd = [settings.ffmpeg_bin, "-y", "-loglevel", "error"]
        for path in files:
            stitch_cmd += ["-i", str(path)]
        v_filters: list[str] = []
        a_filters: list[str] = []
        v_cur = "[0:v]"
        a_cur = "[0:a]"
        offset = scene_durations[0] - xfade_dur
        for idx in range(1, len(files)):
            v_next = f"[v{idx}]" if idx < len(files) - 1 else "[vout]"
            a_next = f"[a{idx}]" if idx < len(files) - 1 else "[aout]"
            v_filters.append(
                f"{v_cur}[{idx}:v]xfade=transition={xfade_style}:duration={xfade_dur:.3f}:offset={max(0.1, offset):.3f}{v_next}"
            )
            a_filters.append(
                f"{a_cur}[{idx}:a]acrossfade=d={xfade_dur:.3f}:c1=tri:c2=tri{a_next}"
            )
            v_cur, a_cur = v_next, a_next
            offset += scene_durations[idx] - xfade_dur
        stitch_cmd += [
            "-filter_complex",
            ";".join(v_filters + a_filters),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            "-threads",
            "2",
            str(video),
        ]
        _run(stitch_cmd)
    else:
        listing = output_dir / "scenes.ffconcat"
        listing.write_text(
            "ffconcat version 1.0\n"
            + "".join(f"file '{str(path.resolve()).replace('\\', '/')}'\n" for path in files),
            encoding="utf-8",
        )
        _run(
            [
                settings.ffmpeg_bin,
                "-y",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(video),
            ]
        )
    probe = _probe(settings, video)
    streams = probe.get("streams", [])
    video_stream = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio_stream = next((item for item in streams if item.get("codec_type") == "audio"), {})
    actual = float(probe.get("format", {}).get("duration", 0))
    technical = (
        video_stream.get("codec_name") == "h264"
        and audio_stream.get("codec_name") == "aac"
        and video_stream.get("width") == width
        and video_stream.get("height") == height
        and 5.0 <= actual < 60.0
    )
    required_unique = min(2, len(prepared))
    media_ok = real_media > 0 and len(unique_media) >= required_unique
    media_warnings: list[str] = []
    if real_media == 0:
        media_warnings.append("Chưa có ảnh/clip sản phẩm; không cho phát hành.")
    elif len(unique_media) < required_unique:
        media_warnings.append("Các cảnh đang lặp một tư liệu; cần ít nhất hai ảnh/clip sản phẩm.")
    manifest = {
        "video_path": str(video.resolve()),
        "duration_s": actual,
        "ratio": ratio,
        "resolution": f"{width}x{height}",
        "template": template,
        "palette": {
            "bg_color": f"#{base_bg.upper()}",
            "accent_color": f"#{base_accent.upper()}",
            "card_color": f"#{base_card.upper()}",
        },
        "transition": transition,
        "fit_mode": "contain",
        "tts_provider": tts_provider,
        "render_seconds": round(time.monotonic() - started, 3),
        "scenes": [
            {
                "scene_id": item["id"],
                "duration_s": round(item["duration"], 3),
                "asset_id": item["asset_id"],
                "motion": item["motion"],
                "graphics": item["graphics"],
                "has_product_media": item["asset"] is not None,
            }
            for item in prepared
        ],
        "qa": {
            "technical_passed": technical,
            "product_media_present": media_ok,
            "passed": technical and media_ok,
            "warnings": media_warnings,
        },
        "probe": probe,
    }
    (output_dir / "result_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return RenderResult(video=video, manifest=manifest)
