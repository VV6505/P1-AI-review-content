"""Cấu hình lớp gọi LLM (ADR-0002). Đè bằng biến môi trường `LLM_<TÊN_HOA>`.

Ví dụ `LLM_PROVIDER=fixture`, `LLM_RETRY_DELAYS_S=5,10,20`.

`GEMINI_API_KEY` giữ tên chuẩn của Google, không có tiền tố.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel

ENV_PREFIX = "LLM_"

# Giá niêm yết USD / 1M token (gói trả phí, Standard), tra 06/10/2026 tại
# https://ai.google.dev/gemini-api/docs/pricing. Giá output đã gồm thinking token.
# Free tier vẫn ghi giá niêm yết (quy ước #74): cost_usd là số quy đổi, không phải tiền đã trả.
PRICES_CHECKED_AT = "2026-10-06"
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.5-flash-lite": (0.30, 2.50),
}


class LLMSettings(BaseModel):
    # gemini: gọi API thật. fixture: đọc response đã lưu, không gọi mạng (CI, test).
    provider: Literal["gemini", "freemodel", "fixture"] = "gemini"
    model: str = "gemini-3.5-flash-lite"
    temperature: float = 0.0
    # Chặn trên output mỗi lời gọi, gồm cả thinking token (spike, mode batch).
    max_output_tokens: int = 16384
    timeout_s: float = 180.0
    # Chờ trước mỗi lần gọi lại khi 429 RPM / 500 / 503 (#70). Hết danh sách thì bỏ cuộc.
    retry_delays_s: tuple[float, ...] = (5, 10, 20, 40, 60)
    fixture_path: str = ""  # file JSON cho provider fixture (xem llm/fixture.py)
    api_key: str = ""  # GEMINI_API_KEY hoặc FREEMODEL_API_KEY theo provider
    base_url: str = "https://freemodel.in/v1"
    # FreeModel trả pricing qua /models nhưng worker không gọi discovery ở mỗi job. Cho phép cấu
    # hình giá model đang chọn; để 0 khi chỉ dùng free allowance/pilot.
    input_price_per_1m: float = 0.0
    output_price_per_1m: float = 0.0

    @property
    def prices(self) -> tuple[float, float]:
        """(giá input, giá output) USD / 1M token của model đang dùng."""
        if self.provider == "freemodel":
            return self.input_price_per_1m, self.output_price_per_1m
        if self.model not in MODEL_PRICES:
            raise ValueError(f"chưa có giá cho model {self.model!r}: thêm vào MODEL_PRICES")
        return MODEL_PRICES[self.model]

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LLMSettings:
        env = os.environ if env is None else env
        provider = env.get("LLM_PROVIDER", "gemini").strip().lower() or "gemini"
        values: dict[str, Any] = {
            "provider": provider,
            "api_key": (
                env.get("FREEMODEL_API_KEY", "")
                if provider == "freemodel"
                else env.get("GEMINI_API_KEY", "")
            ),
        }
        if provider == "freemodel" and not env.get("LLM_MODEL"):
            values["model"] = "gpt-6.1-sol"
        for name, field in cls.model_fields.items():
            raw = env.get(ENV_PREFIX + name.upper())
            if raw is None or name == "api_key":
                continue
            if field.annotation == tuple[float, ...]:
                # Nhận "5,10,20" hoặc JSON "[5, 10, 20]"
                values[name] = json.loads(raw) if raw.lstrip().startswith("[") else raw.split(",")
            else:
                values[name] = raw
        return cls(**values)
