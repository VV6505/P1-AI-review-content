"""Transport cho FreeModel/OpenAI-compatible; một lần gọi, retry do ``LLM`` quản lý."""

from __future__ import annotations

import json
from typing import Any

import httpx

from worker.m1.llm.client import RawResponse
from worker.m1.llm.errors import ProviderError


class OpenAICompatibleTransport:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_s: float,
        provider: str = "openai_compatible",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("thiếu FREEMODEL_API_KEY (đặt trong .env, không đưa vào FE)")
        self.provider = provider
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

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
        # FreeModel công bố capability json_mode theo từng model. Schema vẫn được chèn vào system
        # để model biết contract đầy đủ; validator nội bộ tiếp tục là cổng quyết định cuối cùng.
        schema_text = json.dumps(response_schema, ensure_ascii=False, separators=(",", ":"))
        body = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        system
                        + "\n\nChỉ trả một JSON object tuân thủ chính xác JSON Schema sau; "
                        + "không markdown, không lời dẫn:\n"
                        + schema_text
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        except (httpx.HTTPError, TimeoutError, OSError) as exc:
            raise ProviderError(None, f"{type(exc).__name__}: {exc}") from exc
        if response.is_error:
            try:
                error_doc: object = response.json()
            except ValueError:
                error_doc = {"body": response.text[:500]}
            message = self._error_message(error_doc) or f"HTTP {response.status_code}"
            retry_after = response.headers.get("Retry-After")
            details = {"provider_error": error_doc, "retry_after": retry_after}
            raise ProviderError(response.status_code, message, details)
        try:
            doc = response.json()
            choice = doc["choices"][0]
            content = choice["message"]["content"]
            usage = doc.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                502, "FreeModel trả response không đúng dạng chat completions"
            ) from exc
        if not isinstance(content, str):
            raise ProviderError(502, "FreeModel không trả nội dung text")
        return RawResponse(
            text=content,
            tokens_in=self._integer(usage.get("prompt_tokens")),
            tokens_out=self._integer(usage.get("completion_tokens")),
            finish_reason=str(choice.get("finish_reason") or "").upper(),
        )

    @staticmethod
    def _integer(value: object) -> int | None:
        return value if isinstance(value, int) and value >= 0 else None

    @staticmethod
    def _error_message(doc: object) -> str:
        if not isinstance(doc, dict):
            return ""
        error = doc.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
        return str(doc.get("message") or "")
