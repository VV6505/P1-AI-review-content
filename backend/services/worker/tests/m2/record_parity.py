"""Ghi kỳ vọng parity: chạy validator của Định trên `parity_cases.build_cases()`.

Không phải test (không có tiền tố `test_`). Chạy tay khi contract #83 đổi:

    git worktree add --detach <tmp> <commit>
    .venv/Scripts/python -I -X utf8 tests/m2/record_parity.py \
        <tmp>/spikes/m1-crawl-extract tests/m2 tests/m2/fixtures/parity-<commit>.json

Kết quả 29f868a (11/11) được ghi từ chính `validate_contracts.py`.
"""

import json
import sys
from pathlib import Path

dinh_dir, tests_dir, out = map(Path, sys.argv[1:4])
sys.path[:0] = [str(dinh_dir), str(tests_dir)]
import validate_contracts as vc  # type: ignore[import-not-found]  # noqa: E402
from parity_cases import build_cases  # type: ignore[import-not-found]  # noqa: E402

script_v = vc.validator(vc.SPECS / "m2" / "p1-ac-03-script-vi.v1.schema.json")
res = {}
for c in build_cases():
    if c.kind == "input":
        err = vc.validate_p1_vi_input_schema(c.context)
    elif c.kind == "schema":
        err = vc.first_error(script_v, c.doc)
    elif c.kind == "content":
        err = vc.validate_p1_vi_script_content(c.doc, c.context)
    else:
        err = vc.first_error(script_v, c.doc) or vc.validate_p1_vi_script_content(c.doc, c.context)
    res[c.name] = err
source = "spikes/m1-crawl-extract/validate_contracts.py @ 29f868a (#83)"
doc = {"source": source, "first_error": res}
out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for name, err in res.items():
    print(("FAIL " if err else "PASS ") + name, "|", err[:80])
