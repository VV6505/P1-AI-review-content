"""Validate 1 PKB đầy đủ (`data` + `sources`): model Pydantic v0.3 và luật tham chiếu chéo.

Pydantic không biết `sources`, nên luật "mọi `source_id` trong data phải có trong `sources[].id`"
nằm ở đây (giống `source_id_error` của `spikes/m1-crawl-extract/validate_contracts.py`).
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from worker.m1.pkb.models import PKBData, Source


class PKBInvalid(ValueError):
    """PKB không hợp lệ. `errors` là danh sách lỗi dạng 'đường/dẫn: thông báo'."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors[:5]))
        self.errors = errors


def _pydantic_errors(e: ValidationError, prefix: str) -> list[str]:
    out = []
    for err in e.errors():
        where = "/".join(str(p) for p in err["loc"]) or "(gốc)"
        out.append(f"{prefix}{where}: {err['msg']}")
    return out


def unknown_source_ids(data: Any, known: set[str]) -> list[str]:
    """Các `source_id` (kể cả trong `previous`) không có trong `known`."""
    found: set[str] = set()
    stack: list[Any] = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            sid = node.get("source_id")
            if isinstance(sid, str) and sid not in known:
                found.add(sid)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return sorted(found)


def validate_pkb(data: dict[str, Any], sources: list[dict[str, Any]]) -> PKBData:
    """Trả `PKBData` nếu hợp lệ, không thì ném `PKBInvalid` liệt kê mọi lỗi tìm được."""
    errors: list[str] = []
    model: PKBData | None = None
    try:
        model = PKBData.model_validate(data)
    except ValidationError as e:
        errors += _pydantic_errors(e, "data/")
    ids: set[str] = set()
    for i, s in enumerate(sources):
        try:
            ids.add(Source.model_validate(s).id)
        except ValidationError as e:
            errors += _pydantic_errors(e, f"sources/{i}/")
    if len(ids) != len(sources):
        errors.append("sources: id trùng hoặc không hợp lệ")
    errors += [f"data: source_id '{sid}' không có trong sources" for sid in
               unknown_source_ids(data, ids)]  # fmt: skip
    if errors or model is None:
        raise PKBInvalid(errors)
    return model
