"""Validator contract M2 P1-AC-03, port từ `spikes/m1-crawl-extract/validate_contracts.py` (#83,
commit `29f868a`). Luật giữ nguyên; chỉ đổi cách trả kết quả.

Khác bản gốc:
- Trả **danh sách** lỗi thay vì lỗi đầu tiên. Thứ tự giữ như bản gốc, nên lỗi đầu tiên trùng kết
  luận của script Định (test parity `tests/m2/test_validate.py`).
- Nhận input `p1-ac-03-input.v1` thay cho file context của fixture.

Sửa luật ở đây thì phải sửa ở #83 trước (Định sở hữu contract), rồi chép lại.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from worker.m1.pkb.validate import PKBInvalid, validate_pkb

CONTRACT_DIR = Path(__file__).resolve().parent / "contract"
SCRIPT_SCHEMA = "p1-ac-03-script-vi.v1.schema.json"
INPUT_SCHEMA = "p1-ac-03-input.v1.schema.json"

_PATH_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*")
_TOKEN_RE = re.compile(r"[^.\[\]]+|\[\d+\]")


def conflict_paths_overlap(field_path: str, conflict_path: Any) -> bool:
    """True when either valid dot-bracket path contains the other."""
    if not isinstance(conflict_path, str):
        return False
    if not _PATH_RE.fullmatch(field_path) or not _PATH_RE.fullmatch(conflict_path):
        return False
    path_tokens = _TOKEN_RE.findall(field_path)
    conflict_tokens = _TOKEN_RE.findall(conflict_path)
    common_length = min(len(path_tokens), len(conflict_tokens))
    return path_tokens[:common_length] == conflict_tokens[:common_length]


def load_contract(name: str) -> dict[str, Any]:
    return json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))


@cache
def _validator(name: str) -> Draft202012Validator:
    schema = load_contract(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def schema_errors(name: str, doc: Any) -> list[str]:
    """Mọi lỗi JSON Schema, xếp theo đường dẫn như `first_error` của bản gốc."""
    errors = sorted(_validator(name).iter_errors(doc), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '(gốc)'}: {e.message}" for e in errors]


def resolve_field_path(data: Any, path_str: str) -> Any:
    """`key.key[index].key` → giá trị.

    Sai cú pháp: ValueError. Không tồn tại: KeyError / IndexError / TypeError.
    """
    if not _PATH_RE.fullmatch(path_str):
        raise ValueError("cú pháp phải là key.key[index].key")
    curr = data
    for token in _TOKEN_RE.findall(path_str):
        curr = curr[int(token[1:-1])] if token.startswith("[") else curr[token]
    return curr


def validate_input(inp: dict[str, Any]) -> list[str]:
    """Kiểm input trước khi gọi LLM: schema input, version wrapper khớp data, PKB hợp lệ (M1)."""
    errors = schema_errors(INPUT_SCHEMA, inp)
    if errors:
        return errors
    pkb = inp["approved_pkb"]
    if pkb["schema_version"] != pkb["data"].get("schema_version"):
        return ["schema_version của wrapper không khớp schema_version trong PKB data"]
    if inp["knowledge_version"] < 1:
        return ["knowledge_version phải là phiên bản PKB đã được người dùng xác nhận"]
    try:
        validate_pkb(pkb["data"], pkb["sources"])
    except PKBInvalid as e:
        return [f"approved_pkb: {err}" for err in e.errors]
    return []


def validate_script(doc: Any, inp: dict[str, Any]) -> list[str]:
    """Schema output trước; qua schema thì mới kiểm refs/asset/CTA/segment (như bản gốc)."""
    return schema_errors(SCRIPT_SCHEMA, doc) or content_errors(doc, inp)


def _check_refs(
    refs: list[dict[str, Any]],
    label: str,
    pkb_data: dict[str, Any],
    valid_sources: set[str],
    conflicts: list[Any],
) -> list[str]:
    errors: list[str] = []
    for ref in refs:
        source_id = ref.get("source_id")
        field_path = ref.get("field_path", "")
        try:
            value = resolve_field_path(pkb_data, field_path)
        except (KeyError, IndexError, TypeError, ValueError) as ex:
            errors.append(f"{label}: fact_ref '{field_path}' không tồn tại: {ex}")
            continue
        if value is None:
            errors.append(f"{label}: fact_ref '{field_path}' trả về None")
            continue
        # Đường dẫn có thể trỏ vào giá trị con (vd. identity.name.value): dùng fact gần nhất
        # bao ngoài để kiểm nguồn gốc.
        fact = value if isinstance(value, dict) else None
        prefix = ""
        for token in _TOKEN_RE.findall(field_path):
            prefix += token if token.startswith("[") else ("." if prefix else "") + token
            try:
                candidate = resolve_field_path(pkb_data, prefix)
            except (KeyError, IndexError, TypeError, ValueError):
                continue
            if isinstance(candidate, dict) and ("source_id" in candidate or "origin" in candidate):
                fact = candidate
        if fact is None:
            errors.append(f"{label}: field_path '{field_path}' không trỏ tới fact có provenance")
            continue
        if fact.get("origin") == "inferred":
            errors.append(
                f"{label}: không dùng fact inferred chưa được người dùng xác nhận '{field_path}'"
            )
            continue
        # M1 conflict records can name the field as field_path, field, or path.
        if any(
            isinstance(conflict, dict)
            and any(
                conflict_paths_overlap(field_path, conflict.get(path_key))
                for path_key in ("field_path", "field", "path")
            )
            for conflict in conflicts
        ):
            errors.append(f"{label}: fact '{field_path}' đang có xung đột chưa được giải quyết")
            continue
        fact_source_id = fact.get("source_id")
        if source_id is not None:
            if source_id not in valid_sources:
                errors.append(f"{label}: source_id '{source_id}' không có trong PKB sources")
            elif fact_source_id != source_id:
                if not fact_source_id and fact.get("origin") == "owner":
                    errors.append(
                        f"{label}: source_id không khớp fact '{field_path}'; fact do chủ sở hữu "
                        "cung cấp không có source_id, hãy bỏ thuộc tính source_id khỏi fact_ref"
                    )
                else:
                    errors.append(
                        f"{label}: source_id không khớp fact '{field_path}'; "
                        f"source_id đúng là '{fact_source_id}'"
                    )
        elif fact_source_id and fact_source_id not in valid_sources:
            errors.append(f"{label}: nguồn của fact '{field_path}' không có trong PKB sources")
    return errors


def content_errors(doc: dict[str, Any], inp: dict[str, Any]) -> list[str]:
    """Luật ngoài schema: version PKB, CTA, fact refs, segment, visual/asset allowlist."""
    approved_pkb = inp.get("approved_pkb", {})
    valid_sources = {s["id"] for s in approved_pkb.get("sources", [])}
    pkb_data = approved_pkb.get("data", {})
    declared = approved_pkb.get("schema_version", pkb_data.get("schema_version"))
    # Sai version thì mọi fact ref đều vô nghĩa: dừng ngay như bản gốc.
    if declared not in {"0.2", "0.3"}:
        return [f"PKB schema_version '{declared}' chưa được hỗ trợ"]
    if pkb_data.get("schema_version") != declared:
        return ["schema_version của wrapper không khớp schema_version trong PKB data"]
    if doc.get("product_id") != inp.get("product_id"):
        return ["product_id của output không khớp Product đầu vào"]
    if doc.get("pkb_schema_version") != declared:
        return ["pkb_schema_version của output không khớp PKB đã được người dùng xác nhận"]
    if doc.get("knowledge_version") != inp.get("knowledge_version", doc.get("knowledge_version")):
        return ["knowledge_version của output không khớp PKB đã được người dùng xác nhận"]

    errors: list[str] = []
    conflicts = (pkb_data.get("quality") or {}).get("conflicts") or []
    product_id = doc.get("product_id")
    permitted = {
        a["asset_id"]: a["kind"]
        for a in inp.get("permitted_assets", [])
        if a.get("product_id") == product_id
    }
    requested_cta = (inp.get("content_context") or {}).get("cta")
    cta = doc.get("cta", {})
    if requested_cta:
        if cta.get("text") != requested_cta.get("text"):
            errors.append("cta.text không giữ nguyên nội dung người dùng cung cấp")
        if cta.get("destination") != requested_cta.get("destination"):
            errors.append("cta.destination không giữ nguyên đích người dùng cung cấp")
    elif cta.get("destination") is not None:
        errors.append("cta.destination phải null khi người dùng không cung cấp đích")

    def refs(items: list[dict[str, Any]], label: str) -> list[str]:
        return _check_refs(items, label, pkb_data, valid_sources, conflicts)

    errors += refs(doc.get("hook", {}).get("fact_refs", []), "hook")
    errors += refs(cta.get("fact_refs", []), "cta")

    seen_scenes: set[str] = set()
    seen_segments: set[str] = set()
    for scene in doc.get("scenes", []):
        scene_id = scene.get("scene_id", "")
        if scene_id in seen_scenes:
            errors.append(f"scene_id '{scene_id}' bị trùng")
        seen_scenes.add(scene_id)
        scene_segments: set[str] = set()
        for segment in scene.get("narration_segments", []):
            segment_id = segment.get("segment_id", "")
            if not segment_id.startswith(f"{scene_id}-u"):
                errors.append(f"segment_id '{segment_id}' không thuộc cảnh '{scene_id}'")
            if segment_id in seen_segments:
                errors.append(f"segment_id '{segment_id}' bị trùng")
            seen_segments.add(segment_id)
            scene_segments.add(segment_id)
        visual = scene.get("visual_plan", {})
        source_type = visual.get("source_type")
        if visual.get("kind") == "text_card":
            if source_type != "generated_text" or "asset_id" in visual or not visual.get("text"):
                errors.append("text_card phải dùng generated_text, có text và không có asset_id")
        elif source_type == "existing_asset":
            asset_id = visual.get("asset_id")
            if asset_id not in permitted:
                errors.append(
                    f"asset_id '{asset_id}' không nằm trong allowlist của Product fixture"
                )
            elif visual.get("kind") != permitted[asset_id]:
                errors.append(
                    f"cảnh '{scene_id}': asset_id '{asset_id}' phải dùng visual_plan.kind "
                    f"'{permitted[asset_id]}'"
                )
        elif source_type == "ai_generation":
            if not visual.get("generation_request") or "asset_id" in visual:
                errors.append(
                    "ai_generation cần generation_request riêng và không được có asset_id"
                )
        else:
            errors.append(f"source_type '{source_type}' không hợp lệ")
        for claim in scene.get("claims", []):
            claim_segments = claim.get("segment_ids", [])
            if not claim_segments or not set(claim_segments).issubset(scene_segments):
                errors.append(
                    f"claim '{claim.get('text', '')[:40]}' không gắn với segment trong cảnh"
                )
                continue
            fact_refs = claim.get("fact_refs", [])
            if not fact_refs:
                errors.append(f"claim '{claim.get('text', '')[:40]}' thiếu fact_refs")
                continue
            errors += refs(fact_refs, "claim")
    errors += _spoken_hook_cta_errors(doc)
    return errors


def _spoken(text: str) -> str:
    """So lời đọc theo chữ và dấu câu, chỉ chuẩn hóa khoảng trắng."""
    return " ".join(text.split())


def _spoken_hook_cta_errors(doc: dict[str, Any]) -> list[str]:
    """Hook phải được đọc ở segment đầu của cảnh đầu; cảnh cuối role cta kết bằng cta.text."""
    scenes = doc.get("scenes", [])
    if not scenes or not scenes[0].get("narration_segments"):
        return ["hook cần segment mở đầu"]
    errors: list[str] = []
    first = scenes[0]["narration_segments"][0]["text"]
    if _spoken(first) != _spoken(doc.get("hook", {}).get("text", "")):
        errors.append("hook.text phải được đọc trong segment đầu")
    ending = scenes[-1]
    if ending.get("role") != "cta":
        errors.append("cảnh cuối phải có role cta và lời đọc CTA")
        return errors
    spoken = _spoken(" ".join(s["text"] for s in ending.get("narration_segments", [])))
    cta = _spoken(doc.get("cta", {}).get("text", ""))
    if spoken != cta and not spoken.endswith(" " + cta):
        errors.append("cảnh cta phải kết bằng lời đọc cta.text")
    return errors
