"""`generate_script` với transport fixture: không gọi mạng.

Response "LLM" là ví dụ valid của Định (#83) và các bản sửa của nó; input dựng từ context ví dụ.
"""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tests.m2.parity_cases import LEAD_VIDEO_DESCRIPTION, input_from_context, load
from worker.m1.llm import LLM, LLMSettings
from worker.m1.llm.fixture import FixtureTransport
from worker.m2.generate import M2Settings, ScriptResult, count_syllables, generate_script
from worker.m2.prompt import build_system_prompt, prompt_template
from worker.m2.schema import GEMINI_KEYWORDS, gemini_response_schema, used_keywords
from worker.m2.validate import SCRIPT_SCHEMA, load_contract

NOW = datetime(2026, 10, 29, 8, 0, tzinfo=UTC)
USAGE = {"prompt_token_count": 9000, "candidates_token_count": 2000, "thoughts_token_count": 0}
RPD_429 = json.loads(
    (Path(__file__).parents[1] / "m1" / "fixtures" / "llm" / "error-429-rpd.json").read_text(
        encoding="utf-8"
    )
)


async def _no_sleep(_: float) -> None:
    return None


def example_input() -> dict[str, Any]:
    return input_from_context(load("valid-script-p1-ac-03-vi.context.json"))


def valid_script() -> dict[str, Any]:
    return load("valid-script-p1-ac-03-vi.json")


def run(
    responses: list[dict[str, Any]],
    inp: dict[str, Any] | None = None,
    *,
    repair: bool = False,
    qa_feedback: list[dict[str, Any]] | None = None,
) -> tuple[ScriptResult, FixtureTransport]:
    """`repair=False` mặc định: file này kiểm đường 1 lời gọi (lượt sửa ở test_repair.py)."""
    transport = FixtureTransport(responses)
    llm = LLM(transport, LLMSettings(provider="fixture"), sleep=_no_sleep, now=lambda: NOW)
    res = asyncio.run(
        generate_script(
            inp or example_input(),
            llm,
            settings=M2Settings(syllables_per_s=3.75),
            repair=repair,
            qa_feedback=qa_feedback,
        )
    )
    return res, transport


def ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"data": data, "usage_metadata": USAGE, "finish_reason": "STOP"}


# ---------------------------------------------------------------- thành công


def test_success_adds_estimate_and_cost() -> None:
    res, transport = run([ok(valid_script())])
    assert res.status == "completed" and res.error_code is None
    assert res.data is not None
    segs = [s["text"] for sc in res.data["scenes"] for s in sc["narration_segments"]]
    syllables = sum(count_syllables(t) for t in segs)
    assert res.data["estimated_duration_s"] == round(syllables / 3.75, 1)
    assert any(w.startswith("estimated_duration_s_is_estimate:") for w in res.warnings)
    items = res.cost_breakdown["items"]
    assert len(items) == 1 and items[0]["step"] == "generate_script"
    assert items[0]["cost_status"] == "exact"
    assert len(transport.calls) == 1


def test_estimate_outside_target_is_warning_not_error() -> None:
    res, _ = run([ok(valid_script())])  # ví dụ của Định có 5 câu ngắn: ~10 s
    assert res.status == "completed"
    assert any(w.startswith("estimate_outside_target:") for w in res.warnings)


def test_llm_filled_estimate_is_replaced() -> None:
    doc = valid_script()
    doc["estimated_duration_s"] = 42  # model không được tự điền
    res, _ = run([ok(doc)])
    assert res.status == "completed" and res.data is not None
    assert res.data["estimated_duration_s"] != 42
    assert "llm_filled_worker_field:estimated_duration_s" in res.warnings


def test_unicode_vietnamese_kept() -> None:
    """M2-AC03-02: giữ dấu tiếng Việt / emoji qua fixture → JSON → kết quả."""
    doc = valid_script()
    text = "Thử ngay nhé 🎉 — “xử lý” PDF!"
    doc["hook"]["text"] = text  # hook phải được đọc nguyên văn ở segment đầu
    doc["scenes"][0]["narration_segments"][0]["text"] = text
    res, _ = run([ok(doc)])
    assert res.data is not None
    assert res.data["scenes"][0]["narration_segments"][0]["text"] == text


def test_syllable_count_rule() -> None:
    assert count_syllables("Ghép tối đa 100 tệp, tổng 500MB.") == 7  # số/đơn vị = 1 (đếm thiếu)
    assert count_syllables("Xử lý PDF miễn phí") == 5


# ---------------------------------------------------------------- output sai


def test_schema_invalid_output() -> None:
    doc = valid_script()
    del doc["hook"]
    doc["target_duration_s"] = 30
    res, _ = run([ok(doc)])
    assert res.status == "failed" and res.error_code == "llm_invalid_output"
    assert res.retryable is False and res.data is None
    assert len(res.errors) == 2
    assert res.raw_output is not None and "hook" not in res.raw_output
    assert len(res.cost_breakdown["items"]) == 1  # vẫn ghi chi phí lần gọi


def test_bad_fact_ref_not_repaired() -> None:
    doc = valid_script()
    doc["scenes"][1]["claims"][0]["fact_refs"][0]["field_path"] = "features[99]"
    res, _ = run([ok(doc)])
    assert res.error_code == "llm_invalid_output"
    assert any("features[99]" in e for e in res.errors)
    assert res.raw_output == doc  # không sửa hộ claim


