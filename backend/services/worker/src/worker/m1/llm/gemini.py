"""Transport Gemini: nơi duy nhất import `google-genai` (ADR-0002). 1 lần gọi, không retry."""

from __future__ import annotations

from typing import Any

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from worker.m1.llm.client import RawResponse
from worker.m1.llm.errors import ProviderError

# Đường async của SDK dùng aiohttp nếu import được (Crawl4AI kéo theo), không thì httpx.
# Lỗi mạng / timeout của cả hai đều đổi thành ProviderError(None) để được retry và ghi chi phí.
_NETWORK_ERRORS: tuple[type[BaseException], ...] = (httpx.HTTPError, TimeoutError, OSError)
try:
    import aiohttp

    _NETWORK_ERRORS += (aiohttp.ClientError,)
except ImportError:  # pragma: no cover
    pass


class GeminiTransport:
    provider = "google"

    def __init__(self, api_key: str, timeout_s: float) -> None:
        if not api_key:
            raise ValueError("thiếu GEMINI_API_KEY (đặt trong .env, xem .env.example)")
        # attempts=1: SDK không tự retry. Retry do LLM (client.py) làm để đếm đúng từng lần gọi.
        http = types.HttpOptions(
            timeout=int(timeout_s * 1000), retry_options=types.HttpRetryOptions(attempts=1)
        )
        self._client = genai.Client(api_key=api_key, http_options=http)

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
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
            response_json_schema=response_schema,
        )
        try:
            resp = await self._client.aio.models.generate_content(
                model=model, contents=prompt, config=cfg
            )
        except genai_errors.APIError as e:
            raise ProviderError(e.code, e.message or str(e), e.details) from e
        except _NETWORK_ERRORS as e:  # mạng, timeout
            raise ProviderError(None, f"{type(e).__name__}: {e}") from e
        usage = resp.usage_metadata
        thoughts = (usage.thoughts_token_count or 0) if usage else 0
        finish = resp.candidates[0].finish_reason if resp.candidates else None
        return RawResponse(
            text=resp.text or "",
            tokens_in=usage.prompt_token_count if usage else None,
            tokens_out=((usage.candidates_token_count or 0) + thoughts) if usage else None,
            thoughts_tokens=thoughts,
            finish_reason=getattr(finish, "name", str(finish or "")),
        )
