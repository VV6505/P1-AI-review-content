"""Chuẩn hoá markdown và băm nội dung (NFR-04: trang không đổi thì bỏ qua)."""

from __future__ import annotations

import hashlib
import re

MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
MD_LINK_TARGET = re.compile(r"\]\([^)]*\)")


def normalize_text(md: str) -> str:
    """Chuẩn hoá markdown trước khi băm: bỏ khoảng trắng thừa và dòng trống liên tiếp."""
    lines = [ln.rstrip() for ln in md.replace("\r\n", "\n").split("\n")]
    out: list[str] = []
    for ln in lines:
        if ln == "" and (not out or out[-1] == ""):
            continue
        out.append(ln)
    return "\n".join(out).strip() + "\n"


def content_hash(text: str) -> str:
    """Băm nội dung đã bỏ ảnh và URL đích của link, để hash chỉ đổi khi chữ đổi (SP-07).

    Link có token đổi theo mỗi lần tải trang (vd. claude.ai/redirect/<uuid>/…); ảnh lazy-load
    đổi vị trí.
    """
    stable = MD_LINK_TARGET.sub("]", MD_IMAGE.sub("", text))
    stable = "\n".join(ln for ln in stable.splitlines() if ln.strip())
    return "sha256:" + hashlib.sha256(stable.encode("utf-8")).hexdigest()
