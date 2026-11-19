"""Các ca parity, dựng từ `validate_contracts.py` của Định tại commit 29f868a.

Dùng ở hai nơi:
- `test_validate.py`: chạy validator của worker trên các ca này.
- Script ghi kỳ vọng (`fixtures/parity-29f868a.json`): chạy hàm của Định trên cùng các ca.
  Cách tạo lại: xem docstring của `test_validate.py`.

Không import gì của worker để script của Định cũng import được file này.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

EXAMPLES = Path(__file__).resolve().parents[2] / "src" / "worker" / "m2" / "contract" / "examples"
# Câu mẫu của lead ở #94 (31/10) cho `content_context.video_description`.
LEAD_VIDEO_DESCRIPTION = (
    "Mình muốn giới thiệu sản phẩm cho nhân viên văn phòng, tập trung vào việc học AI để ứng dụng "
    "trong công việc, giọng thân thiện và dễ hiểu."
)
PRODUCT_ID = "9f8a3c20-7b41-4e89-bc52-1d0e4f3a7a99"  # product_id cố định trong script của Định
EXAMPLE_FILES = (
    "invalid-script-p1-ac-03-vi-missing-fact-ref.json",
    "invalid-script-p1-ac-03-vi-unknown-asset.json",
    "valid-script-p1-ac-03-vi.json",
)

# input: kiểm wrapper input. script: schema rồi content. content: chỉ content. schema: chỉ schema.
Kind = Literal["input", "script", "content", "schema"]


@dataclass
class Case:
    name: str
    kind: Kind
    context: dict[str, Any]  # dạng context của Định (có pkb_file)
    doc: dict[str, Any] = field(default_factory=dict)


def load(name: str) -> Any:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def load_pkb() -> dict[str, Any]:
    """PKB ElevenLabs mà context ở contract 73f4df9 trỏ tới."""
    return load("elevenlabs-pkb.gemini-3.5-flash-lite.json")


def input_from_context(context: dict[str, Any]) -> dict[str, Any]:
    """Context của Định → input p1-ac-03-input.v1, dựng như `validate_p1_vi_input_schema`."""
    pkb = load_pkb()
    approved = context.get("approved_pkb")
    doc: dict[str, Any] = {
        "schema_version": "p1-ac-03-input.v1-draft",
        "product_id": PRODUCT_ID,
        "knowledge_version": context.get("knowledge_version", 1),
        "approved_pkb": {
            "status": "approved",
            "schema_version": approved["schema_version"]
            if approved
            else context.get("pkb_schema_version", pkb["data"].get("schema_version")),
            "data": approved["data"] if approved else pkb["data"],
            "sources": approved["sources"] if approved else pkb["sources"],
        },
        "permitted_assets": context["permitted_assets"],
    }
    if "content_context" in context:
        doc["content_context"] = context["content_context"]
    return doc


def build_cases() -> list[Case]:
    ctx = load("valid-script-p1-ac-03-vi.context.json")
    script = load("valid-script-p1-ac-03-vi.json")
    pkb = load_pkb()
    standalone_ctx = {k: v for k, v in ctx.items() if k != "content_context"}
    cases: list[Case] = [
        Case("m2/p1-ac-03-input.v1.schema.json", "input", ctx),
        Case("m2/input-without-campaign.json", "input", standalone_ctx),
        Case(
            "m2/input-pkb-version-must-match-data.json",
            "input",
            {**ctx, "pkb_schema_version": "0.3"},
        ),
    ]
    cases += [Case(f"m2/examples/{n}", "script", ctx, load(n)) for n in EXAMPLE_FILES]

    for target in (39, 40, 45, 46):
        doc = deepcopy(script)
        doc["target_duration_s"] = target
        cases.append(Case(f"m2/target-duration-{target}s-contract-only", "script", ctx, doc))

    doc = deepcopy(script)
    visual = doc["scenes"][0]["visual_plan"]
    visual.pop("asset_id")
    visual["kind"] = "ai_generated_image"
    visual["source_type"] = "ai_generation"
    visual["generation_request"] = "Ảnh minh họa trừu tượng, không khẳng định tính năng mới."
    cases.append(Case("m2/ai-generation-request-is-not-asset", "script", ctx, doc))

    doc = deepcopy(script)
    doc["scenes"] = doc["scenes"][:1]
    doc["scenes"][0]["narration_segments"].append(
        {"segment_id": "s01-u02", "text": script["cta"]["text"]}
    )
    doc["scenes"][0]["role"] = "cta"
    cases.append(Case("m2/one-scene-with-multiple-tts-segments.json", "script", ctx, doc))

    def with_scene_count(count: int) -> dict[str, Any]:
        out = deepcopy(script)
        template = script["scenes"][0]
        out["scenes"] = []
        for index in range(1, count + 1):
            scene = deepcopy(template)
            scene_id = f"s{index:02d}"
            scene["scene_id"] = scene_id
            ids = []
            for seg_index, seg in enumerate(scene["narration_segments"], start=1):
                seg["segment_id"] = f"{scene_id}-u{seg_index:02d}"
                ids.append(seg["segment_id"])
            for claim in scene["claims"]:
                claim["segment_ids"] = ids
            out["scenes"].append(scene)
        out["scenes"][-1]["role"] = "cta"
        out["scenes"][-1]["narration_segments"].append(
            {"segment_id": f"s{count:02d}-u02", "text": out["cta"]["text"]}
        )
        return out

    cases.append(
        Case("m2/12-scenes-within-technical-limit.json", "script", ctx, with_scene_count(12))
    )
    cases.append(
        Case("m2/13-scenes-over-technical-limit.json", "script", ctx, with_scene_count(13))
    )

    doc = deepcopy(script)
    card = doc["scenes"][3]["visual_plan"]
    card.update(source_type="generated_text", text="CTA card", asset_id="fixture:card:cta")
    cases.append(Case("m2/text-card-must-not-reference-an-asset.json", "schema", ctx, doc))

    owner_ctx = deepcopy(ctx)
    owner_ctx["approved_pkb"] = {
        "schema_version": "0.2",
        "data": deepcopy(pkb["data"]),
        "sources": pkb["sources"],
    }
    owner_fact = owner_ctx["approved_pkb"]["data"]["identity"]["category"]
    owner_fact["origin"] = "owner"
    owner_fact.pop("source_id", None)
    owner_script = deepcopy(script)
    owner_script["hook"]["fact_refs"][0].pop("source_id", None)
    owner_script["scenes"][0]["claims"][0]["fact_refs"][0].pop("source_id", None)
    cases.append(
        Case(
            "m2/owner-fact-reference-without-crawl-source.json", "content", owner_ctx, owner_script
        )
    )

    inferred_ctx = deepcopy(owner_ctx)
    inferred_ctx["approved_pkb"]["data"]["identity"]["category"]["origin"] = "inferred"
    cases.append(
        Case("m2/unapproved-inferred-fact-is-rejected.json", "content", inferred_ctx, owner_script)
    )

    conflict_ctx = deepcopy(owner_ctx)
    quality = conflict_ctx["approved_pkb"]["data"].get("quality") or {}
    quality["conflicts"] = [{"field_path": "identity.category"}]
    conflict_ctx["approved_pkb"]["data"]["quality"] = quality
    cases.append(
        Case("m2/unresolved-conflict-fact-is-rejected.json", "content", conflict_ctx, owner_script)
    )

    def script_with_refs(field_path: str, source_id: str) -> dict[str, Any]:
        out = deepcopy(script)
        refs = [out["hook"]["fact_refs"][0], out["scenes"][0]["claims"][0]["fact_refs"][0]]
        for ref in refs:
            ref["field_path"] = field_path
            ref["source_id"] = source_id
        return out

    def conflict_case(
        name: str,
        ref_path: str,
        source_id: str,
        conflict_path: str,
        conflict_key: str = "field_path",
    ) -> Case:
        case_ctx = deepcopy(ctx)
        approved = input_from_context(case_ctx)["approved_pkb"]
        quality = approved["data"].get("quality") or {}
        quality["conflicts"] = [{conflict_key: conflict_path}]
        approved["data"]["quality"] = quality
        case_ctx["approved_pkb"] = approved
        return Case(name, "content", case_ctx, script_with_refs(ref_path, source_id))

    cases += [
        conflict_case(
            "m2/conflict-parent-blocks-child-reference.json",
            "identity.category.value",
            "src_01",
            "identity.category",
        ),
        conflict_case(
            "m2/conflict-field-alias-blocks-nested-reference.json",
            "identity.category.value",
            "src_01",
            "identity.category",
            "field",
        ),
        conflict_case(
            "m2/conflict-child-blocks-fact-reference.json",
            "identity.category",
            "src_01",
            "identity.category.value",
        ),
        conflict_case(
            "m2/conflict-child-blocks-parent-reference.json",
            "pricing.plans[0]",
            "src_02",
            "pricing.plans[0].list_price",
        ),
        conflict_case(
            "m2/conflict-does-not-block-sibling-reference.json",
            "pricing.plans[0].name",
            "src_02",
            "pricing.plans[0].list_price",
        ),
        conflict_case(
            "m2/array-index-conflict-paths-use-token-boundaries.json",
            "pricing.plans[1].list_price",
            "src_02",
            "pricing.plans[10].list_price",
        ),
        conflict_case(
            "m2/conflict-does-not-block-unrelated-fact.json",
            "identity.category",
            "src_01",
            "pricing.plans[0].list_price",
        ),
    ]

    def mutate(fn: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        doc = deepcopy(script)
        fn(doc)
        return doc

    def wrong_source(d: dict[str, Any]) -> None:
        d["hook"]["fact_refs"][0]["source_id"] = "src_02"

    def bad_path(d: dict[str, Any]) -> None:
        d["hook"]["fact_refs"][0]["field_path"] = "identity..category"

    def wrong_cta(d: dict[str, Any]) -> None:
        d["cta"]["destination"] = "https://unprovided.example/"

    def cta_fact_ref(d: dict[str, Any]) -> None:
        d["cta"]["fact_refs"] = [{"field_path": "identity.category", "source_id": "src_01"}]

    def invalid_cta_fact_ref(d: dict[str, Any]) -> None:
        d["cta"]["fact_refs"] = [{"field_path": "identity..category", "source_id": "src_01"}]

    def wrong_product_id(d: dict[str, Any]) -> None:
        d["product_id"] = "00000000-0000-4000-8000-000000000000"

    cases += [
        Case("m2/source-id-must-match-referenced-fact.json", "content", ctx, mutate(wrong_source)),
        Case("m2/fact-ref-path-syntax.json", "content", ctx, mutate(bad_path)),
        Case("m2/cta-destination-must-match-input.json", "content", ctx, mutate(wrong_cta)),
        Case(
            "m2/cta-fact-refs-are-validated-like-claim-refs.json",
            "content",
            ctx,
            mutate(cta_fact_ref),
        ),
        Case(
            "m2/cta-fact-refs-must-resolve-to-pkb.json",
            "content",
            ctx,
            mutate(invalid_cta_fact_ref),
        ),
        Case(
            "m2/output-product-id-must-match-input.json",
            "content",
            ctx,
            mutate(wrong_product_id),
        ),
    ]

    standalone = deepcopy(script)
    standalone.update(
        {
            "platform": "tiktok",
            "audience": "Người xem phổ thông",
            "context_defaults_applied": ["platform", "intent", "audience", "cta"],
            "intent": "awareness",
            "cta": {"text": "Xem thêm thông tin.", "destination": None},
        }
    )
    standalone["scenes"][-1]["narration_segments"][0]["text"] = standalone["cta"]["text"]
    cases.append(
        Case("m2/script-without-campaign-context.json", "script", standalone_ctx, standalone)
    )

    # Hook/CTA phải được đọc (73f4df9): 4 ca `m2/{hook-mismatch,...}` của Định.
    for label in ("hook-mismatch", "missing-cta-scene", "cta-not-spoken", "speech-whitespace"):
        speech = deepcopy(script)
        if label == "hook-mismatch":
            speech["scenes"][0]["narration_segments"][0]["text"] = "Nội dung khác."
        elif label == "missing-cta-scene":
            speech["scenes"][-1]["role"] = "result"
        elif label == "cta-not-spoken":
            speech["scenes"][-1]["narration_segments"][0]["text"] = "Lời kết khác."
        else:
            hook_text = speech["hook"]["text"]
            speech["scenes"][0]["narration_segments"][0]["text"] = "  " + hook_text + "\n"
        cases.append(Case(f"m2/{label}", "script", ctx, speech))

    # Clip quay màn hình không được khai báo là logo (29f868a).
    wrong_kind = deepcopy(script)
    wrong_kind["scenes"][0]["visual_plan"]["kind"] = "logo"
    cases.append(Case("m2/screen-recording-cannot-be-used-as-logo.json", "script", ctx, wrong_kind))

    # stat_display đủ bốn trường (chỉ cấu trúc, không kiểm nghĩa): 5 ca `m2/stat-display-*`.
    stat = {
        "value": "40",
        "label": "Giá trị fixture",
        "unit": "%",
        "scope": "Synthetic schema check only",
    }
    for missing in (None, "value", "label", "unit", "scope"):
        with_stat = deepcopy(script)
        with_stat["scenes"][0]["claims"][0]["stat_display"] = deepcopy(stat)
        if missing:
            del with_stat["scenes"][0]["claims"][0]["stat_display"][missing]
        cases.append(Case(f"m2/stat-display-{missing or 'complete'}", "schema", ctx, with_stat))

    # Ca video_description theo #83 fb4f0ed (`m2/video-description-*` trong validate_contracts.py),
    # thêm ca câu mẫu của lead.
    for label, description in (
        ("absent", None),
        ("one-character", "A"),
        ("max-length", "A" * 2000),
        ("too-long", "A" * 2001),
        ("empty", ""),
        ("whitespace", " \n\t"),
        ("wrong-type", 123),
        ("lead-sample-94", LEAD_VIDEO_DESCRIPTION),
    ):
        desc_ctx = deepcopy(ctx)
        if description is None:
            desc_ctx["content_context"].pop("video_description", None)
        else:
            desc_ctx["content_context"]["video_description"] = description
        cases.append(Case(f"m2/video-description-{label}", "input", desc_ctx))

    description_ref = deepcopy(script)
    description_ref["scenes"][0]["claims"][0]["fact_refs"] = [
        {"field_path": "content_context.video_description"}
    ]
    cases.append(Case("m2/video-description-is-not-pkb-fact", "content", ctx, description_ref))

    other_ctx = deepcopy(ctx)
    other_ctx["permitted_assets"][0]["product_id"] = "00000000-0000-4000-8000-000000000000"
    cases.append(
        Case("m2/asset-from-different-product.json", "content", other_ctx, deepcopy(script))
    )
    return cases
