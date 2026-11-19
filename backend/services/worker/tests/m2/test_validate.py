"""Parity: validator worker cho cùng kết luận (và cùng lỗi đầu tiên) với script của Định.

Kỳ vọng `fixtures/parity-29f868a.json` được ghi bằng cách chạy chính `validate_contracts.py` ở
commit 29f868a trên các ca của `parity_cases.py`, không viết tay. Tạo lại khi contract đổi: xem
`record_parity.py`.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tests.m2.parity_cases import Case, build_cases, input_from_context
from worker.m2.validate import SCRIPT_SCHEMA, content_errors, schema_errors, validate_input

EXPECTED = json.loads(
    (Path(__file__).parent / "fixtures" / "parity-29f868a.json").read_text(encoding="utf-8")
)["first_error"]
CASES = build_cases()
FIRST_ERROR_MAX = 90  # `first_error` của bản gốc cắt lỗi schema còn 90 ký tự


def run_worker(case: Case) -> list[str]:
    inp = input_from_context(case.context)
    if case.kind == "input":
        return validate_input(inp)
    if case.kind == "schema":
        return schema_errors(SCRIPT_SCHEMA, case.doc)
    if case.kind == "content":
        return content_errors(case.doc, inp)
    return schema_errors(SCRIPT_SCHEMA, case.doc) or content_errors(case.doc, inp)


def test_every_case_has_expectation() -> None:
    assert {c.name for c in CASES} == set(EXPECTED)


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_parity_with_dinh_validator(case: Case) -> None:
    errors = run_worker(case)
    want = EXPECTED[case.name]
    if not want:
        assert errors == []
        return
    assert errors, f"worker chấp nhận, script Định từ chối: {want}"
    first = errors[0]
    assert first == want or (len(want) == FIRST_ERROR_MAX and first.startswith(want))


def test_conflict_child_path_is_rejected() -> None:
    """Worker phải theo luật conflict path đã chốt trong contract #83."""
    case = next(c for c in CASES if c.name == "m2/conflict-parent-blocks-child-reference.json")
    errors = run_worker(case)
    assert errors and "đang có xung đột" in errors[0]


def test_lists_all_errors_not_only_first() -> None:
    """Worker trả mọi lỗi: hai claim sai cùng lúc thì có hai lỗi."""
    case = next(c for c in CASES if c.name == "m2/fact-ref-path-syntax.json")
    doc = deepcopy(case.doc)
    doc["scenes"][1]["claims"][0]["fact_refs"][0]["field_path"] = "features[99]"
    errors = content_errors(doc, input_from_context(case.context))
    assert len(errors) == 2
    assert "identity..category" in errors[0] and "features[99]" in errors[1]


def test_input_rejects_unapproved_pkb() -> None:
    case = CASES[0]
    inp = input_from_context(case.context)
    inp["approved_pkb"]["status"] = "draft"
    assert validate_input(inp)


def test_input_runs_m1_pkb_validation() -> None:
    """approved_pkb.data phải qua model PKB của M1 (vd. source_id phải có trong sources)."""
    inp = input_from_context(CASES[0].context)
    inp["approved_pkb"]["data"]["identity"]["name"]["source_id"] = "src_99"
    errors = validate_input(inp)
    assert errors and all(e.startswith("approved_pkb:") for e in errors)
