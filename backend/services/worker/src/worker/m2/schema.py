"""Schema output của Định → dạng gửi `response_json_schema` của Gemini.

Chỉ giữ từ khoá đã chạy thật với Gemini ở #90 (`PKBExtract.model_json_schema()`, 18 lời gọi 21/10,
không lỗi). Từ khoá khác bị lược để lần gọi thật không hỏng vì 400. Phần bị lược **không mất**:
`validate_script` vẫn kiểm output bằng schema đầy đủ của Định.

Những chỗ lược (ghi cả trong báo cáo):
- `oneOf` của `visual_plan` (ràng buộc asset_id / generation_request / text theo source_type): bỏ.
  Prompt (luật 5) đã nêu luật này. Không đổi sang `anyOf` vì nhánh chỉ có một phần thuộc tính,
  model có thể sinh object thiếu trường.
- `allOf` / `if` / `then` (claim có stat_display thì fact_refs ≥ 1): bỏ. Validator vẫn chặn claim
  thiếu fact_refs.
- `uniqueItems`, `minItems`, `maxItems`, `minimum`, `maximum`, `exclusiveMinimum`, `format`,
  `additionalProperties`, `$schema`, `$id`: bỏ (chưa kiểm trên Gemini).
- `type: [X, "null"]` → `anyOf: [{type: X, ...}, {type: "null"}]` (dạng Pydantic sinh ở #90).
- `estimated_duration_s`: bỏ khỏi schema. Worker tự tính sau khi nhận lời thoại.
- `const: X` → `enum: [X]`. Lần chạy thật 1 (29/10): Gemini **nhận** `const` (không 400) nhưng
  **không tuân**: trả `schema_version: "0.3"` thay vì `"p1-ac-03.v1-draft"`. Ở #90 `const` chỉ có
  ở `origin: "crawled"`, model ghi đúng nhờ description, nên trước đó chưa thấy lỗi này.
"""

from __future__ import annotations

from typing import Any

from worker.m2.validate import SCRIPT_SCHEMA, load_contract

# Từ khoá có trong `PKBExtract.model_json_schema()` (#90), đã qua Gemini thật. `const` cũng qua
# nhưng không được tuân, nên đổi sang `enum` (xem docstring).
GEMINI_KEYWORDS = frozenset(
    {
        "$defs", "$ref", "anyOf", "default", "description", "enum", "items",
        "maxLength", "minLength", "pattern", "properties", "required", "title", "type",
    }
)  # fmt: skip
WORKER_FIELDS = ("estimated_duration_s",)  # worker điền, LLM không sinh


def _convert(node: Any) -> Any:
    if isinstance(node, list):
        return [_convert(x) for x in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "const":
            out["enum"] = [value]
            continue
        if key not in GEMINI_KEYWORDS:
            continue
        if key in ("properties", "$defs"):  # map tên → schema: giữ mọi tên
            out[key] = {name: _convert(sub) for name, sub in value.items()}
        else:
            out[key] = _convert(value)
    kind = out.get("type")
    if isinstance(kind, list):  # ["string", "null"] → anyOf như Pydantic
        meta = {k: out.pop(k) for k in ("description", "title", "default") if k in out}
        out.pop("type")
        branches = []
        for t in kind:
            branch = {"type": t}
            if t != "null":
                branch.update(out)
            branches.append(branch)
        out = {"anyOf": branches, **meta}
    return out


def gemini_response_schema() -> dict[str, Any]:
    schema = load_contract(SCRIPT_SCHEMA)
    converted = _convert(schema)
    for name in WORKER_FIELDS:
        converted["properties"].pop(name, None)
    return converted


def used_keywords(node: Any) -> set[str]:
    """Mọi từ khoá schema trong `node` (bỏ qua tên thuộc tính). Dùng cho test."""
    found: set[str] = set()
    if isinstance(node, list):
        for x in node:
            found |= used_keywords(x)
    elif isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            if key in ("properties", "$defs"):
                for sub in value.values():
                    found |= used_keywords(sub)
            else:
                found |= used_keywords(value)
    return found
