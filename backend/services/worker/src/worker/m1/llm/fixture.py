"""Transport fixture (`LLM_PROVIDER=fixture`): đọc response đã lưu, không gọi mạng (CI, test).

File JSON `{"responses": [...]}`. Mỗi lần gọi lấy phần tử kế tiếp, hết thì báo lỗi. Một phần tử là:
- thành công: `{"text": "<json>", "usage_metadata": {"prompt_token_count": ..,
  "candidates_token_count": .., "thoughts_token_count": ..}, "finish_reason": "STOP"}`;
  có thể dùng `"data": {...}` thay cho `"text"`;
- lỗi: `{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "..", "details": [..]}}`,
  cùng dạng JSON lỗi của Gemini. `"code": null` = lỗi mạng.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worker.m1.llm.client import RawResponse
from worker.m1.llm.errors import ProviderError


class FixtureTransport:
    provider = "google"  # fixture đứng thay Gemini; item chi phí vẫn ghi provider/model như thật

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []  # tham số từng lần gọi, để test kiểm prompt

    @classmethod
    def from_file(cls, path: str | Path) -> FixtureTransport:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(doc["responses"])

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
        self.calls.append({"model": model, "system": system, "prompt": prompt})
        if len(self.calls) > len(self._responses):
            raise RuntimeError(f"fixture hết response (đã gọi {len(self.calls)} lần)")
        r = self._responses[len(self.calls) - 1]
        if "error" in r:
            err = r["error"]
            raise ProviderError(err.get("code"), err.get("message", ""), {"error": err})
        usage = r.get("usage_metadata")
        text = r["text"] if "text" in r else json.dumps(r["data"], ensure_ascii=False)
        thoughts = (usage.get("thoughts_token_count") or 0) if usage else 0
        return RawResponse(
            text=text,
            tokens_in=usage.get("prompt_token_count") if usage else None,
            tokens_out=((usage.get("candidates_token_count") or 0) + thoughts) if usage else None,
            thoughts_tokens=thoughts,
            finish_reason=r.get("finish_reason", "STOP"),
        )
