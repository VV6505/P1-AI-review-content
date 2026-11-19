"""`cost_breakdown` v1 (docs/specs/contracts/cost-breakdown.v1.schema.json) ở dạng Pydantic.

Worker chỉ ghi cột này; DB tự cộng tokens/cost. Retry = thêm item, `attempt` tăng dần.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CostItem(BaseModel):
    """1 lần gọi provider. Khớp `$defs/Item` của schema v1.

    `extra="forbid"` tương ứng `additionalProperties: false`.
    """

    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(min_length=1)
    category: Literal["llm", "tts", "video_provider", "other"]
    step: str | None = None
    provider: str | None = None
    model: str | None = None
    attempt: int = Field(ge=1)
    cache_hit: bool
    tokens_in: int | None = Field(default=None, ge=0)
    tokens_out: int | None = Field(default=None, ge=0)
    unit_price_in_per_1m: float | None = Field(default=None, ge=0)
    unit_price_out_per_1m: float | None = Field(default=None, ge=0)
    prices_checked_at: str | None = None
    cost_usd: float = Field(ge=0)
    tokens_in_cached: int | None = Field(default=None, ge=0)
    unit_price_cached_in_per_1m: float | None = Field(default=None, ge=0)
    cost_status: Literal["exact", "estimated"]

    @model_validator(mode="after")
    def contract_rules(self) -> CostItem:
        if self.category == "llm":
            required = (
                "step", "provider", "model", "tokens_in", "tokens_out", "unit_price_in_per_1m",
                "unit_price_out_per_1m", "prices_checked_at",
            )  # fmt: skip
            missing = [f for f in required if getattr(self, f) is None]
            if missing:
                raise ValueError(f"item llm thiếu {missing}")
        if self.cache_hit and (self.cost_usd != 0 or self.tokens_in or self.tokens_out):
            raise ValueError("cache_hit thì cost_usd, tokens_in, tokens_out phải là 0")
        return self


class CostBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    currency: Literal["USD"] = "USD"
    items: list[CostItem] = Field(default_factory=list)

    def dump(self) -> dict:
        """Dict để ghi vào jsonb: bỏ trường None (schema không cho null)."""
        return self.model_dump(exclude_none=True)


def new_call_id() -> str:
    return str(uuid.uuid4())


def llm_cost_usd(
    tokens_in: int, tokens_out: int, price_in_per_1m: float, price_out_per_1m: float
) -> float:
    """Làm tròn 6 chữ số như contract yêu cầu."""
    return round((tokens_in * price_in_per_1m + tokens_out * price_out_per_1m) / 1_000_000, 6)
