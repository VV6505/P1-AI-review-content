"""Vietnamese TTS adapters with deterministic file caching."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Any, Protocol

from worker.settings import Settings


class TtsError(RuntimeError):
    pass


class Synthesizer(Protocol):
    def synthesize(self, scene_id: str, text: str, output_dir: Path) -> tuple[Path, float]: ...


class FallbackTts:
    """Dùng một provider duy nhất cho toàn video, tránh đổi giọng giữa các cảnh."""

    def __init__(self, primary: Synthesizer, fallback: Synthesizer) -> None:
        self.primary = primary
        self.fallback = fallback

    def synthesize(self, scene_id: str, text: str, output_dir: Path) -> tuple[Path, float]:
        try:
            return self.primary.synthesize(scene_id, text, output_dir)
        except TtsError:
            return self.fallback.synthesize(scene_id, text, output_dir)

    def synthesize_all(
        self, items: list[tuple[str, str]], output_dir: Path
    ) -> dict[str, tuple[Path, float]]:
        try:
            return {
                scene_id: self.primary.synthesize(scene_id, text, output_dir)
                for scene_id, text in items
            }
        except TtsError:
            # Một cảnh lỗi thì dựng lại tất cả bằng provider dự phòng. Không trộn giọng.
            return {
                scene_id: self.fallback.synthesize(scene_id, text, output_dir)
                for scene_id, text in items
            }


def split_tts_text(text: str, max_chars: int = 160) -> list[str]:
    """Chia lời dài ở biên câu/từ để Edge không trả ``NoAudioReceived``."""
    units = re.split(r"(?<=[.!?…])\s+", text.strip())
    chunks: list[str] = []
    for unit in units:
        words = unit.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = word
            else:
                current = candidate
        if current:
            if chunks and len(chunks[-1]) + 1 + len(current) <= max_chars:
                chunks[-1] = f"{chunks[-1]} {current}"
            else:
                chunks.append(current)
    return chunks


def duration_s(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as audio:
            if audio.getframerate() <= 0 or audio.getnframes() <= 0:
                raise TtsError("TTS trả về WAV rỗng")
            return audio.getnframes() / audio.getframerate()
    except (OSError, EOFError, wave.Error) as exc:
        raise TtsError("TTS trả về WAV không hợp lệ") from exc


class EdgeTts:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def synthesize(self, scene_id: str, text: str, output_dir: Path) -> tuple[Path, float]:
        output_dir.mkdir(parents=True, exist_ok=True)
        wav = output_dir / f"{scene_id}.wav"
        meta = output_dir / f"{scene_id}.json"
        key = hashlib.sha256(f"edge\n{self.settings.tts_voice}\n{text}".encode()).hexdigest()
        try:
            saved = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        if saved.get("cache_key") == key and wav.is_file():
            return wav, duration_s(wav)
        parts = [
            output_dir / f"{scene_id}-{index:02}.mp3"
            for index, _ in enumerate(split_tts_text(text), 1)
        ]
        listing = output_dir / f"{scene_id}.ffconcat"
        try:
            chunks = split_tts_text(text)
            if not chunks:
                raise TtsError("Edge TTS không nhận được lời đọc")
            for chunk, mp3 in zip(chunks, parts, strict=True):
                last_error: subprocess.CalledProcessError | None = None
                for attempt in range(3):
                    try:
                        subprocess.run(
                            [
                                sys.executable,
                                "-m",
                                "edge_tts",
                                "--voice",
                                self.settings.tts_voice,
                                "--text",
                                chunk,
                                "--write-media",
                                str(mp3),
                            ],
                            check=True,
                            capture_output=True,
                            text=True,
                            timeout=180,
                        )
                        last_error = None
                        break
                    except subprocess.CalledProcessError as exc:
                        last_error = exc
                        if attempt < 2:
                            time.sleep(attempt + 1)
                if last_error is not None:
                    detail = (last_error.stderr or last_error.stdout or str(last_error))[-500:]
                    raise TtsError(f"Edge TTS không trả audio: {detail}") from last_error
            listing.write_text(
                "ffconcat version 1.0\n"
                + "".join(f"file '{str(part.resolve()).replace('\\', '/')}'\n" for part in parts),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    self.settings.ffmpeg_bin,
                    "-y",
                    "-loglevel",
                    "error",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(listing),
                    "-ac",
                    "1",
                    "-ar",
                    "24000",
                    str(wav),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except TtsError:
            raise
        except (OSError, subprocess.SubprocessError) as exc:
            raise TtsError(f"Edge TTS thất bại: {str(exc)[:300]}") from exc
        finally:
            listing.unlink(missing_ok=True)
            for part in parts:
                part.unlink(missing_ok=True)
        length = duration_s(wav)
        meta.write_text(
            json.dumps(
                {"cache_key": key, "provider": "edge", "voice": self.settings.tts_voice},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return wav, length


class GoogleTranslateTts:
    """TTS tiếng Việt miễn phí, không cần key; dùng làm dự phòng cho Edge."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def synthesize(self, scene_id: str, text: str, output_dir: Path) -> tuple[Path, float]:
        from gtts import gTTS

        output_dir.mkdir(parents=True, exist_ok=True)
        wav = output_dir / f"{scene_id}.wav"
        mp3 = output_dir / f"{scene_id}-google.mp3"
        meta = output_dir / f"{scene_id}.json"
        key = hashlib.sha256(f"gtts\nvi\n{text}".encode()).hexdigest()
        try:
            saved = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        if saved.get("cache_key") == key and wav.is_file():
            return wav, duration_s(wav)
        try:
            gTTS(text=text, lang="vi").save(str(mp3))
            subprocess.run(
                [
                    self.settings.ffmpeg_bin,
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(mp3),
                    "-ac",
                    "1",
                    "-ar",
                    "24000",
                    str(wav),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            raise TtsError(f"TTS dự phòng Google thất bại: {str(exc)[:300]}") from exc
        finally:
            mp3.unlink(missing_ok=True)
        length = duration_s(wav)
        meta.write_text(
            json.dumps(
                {"cache_key": key, "provider": "google-translate", "language": "vi"},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return wav, length


class GeminiTts:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        if not settings.gemini_api_key.get_secret_value():
            raise TtsError("TTS Gemini cần GEMINI_API_KEY")
        self.settings = settings
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.settings.gemini_api_key.get_secret_value())
        return self._client

    def synthesize(self, scene_id: str, text: str, output_dir: Path) -> tuple[Path, float]:
        output_dir.mkdir(parents=True, exist_ok=True)
        wav = output_dir / f"{scene_id}.wav"
        meta = output_dir / f"{scene_id}.json"
        key = hashlib.sha256(
            f"gemini\n{self.settings.gemini_tts_model}\n{self.settings.tts_voice}\n{text}".encode()
        ).hexdigest()
        try:
            saved = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        if saved.get("cache_key") == key and wav.is_file():
            return wav, duration_s(wav)
        try:
            interaction = self.client.interactions.create(
                model=self.settings.gemini_tts_model,
                input=text,
                response_format={"type": "audio"},
                generation_config={"speech_config": [{"voice": self.settings.tts_voice}]},
                timeout=180,
            )
            raw = interaction.output_audio.data
            audio = raw if isinstance(raw, bytes) else base64.b64decode(raw, validate=True)
            wav.write_bytes(audio)
        except Exception as exc:
            message = str(exc).replace(self.settings.gemini_api_key.get_secret_value(), "***")
            raise TtsError(f"Gemini TTS thất bại: {message[:300]}") from exc
        length = duration_s(wav)
        meta.write_text(
            json.dumps(
                {"cache_key": key, "provider": "gemini", "model": self.settings.gemini_tts_model},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return wav, length


def make_tts(settings: Settings) -> Synthesizer:
    if settings.tts_provider == "gemini":
        return GeminiTts(settings)
    if settings.tts_provider == "edge":
        return FallbackTts(EdgeTts(settings), GoogleTranslateTts(settings))
    raise TtsError("TTS_PROVIDER chỉ hỗ trợ edge hoặc gemini")
