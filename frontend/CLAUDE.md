@AGENTS.md

# AI-review-FE

Web app của **AI Review Content Factory**, là một nửa của split repo. Backend, schema DB và docs nằm ở `PotatoMine725/AI-review-BE`
(trên máy: `../AI-review-BE`). Đọc `../AI-review-BE/docs/specs/PRD.md` (§30–32, §62 cho màn hình) trước khi làm UI.
Quy ước Git/PR/DoD nằm trong `CONTRIBUTING.md`. Tài liệu chỉ nằm ở `../AI-review-BE/docs/` (xem `docs/README.md` của repo này).

## Stack
Next.js (App Router, `src/`) + TypeScript + Tailwind CSS v4 + shadcn/ui, pnpm. Không thêm thư viện ngoài stack khi chưa hỏi.
Component UI thêm bằng `pnpm dlx shadcn@latest add <tên>`, không tự viết lại component shadcn đã có.

## Lệnh
```bash
pnpm install
pnpm dev
pnpm lint && pnpm exec next typegen && pnpm exec tsc --noEmit   # giống CI
```

## Cấu trúc và lớp truy cập dữ liệu
Lý do và cách mở rộng của cấu trúc này nằm trong `../AI-review-BE/docs/adr/0005-repo-structure-and-extensibility.md`.
- **Mọi lời gọi backend đi qua một chỗ**, component và page không gọi trực tiếp:
  - `src/lib/api/`: gọi HTTP tới worker (và các service sau này);
  - `src/lib/supabase/`: client Supabase (server và browser).

  Khi backend đổi endpoint hoặc provider thì chỉ phải sửa lớp này. Tạo thư mục khi có lời gọi đầu tiên, không tạo trước.
- Code theo tính năng đặt trong `src/features/<module>/` (ví dụ `src/features/m1-onboarding/`). `src/components/ui/` chỉ chứa component shadcn.

## Quy tắc
- Branch `feat/<module>-<mô-tả>` | `fix/…` | `docs/…` | `chore/…`, tạo từ `dev` và mở PR vào `dev` (không vào `main`). Conventional Commits.
  Squash merge, cần ≥ 1 review. `dev → staging → main` chỉ promote bằng merge commit (xem CONTRIBUTING §2, §4).
- API của worker theo `../AI-review-BE/docs/specs/api-contract.md`. Schema DB theo `../AI-review-BE/supabase/migrations/`. Không tự đặt ra API.
- `SUPABASE_SERVICE_ROLE_KEY` chỉ được dùng ở code server. Biến dùng ở client phải có tiền tố `NEXT_PUBLIC_`.
- Có biến môi trường mới thì cập nhật `.env.example`.
