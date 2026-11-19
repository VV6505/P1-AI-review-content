import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from worker.render.ffmpeg import RenderError, _display_headline, render_video
from worker.render.tts import FallbackTts, TtsError, split_tts_text
from worker.settings import Settings


class ToneTts:
    def synthesize(self, scene_id: str, text: str, output_dir: Path) -> tuple[Path, float]:
        del text
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"{scene_id}.wav"
        with wave.open(str(target), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\0\0" * 8000)
        return target, 1.0


class StubTts:
    def __init__(self, *, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.calls: list[str] = []

    def synthesize(self, scene_id: str, text: str, output_dir: Path) -> tuple[Path, float]:
        del text
        self.calls.append(scene_id)
        if scene_id == self.fail_on:
            raise TtsError("provider tạm lỗi")
        return output_dir / f"{scene_id}.wav", 1.0


def test_video_headlines_use_approved_copy_instead_of_internal_roles() -> None:
    script = {
        "hook": {"text": "Ảnh quá nặng, website tải mãi chưa xong?"},
        "cta": {"text": "Khám phá Squoosh để nén ảnh của bạn."},
    }
    assert _display_headline({"role": "hook"}, script, {}, "Lời đọc") == script["hook"]["text"]
    assert _display_headline({"role": "cta"}, script, {}, "Lời đọc") == script["cta"]["text"]
    assert _display_headline({"role": "demo"}, script, {}, "Kéo ảnh vào Squoosh") == "Kéo ảnh vào Squoosh"


def test_tts_text_is_split_on_safe_boundaries() -> None:
    text = "Câu thứ nhất khá dài nhưng vẫn phải dễ nghe. " * 12
    chunks = split_tts_text(text)
    assert len(chunks) > 1
    assert all(chunk and len(chunk) <= 160 for chunk in chunks)
    assert " ".join(chunks) == " ".join(text.split())


def test_fallback_tts_recreates_every_scene_with_one_provider(tmp_path: Path) -> None:
    primary = StubTts(fail_on="s02")
    fallback = StubTts()
    result = FallbackTts(primary, fallback).synthesize_all(
        [("s01", "Một"), ("s02", "Hai"), ("s03", "Ba")], tmp_path
    )
    assert set(result) == {"s01", "s02", "s03"}
    assert primary.calls == ["s01", "s02"]
    assert fallback.calls == ["s01", "s02", "s03"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg chưa cài")
@pytest.mark.parametrize(
    ("ratio", "resolution", "template", "expected_resolution", "expected_fps"),
    [
        ("16:9", "720p", "cinematic", "1280x720", "24/1"),
        ("9:16", "720p", "cinematic", "720x1280", "24/1"),
        ("9:16", "1080p", "review-pro", "1080x1920", "30/1"),
        ("9:16", "720p", "reels-aurora", "720x1280", "30/1"),
    ],
)
def test_ffmpeg_renderer_outputs_qa_video(
    tmp_path: Path,
    ratio: str,
    resolution: str,
    template: str,
    expected_resolution: str,
    expected_fps: str,
) -> None:
    images = [tmp_path / "product-a.png", tmp_path / "product-b.png"]
    for index, image in enumerate(images):
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"{'testsrc' if index == 0 else 'testsrc2'}=size=320x180:rate=1",
                "-frames:v",
                "1",
                str(image),
            ],
            check=True,
        )
    scenes = []
    for index in range(1, 5):
        scenes.append(
            {
                "scene_id": f"s{index:02}",
                "role": "hook" if index == 1 else "cta" if index == 4 else "demo",
                "narration_segments": [
                    {"segment_id": f"s{index:02}-u01", "text": f"Tìm kiếm kết quả cảnh số {index}"}
                ],
                "subtitle_text": f"Cảnh số {index}",
                "visual_plan": {"asset_id": f"product-image-{(index - 1) % 2}"},
            }
        )
    result = render_video(
        {"scenes": scenes},
        {
            "aspect_ratio": ratio,
            "resolution": resolution,
            "template": template,
            "asset_paths": {
                "product-image-0": str(images[0]),
                "product-image-1": str(images[1]),
            },
        },
        tmp_path / "output",
        Settings(page_store_dir=str(tmp_path)),
        ToneTts(),
    )
    assert result.video.is_file()
    assert result.manifest["qa"]["passed"] is True
    assert result.manifest["resolution"] == expected_resolution
    assert result.manifest["fit_mode"] == "contain"
    if template in {"review-pro", "reels-aurora"}:
        assert result.manifest["scenes"][0]["graphics"]["card"] == "hook"
        assert result.manifest["scenes"][0]["graphics"]["badge"] == "TÌM KIẾM"
        assert result.manifest["scenes"][-1]["graphics"]["card"] == "cta"
    video_stream = next(
        stream for stream in result.manifest["probe"]["streams"]
        if stream["codec_type"] == "video"
    )
    assert video_stream["r_frame_rate"] == expected_fps
    assert 5.0 <= result.manifest["duration_s"] < 60.0
    # Lời test ngắn không bị ép kéo lên 40 giây; các cảnh giữ đúng thời lượng nội dung.
    durations = [scene["duration_s"] for scene in result.manifest["scenes"]]
    assert max(durations) - min(durations) < 0.01


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg chưa cài")
def test_renderer_combines_browser_clip_and_motion_image(tmp_path: Path) -> None:
    clip = tmp_path / "agent.webm"
    image = tmp_path / "product.png"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
            "testsrc2=size=640x360:rate=24", "-t", "2", "-c:v", "libvpx", str(clip),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
            "testsrc=size=640x360:rate=1", "-frames:v", "1", str(image),
        ],
        check=True,
    )
    result = render_video(
        {
            "scenes": [
                {
                    "scene_id": "s01",
                    "narration_segments": [{"text": "Clip thao tác sản phẩm"}],
                    "visual_plan": {"asset_id": "agent-clip"},
                },
                {
                    "scene_id": "s02",
                    "narration_segments": [{"text": "Ảnh giới thiệu sản phẩm"}],
                    "visual_plan": {"asset_id": "product-image"},
                },
            ]
        },
        {
            "aspect_ratio": "9:16",
            "asset_paths": {"agent-clip": str(clip), "product-image": str(image)},
            "scene_overrides": {"s02": {"motion": "pan_right"}},
        },
        tmp_path / "output",
        Settings(page_store_dir=str(tmp_path)),
        ToneTts(),
    )
    assert result.manifest["qa"]["passed"] is True
    assert result.manifest["scenes"][0]["asset_id"] == "agent-clip"
    assert result.manifest["scenes"][1]["motion"] == "pan_right"


def test_renderer_rejects_asset_outside_worker_store(tmp_path: Path) -> None:
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"not-read")
    with pytest.raises(RenderError, match="ngoài kho tư liệu"):
        render_video(
            {
                "scenes": [
                    {
                        "scene_id": "s01",
                        "narration_segments": [{"segment_id": "u1", "text": "Xin chào"}],
                        "visual_plan": {"asset_id": "outside"},
                    }
                ]
            },
            {"asset_paths": {"outside": str(outside)}},
            tmp_path / "output",
            Settings(page_store_dir=str(tmp_path / "allowed")),
            ToneTts(),
        )
