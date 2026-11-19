"""Mã lỗi của lớp gọi LLM. Hàng đợi BE đọc `code`, `retryable` và `retry_after`.

Adapter đã tự retry 429 RPM / 500 / 503 trong lần chạy. Lỗi trả ra ngoài là lỗi còn lại sau đó.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from worker.m1.llm.cost import CostItem


class LLMErrorCode(StrEnum):
    # 429 do hết quota ngày (RPD). Không retry ngay: job chờ tới `retry_after`
    # (0h giờ Thái Bình Dương).
    QUOTA_DAILY = "llm_quota_daily"
    # 429 do vượt RPM, đã retry hết lịch backoff mà vẫn bị.
    RATE_LIMITED = "llm_rate_limited"
    # 500 / 503 hoặc lỗi mạng, đã retry hết lịch backoff.
    UNAVAILABLE = "llm_unavailable"
    # Lỗi khác của provider (400, 401, 403, 404...). Không retry.
    REQUEST_FAILED = "llm_request_failed"
    # Response không dùng được: bị cắt (MAX_TOKENS), bị chặn, không phải JSON hoặc sai schema.
    INVALID_OUTPUT = "llm_invalid_output"

    @property
    def retryable(self) -> bool:
        return self in _RETRYABLE


_RETRYABLE = frozenset(
    {LLMErrorCode.QUOTA_DAILY, LLMErrorCode.RATE_LIMITED, LLMErrorCode.UNAVAILABLE}
)


class LLMError(Exception):
    """Lỗi cuối cùng của 1 lời gọi.

    `cost_items` gồm mọi lần thử (kể cả lần lỗi), để job lỗi vẫn ghi được chi phí.
    """

    def __init__(
        self,
        code: LLMErrorCode,
        detail: str = "",
        *,
        retry_after: datetime | None = None,
        cost_items: list[CostItem] | None = None,
    ) -> None:
        super().__init__(f"{code.value}: {detail}" if detail else code.value)
        self.code = code
        self.detail = detail
        self.retry_after = retry_after
        self.cost_items: list[CostItem] = list(cost_items or [])

    @property
    def retryable(self) -> bool:
        return self.code.retryable

    @property
    def message(self) -> str:
        return str(self)


class ProviderError(Exception):
    """Lỗi của 1 lần gọi transport (chưa phân loại). `details` là JSON lỗi provider trả về."""

    def __init__(self, status_code: int | None, message: str, details: object = None) -> None:
        super().__init__(f"{status_code} {message}")
        self.status_code = status_code  # None = lỗi mạng / timeout
        self.message = message
        self.details = details
