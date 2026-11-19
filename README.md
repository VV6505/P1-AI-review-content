# P1 AI review content

Mã nguồn local của luồng tạo video giới thiệu sản phẩm: cung cấp link → khám phá → duyệt PKB → duyệt kịch bản → dựng video → QA và tải MP4.

- `frontend/`: giao diện Next.js; chạy theo hướng dẫn trong `frontend/README.md`.
- `backend/services/worker/`: API, runner, M1, M2 và renderer; xem `backend/services/worker/README.md`.
- `backend/supabase/`: cấu hình và migration cơ sở dữ liệu dùng cùng worker.

Tạo file `.env` riêng từ `.env.example` ở từng ứng dụng. Repo không lưu API key, phiên đăng nhập, dữ liệu crawl hay video xuất.
