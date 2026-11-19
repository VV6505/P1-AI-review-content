"""Model PKB của worker phải cho cùng kết luận với ví dụ trong docs/specs/pkb/examples/."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from worker.m1.pkb.validate import PKBInvalid, validate_pkb

EXAMPLES = Path(__file__).resolve().parents[4] / "docs" / "specs" / "pkb" / "examples"
FILES = sorted(EXAMPLES.glob("*.json")) if EXAMPLES.exists() else []


@pytest.mark.skipif(not FILES, reason="cần thư mục docs của repo")
@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_vi_du_pkb(path: Path) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if path.name.startswith("valid-"):
        validate_pkb(doc["data"], doc["sources"])
    else:
        with pytest.raises(PKBInvalid):
            validate_pkb(doc["data"], doc["sources"])


def test_source_id_la_bi_bat_du_pydantic_hop_le() -> None:
    doc = json.loads((EXAMPLES / "valid-v03-software.json").read_text(encoding="utf-8"))
    doc["data"]["identity"]["name"]["source_id"] = "src_09"
    with pytest.raises(PKBInvalid, match="src_09"):
        validate_pkb(doc["data"], doc["sources"])
