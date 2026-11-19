# Nguồn contract M2

Các file trong thư mục này là **bản chép nguyên byte** từ commit `8008cbf` (nhánh
`feat/m2-p1-ac-03-script-vi`, PR #83). Chủ sở hữu là Định (@VoHoangDinh). **Không sửa tại đây**:
muốn đổi thì đề xuất ở #83, rồi chép lại bản mới và cập nhật SHA trong
`tests/m2/test_contract.py`.

| File ở đây | Đường dẫn ở commit 8008cbf |
|---|---|
| `p1-ac-03-script-vi.prompt.md` | `docs/specs/m2/p1-ac-03-script-vi.prompt.md` |
| `p1-ac-03-script-vi-repair.prompt.md` | `docs/specs/m2/p1-ac-03-script-vi-repair.prompt.md` (template một lượt sửa) |
| `p1-ac-03-script-vi.v1.schema.json` | `docs/specs/m2/p1-ac-03-script-vi.v1.schema.json` |
| `p1-ac-03-input.v1.schema.json` | `docs/specs/m2/p1-ac-03-input.v1.schema.json` |
| `examples/*-script-p1-ac-03-vi*.json` | `docs/specs/m2/examples/` |
| `examples/elevenlabs-pkb.gemini-3.5-flash-lite.json` | `spikes/m1-crawl-extract/output/elevenlabs/pkb.gemini-3.5-flash-lite.json` (PKB mà `valid-script-p1-ac-03-vi.context.json` trỏ tới) |

Chép bằng `git cat-file blob 8008cbf:<đường dẫn> > <file>` (Git Bash, không qua PowerShell để tránh
BOM/CRLF). `.gitattributes` đặt `-text` cho thư mục này để git không đổi xuống dòng.

Từ `4c5b72b` đến `29f868a` chỉ prompt đổi trong thư mục này (blob `f70564b` → `2487354`); schema, ví dụ và PKB
giữ nguyên blob. `validate_contracts.py` đổi (`09224cf` → `638f499`): thêm luật `visual_plan.kind` phải
khớp `kind` của asset trong allowlist khi `source_type: existing_asset`, đã port vào `validate.py`. Parity ghi
lại ở `tests/m2/fixtures/parity-29f868a.json`.

Từ `29f868a` đến `8008cbf` (bàn giao 11/11): prompt sinh đổi (blob `2487354` → `f222ad1`, thêm luật 12 và ghi chú
tích hợp), thêm template sửa `p1-ac-03-script-vi-repair.prompt.md` (blob `a2f073d`), README đổi. Schema, ví dụ,
PKB và `validate_contracts.py` (blob `638f499`) giữ nguyên, nên `validate.py` và parity
(`tests/m2/fixtures/parity-29f868a.json`) không đổi. Chuẩn bị `kind` và lượt sửa là việc của worker
(`kind.py`, `repair.py`, `generate.py`), không nằm trong contract này.
