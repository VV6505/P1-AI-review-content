"""Chuẩn bị `kind` + đúng một lượt sửa (bàn giao 11/11 của #83, `8008cbf`). Transport fixture."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from tests.m2.test_generate import example_input, ok, run, valid_script
from worker.m2.generate import narration_syllables
from worker.m2.kind import MISSING, allowlist_errors, prepare_kinds
from worker.m2.repair import build_repair_prompt, syllable_feedback
from worker.m2.validate import content_errors, schema_errors

SCRIPT_SCHEMA = "p1-ac-03-script-vi.v1.schema.json"


def wrong_kind_script() -> dict[str, Any]:
    doc = valid_script()
    doc["scenes"][0]["visual_plan"]["kind"] = "screenshot"  # allowlist: screen_recording
    return doc


# ---------------------------------------------------------------- chuẩn bị kind


def test_prepare_replaces_kind_and_keeps_raw() -> None:
    raw = wrong_kind_script()
    before = deepcopy(raw)
    prepared, audit = prepare_kinds(raw, example_input())
    assert raw == before  # output thô không bị sửa
    assert prepared["scenes"][0]["visual_plan"]["kind"] == "screen_recording"
    first = audit[0]
    assert first["scene_id"] == "s01" and first["status"] == "replaced"
    assert (first["old_kind"], first["new_kind"]) == ("screenshot", "screen_recording")
    # Chỉ kind đổi.
    prepared["scenes"][0]["visual_plan"]["kind"] = "screenshot"
    assert prepared == raw


def test_prepare_fills_missing_kind() -> None:
    raw = valid_script()
    del raw["scenes"][1]["visual_plan"]["kind"]
    prepared, audit = prepare_kinds(raw, example_input())
    assert prepared["scenes"][1]["visual_plan"]["kind"] == "screen_recording"
    entry = next(a for a in audit if a["scene_id"] == "s02")
    assert entry["status"] == "filled" and entry["old_kind"] == MISSING


def test_prepare_does_not_guess_unknown_or_foreign_asset() -> None:
    raw = valid_script()
    raw["scenes"][0]["visual_plan"]["asset_id"] = "khong-co"
    inp = example_input()
    other = deepcopy(inp["permitted_assets"][0])
    other.update(asset_id="cua-product-khac", product_id="00000000-0000-4000-8000-000000000000")
    inp["permitted_assets"].append(other)
    raw["scenes"][1]["visual_plan"]["asset_id"] = "cua-product-khac"
    prepared, audit = prepare_kinds(raw, inp)
    assert [a["status"] for a in audit[:2]] == ["error:unknown_asset", "error:wrong_product"]
    assert prepared["scenes"][0]["visual_plan"] == raw["scenes"][0]["visual_plan"]
    assert prepared["scenes"][1]["visual_plan"] == raw["scenes"][1]["visual_plan"]


def test_prepare_leaves_text_card_alone() -> None:
    prepared, audit = prepare_kinds(valid_script(), example_input())
    assert prepared["scenes"][3]["visual_plan"]["kind"] == "text_card"
    assert all(a["scene_id"] != "s04" for a in audit)


def test_allowlist_duplicate_id_is_input_error() -> None:
    inp = example_input()
    inp["permitted_assets"].append(deepcopy(inp["permitted_assets"][0]))
    assert any("trùng" in e for e in allowlist_errors(inp))
    res, transport = run([ok(valid_script())], inp)
    assert res.error_code == "m2_input_invalid" and transport.calls == []


def test_validator_still_rejects_unprepared_wrong_kind() -> None:
    assert content_errors(wrong_kind_script(), example_input())


# ---------------------------------------------------------------- orchestration


def long_script() -> dict[str, Any]:
    """Ví dụ của Định, lời đọc dài thêm cho vào mốc 150–170 âm tiết (không đổi hook/CTA)."""
    doc = valid_script()
    seg = doc["scenes"][1]["narration_segments"][0]
    seg["text"] = seg["text"] + " " + " ".join(["ý"] * (160 - narration_syllables(doc)))
    assert 150 <= narration_syllables(doc) <= 170
    return doc


def test_kind_prepare_alone_makes_valid_without_repair_call() -> None:
    res, transport = run([ok(long_script() | {})], repair=True)  # kind đúng, trong mốc
    assert res.status == "completed" and len(transport.calls) == 1
    doc = long_script()
    doc["scenes"][0]["visual_plan"]["kind"] = "screenshot"
    res, transport = run([ok(doc)], repair=True)
    assert res.status == "completed", res.errors
    assert len(transport.calls) == 1  # lệch kind được chuẩn bị, không tốn lượt sửa
    assert res.data is not None
    assert res.data["scenes"][0]["visual_plan"]["kind"] == "screen_recording"
    assert res.stages["initial"]["raw"]["scenes"][0]["visual_plan"]["kind"] == "screenshot"
    assert res.stages["initial"]["kind_audit"][0]["status"] == "replaced"
    assert res.stages["feedback"] == []
    assert res.stages["allowlist_revision"]["permitted_assets_sha256"]


def test_one_repair_call_fixes_validator_error() -> None:
    bad = long_script()
    bad["scenes"][1]["claims"][0]["fact_refs"][0]["field_path"] = "features[99]"
    res, transport = run([ok(bad), ok(long_script())], repair=True)
    assert res.status == "completed", res.errors
    assert len(transport.calls) == 2
    steps = [i["step"] for i in res.cost_breakdown["items"]]
    assert steps == ["generate_script", "generate_script_repair"]  # chi phí từng lời gọi riêng
    fb = res.stages["feedback"]
    assert fb and fb[0]["source"] == "content_validator" and "features[99]" in fb[0]["message"]
    assert "features[99]" in transport.calls[1]["system"]  # feedback đi vào prompt sửa
    assert "{{" not in transport.calls[1]["system"]
    assert res.stages["repair"]["valid"] and res.stages["final"]["from"] == "repair"
    assert res.stages["initial"]["raw"] == bad  # thô giữ nguyên


def test_no_second_repair_when_still_invalid() -> None:
    bad = long_script()
    bad["scenes"][1]["claims"][0]["fact_refs"][0]["field_path"] = "features[99]"
    still = deepcopy(bad)
    res, transport = run([ok(bad), ok(still), ok(long_script())], repair=True)
    assert res.status == "failed" and res.error_code == "llm_invalid_output"
    assert len(transport.calls) == 2  # tối đa 1 lời gọi sửa
    assert res.raw_output == still and any("features[99]" in e for e in res.errors)
    assert len(res.cost_breakdown["items"]) == 2


def test_syllable_advisory_triggers_single_repair_and_is_not_an_error() -> None:
    res, transport = run([ok(valid_script()), ok(long_script())], repair=True)
    assert res.status == "completed" and len(transport.calls) == 2
    assert res.stages["feedback"][0]["source"] == "syllable_advisory"
    assert narration_syllables(valid_script()) < 150


def test_advisory_only_failed_repair_keeps_valid_candidate() -> None:
    broken = valid_script()
    del broken["hook"]
    res, _ = run([ok(valid_script()), ok(broken)], repair=True)
    assert res.status == "completed" and res.stages["final"]["from"] == "initial"
    assert any(w.startswith("repair_rejected_keep_candidate") for w in res.warnings)
    assert res.stages["repair"]["valid"] is False


def test_qa_feedback_failed_repair_does_not_keep_candidate() -> None:
    qa = [{"source": "x", "message": "claims[].text phải bằng tiếng Việt", "scene_id": "s02"}]
    broken = long_script()
    del broken["hook"]
    res, _ = run([ok(long_script()), ok(broken)], repair=True, qa_feedback=qa)
    assert res.status == "failed"
    assert res.stages["feedback"][0] == {**qa[0], "source": "qa"}  # nhãn qa chỉ do bên ngoài


def test_repair_disabled_makes_single_call() -> None:
    bad = long_script()
    del bad["hook"]
    res, transport = run([ok(bad)], repair=False)
    assert res.status == "failed" and len(transport.calls) == 1


def test_repair_prompt_fills_all_variables() -> None:
    inp = example_input()
    prompt = build_repair_prompt(inp, valid_script(), [{"source": "qa", "message": "“x” \\ y"}])
    assert "{{" not in prompt
    assert inp["product_id"] in prompt  # prompt sinh đầu tiên được nhúng
    assert '"title": "P1-AC-03 Vietnamese Script v1 (Draft)"' in prompt
    assert '"message": "“x” \\\\ y"' in prompt  # feedback là JSON đã escape


def test_syllable_feedback_range() -> None:
    assert syllable_feedback(150) == [] and syllable_feedback(170) == []
    assert syllable_feedback(149)[0]["source"] == "syllable_advisory"
    assert syllable_feedback(171)[0]["syllables"] == 171
    assert schema_errors(SCRIPT_SCHEMA, long_script()) == []
