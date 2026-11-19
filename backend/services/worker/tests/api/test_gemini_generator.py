import asyncio
from typing import Any

import pytest
from pydantic import SecretStr

from worker.api import generator as gen_mod
from worker.api.deps import get_script_generator
from worker.api.generator import GeminiScriptGenerator, ScriptGenerationError
from worker.m2.generate import ScriptResult
from worker.settings import Settings


def run() -> Any:
    return asyncio.run(GeminiScriptGenerator()({"x": 1}))


def patch(monkeypatch: pytest.MonkeyPatch, result: ScriptResult) -> None:
    async def fake(inp: dict[str, Any], llm: object) -> ScriptResult:
        return result

    monkeypatch.setattr(gen_mod, "make_llm", lambda: object())
    monkeypatch.setattr(gen_mod, "generate_script", fake)


def test_success_maps_content_report_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    patch(
        monkeypatch,
        ScriptResult(
            status="completed",
            data={"scenes": [1]},
            cost_breakdown={"items": [1]},
            warnings=["w"],
            stages={"initial": {}},
        ),
    )
    out = run()
    assert out.content == {"scenes": [1]} and out.cost_breakdown == {"items": [1]}
    assert out.report == {"warnings": ["w"], "stages": {"initial": {}}}


@pytest.mark.parametrize(
    ("code", "retryable", "invalid"),
    [
        ("llm_invalid_output", False, True),
        ("m2_input_invalid", False, True),
        ("llm_quota_daily", False, False),
        ("llm_rate_limited", True, False),
    ],
)
def test_failure_mapping(
    monkeypatch: pytest.MonkeyPatch, code: str, retryable: bool, invalid: bool
) -> None:
    patch(
        monkeypatch,
        ScriptResult(
            status="failed",
            data=None,
            cost_breakdown={"items": [2]},
            error_code=code,
            error_message="msg",
            retryable=retryable,
            errors=["e1", "e2"],
        ),
    )
    with pytest.raises(ScriptGenerationError) as e:
        run()
    assert (e.value.retryable, e.value.invalid) == (retryable, invalid)
    assert code in e.value.message and "e1" in e.value.message
    assert e.value.cost_breakdown == {"items": [2]}


def test_bad_llm_config_not_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad() -> object:
        raise ValueError("LLM_PROVIDER=fixture cần LLM_FIXTURE_PATH")

    monkeypatch.setattr(gen_mod, "make_llm", bad)
    with pytest.raises(ScriptGenerationError) as e:
        run()
    assert not e.value.retryable and "LLM_FIXTURE_PATH" in e.value.message


def test_dependency_needs_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert get_script_generator(Settings()) is None
    keyed = Settings(gemini_api_key=SecretStr("k"))
    assert isinstance(get_script_generator(keyed), GeminiScriptGenerator)


def test_dependency_fixture_provider_needs_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fixture")
    assert isinstance(get_script_generator(Settings()), GeminiScriptGenerator)


def test_dependency_freemodel_requires_its_own_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "freemodel")
    assert get_script_generator(Settings(gemini_api_key=SecretStr("gemini"))) is None
    settings = Settings(freemodel_api_key=SecretStr("fm_test"))
    assert isinstance(get_script_generator(settings), GeminiScriptGenerator)
