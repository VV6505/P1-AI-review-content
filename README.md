# P1 AI review content

Mã nguồn local của luồng tạo video giới thiệu sản phẩm: cung cấp link → khám phá → duyệt PKB → duyệt kịch bản → dựng video → QA và tải MP4.

- `frontend/`: giao diện Next.js; chạy theo hướng dẫn trong `frontend/README.md`.
- `backend/services/worker/`: API, runner, M1, M2 và renderer; xem `backend/services/worker/README.md`.
- `backend/supabase/`: cấu hình và migration cơ sở dữ liệu dùng cùng worker.

## Chạy luồng P1 trên Windows

Máy cần **Python 3.12**, [uv](https://docs.astral.sh/uv/), **Node.js 24**, pnpm (xem `frontend/package.json`) và **FFmpeg + ffprobe** trong `PATH`. Các lệnh bên dưới chạy bằng PowerShell, từ thư mục gốc repo. Chế độ local dùng dữ liệu trên máy, không cần chạy Supabase.

### 1. Cấu hình backend

```powershell
cd backend/services/worker
Copy-Item .env.example .env
uv sync
uv run playwright install chromium
```

Mở `.env` và đặt tối thiểu:

```dotenv
LOCAL_P1_MODE=1
N8N_SERVICE_TOKEN=mot-token-tu-ban-dat
GEMINI_API_KEY=key-gemini-cua-ban
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.5-flash-lite
TTS_PROVIDER=edge
```

Token là chuỗi bất kỳ đủ khó đoán, **phải giống** `P1_SERVICE_TOKEN` ở frontend. Giữ `.env` trên máy, không đưa key hoặc token vào Git. Nếu thay `.env` khi đang chạy, dừng và mở lại cả API lẫn runner.

### 2. Cấu hình frontend

Mở một terminal khác ở thư mục gốc repo:

```powershell
cd frontend
Copy-Item .env.example .env.local
pnpm install
```

Đặt trong `frontend/.env.local`:

```dotenv
P1_LOCAL_MODE=1
P1_API_BASE_URL=http://127.0.0.1:8000
P1_SERVICE_TOKEN=mot-token-tu-ban-dat
```

### 3. Mở ba terminal

Chạy **mỗi lệnh trong một terminal riêng**:

```powershell
cd backend/services/worker
uv run --env-file .env uvicorn worker.main:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
cd backend/services/worker
uv run --env-file .env python -m worker.runner
```

```powershell
cd frontend
pnpm dev
```

Kiểm tra API tại `http://127.0.0.1:8000/health` (trả `{"status":"ok"}`), rồi mở `http://localhost:3000/creator/create`. Đăng nhập tài khoản Creator mẫu `creator` / `123456` nếu giao diện yêu cầu. Chọn **Tạo dự án mới**, dán link sản phẩm và đi theo các bước khám phá → duyệt PKB → duyệt kịch bản → chọn template → dựng video → tải MP4. Nếu website yêu cầu đăng nhập, dùng cửa sổ đăng nhập do luồng P1 mở để tự nhập tài khoản; không đưa mật khẩu vào ô mô tả.

`/health` chỉ là kiểm tra API, không phải giao diện web. API nhận yêu cầu; **runner phải chạy** để xử lý khám phá và dựng video. Dừng từng tiến trình bằng `Ctrl+C` tại terminal của nó.

Chi tiết cấu hình và xử lý lỗi: [frontend/README.md](frontend/README.md), [backend/services/worker/README.md](backend/services/worker/README.md). Repo không lưu API key, phiên đăng nhập, dữ liệu crawl hay video xuất.
