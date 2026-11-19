# Nguồn schema M2

`m2-script.schema.json` được chép từ [AI-review-BE PR #83](https://github.com/PotatoMine725/AI-review-BE/pull/83), không thêm quy tắc riêng của FE:

- Commit: `67f68275c4e43e3e1266e3df91999968ee6d6f51` (29/10/2026).
- File gốc: [`docs/specs/m2/p1-ac-03-script-vi.v1.schema.json`](https://github.com/PotatoMine725/AI-review-BE/blob/67f68275c4e43e3e1266e3df91999968ee6d6f51/docs/specs/m2/p1-ac-03-script-vi.v1.schema.json).
- Git blob SHA-1 (LF): `2b029141c551a8356048249977d73b00e5820ce5`.

`estimated_duration_s` là trường tùy chọn ở cấp script, kiểu number với `0 < value <= 600`. Giữ nguyên giá trị trong `Project.sourcePayload`; thời lượng cảnh vẫn lấy từ `presentation.scenes[].duration_s` và timing segment đã bàn giao. Trường này không xác nhận thời lượng MP4 đạt 40–45 giây.

Bản này cũng nhận visual kind `ai_generated_image`. Ảnh đã có vẫn cần asset thuộc Product và allowlist; yêu cầu `ai_generation` chưa phải file media có thể render. BE vẫn kiểm PKB, nguồn fact, conflict, ownership và quyền sử dụng trước khi bàn giao.

Khi cập nhật schema, chép lại từ một commit BE cụ thể, cập nhật thông tin nguồn tại đây và chạy các ca tương thích/kiểm dữ liệu sai trong `tests/video-template.test.mjs`.
