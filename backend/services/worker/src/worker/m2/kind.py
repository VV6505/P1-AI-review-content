"""Chuẩn bị `visual_plan.kind` từ allowlist đã xác nhận (bàn giao 11/11 của #83, `8008cbf`).

Với `source_type: existing_asset`, worker chỉ được điền hoặc thay **`kind`**, lấy từ allowlist
của đúng Product và `asset_id`. Không đổi asset, CTA, lời, claim, ref hay quyền tư liệu; không đoán
loại từ tên file. Bước này chỉ xử lý metadata, không xác nhận clip hợp nội dung cảnh.

- Output thô giữ nguyên (hàm trả bản sao đã chuẩn bị, không sửa `raw`).
- Cảnh không chuẩn bị được (ID lạ, ID thuộc Product khác, thiếu `asset_id`) giữ nguyên và ghi
  vào audit với `status` lỗi; validator sẽ báo lỗi cụ thể cho cảnh đó.
- Allowlist hỏng (trùng ID trong Product, kind ngoài enum hỗ trợ) là lỗi input: dùng
  `allowlist_errors` trước khi gọi LLM.
- Validator vẫn từ chối kind lệch registry nếu gọi trực tiếp trên JSON chưa chuẩn bị.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from typing import Any

from worker.m2.validate import SCRIPT_SCHEMA, load_contract

MISSING = "<thiếu>"  # kind cũ khi model không khai trường kind


def supported_kinds() -> frozenset[str]:
    """Enum `visual_plan.kind` của schema, trừ `text_card` (chỉ dùng với `generated_text`)."""
    schema = load_contract(SCRIPT_SCHEMA)
    visual = _find_visual_plan(schema)
    return frozenset(visual["properties"]["kind"]["enum"]) - {"text_card"}


def _find_visual_plan(node: Any) -> dict[str, Any]:
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict) and "kind" in props and "source_type" in props:
            return node
        for value in node.values():
            found = _find_visual_plan(value)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_visual_plan(value)
            if found:
                return found
    return {}


def allowlist_revision(inp: dict[str, Any]) -> dict[str, Any]:
    """Phiên bản/hash input để audit: Product, knowledge_version và hash allowlist (JSON chuẩn)."""
    canonical = json.dumps(
        inp.get("permitted_assets", []), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        "product_id": inp.get("product_id"),
        "knowledge_version": inp.get("knowledge_version"),
        "permitted_assets_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "permitted_assets_count": len(inp.get("permitted_assets", [])),
    }


def allowlist_errors(inp: dict[str, Any]) -> list[str]:
    """Allowlist của Product phải ánh xạ asset_id → kind duy nhất và kind thuộc enum hỗ trợ."""
    product_id = inp.get("product_id")
    records = [a for a in inp.get("permitted_assets", []) if a.get("product_id") == product_id]
    errors: list[str] = []
    counts = Counter(a.get("asset_id") for a in records)
    for asset_id, n in sorted(counts.items(), key=lambda kv: str(kv[0])):
        if n > 1:
            errors.append(f"allowlist: asset_id '{asset_id}' trùng {n} lần trong Product")
    kinds = supported_kinds()
    for a in records:
        if a.get("kind") not in kinds:
            errors.append(
                f"allowlist: asset_id '{a.get('asset_id')}' có kind '{a.get('kind')}' "
                f"ngoài enum hỗ trợ {sorted(kinds)}"
            )
    return errors


def prepare_kinds(
    script: dict[str, Any], inp: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Trả `(bản chuẩn bị, audit)`. `script` không bị sửa.

    Mỗi phần tử audit: `scene_id`, `asset_id`, `old_kind`, `new_kind`, `status`:
    - `unchanged`: kind đã đúng;
    - `filled`: model không khai kind, worker điền;
    - `replaced`: kind của model khác allowlist, worker thay;
    - `error:unknown_asset` / `error:wrong_product` / `error:missing_asset_id` /
      `error:allowlist_invalid`: không đoán, giữ nguyên cảnh.
    """
    prepared = deepcopy(script)
    audit: list[dict[str, Any]] = []
    product_id = inp.get("product_id")
    allowed = {a.get("asset_id"): a for a in inp.get("permitted_assets", [])}
    own: dict[Any, list[dict[str, Any]]] = {}
    for a in inp.get("permitted_assets", []):
        if a.get("product_id") == product_id:
            own.setdefault(a.get("asset_id"), []).append(a)
    kinds = supported_kinds()

    scenes = prepared.get("scenes") if isinstance(prepared, dict) else None
    if not isinstance(scenes, list):
        return prepared, audit
    for scene in scenes:
        visual = scene.get("visual_plan") if isinstance(scene, dict) else None
        if not isinstance(visual, dict) or visual.get("source_type") != "existing_asset":
            continue
        asset_id = visual.get("asset_id")
        old = visual.get("kind", MISSING)
        entry = {
            "scene_id": scene.get("scene_id"),
            "asset_id": asset_id,
            "old_kind": old,
            "new_kind": old,
        }
        if not isinstance(asset_id, str) or not asset_id:
            audit.append({**entry, "status": "error:missing_asset_id"})
            continue
        records = own.get(asset_id, [])
        if not records:
            other = allowed.get(asset_id)
            status = "error:wrong_product" if other else "error:unknown_asset"
            audit.append({**entry, "status": status})
            continue
        if len(records) != 1 or records[0].get("kind") not in kinds:
            audit.append({**entry, "status": "error:allowlist_invalid"})
            continue
        new = records[0]["kind"]
        entry["new_kind"] = new
        if old == new:
            audit.append({**entry, "status": "unchanged"})
            continue
        visual["kind"] = new
        audit.append({**entry, "status": "filled" if old == MISSING else "replaced"})
    return prepared, audit


def audit_errors(audit: list[dict[str, Any]]) -> list[str]:
    return [
        f"chuẩn bị kind: cảnh '{e['scene_id']}' asset_id '{e['asset_id']}' → {e['status']}"
        for e in audit
        if str(e["status"]).startswith("error:")
    ]
