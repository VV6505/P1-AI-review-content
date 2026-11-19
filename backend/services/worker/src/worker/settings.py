"""Cấu hình và khoá API của worker (một chỗ duy nhất). Đọc từ biến môi trường, không đọc file.

Quy tắc:
- Giá trị thật chỉ nằm trong `.env` (đã gitignore) hoặc biến môi trường của nơi chạy. Không commit,
không ghi vào workflow n8n.
- Mọi khoá là `SecretStr`: `repr()`, log và lỗi chỉ in `**********`. Chỉ gọi `.get_secret_value()`
ngay tại chỗ gửi request.
- Thiếu khoá thì báo tên biến thiếu (không bao giờ in giá trị) qua `Settings.require(...)` →
`MissingConfigError`.

`GEMINI_API_KEY`, `FAL_KEY`, `CLOUDFLARE_*` giữ tên chuẩn của nhà cung cấp, không có tiền tố.
Hướng dẫn lưu khoá, hạn mức và cách xoay khoá: `docs/specs/p1-secrets-and-quota.md`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, SecretStr

# Biến môi trường mà từng bước cần. Bước nào thiếu thì báo trước khi gọi, không đợi provider trả
# 401.
STEP_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "api": ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"),
    "api_service": ("N8N_SERVICE_TOKEN",),
    "runner": ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"),
    "extract": ("GEMINI_API_KEY",),
    "script": ("GEMINI_API_KEY",),
    "ai_scene": ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"),
}


class MissingConfigError(RuntimeError):
    """Thiếu biến môi trường. Chỉ chứa tên biến, không chứa giá trị."""

    def __init__(self, names: Sequence[str]) -> None:
        self.names = tuple(names)
        super().__init__("thiếu cấu hình: " + ", ".join(self.names))


class CostLimitExceededError(RuntimeError):
    def __init__(self, cost_usd: float, limit_usd: float) -> None:
        self.cost_usd = cost_usd
        self.limit_usd = limit_usd
        super().__init__(f"chi phí {cost_usd:.6f} USD vượt ngưỡng {limit_usd:.6f} USD của một job")


class Settings(BaseModel):
    # Chế độ demo local: giữ nguyên API contract nhưng lưu vào JSON thay cho Supabase. Chỉ bật
    # khi người phát triển chủ động đặt LOCAL_P1_MODE=1; không được dùng ở production.
    local_p1_mode: bool = False
    local_data_dir: str = "./data/local-p1"
    local_auth_dir: str = "./data/local-p1/auth"
    local_owner_id: str = "00000000-0000-4000-8000-000000000001"
    # Supabase. URL local mặc định của `supabase start`. Khoá anon dùng khi đọc thay mặt người
    # dùng (RLS);
    # khoá service_role chỉ ở server, không bao giờ gửi cho FE.
    supabase_url: str = ""
    supabase_anon_key: SecretStr = SecretStr("")
    supabase_service_role_key: SecretStr = SecretStr("")
    # Token chung để n8n gọi các endpoint dịch vụ (header X-Service-Token). Để trống = tắt các
    # endpoint đó.
    n8n_service_token: SecretStr = SecretStr("")
    # Nhà cung cấp (chỉ cần khi chạy bước tương ứng).
    gemini_api_key: SecretStr = SecretStr("")
    freemodel_api_key: SecretStr = SecretStr("")
    fal_key: SecretStr = SecretStr("")
    cloudflare_account_id: SecretStr = SecretStr("")
    cloudflare_api_token: SecretStr = SecretStr("")
    # Ngưỡng chi phí một job (USD, giá niêm yết). None = không chặn. Vượt ngưỡng thì job
    # `failed` với lỗi rõ.
    job_cost_limit_usd: float | None = None
    http_timeout_s: float = 15.0
    # Bộ chạy job (`python -m worker.runner`): thư mục lưu markdown trang crawl, chu kỳ hỏi hàng
    # đợi, số lần chạy tối đa mỗi job (kể cả lần đầu), thời gian chờ cơ sở giữa các lần retry.
    page_store_dir: str = "./data/pages"
    runner_poll_interval_s: float = 5.0
    runner_max_attempts: int = 3
    runner_retry_backoff_s: float = 30.0
    video_output_dir: str = "./data/videos"
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    tts_provider: str = "edge"
    tts_voice: str = "vi-VN-HoaiMyNeural"
    gemini_tts_model: str = "gemini-2.5-flash-preview-tts"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        limit = env.get("JOB_COST_LIMIT_USD", "").strip()
        return cls(
            local_p1_mode=env.get("LOCAL_P1_MODE", "").strip().lower()
            in {"1", "true", "yes", "on"},
            local_data_dir=env.get("LOCAL_P1_DATA_DIR", "").strip() or "./data/local-p1",
            local_auth_dir=env.get("LOCAL_P1_AUTH_DIR", "").strip() or "./data/local-p1/auth",
            local_owner_id=env.get("LOCAL_P1_OWNER_ID", "").strip()
            or "00000000-0000-4000-8000-000000000001",
            supabase_url=env.get("SUPABASE_URL", "").strip().rstrip("/"),
            supabase_anon_key=SecretStr(env.get("SUPABASE_ANON_KEY", "").strip()),
            supabase_service_role_key=SecretStr(env.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()),
            n8n_service_token=SecretStr(env.get("N8N_SERVICE_TOKEN", "").strip()),
            gemini_api_key=SecretStr(env.get("GEMINI_API_KEY", "").strip()),
            freemodel_api_key=SecretStr(env.get("FREEMODEL_API_KEY", "").strip()),
            fal_key=SecretStr(env.get("FAL_KEY", "").strip()),
            cloudflare_account_id=SecretStr(env.get("CLOUDFLARE_ACCOUNT_ID", "").strip()),
            cloudflare_api_token=SecretStr(env.get("CLOUDFLARE_API_TOKEN", "").strip()),
            job_cost_limit_usd=float(limit) if limit else None,
            http_timeout_s=float(env.get("WORKER_HTTP_TIMEOUT_S", "15") or 15),
            page_store_dir=env.get("WORKER_PAGE_STORE_DIR", "").strip() or "./data/pages",
            runner_poll_interval_s=float(env.get("RUNNER_POLL_INTERVAL_S", "5") or 5),
            runner_max_attempts=int(env.get("RUNNER_MAX_ATTEMPTS", "3") or 3),
            runner_retry_backoff_s=float(env.get("RUNNER_RETRY_BACKOFF_S", "30") or 30),
            video_output_dir=env.get("VIDEO_OUTPUT_DIR", "").strip() or "./data/videos",
            ffmpeg_bin=env.get("FFMPEG_BIN", "").strip() or "ffmpeg",
            ffprobe_bin=env.get("FFPROBE_BIN", "").strip() or "ffprobe",
            tts_provider=env.get("TTS_PROVIDER", "edge").strip().lower() or "edge",
            tts_voice=env.get("TTS_VOICE", "vi-VN-HoaiMyNeural").strip() or "vi-VN-HoaiMyNeural",
            gemini_tts_model=env.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts").strip()
            or "gemini-2.5-flash-preview-tts",
        )

    def _value(self, env_name: str) -> str:
        field = env_name.lower()
        raw = getattr(self, field)
        return raw.get_secret_value() if isinstance(raw, SecretStr) else str(raw)

    def missing(self, *steps: str) -> list[str]:
        """Tên biến còn trống của các bước (xem `STEP_REQUIREMENTS`), không trùng lặp, giữ
        thứ tự."""
        names: list[str] = []
        for step in steps:
            if step not in STEP_REQUIREMENTS:
                raise KeyError(f"bước không có trong STEP_REQUIREMENTS: {step}")
            # Local P1 thay Supabase bằng LocalDatabase; các provider AI vẫn phải có key riêng.
            requirements = STEP_REQUIREMENTS[step]
            if self.local_p1_mode and step in {"api", "runner"}:
                requirements = tuple(n for n in requirements if not n.startswith("SUPABASE_"))
            names.extend(n for n in requirements if not self._value(n))
        return list(dict.fromkeys(names))

    def require(self, *steps: str) -> None:
        names = self.missing(*steps)
        if names:
            raise MissingConfigError(names)

    def check_cost(self, cost_usd: float) -> None:
        """Raise `CostLimitExceededError` nếu chi phí job vượt ngưỡng đã đặt."""
        limit = self.job_cost_limit_usd
        if limit is not None and cost_usd > limit:
            raise CostLimitExceededError(cost_usd, limit)
