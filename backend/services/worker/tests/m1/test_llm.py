"""Test adapter LLM bằng transport fixture: retry, quota ngày, cost_breakdown. Không gọi mạng."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import aiohttp
import httpx
import pytest
from google.genai import errors as genai_errors
from pydantic import ValidationError

from worker.m1.llm import LLM, LLMError, LLMErrorCode, LLMSettings, ProviderError, make_llm
from worker.m1.llm.cost import CostBreakdown, CostItem
from worker.m1.llm.fixture import FixtureTransport
from worker.m1.llm.gemini import GeminiTransport
from worker.m1.llm.openai_compatible import OpenAICompatibleTransport
from worker.m1.llm.quota import classify_429, next_daily_reset

FIXTURES = Path(__file__).parent / "fixtures" / "llm"
REPO = Path(__file__).resolve().parents[4]
CONTRACT_EXAMPLES = REPO / "docs" / "specs" / "contracts" / "examples"
NOW = datetime(2026, 10, 21, 3, 0, tzinfo=UTC)  # 10h sáng giờ Việt Nam


def load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


RPD = load("error-429-rpd.json")
RPM = load("error-429-rpm.json")
OK = {
    "data": {"ok": True},
    "usage_metadata": {"prompt_token_count": 1000, "candidates_token_count": 200},
    "finish_reason": "STOP",
}


def err(code: int | None, message: str = "boom") -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def run(responses: list[dict[str, Any]], **settings: Any) -> tuple[Any, list[float]]:
    """Chạy 1 lời gọi; trả (LLMResult hoặc LLMError, danh sách giây đã chờ)."""
    slept: list[float] = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)

    llm = LLM(
        FixtureTransport(responses),
        LLMSettings(provider="fixture", **settings),
        sleep=fake_sleep,
        now=lambda: NOW,
    )

    async def call() -> Any:
        try:
            return await llm.generate_json(
                step="extract", system="s", prompt="p", response_schema={}
            )
        except LLMError as e:
            return e

    return asyncio.run(call()), slept


def test_thanh_cong_ghi_1_item_exact_theo_gia_niem_yet() -> None:
    res, slept = run([OK])
    assert res.data == {"ok": True}
    assert slept == []
    [item] = res.cost_items
    assert item.attempt == 1 and item.cost_status == "exact"
    assert (item.tokens_in, item.tokens_out) == (1000, 200)
    assert item.cost_usd == round((1000 * 0.30 + 200 * 2.50) / 1e6, 6)
    assert item.model == "gemini-3.5-flash-lite" and item.provider == "google"


def test_429_rpm_retry_theo_backoff_roi_thanh_cong() -> None:
    res, slept = run([RPM, RPM, RPM, OK])
    assert res.data == {"ok": True}
    # RetryInfo gợi ý 7s: lần đầu chờ max(5, 7)
    assert slept == [7, 10, 20]
    assert [i.attempt for i in res.cost_items] == [1, 2, 3, 4]
    assert [i.cost_status for i in res.cost_items] == ["estimated"] * 3 + ["exact"]
    assert all(i.cost_usd == 0 and i.tokens_in == 0 for i in res.cost_items[:3])
    assert len({i.call_id for i in res.cost_items}) == 4


def test_429_rpm_het_lich_backoff_tra_llm_rate_limited() -> None:
    res, slept = run([RPM] * 6)
    assert isinstance(res, LLMError)
    assert res.code is LLMErrorCode.RATE_LIMITED and res.retryable
    assert slept == [7, 10, 20, 40, 60]
    assert len(res.cost_items) == 6


def test_429_rpd_khong_retry_tra_llm_quota_daily_kem_retry_after() -> None:
    res, slept = run([RPD, OK])
    assert isinstance(res, LLMError)
    assert res.code is LLMErrorCode.QUOTA_DAILY and res.retryable
    assert slept == []  # không chờ trong worker: hàng đợi BE đưa job về chờ
    # NOW = 20h ngày 20/10 giờ PT, còn giờ mùa hè (PDT, UTC-7):
    # 0h PT ngày 21/10 = 07:00 UTC = 14h giờ Việt Nam
    assert res.retry_after == datetime(2026, 10, 21, 7, 0, tzinfo=UTC)
    [item] = res.cost_items
    assert item.cost_usd == 0 and item.cost_status == "estimated"


def test_gio_reset_rpd_sau_khi_het_gio_mua_he() -> None:
    # Giờ mùa hè ở Mỹ hết 01/11/2026 → PST (UTC-8): 0h PT = 08:00 UTC = 15h giờ Việt Nam
    # 10h sáng 05/11 giờ VN = 19h ngày 04/11 giờ PT → reset 0h PT ngày 05/11
    assert next_daily_reset(datetime(2026, 11, 5, 3, 0, tzinfo=UTC)) == datetime(
        2026, 11, 5, 8, 0, tzinfo=UTC
    )
    # Đúng 0h PT thì reset kế tiếp là ngày hôm sau
    assert next_daily_reset(datetime(2026, 11, 6, 8, 0, tzinfo=UTC)) == datetime(
        2026, 11, 7, 8, 0, tzinfo=UTC
    )


def test_nhan_dien_rpd_rpm_theo_noi_dung_loi() -> None:
    assert classify_429(RPD) == "rpd"
    assert classify_429(RPM) == "rpm"
    # Không có QuotaFailure: dựa vào message
    assert classify_429({"error": {"message": "Quota exceeded: requests per day"}}) == "rpd"
    assert classify_429({"error": {"message": "Resource has been exhausted"}}) == "rpm"
    assert classify_429(None, "") == "rpm"


@pytest.mark.parametrize("code", [500, 503, None])
def test_5xx_va_loi_mang_retry_roi_thanh_cong(code: int | None) -> None:
    res, slept = run([err(code), err(code), OK])
    assert res.data == {"ok": True}
    assert slept == [5, 10]
    assert [i.attempt for i in res.cost_items] == [1, 2, 3]


def test_5xx_het_lich_backoff_tra_llm_unavailable() -> None:
    res, slept = run([err(503)] * 6)
    assert isinstance(res, LLMError)
    assert res.code is LLMErrorCode.UNAVAILABLE and res.retryable
    assert len(res.cost_items) == 6 and len(slept) == 5


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_loi_khac_khong_retry(code: int) -> None:
    res, slept = run([err(code), OK])
    assert isinstance(res, LLMError)
    assert res.code is LLMErrorCode.REQUEST_FAILED and not res.retryable
    assert slept == [] and len(res.cost_items) == 1


def test_response_bi_cat_hoac_khong_phai_json_tra_llm_invalid_output_van_co_chi_phi() -> None:
    cut = {**OK, "finish_reason": "MAX_TOKENS"}
    bad = {"text": "{not json", "usage_metadata": OK["usage_metadata"]}
    for r in (cut, bad):
        res, _ = run([r])
        assert isinstance(res, LLMError) and res.code is LLMErrorCode.INVALID_OUTPUT
        assert not res.retryable
        [item] = res.cost_items
        assert item.cost_status == "exact" and item.tokens_in == 1000


def test_khong_co_usage_thi_estimated() -> None:
    res, _ = run([{"data": {"ok": True}}])
    assert res.cost_items[0].cost_status == "estimated"


def test_settings_doc_tu_env() -> None:
    s = LLMSettings.from_env(
        {"LLM_PROVIDER": "fixture", "LLM_RETRY_DELAYS_S": "1,2", "GEMINI_API_KEY": "k"}
    )
    assert s.provider == "fixture" and s.retry_delays_s == (1, 2) and s.api_key == "k"
    with pytest.raises(ValueError, match="chưa có giá"):
        _ = LLMSettings(model="unknown-model").prices


def test_settings_freemodel_reads_its_own_key_and_default_model() -> None:
    s = LLMSettings.from_env(
        {"LLM_PROVIDER": "freemodel", "FREEMODEL_API_KEY": "fm_test"}
    )
    assert s.provider == "freemodel"
    assert s.api_key == "fm_test"
    assert s.model == "gpt-6.1-sol"
    assert s.prices == (0.0, 0.0)


# ---------------------------------------------------------------- contract cost_breakdown v1
@pytest.mark.skipif(not CONTRACT_EXAMPLES.exists(), reason="cần thư mục docs của repo")
def test_cost_item_khop_vi_du_contract_v1() -> None:
    for path in sorted(CONTRACT_EXAMPLES.glob("valid-*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if "items" in doc:
            CostBreakdown.model_validate(doc)
    for name in (
        "invalid-cache-hit-with-cost.json",
        "invalid-llm-missing-model.json",
        "invalid-missing-call-id.json",
        "invalid-missing-cost-status.json",
    ):
        doc = json.loads((CONTRACT_EXAMPLES / name).read_text(encoding="utf-8"))
        with pytest.raises(ValidationError):
            CostBreakdown.model_validate(doc)


def test_item_cua_adapter_hop_le_contract_va_bo_truong_none() -> None:
    res, _ = run([RPM, OK])
    dumped = CostBreakdown(items=res.cost_items).dump()
    assert all(None not in item.values() for item in dumped["items"])
    CostBreakdown.model_validate(dumped)
    with pytest.raises(ValidationError):  # additionalProperties: false
        CostItem.model_validate({**dumped["items"][0], "usage_unit": "token"})


# ---------------------------------------------------------------- transport Gemini, factory
class _RaisingModels:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    async def generate_content(self, **_: Any) -> Any:
        raise self.exc


def _gemini_error(exc: BaseException) -> ProviderError:
    """Gọi GeminiTransport với client giả ném `exc`; không gọi mạng."""
    t = GeminiTransport(api_key="test-key", timeout_s=1)
    t._client = SimpleNamespace(aio=SimpleNamespace(models=_RaisingModels(exc)))  # type: ignore[assignment]

    async def call() -> ProviderError:
        try:
            await t.generate(
                model="m",
                system="s",
                prompt="p",
                response_schema={},
                temperature=0,
                max_output_tokens=1,
            )
        except ProviderError as e:
            return e
        raise AssertionError("không ném ProviderError")

    return asyncio.run(call())


def test_gemini_doi_loi_sdk_va_loi_mang_thanh_provider_error() -> None:
    e = _gemini_error(genai_errors.ClientError(429, RPD))
    assert e.status_code == 429 and classify_429(e.details) == "rpd"
    for exc in (aiohttp.ClientConnectionError("down"), TimeoutError(), httpx.ConnectError("x")):
        assert _gemini_error(exc).status_code is None


def test_make_llm_fixture_doc_file(tmp_path: Path) -> None:
    path = tmp_path / "fx.json"
    path.write_text(json.dumps({"responses": [RPM, OK]}), encoding="utf-8")
    llm = make_llm(LLMSettings(provider="fixture", fixture_path=str(path)))
    assert isinstance(llm.transport, FixtureTransport)
    with pytest.raises(ValueError, match="LLM_FIXTURE_PATH"):
        make_llm(LLMSettings(provider="fixture"))


def test_freemodel_transport_uses_json_mode_and_parses_usage() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://freemodel.in/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer fm_test"
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        assert "JSON Schema" in body["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            },
        )

    transport = OpenAICompatibleTransport(
        api_key="fm_test",
        base_url="https://freemodel.in/v1/",
        timeout_s=1,
        provider="freemodel",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    raw = asyncio.run(
        transport.generate(
            model="gpt-6-luna",
            system="system",
            prompt="prompt",
            response_schema={"type": "object"},
            temperature=0,
            max_output_tokens=100,
        )
    )
    assert raw.text == '{"ok":true}'
    assert (raw.tokens_in, raw.tokens_out, raw.finish_reason) == (12, 3, "STOP")


def test_freemodel_transport_maps_gateway_error_for_retry() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"error": {"message": "upstream busy"}})

    transport = OpenAICompatibleTransport(
        api_key="fm_test",
        base_url="https://freemodel.in/v1",
        timeout_s=1,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    async def call() -> ProviderError:
        try:
            await transport.generate(
                model="m", system="s", prompt="p", response_schema={},
                temperature=0, max_output_tokens=10,
            )
        except ProviderError as exc:
            return exc
        raise AssertionError("không ném ProviderError")

    error = asyncio.run(call())
    assert error.status_code == 502 and error.message == "upstream busy"
