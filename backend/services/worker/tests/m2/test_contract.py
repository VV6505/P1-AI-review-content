"""Contract M2 trong worker phải trùng byte với commit 8008cbf của #83.

So bằng git blob SHA-1 (`sha1(b"blob <len>\\0" + bytes)`), tính bằng Python thuần, nên chạy được
trên CI clone nông không có commit 8008cbf. SHA lấy từ `git ls-tree -r 8008cbf`.
"""

from __future__ import annotations

import hashlib

import pytest

from worker.m2.validate import CONTRACT_DIR

BLOB_SHA_8008CBF = {
    "p1-ac-03-script-vi.prompt.md": "f222ad1ed3f6be4a8cfbc8c2ee7d102e6722f163",
    "p1-ac-03-script-vi-repair.prompt.md": "a2f073d84c25c43e047c242b20fe5707ff24f522",
    "p1-ac-03-script-vi.v1.schema.json": "149ba9f538346d9c62345dfa30af21c0fef2e3a6",
    "p1-ac-03-input.v1.schema.json": "0b567b22c53f3ab016ec2cc6b5d64414b7c573b9",
    "examples/invalid-script-p1-ac-03-vi-missing-fact-ref.json": (
        "5e58f0ccca0d4f550ba746c487dc5e8b055e1a0d"
    ),
    "examples/invalid-script-p1-ac-03-vi-unknown-asset.json": (
        "a73ebd0f3b52d7bc085de3a74acd20e1989be15b"
    ),
    "examples/valid-script-p1-ac-03-vi.context.json": "cbb2d7bd8c5790f6a5869b2f5f7006e11ef57a20",
    "examples/valid-script-p1-ac-03-vi.json": "01e8534530edd2efcb7ed30b8461da4aa4280f56",
    # spikes/m1-crawl-extract/output/elevenlabs/pkb.gemini-3.5-flash-lite.json
    "examples/elevenlabs-pkb.gemini-3.5-flash-lite.json": (
        "fdfcb70f3cfa601125938b101d2ce8fca833e268"
    ),
}


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


@pytest.mark.parametrize("name", sorted(BLOB_SHA_8008CBF))
def test_contract_file_matches_commit_8008cbf(name: str) -> None:
    assert git_blob_sha((CONTRACT_DIR / name).read_bytes()) == BLOB_SHA_8008CBF[name]


def test_no_untracked_contract_files() -> None:
    """File mới trong contract/ phải được ghi nguồn và SHA ở đây (trừ SOURCE.md)."""
    found = {p.relative_to(CONTRACT_DIR).as_posix() for p in CONTRACT_DIR.rglob("*") if p.is_file()}
    assert found - {"SOURCE.md"} == set(BLOB_SHA_8008CBF)
