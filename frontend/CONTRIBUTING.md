# Quy ước đóng góp — AI Review Content Factory

> File này **giống hệt nhau** ở `AI-review-BE` và `AI-review-FE`. Sửa ở repo nào thì sửa luôn repo kia trong cùng ngày.
> Team có thể đổi quy ước ở buổi retro thứ Sáu; quyết định ghi vào `docs/logs/decision-log.md` (repo BE).

## 1. Repo nào chứa gì

| Repo | Nội dung |
|---|---|
| [`AI-review-FE`](https://github.com/PotatoMine725/AI-review-FE) | Web: Next.js (App Router) + TypeScript + Tailwind + shadcn/ui, pnpm |
| [`AI-review-BE`](https://github.com/PotatoMine725/AI-review-BE) | `services/` (mỗi service một thư mục; hiện có `services/worker`: Python 3.12 + FastAPI, uv), `supabase/` (migrations), `docs/` (specs, plan, ADR, report, review, logs; xem `docs/README.md`) |

- Thay đổi schema DB thì làm ở BE (`supabase/migrations/`). Web dùng type sinh ra từ schema đó.
- Thay đổi API của worker thì cập nhật `docs/specs/api-contract.md` (BE) trong cùng PR.
- Một tính năng chạm cả 2 repo cần **2 PR**, link chéo nhau (`PotatoMine725/AI-review-BE#12`). PR BE (schema/API) merge trước.

## 2. Git: `dev` → `staging` → `main`

| Branch | Vai trò | Nhận thay đổi từ |
|---|---|---|
| `dev` | Nhánh tích hợp hằng ngày. Dev tạo branch từ đây | PR từ `feat/…`, `fix/…`, `docs/…`, `chore/…` |
| `staging` | Bản để tester kiểm thử | PR `dev → staging`, khi team chốt một đợt test |
| `main` | Bản ổn định, mỗi milestone một lần (gắn tag, ví dụ `v0.1.0`) | PR `staging → main`, sau khi QA duyệt |

- Không push thẳng vào `dev`, `staging`, `main`. Mọi thay đổi đi qua PR.
- 3 nhánh này tồn tại lâu dài, **không bao giờ xóa**.
- Branch làm việc ngắn hạn (lý tưởng ≤ 2 ngày), tạo từ `dev` mới nhất, mở PR vào `dev`:
  - `feat/<module>-<mô-tả>`, ví dụ `feat/m1-crawl-robots`, `feat/web-onboarding-form`
  - `fix/<module>-<mô-tả>`, ví dụ `fix/worker-health-timeout`
  - `docs/<mô-tả>`, ví dụ `docs/adr-0001-crawl-tool`
  - `chore/<mô-tả>` cho cấu hình, CI, dependency
- `<module>` là `m1`…`m8` theo PRD/đặc tả, hoặc `web`, `worker`, `db`, `ci`.
- Mô tả dùng chữ thường không dấu, nối bằng `-`.

**Sửa lỗi gấp trên `main` (hotfix):** tạo `fix/<module>-<mô-tả>` từ `main`, mở PR vào `main`.
Merge xong thì mở tiếp PR `main → staging` và `staging → dev` (merge commit) để bản sửa không bị mất ở lần promote sau.

## 3. Commit: Conventional Commits

```
<type>(<scope tùy chọn>): <mô tả ngắn>
```
`type` gồm: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`. Ví dụ: `feat(m1): lưu content_hash cho crawled_pages`.

## 4. Pull request

- Mở PR sớm (có thể ở dạng Draft), điền đủ PR template, link card trên board / issue (`Closes #N`).
- Cần **≥ 1 review approve** của người khác trước khi merge.
- Cách merge tùy loại PR:
  - PR từ branch làm việc vào `dev` (hoặc hotfix vào `main`): **squash merge**. Tiêu đề PR là commit message cuối cùng nên phải theo Conventional Commits.
  - PR promote `dev → staging`, `staging → main` và PR đồng bộ ngược sau hotfix: **merge commit**, không squash.
    Squash ở bước này tạo commit mà nhánh nguồn không có, nên lần promote sau sẽ bị conflict và hiện lại thay đổi cũ.
- Người mở PR tự merge sau khi đủ điều kiện, rồi xóa branch làm việc. Không xóa `dev`, `staging`, `main`.

## 5. Definition of Done

Một task chỉ được chuyển sang **Done** khi:
- [ ] Đã được review và approve
- [ ] CI xanh
- [ ] Có test, hoặc ghi rõ trong PR vì sao chưa có
- [ ] Tài liệu liên quan đã cập nhật (README, `docs/specs/api-contract.md`, ADR, `.env.example`…)

_QA bổ sung chi tiết DoD và template test case trong tuần 1._

## 6. Secrets và chi phí API

- Mọi key (Supabase, Gemini, fal…) đặt trong `.env`, **không bao giờ commit**. Chỉ commit `.env.example` với giá trị rỗng.
- Lỡ commit key thì báo ngay và rotate key, xóa commit thôi là không đủ.
- Spike tuần 1 có tổng ngân sách ≤ $20. Ghi lại số tiền đã dùng.

## 7. Giao tiếp

- Câu hỏi nghiệp vụ ghi vào `docs/logs/qa-log.md` (BE), quyết định ghi vào `docs/logs/decision-log.md`.
- Bị chặn thì báo ở standup hoặc kênh chung trong vòng 2 giờ, và đổi card sang "Bị chặn".
