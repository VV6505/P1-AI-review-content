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

from worker.render.tts import FallbackTts, Synthesizer
from worker.settings import Settings


PRO_TEMPLATES = {
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


def _display_headline(
    scene: dict[str, Any], script: dict[str, Any], override: dict[str, Any], narration: str
) -> str:
    """Dùng câu người xem hiểu được, không đưa role nội bộ lên video."""
    role = str(scene.get("role") or "").lower()
    approved = script.get("hook") if role == "hook" else script.get("cta") if role == "cta" else None
    approved_text = approved.get("text") if isinstance(approved, dict) else None
    candidate = (
        override.get("headline")
        or approved_text
        or scene.get("subtitle_text")
        or narration
    )
    words = str(candidate or "").strip().split()
    headline = " ".join(words[:11])
    if len(words) > 11:
        headline += "…"
    return headline[:90]


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
) -> None:
    size = 42 if height <= 1280 else 58
    margin = 90 if height > width else 60
    style_by_template = {
        "short-countdown": ("Arial", "&H00FFFFFF", "&H00111827"),
        "cinematic": ("Arial", "&H00FFFFFF", "&H00101824"),
        "animation": ("Arial", "&H00FFFFFF", "&H00601F74"),
        "vintage": ("Georgia", "&H00E8E0C8", "&H0033261B"),
        "review-pro": ("Arial", "&H00FFFFFF", "&H00101917"),
        "reels-aurora": ("Arial", "&H00FFFFFF", "&H00351016"),
        "reels-editorial": ("Arial", "&H0028231F", "&H00EFE9DF"),
        "reels-neon": ("Arial", "&H00FFFFFF", "&H00120907"),
        "reels-comparison": ("Arial", "&H00FFFFFF", "&H00181907"),
    }
    font, primary, outline = style_by_template.get(template, style_by_template["cinematic"])
    style_format = (
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
    )
    caption_size = 64 if template == "short-countdown" and height > 1280 else (52 if template in PRO_TEMPLATES and height > 1280 else size)
    style = (
        f"Style: Caption,{font},{caption_size},{primary},&H000000FF,{outline},&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,3,1,2,{margin},{margin},{margin},1"
    )
    headline_primary = "&H0028231F" if template == "reels-editorial" else "&H00FFFFFF"
    headline_outline = "&H00EFE9DF" if template == "reels-editorial" else "&H00101917"
    headline_style = (
        f"Style: Headline,{font},{76 if height > 1280 else 48},{headline_primary},"
        f"&H000000FF,{headline_outline},&H80000000,-1,0,0,0,100,100,0,0,1,3,1,8,70,70,110,1"
    )
    accent_hex = TEMPLATE_PALETTES.get(template, ("111827", "8ee8bc", "15231d"))[1]
    accent_ass = _ass_color(accent_hex)
    badge_style = (
        f"Style: Badge,{font},{34 if height > 1280 else 24},{accent_ass},&H000000FF,"
        f"{headline_outline},&HAA101917,-1,0,0,0,100,100,1,0,3,1,0,7,70,70,70,1"
    )
    card_style = (
        f"Style: Card,{font},{58 if height > 1280 else 38},{headline_primary},&H000000FF,"
        f"{accent_ass},&HD0101917,-1,0,0,0,100,100,0,0,3,3,1,5,90,90,120,1"
    )
    events: list[str] = []
    if template in PRO_TEMPLATES:
        if template == "short-countdown":
            number = str(graphics.get("countdown", ""))
            if number:
                events.append(
                    f"Dialogue: 1,0:00:00.00,{_ass_time(duration)},Headline,,0,0,0,,"
                    f"{{\\an7\\pos(95,145)\\fs220\\bord5\\c&H00FFFFFF&\\fad(100,150)}}{_ass_escape(number)}"
                )
        card = str(graphics.get("card", "feature"))
        if card in {"hook", "cta", "comparison", "countdown"}:
            end = min(duration, 3.2 if card == "hook" else duration)
            start = 0.0 if card == "hook" else max(0.0, duration - 3.6)
            events.append(
                f"Dialogue: 3,{_ass_time(start)},{_ass_time(end)},Card,,0,0,0,,"
                f"{{\\fad(180,220)}}{_ass_escape(headline)}"
            )
        else:
            events.append(
                f"Dialogue: 1,0:00:00.00,{_ass_time(duration)},Headline,,0,0,0,,"
                f"{{\\fad(180,180)}}{_ass_escape(headline)}"
            )
        events.append(
            f"Dialogue: 4,0:00:00.25,{_ass_time(min(duration, 3.8))},Badge,,0,0,0,,"
            f"{{\\fad(120,180)}}{_ass_escape(str(graphics.get('icon_glyph', '✦')))}  "
            f"{_ass_escape(str(graphics.get('badge', 'ĐIỂM NỔI BẬT')))}"
        )
        chunks = _caption_chunks(text, target_words=4 if template in {"animation", "short-countdown"} else 7)
        chunk_duration = duration / max(1, len(chunks))
        for index, chunk in enumerate(chunks):
            start = index * chunk_duration
            end = min(duration, (index + 1) * chunk_duration + 0.08)
            entrance = (
                r"{\fad(70,90)\fscx88\fscy88\t(0,140,\fscx100\fscy100)}"
                if template in {"animation", "short-countdown"}
                else r"{\fad(100,100)}"
            )
            events.append(
                f"Dialogue: 2,{_ass_time(start)},{_ass_time(end)},Caption,,0,0,0,,"
                f"{entrance}{_highlight_ass(chunk, list(graphics.get('keywords', [])), accent_ass)}"
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
    """Ken Burns nhẹ cho ảnh tĩnh; giữ mức zoom nhỏ để sản phẩm vẫn nằm trong khung."""
    frames = max(1, round(duration * fps))
    center_x = "iw/2-(iw/zoom/2)"
    center_y = "ih/2-(ih/zoom/2)"
    if style == "zoom_out":
        zoom = "if(eq(on,0),1.06,max(1.0,zoom-0.00055))"
        x, y = center_x, center_y
    elif style == "pan_left":
        zoom = "1.06"
        x, y = f"(iw-iw/zoom)*(1-on/{frames})", center_y
    elif style == "pan_right":
        zoom = "1.06"
        x, y = f"(iw-iw/zoom)*(on/{frames})", center_y
    elif style == "none":
        return ""
    else:
        zoom = "min(zoom+0.00055,1.06)"
        x, y = center_x, center_y
    return f",zoompan=z='{zoom}':x='{x}':y='{y}':d=1:s={width}x{height}:fps={fps}"


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
    transition = options.get("transition", "fade")
    if transition not in {"fade", "none"}:
        raise RenderError("transition chỉ nhận fade hoặc none")
    colors = {
        "cinematic": "111827",
        "animation": "312e81",
        "vintage": "3f2d20",
        **{name: palette[0] for name, palette in TEMPLATE_PALETTES.items()},
    }
    color = colors.get(template, colors["cinematic"])
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
                "audio": audio,
                "speech": speech,
                "duration": max(4.0, speech + 0.55),
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
        prepared[-1]["graphics"] = _graphic_cues(
            prepared[-1]["role"], prepared[-1]["headline"], narration
        )
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
    accent_for_icons = TEMPLATE_PALETTES.get(template, ("111827", "8ee8bc", "15231d"))[1]
    icon_paths = _rasterize_lucide_icons(
        {str(item["graphics"].get("icon", "")) for item in prepared},
        output_dir / "graphics",
        accent_for_icons,
    )
    for item in prepared:
        scene_path = scene_dir / f"{item['id']}.mp4"
        ass = scene_dir / f"{item['id']}.ass"
        _ass(
            ass,
            item["subtitle"],
            item["headline"],
            width,
            height,
            item["duration"],
            template,
            item["graphics"],
        )
        asset: Path | None = item["asset"]
        command = [settings.ffmpeg_bin, "-y", "-loglevel", "error"]
        if asset is None:
            command += [
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x{color}:s={width}x{height}:r={fps}:d={item['duration']}",
            ]
        elif asset.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            if not _image_has_content(asset):
                raise RenderError(f"asset {item['asset_id']} là ảnh trắng hoặc không đọc được")
            real_media += 1
            unique_media.add(str(item["asset_id"]))
            command += ["-loop", "1", "-framerate", str(fps), "-i", str(asset)]
        elif asset.suffix.lower() in {".mp4", ".webm", ".mov", ".mkv"}:
            real_media += 1
            unique_media.add(str(item["asset_id"]))
            command += ["-stream_loop", "-1", "-i", str(asset)]
        else:
            raise RenderError(f"asset {item['asset_id']} có loại file chưa hỗ trợ")
        review_composite = template in PRO_TEMPLATES and asset is not None
        if review_composite:
            background, _, _ = TEMPLATE_PALETTES[template]
            if template == "short-countdown":
                background = ("facc15", "1e293b", "0f766e", "6b21a8", "9a3412")[len(files) % 5]
            command += [
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x{background}:s={width}x{height}:r={fps}:d={item['duration']}",
            ]
        audio_input_index = 2 if review_composite else 1
        command += ["-i", str(item["audio"])]
        icon_name = str(item["graphics"].get("icon", ""))
        icon_path = icon_paths.get(icon_name)
        icon_input_index = audio_input_index + 1
        if icon_path is not None:
            command += ["-loop", "1", "-i", str(icon_path)]
        template_filter = {
            "short-countdown": "eq=contrast=1.08:saturation=1.12",
            "cinematic": "eq=contrast=1.08:saturation=1.05",
            "animation": "eq=contrast=1.04:saturation=1.18",
            "vintage": "colorchannelmixer=.393:.769:.189:.349:.686:.168:.272:.534:.131",
            "review-pro": "eq=contrast=1.06:saturation=1.08",
            "reels-aurora": "eq=contrast=1.05:saturation=1.14",
            "reels-editorial": "eq=contrast=1.03:saturation=.90:brightness=.02",
            "reels-neon": "eq=contrast=1.12:saturation=1.18",
            "reels-comparison": "eq=contrast=1.07:saturation=1.10",
        }[template]
        transition_filter = ""
        audio_fade = ""
        if transition == "fade":
            fade_out = max(0.0, float(item["duration"]) - 0.35)
            transition_filter = f",fade=t=out:st={fade_out:.3f}:d=0.35"
            audio_fade = (
                f",afade=t=in:st=0:d=0.2,afade=t=out:st={fade_out:.3f}:d=0.3"
            )
        if asset is None:
            visual_filter = f"scale={width}:{height},fps={fps}"
        elif template in PRO_TEMPLATES:
            _, accent, chrome = TEMPLATE_PALETTES[template]
            viewport_width = round(width * 0.86)
            viewport_height = round(height * (0.54 if height > width else 0.68))
            viewport_y = round(height * (0.22 if height > width else 0.16))
            viewport_x = (width - viewport_width) // 2
            bar_height = max(34, round(height * 0.028))
            dot = max(9, round(bar_height * 0.28))
            visual_filter = (
                f"scale={viewport_width}:{viewport_height}:force_original_aspect_ratio=decrease,"
                "setsar=1[product];"
                f"[1:v][product]overlay=(W-w)/2:{viewport_y}+({viewport_height}-h)/2,"
                f"drawbox=x={viewport_x}:y={viewport_y}:w={viewport_width}:h={viewport_height}:"
                f"color=0x{accent}@0.62:t=4,"
                f"drawbox=x={viewport_x}:y={viewport_y}:w={viewport_width}:h={bar_height}:"
                f"color=0x{chrome}:t=fill,"
                f"drawbox=x={viewport_x + 22}:y={viewport_y + (bar_height-dot)//2}:w={dot}:h={dot}:color=0xff6b6b:t=fill,"
                f"drawbox=x={viewport_x + 22 + dot + 12}:y={viewport_y + (bar_height-dot)//2}:w={dot}:h={dot}:color=0xffd166:t=fill,"
                f"drawbox=x={viewport_x + 22 + (dot + 12)*2}:y={viewport_y + (bar_height-dot)//2}:w={dot}:h={dot}:color=0x4ade80:t=fill,"
                f"fps={fps}"
            )
        else:
            # Nền blur lấp đầy khung dọc, lớp trước vẫn contain nên không cắt mất sản phẩm.
            visual_filter = (
                f"split=2[bg][fg];"
                f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},gblur=sigma=24[back];"
                f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[front];"
                f"[back][front]overlay=(W-w)/2:(H-h)/2,fps={fps}"
            )
        is_still = asset is not None and asset.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        motion_filter = (
            _motion_filter(item["motion"], width, height, fps, float(item["duration"]))
            if is_still and template not in PRO_TEMPLATES
            else ""
        )
        # Không vẽ focus/click ở tọa độ cố định: chỉ clip Agent thật mới có thao tác.
        graphic_filter = ""
        visual_chain = (
            f"[0:v]{visual_filter}"
            if template not in PRO_TEMPLATES or asset is None
            else f"[0:v]{visual_filter}"
        )
        if icon_path is not None:
            icon_size = max(48, round(min(width, height) * 0.10))
            icon_x = round(width * 0.11)
            icon_y = round(height * 0.065)
            video_filter = (
                f"{visual_chain}{motion_filter}{graphic_filter},{template_filter},format=yuv420p,"
                f"subtitles={_filter_path(ass)}{transition_filter}[base];"
                f"[{icon_input_index}:v]scale={icon_size}:{icon_size},format=rgba[icon];"
                f"[base][icon]overlay={icon_x}:{icon_y}:shortest=1:"
                f"enable='between(t,0.15,3.8)'[video];"
                f"[{audio_input_index}:a]apad=pad_dur={item['duration']}{audio_fade}[audio]"
            )
        else:
            video_filter = (
                f"{visual_chain}{motion_filter}{graphic_filter},{template_filter},format=yuv420p,"
                f"subtitles={_filter_path(ass)}{transition_filter}[video];"
                f"[{audio_input_index}:a]apad=pad_dur={item['duration']}{audio_fade}[audio]"
            )
        command += [
            "-filter_complex",
            video_filter,
            "-map",
            "[video]",
            "-map",
            "[audio]",
            "-t",
            f"{item['duration']:.3f}",
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
    listing = output_dir / "scenes.ffconcat"
    listing.write_text(
        "ffconcat version 1.0\n"
        + "".join(f"file '{str(path.resolve()).replace('\\', '/')}'\n" for path in files),
        encoding="utf-8",
    )
    video = output_dir / "video.mp4"
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
