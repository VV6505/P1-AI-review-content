"""Cổng sinh script (M2). API chỉ biết Protocol này; adapter mặc định là `GeminiScriptGenerator`.

Thiếu cấu hình LLM thì `get_script_generator()` trả None → endpoint trả 503 rõ ràng, không đoán.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from worker.m1.llm import LLMErrorCode, make_llm
from worker.m2.generate import M2ErrorCode, generate_script


@dataclass
class GeneratedScript:
    content: dict[str, Any]  # script_revisions.content (script M2 đã qua validator)
    report: dict[str, Any] = field(default_factory=dict)  # validator, các tầng, cảnh báo
    cost_breakdown: dict[str, Any] = field(default_factory=dict)


class ScriptGenerationError(Exception):
    """Sinh script thất bại. `invalid`: LLM trả script không đạt validator sau lượt sửa."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        invalid: bool = False,
        cost_breakdown: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.invalid = invalid
        self.cost_breakdown = cost_breakdown or {}


class ScriptGenerator(Protocol):
    async def __call__(self, m2_input: dict[str, Any]) -> GeneratedScript:
        """`m2_input` theo `p1-ac-03-input.v1`. Lỗi thì raise `ScriptGenerationError`."""
        ...


class GeminiScriptGenerator:
    """Adapter mặc định: `generate_script` của M2 (sinh + tối đa 1 lượt sửa), provider theo
    `LLM_PROVIDER`. Lỗi validator/schema (`m2_input_invalid`, `llm_invalid_output`) là `invalid`
    (422); lỗi provider (429, 5xx, timeout) là 502 kèm `retryable`.
    """

    async def __call__(self, m2_input: dict[str, Any]) -> GeneratedScript:
        try:
            llm = make_llm()
        except ValueError as e:  # cấu hình LLM sai: không retry
            raise ScriptGenerationError(f"cấu hình LLM không hợp lệ: {e}") from e
        res = await generate_script(m2_input, llm)
        if res.status == "completed" and res.data is not None:
            return GeneratedScript(
                content=res.data,
                report={"warnings": res.warnings, "stages": res.stages},
                cost_breakdown=res.cost_breakdown,
            )
        code = res.error_code or "unknown"
        detail = "; ".join(res.errors[:5])
        message = f"{code}: {res.error_message or ''}" + (f" ({detail})" if detail else "")
        raise ScriptGenerationError(
            message,
            retryable=res.retryable,
            invalid=code in (M2ErrorCode.INPUT_INVALID.value, LLMErrorCode.INVALID_OUTPUT.value),
            cost_breakdown=res.cost_breakdown,
        )
