# services/worker

Python 3.12 + FastAPI, quản lý bằng **uv**. Cấu trúc và cách mở rộng: `docs/adr/0005-repo-structure-and-extensibility.md`.

```bash
uv sync
uv run uvicorn worker.main:app --reload --port 8000
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest   # giống CI
```

## Chạy thử P1 trọn luồng trên local

Bản local giữ nguyên hai cổng duyệt PKB/kịch bản nhưng thay Supabase bằng một file JSON và thay
Remotion bằng TTS + FFmpeg tuần tự (tối đa 2 luồng CPU mỗi cảnh). Đây chỉ là chế độ demo một
người; không dùng cho production hoặc nhiều process ghi đồng thời.

Trong `.env` (không commit), đặt tối thiểu:

```dotenv
LOCAL_P1_MODE=1
N8N_SERVICE_TOKEN=mot-token-local-tu-dat
GEMINI_API_KEY=key-cua-ban
TTS_PROVIDER=edge
```

Sau khi đã `uv sync`, cài Chromium một lần bằng `uv run playwright install chromium`. Mở hai cửa
sổ terminal tại `services/worker`: một cửa sổ chạy API bằng
`uv run uvicorn worker.main:app --reload --port 8000`; cửa sổ còn lại chạy hàng đợi bằng
`uv run python -m worker.runner`. Runner xử lý cả job crawl/PKB lẫn job TTS/FFmpeg.

`TTS_PROVIDER=edge` là lựa chọn nhẹ và không tiêu tốn API key; đổi thành `gemini` nếu muốn dùng
Gemini TTS. Nếu Edge tạm không trả audio, demo local tự dùng Google Translate TTS tiếng Việt làm
dự phòng (không cần key). Video chỉ được endpoint tải xuống trả về khi ffprobe đạt H.264/AAC, đúng
kích thước, ảnh không trắng và kịch bản tham chiếu ít nhất hai tư liệu sản phẩm khác nhau.

Trước khi tạo crawl job, FE gọi preflight bằng Playwright. Nếu gặp password field, redirect login
hoặc HTTP 401/403, FE hiện thẻ **Cần đăng nhập**. Owner bấm mở Chromium và tự đăng nhập trên trang
thật; mật khẩu không đi qua API/AI. API chỉ lưu `storage_state.json` dưới `LOCAL_P1_AUTH_DIR`, rồi
runner dùng phiên đó cho Crawl4AI và bước chụp tư liệu. Cơ chế này chỉ dành cho demo local; cloud
cần browser từ xa/noVNC và chính sách vòng đời secret riêng.

## M1 — crawl (`src/worker/m1/`)

Điểm vào: `worker.m1.crawl.service.crawl_product(url, options, fetcher, store, previous_hashes=...)` trả `CrawlResult`
(`status`, `error_code`, `retryable`, `pages` đủ trường `sources[]` của PKB). Module không biết DB, hàng đợi hay API:
hàng đợi gọi hàm này, ghi `error_message` vào `generation_jobs.error` và tự retry theo `retryable`.
Mã lỗi và quy tắc crawl: `docs/specs/m1-product-intelligence.md` (Quy tắc crawl, Mã lỗi crawl).

| File | Việc |
|---|---|
| `url.py` | `normalize_product_url` (khoá `products.website_url`), `normalize_page_url` |
| `config.py` | `CrawlSettings` (giá trị mặc định bằng spike, đè bằng biến môi trường `M1_CRAWL_<TÊN_HOA>`), `CrawlOptions` (host phụ, bật theo từng product) |
| `crawl/robots.py`, `throttle.py`, `discover.py`, `blocks.py` | robots RFC 9309, ≤ 1 request/giây/host, sitemap + chấm điểm + quota, nhận diện WAF / đăng nhập |
| `crawl/fetcher.py` | adapter Crawl4AI sau interface `PageFetcher` (đổi provider chỉ sửa file này) |
| `crawl/store.py` | `PageStore` + `LocalPageStore`; Supabase Storage cắm vào sau |

### Chạy thật bằng tay

```bash
uv run playwright install chromium     # một lần: cài trình duyệt cho Crawl4AI
uv run python -m worker.m1.crawl https://elevenlabs.io --out <thư mục tạm ngoài repo>
```

Ghi `pages/*.md` và `crawl.json` vào thư mục `--out`. Không commit output.

### Crawl4AI

