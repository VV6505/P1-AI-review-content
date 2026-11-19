"""Adapter LLM: retry theo loại lỗi, ghi `cost_breakdown` cho mỗi lần gọi, trả JSON đã parse.

Transport (gemini.py, fixture.py) chỉ làm 1 lần gọi và ném `ProviderError`. Mọi retry nằm ở đây,
SDK không tự retry, để `attempt` và số item chi phí khớp số lần gọi thật.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from worker.m1.llm.config import PRICES_CHECKED_AT, LLMSettings
from worker.m1.llm.cost import CostItem, llm_cost_usd, new_call_id
from worker.m1.llm.errors import LLMError, LLMErrorCode, ProviderError
from worker.m1.llm.quota import classify_429, next_daily_reset, retry_delay_s

RETRY_STATUS = frozenset({500, 502, 503, 504})  # gateway/upstream tạm lỗi: chờ rồi gọi lại
OK_FINISH = frozenset({"", "STOP"})


@dataclass
class RawResponse:
    """Kết quả 1 lần gọi thành công. Token None = provider không trả usage."""

    text: str
    tokens_in: int | None
    tokens_out: int | None  # candidates + thinking (cả hai tính giá output)
    thoughts_tokens: int = 0
    finish_reason: str = ""


class Transport(Protocol):
    provider: str

    async def generate(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        response_schema: dict[str, Any],
        temperature: float,
        max_output_tokens: int,
    ) -> RawResponse:
        """Gọi 1 lần. Lỗi thì ném `ProviderError`."""
        ...


@dataclass
class LLMResult:
    data: dict[str, Any]
    raw: RawResponse
    cost_items: list[CostItem] = field(default_factory=list)
    attempts: int = 1
    wait_seconds: float = 0.0


Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class LLM:
    def __init__(
        self,
        transport: Transport,
        settings: LLMSettings,
        *,
        sleep: Sleep = asyncio.sleep,
        now: Clock = _utc_now,
    ) -> None:
        self.transport = transport
        self.settings = settings
        self.model = settings.model
        self._prices = settings.prices  # kiểm có giá ngay khi tạo, không đợi tới lúc gọi
        self._sleep = sleep
        self._now = now

    def _item(self, step: str, attempt: int, raw: RawResponse | None) -> CostItem:
        """Lần lỗi (raw None): token 0, cost 0, estimated. Lần thành công có usage: exact."""
        tin = raw.tokens_in if raw else None
        tout = raw.tokens_out if raw else None
        exact = tin is not None and tout is not None
        tin, tout = tin or 0, tout or 0
        p_in, p_out = self._prices
        return CostItem(
            call_id=new_call_id(),
            category="llm",
            step=step,
            provider=self.transport.provider,
            model=self.model,
            attempt=attempt,
            cache_hit=False,
            tokens_in=tin,
            tokens_out=tout,
            unit_price_in_per_1m=p_in,
            unit_price_out_per_1m=p_out,
            prices_checked_at=PRICES_CHECKED_AT,
            cost_usd=llm_cost_usd(tin, tout, p_in, p_out),
            cost_status="exact" if exact else "estimated",
        )

    async def generate_json(
        self, *, step: str, system: str, prompt: str, response_schema: dict[str, Any]
    ) -> LLMResult:
        """Gọi structured output, trả JSON đã parse. Lỗi cuối cùng → `LLMError` (kèm cost_items)."""
        s = self.settings
        items: list[CostItem] = []
        waited = 0.0
        attempt = 0
        while True:
            attempt += 1
            try:
                raw = await self.transport.generate(
                    model=self.model,
                    system=system,
                    prompt=prompt,
                    response_schema=response_schema,
                    temperature=s.temperature,
                    max_output_tokens=s.max_output_tokens,
                )
            except ProviderError as e:
                items.append(self._item(step, attempt, None))
                code, delay = self._classify(e, attempt)
                if code is LLMErrorCode.QUOTA_DAILY:
                    raise LLMError(
                        code,
                        e.message,
                        retry_after=next_daily_reset(self._now()),
                        cost_items=items,
                    ) from e
                if delay is None:
                    raise LLMError(code, e.message, cost_items=items) from e
                await self._sleep(delay)
                waited += delay
                continue
            items.append(self._item(step, attempt, raw))
            break

        if raw.finish_reason not in OK_FINISH:
            raise LLMError(
                LLMErrorCode.INVALID_OUTPUT, f"finish_reason={raw.finish_reason}", cost_items=items
            )
        try:
            data = json.loads(raw.text)
        except json.JSONDecodeError as e:
            raise LLMError(LLMErrorCode.INVALID_OUTPUT, f"json: {e}", cost_items=items) from e
        if not isinstance(data, dict):
            raise LLMError(LLMErrorCode.INVALID_OUTPUT, "json không phải object", cost_items=items)
        return LLMResult(data, raw, items, attempt, waited)

    def _classify(self, e: ProviderError, attempt: int) -> tuple[LLMErrorCode, float | None]:
        """Trả (mã lỗi nếu bỏ cuộc, số giây chờ nếu còn được retry)."""
        delays = self.settings.retry_delays_s
        left = attempt <= len(delays)  # lần thứ n lỗi thì chờ delays[n-1]
        if e.status_code == 429:
            if classify_429(e.details, e.message) == "rpd":
                return LLMErrorCode.QUOTA_DAILY, None
            if not left:
                return LLMErrorCode.RATE_LIMITED, None
            delay = delays[attempt - 1]
            hint = retry_delay_s(e.details)  # provider gợi ý chờ lâu hơn thì theo, tối đa 60 s
            return LLMErrorCode.RATE_LIMITED, max(delay, min(hint or 0, 60.0))
        if e.status_code is None or e.status_code in RETRY_STATUS:
            return LLMErrorCode.UNAVAILABLE, delays[attempt - 1] if left else None
        return LLMErrorCode.REQUEST_FAILED, None
