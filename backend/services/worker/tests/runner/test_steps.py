import asyncio
from pathlib import Path

import pytest

from tests.runner.fakes import crawl_ok
from worker.m1.extract import service as extract_service
from worker.m1.extract.service import ExtractError, ExtractErrorCode, ExtractResult
from worker.runner import steps
from worker.runner.steps import GeminiExtractStep, StepError


def call(crawl=None):  # type: ignore[no-untyped-def]
    return asyncio.run(GeminiExtractStep()(crawl or crawl_ok(), Path("/tmp/x")))


def test_success_maps_result(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_extract(crawl, store, llm):  # type: ignore[no-untyped-def]
        return ExtractResult(
            data={"identity": {}},
            sources=[{"source_id": "src_01"}],
            cost_breakdown={"items": []},
            warnings=["w"],
        )

    monkeypatch.setattr(steps, "make_llm", lambda: object())
    monkeypatch.setattr(steps, "extract_product", fake_extract)
    out = call()
    assert out.data == {"identity": {}} and out.sources == [{"source_id": "src_01"}]
    assert out.cost_breakdown == {"items": []} and out.warnings == ["w"]


def test_extract_error_keeps_retryable_and_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(crawl, store, llm):  # type: ignore[no-untyped-def]
        raise ExtractError(ExtractErrorCode.NO_PAGES, "không có trang", retryable=True)

    monkeypatch.setattr(steps, "make_llm", lambda: object())
    monkeypatch.setattr(steps, "extract_product", boom)
    with pytest.raises(StepError) as e:
        call()
    assert e.value.retryable is True and "extract_no_pages" in e.value.message
    assert "items" in e.value.cost_breakdown


def test_bad_llm_config_is_not_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad():  # type: ignore[no-untyped-def]
        raise ValueError("LLM_PROVIDER=fixture cần LLM_FIXTURE_PATH")

    monkeypatch.setattr(steps, "make_llm", bad)
    with pytest.raises(StepError) as e:
        call()
    assert e.value.retryable is False and "LLM_FIXTURE_PATH" in e.value.message


def test_module_is_the_one_runner_imports() -> None:
    assert steps.extract_product is extract_service.extract_product