- Dùng như thư viện (không chạy Docker server), ghim `crawl4ai==0.9.4` như spike. Không bật `enable_stealth`, không đổi User-Agent, không proxy.
- Kéo theo `unclecode-litellm` (fork của litellm, đụng tên module `litellm`) và `patchright`; đã kiểm tra ở ADR-0001.
- License: Apache-2.0 **kèm điều khoản ghi công**; web app phải ghi credit (xem ADR-0001, mục License Crawl4AI).

### Ngôn ngữ trang

`M1_CRAWL_LANGUAGES=en,vi` (mặc định) là các ngôn ngữ được crawl, theo thứ tự ưu tiên. Ngôn ngữ dò theo tiền tố path
(`/vi/`, `/en-us/`); path không có tiền tố coi là `en`. Trang ngôn ngữ khác: `language_not_allowed`. Bản dịch của trang
đã giữ ở ngôn ngữ ưu tiên hơn: `translation_duplicate`.

## M1 — extract 1.4 (`src/worker/m1/extract/`, `llm/`, `pkb/`)

Điểm vào: `await extract_product(crawl_result, page_store, llm)` trả `ExtractResult(data, sources, cost_breakdown,
warnings)`: PKB v0.3 `software` đã validate, `cost_breakdown` v1. Lỗi: `ExtractError` có `code`, `retryable`,
`retry_after` (hết quota ngày) và `cost_breakdown`. Mã lỗi, warning, cách nhận diện 429: đặc tả M1, mục
"Extract 1.4 trong worker".

| File | Việc |
|---|---|
| `llm/client.py` | `LLM.generate_json`: retry 429 RPM / 500 / 503 (5 → 10 → 20 → 40 → 60 s), 429 RPD → `llm_quota_daily`, 1 item chi phí mỗi lần gọi |
| `llm/gemini.py` | nơi duy nhất import `google-genai`; SDK không tự retry |
| `llm/fixture.py` | `LLM_PROVIDER=fixture`: đọc response đã lưu (`LLM_FIXTURE_PATH`), không gọi mạng |
| `llm/quota.py`, `cost.py` | nhận diện RPM / RPD, giờ reset 0h giờ Thái Bình Dương (`tzdata`); `CostItem` theo contract v1 |
| `pkb/models.py`, `validate.py` | model PKB v0.3 port từ spike; kiểm `source_id` có trong `sources` |
| `extract/service.py` | chọn top-k trang, gọi LLM, kiểm evidence, gộp, conflicts, nâng lên v0.3 |

```bash
# Cần GEMINI_API_KEY trong .env. Mỗi lần chạy = 1 lời gọi generate, tính vào 500 RPD của project.
uv run python -m worker.m1.extract <thư mục crawl> --out <thư mục tạm ngoài repo>
```

Ghi `pkb.json` ({data, sources}), `cost_breakdown.json`, `extract.json` (warnings hoặc lỗi). Không commit output.

**Thời gian xấu nhất của 1 lần extract** (đặt timeout job BE theo số này): `LLM_TIMEOUT_S × (1 + số bước của
LLM_RETRY_DELAYS_S) + tổng thời gian chờ`. Với mặc định: 180 s × 6 lần = 1080 s, cộng 135 s chờ (5 + 10 + 20 + 40 +
60) = **1215 s (~20 phút)**. Khi 429 RPM kèm `RetryInfo` ≥ 60 s ở mọi lần, mỗi lần chờ là 60 s: 1080 + 300 =
**1380 s (~23 phút)**. 429 RPD không retry nên kết thúc ngay. Chạy thật 21/10: mỗi lần 1 lời gọi, không retry.
Model PKB là bản port: sửa luật ở `spikes/m1-crawl-extract/schema_v03.py` thì sửa cả `pkb/models.py`
(`tests/m1/test_pkb.py` chạy model trên `docs/specs/pkb/examples/`).

### Test

`uv run pytest` chạy không cần mạng và không cần trình duyệt: `PageFetcher`, HTTP (robots, sitemap) và đồng hồ throttle
được thay bằng fake trong `tests/m1/fakes.py`; LLM dùng `FixtureTransport`; fixture ở `tests/m1/fixtures/`. Fixture 429
(`fixtures/llm/error-429-*.json`) là dữ liệu synthetic: chưa có response 429 thật.

## M2 — sinh kịch bản P1-AC-03 (`src/worker/m2/`)

Điểm vào: `await generate_script(input, llm, settings=None)` trả `ScriptResult(status, data, cost_breakdown,
warnings, error_code, error_message, retryable, retry_after, errors, raw_output)`. Lỗi trả trong kết quả, không
raise. `input` theo `p1-ac-03-input.v1`; `llm` là `LLM` của M1 (dùng chung retry / quota / cost).