def test_product_id_mismatch_rejected() -> None:
    doc = valid_script()
    doc["product_id"] = "00000000-0000-4000-8000-000000000000"
    res, _ = run([ok(doc)])
    assert res.error_code == "llm_invalid_output"


def test_not_json_output() -> None:
    res, _ = run([{"text": "không phải json", "usage_metadata": USAGE}])
    assert res.error_code == "llm_invalid_output" and res.raw_output is None


# ---------------------------------------------------------------- lỗi provider / input


def test_429_rpd_returns_quota_daily_without_retry() -> None:
    res, transport = run([RPD_429, ok(valid_script())])
    assert res.status == "failed" and res.error_code == "llm_quota_daily"
    assert res.retryable is True and res.retry_after is not None
    assert len(transport.calls) == 1  # RPD không retry
    item = res.cost_breakdown["items"][0]
    assert item["cost_usd"] == 0 and item["cost_status"] == "estimated"


def test_invalid_input_does_not_call_llm() -> None:
    inp = example_input()
    inp["approved_pkb"]["status"] = "draft"
    res, transport = run([ok(valid_script())], inp)
    assert res.error_code == "m2_input_invalid" and res.errors
    assert transport.calls == [] and res.cost_breakdown["items"] == []


# ---------------------------------------------------------------- prompt / schema gửi Gemini


def test_system_prompt_is_dinh_template_filled() -> None:
    inp = example_input()
    system = build_system_prompt(inp)
    template = prompt_template()
    assert template.startswith("Bạn là biên kịch video review sản phẩm.")
    assert "{{" not in system
    assert inp["product_id"] in system
    assert str(inp["knowledge_version"]) in system
    head = template.split("{{approved_pkb_json}}")[0]
    assert system.startswith(head)  # câu chữ của Định giữ nguyên
    assert json.dumps(inp["permitted_assets"], ensure_ascii=False) in system


def test_local_duration_range_replaces_advisory_without_editing_contract() -> None:
    system = build_system_prompt(example_input(), (110, 116))
    assert "110–116 âm tiết" in system
    assert "150–170 âm tiết" not in system


def test_prompt_data_with_braces_is_not_substituted() -> None:
    inp = example_input()
    inp = deepcopy(inp)
    inp["content_context"]["audience"] = "{{permitted_assets_json}}"
    system = build_system_prompt(inp)
    assert '"audience": "{{permitted_assets_json}}"' in system


def lead_sample_input() -> dict[str, Any]:
    inp = deepcopy(example_input())
    inp["content_context"]["video_description"] = LEAD_VIDEO_DESCRIPTION  # câu mẫu của lead, #94
    return inp


def test_video_description_goes_through_content_context_placeholder() -> None:
    """Worker không thêm luật riêng: mô tả đi nguyên trong `{{content_context_json}}`."""
    inp = lead_sample_input()
    system = build_system_prompt(inp)
    context_json = json.dumps(inp["content_context"], ensure_ascii=False)
    assert f'"video_description": "{LEAD_VIDEO_DESCRIPTION}"' in context_json
    assert system.count(context_json) == 1
    assert system.count(LEAD_VIDEO_DESCRIPTION) == 1
    assert "content_context.video_description" in prompt_template()  # luật là của Định


def test_generate_sends_lead_sample_description_to_llm() -> None:
    res, transport = run([ok(valid_script())], lead_sample_input())
    assert res.status == "completed", res.errors
    assert LEAD_VIDEO_DESCRIPTION in transport.calls[0]["system"]


def test_input_without_video_description_is_still_valid() -> None:
    inp = deepcopy(example_input())
    inp["content_context"].pop("video_description")
    res, transport = run([ok(valid_script())], inp)
    assert res.status == "completed", res.errors
    assert '"video_description":' not in transport.calls[0]["system"]


def test_invalid_video_description_stops_before_llm() -> None:
    inp = deepcopy(example_input())
    inp["content_context"]["video_description"] = "   "
    res, transport = run([], inp)
    assert res.error_code == "m2_input_invalid" and transport.calls == []


def test_gemini_schema_only_uses_proven_keywords() -> None:
    schema = gemini_response_schema()
    assert used_keywords(schema) <= GEMINI_KEYWORDS
    assert "estimated_duration_s" not in schema["properties"]
    unit = schema["properties"]["scenes"]["items"]["properties"]["claims"]["items"]["properties"][
        "stat_display"
    ]["properties"]["unit"]
    assert unit["anyOf"] == [{"type": "string", "maxLength": 40}, {"type": "null"}]
    # Thuộc tính và required giữ đủ (trừ trường worker)
    full = load_contract(SCRIPT_SCHEMA)
    assert set(schema["required"]) == set(full["required"])
    assert set(schema["properties"]) == set(full["properties"]) - {"estimated_duration_s"}


def test_gemini_schema_const_becomes_enum() -> None:
    """Chạy thật 1: Gemini bỏ qua `const` của schema_version. `enum` 1 phần tử thay thế."""
    props = gemini_response_schema()["properties"]
    assert props["schema_version"] == {"type": "string", "enum": ["p1-ac-03.v1-draft"]}
    assert props["language"]["enum"] == ["vi"]


@pytest.mark.parametrize(
    "dropped", ["oneOf", "not", "allOf", "if", "uniqueItems", "format", "const"]
)
def test_gemini_schema_drops_unproven(dropped: str) -> None:
    assert dropped not in used_keywords(gemini_response_schema())