| File | Việc |
|---|---|
| `contract/` | prompt, schema, ví dụ của Định, **chép nguyên byte** từ commit `8008cbf` (#83). Không sửa tại đây (`SOURCE.md`) |
| `validate.py` | port luật M2 của `spikes/m1-crawl-extract/validate_contracts.py`, trả mọi lỗi; `validate_input` chạy cả `validate_pkb` của M1 |
| `schema.py` | schema output → dạng Gemini nhận: chỉ giữ từ khoá đã chạy thật, `const` → `enum`, bỏ `estimated_duration_s` |
| `prompt.py` | system prompt = khối ```text của Định, điền 3 placeholder; `product_id`, `knowledge_version` đi ở tin nhắn user |
| `kind.py` | chuẩn bị `visual_plan.kind` từ allowlist (chỉ `kind`, audit cũ → mới + hash allowlist, ID lạ / sai Product / trùng thì báo lỗi, không đoán) |
| `repair.py` | template sửa của Định + feedback (`schema`, `content_validator`, `qa`, `syllable_advisory`) |
| `generate.py` | `generate_script` (sinh → chuẩn bị kind → validator → tối đa 1 lượt sửa) + CLI |

Mã lỗi: `m2_input_invalid` (input sai hoặc allowlist trùng ID, không gọi LLM), các mã `llm_*` của M1. Output sai
schema / refs / asset / CTA: `llm_invalid_output` kèm `errors` và `raw_output`. Worker không vá nội dung; ngoài
`kind` (điền theo allowlist) thì chỉ có **tối đa 1 lời gọi sửa** (`generate_script_repair`) khi còn lỗi validator,
lỗi QA cụ thể (`qa_feedback`) hoặc số âm tiết ngoài 150–170 (khuyến nghị, không phải lỗi). Sau lượt sửa còn lỗi
thì dừng. Mọi tầng nằm trong `ScriptResult.stages` (thô → sau chuẩn bị kind → feedback → bản sửa → kết quả
kiểm); mỗi lời gọi một item trong `cost_breakdown`. `estimated_duration_s` do worker tính:
tổng âm tiết lời thoại ÷ `M2_SYLLABLES_PER_S` (mặc định 3.75). Đây là **ước tính**, không phải duration TTS hay MP4.

```bash
# Cần GEMINI_API_KEY trong .env. Mỗi lần chạy = 1 lời gọi sinh + tối đa 1 lời gọi sửa (--no-repair để tắt).
uv run python -m worker.m2.generate <input.json> --out <thư mục>
```

Ghi `script.json` (kịch bản, hoặc output thô nếu không hợp lệ), `validation.json`, `cost.json`, `stages.json`, `feedback.json`, `initial|repair.{raw,prepared,kind_audit}.json`. Khoá `_note` trong
file input (ghi chú cho người đọc) được bỏ trước khi kiểm. Lần chạy đầu: `docs/report/m2-first-run-pdfcraft.md`.

## Bộ chạy job (`src/worker/runner/`)

Tiến trình riêng, tách khỏi API: `uv run python -m worker.runner` (`--once` để xử lý hết job rồi thoát). Cần `.env` có `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY` (hoặc `LLM_PROVIDER=fixture`) và `uv run playwright install chromium`.

Nhận job `crawl` ở trạng thái `queued` (cũ nhất trước), claim bằng `UPDATE ... WHERE status='queued'` (nguyên tử, không cần migration), chạy M1 crawl, rồi extract (M1, Gemini, 1 lời gọi/job) → `create_pkb_version` → ghi `pkb_version` và `result_manifest` → `completed`. Lỗi `retryable` được xếp lại `queued` (tối đa `RUNNER_MAX_ATTEMPTS`, chờ lũy thừa 2 từ `RUNNER_RETRY_BACKOFF_S`), còn lại `failed` kèm `error`. Markdown trang lưu ở `WORKER_PAGE_STORE_DIR/<job_id>/pages/` (đặt ngoài repo).

Bước nặng nằm sau Protocol `CrawlStep`/`ExtractStep` (`runner/steps.py`); test dùng fake, không cần trình duyệt hay LLM. Runner local còn nhận job `video`, đọc đúng script revision đã duyệt, tạo TTS, dựng MP4 bằng FFmpeg và ghi kết quả QA. **Chưa có:** timeout cho cả job (extract xấu nhất ~20 phút, xem mục extract), dọn job kẹt `running` khi runner chết (bảng chưa có `updated_at`), `previous_hashes` giữa các lần crawl.
