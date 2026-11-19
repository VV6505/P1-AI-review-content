# AI-review-FE

Web app của **AI Review Content Factory & Affiliate Network**: giao diện mock Creator tạo video và Admin quản lý người dùng, token, gói đăng ký, PKB.

Backend, schema DB và tài liệu (PRD, ADR, log) nằm ở [AI-review-BE](https://github.com/PotatoMine725/AI-review-BE).

## Stack
Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui, pnpm.

## Cấu trúc

```
AI-review-FE/
├── src/
│   ├── app/             # App Router: layout.tsx, page.tsx, globals.css
│   ├── components/ui/   # component shadcn/ui (thêm bằng: pnpm dlx shadcn@latest add <tên>)
│   ├── features/        # (khi có) code theo tính năng: features/<module>/
│   └── lib/
│       ├── utils.ts
│       ├── api/         # (khi có) MỌI lời gọi HTTP tới worker/service đi qua đây
│       └── supabase/    # (khi có) client Supabase server + browser
├── components.json      # cấu hình shadcn/ui
├── .env.example
└── .github/             # CI (ci.yml), PR/issue template, CODEOWNERS
```

## Chạy local

Yêu cầu: Node.js 24, pnpm (phiên bản trong `packageManager` của `package.json`).

```bash
pnpm install
cp .env.example .env.local    # tùy chọn khi cấu hình kết nối; giao diện mock không cần backend
pnpm dev                      # http://localhost:3000
```

### Bật luồng P1 thật trên local

Đặt ba biến server-only sau trong `.env.local` (token phải giống `N8N_SERVICE_TOKEN` trong
`services/worker/.env` của BE):

```dotenv
P1_LOCAL_MODE=1
P1_API_BASE_URL=http://127.0.0.1:8000
P1_SERVICE_TOKEN=mot-token-local-tu-dat
```

Sau khi API và runner của BE đang chạy, đăng nhập Creator rồi mở `/creator/create`. Trang này sẽ
thay luồng mock bằng: link + mô tả tùy chọn → M1/PKB → duyệt PKB → AI concept/kịch bản → duyệt
kịch bản → template/TTS/FFmpeg → QA → tải MP4. Service token chỉ được Route Handler phía server
đọc, không đưa xuống JavaScript trình duyệt. Tắt `P1_LOCAL_MODE` để trở lại giao diện demo cũ.

## Mô tả giao diện

Trang `/` dùng minh họa Creative bằng chữ trắng/bạc, nút phát và dải phim trên nền trong suốt để giới thiệu sáng tạo video sản phẩm cùng AI. Có thể đổi phong cách, khung hình và phát/tạm dừng chuyển động minh họa. Navigation trong suốt trên hero, có menu Cài đặt thả xuống để chuyển Việt/Anh và sáng/tối, cùng menu điều hướng di động. Các trang `/price` (gói minh họa và câu hỏi thường gặp), `/about` (giới thiệu Reviewlab) và `/credits` dùng chung header/footer với landing. Đăng nhập, đăng ký là các trang riêng không có navigation/footer, dùng cùng bảng màu xám/trắng của workspace, minh họa 3D nhân vật tương tác với video AI và các chi tiết bong bóng/ngôi sao nhẹ. Liên kết Crawl4AI nằm trong footer. Các trang này xem được khi chưa đăng nhập. Hình minh họa không gọi AI hoặc tạo video; navigation giữ đủ Home / Create / Price / About (có bản dịch Việt/Anh), bảng giá vẫn là dữ liệu mẫu, chưa có thanh toán.

Đăng nhập tại `/login`, đăng ký tại `/signup`. Đây là **mock phía trình duyệt**, chưa có xác thực server hoặc kết nối BE. Dùng mật khẩu mẫu, không nhập mật khẩu đang dùng ở dịch vụ khác.

- Creator: `creator`
- Admin: `admin`
- Mật khẩu chung: `123456`

Đăng nhập bằng tên tài khoản mẫu hoặc email đã đăng ký. Tài khoản mẫu đã lưu trên trình duyệt được cập nhật mật khẩu, giữ nguyên dữ liệu dự án.

Tài khoản đăng ký được lưu trên trình duyệt; mỗi tài khoản mới có dữ liệu dự án và tệp tham khảo riêng. Đăng xuất trong phần Cài đặt tài khoản. Hai tài khoản mẫu dùng chung workspace demo hiện có.

Trong màn tạo video, nhập link rồi mở **Chi tiết** để xem tiến trình mô phỏng thu thập nguồn → chuẩn hóa thông tin → review sản phẩm. Kiểm tra/sửa thông tin và xác nhận trước khi tạo video mẫu. Đóng hộp thoại sẽ hủy tiến trình đang chạy; tiến trình không truy cập website hoặc gọi AI.

Theo [BE #94](https://github.com/PotatoMine725/AI-review-BE/issues/94), Creator có một trường **Mô tả / mong muốn về video** để nêu đối tượng, thông điệp và giọng điệu, không cần nhập kịch bản/JSON. Nút **Thử với AISoEasy** điền link và mong muốn minh họa, không thu thập dữ liệu thật. Sau khi xác nhận sản phẩm, nút Tạo mở **Duyệt yêu cầu video** để kiểm/sửa mô tả và cấu hình. Chỉ **Xác nhận và xem mẫu** mới ghi lịch sử và trừ token mẫu. Yêu cầu được lưu nguyên văn trong `notes` cũ để giữ tương thích; thông tin mới hoặc số liệu người dùng nhập không tự trở thành fact đã duyệt. Thay đổi yêu cầu/cấu hình cần duyệt lại; lịch sử cũ không bị sửa hay được xác nhận ngầm. Đây là xác nhận đầu vào FE, không thay việc duyệt revision kịch bản hoặc kiểm quyền/job ở BE.

## Preview template trong Creator

Video demo có sẵn trong Git: [PDFCraft · chuyển PDF sang Word, 16:9, 18,77 giây](public/video-template/demo/pdfcraft-word-template-16x9.mp4). Dùng template HTML hiện tại, giữ toàn bộ clip và âm thanh gốc; [thông tin demo](public/video-template/demo/README.md).

Trang `/creator/template-review` dành cho đối chiếu template–renderer: tự nạp bộ s03 khi có thư mục bàn giao cục bộ, đổi phong cách/tỷ lệ, tua hình và xuất HTML. Dùng tài khoản mock hiện có để mở trang. Luồng Tạo vẫn dùng clip minh họa/localStorage, chưa nối pipeline AI–BE.

Composer hỗ trợ ba phong cách, **16:9 / 9:16** và mục tiêu **40 / 42 / 45 giây**. Lịch sử cũ được giữ; khi dùng lại, bản nháp chuyển sang lựa chọn P1. Màu/bố cục nhận theo từng sản phẩm qua cấu hình, người dùng không nhập prompt hay chỉnh thiết kế thủ công.

- Bốn layout Hưng nhận: `feature_clip`, `steps`, `before_after`, `highlight_zoom`, dùng chung bộ dựng HTML/CSS. Ba phong cách và layout là bản FE thử chờ Vũ review.
- Một mẫu tổng hợp bốn cảnh để xem bố cục; không phải kịch bản M2 hay video sản phẩm thật. Mẫu 24 giây không phải đầu ra P1 hoàn chỉnh.
- Schema M2 lấy từ BE #83 tại `057292f77a5824a936d7c29079ea4a47bf5528aa`. Adapter giữ script, IDs/refs/PKB version; validate bằng Ajv và kiểm mapping/asset/timeline. Không chép plan, font/icon hay layout ngoài phần Hưng từ spike #88.

Trong **Kiểm tra bàn giao và tư liệu**, nạp gói `{script, presentation, assets, source_url, product_name, product_design?}` và bind file cục bộ theo asset ID. Giới hạn 25 MB/file, khoảng 50 MB tổng. Không fetch URL/path từ nội dung và không lưu media vào localStorage. `product_design` gắn đúng Product/link, kiểm màu/tương phản; FE không suy màu từ URL.

Preview chỉ hình, không phát voice/karaoke; phân biệt timing `fixture`, `measured`. Xuất HTML một cảnh nhúng CSS/runtime/media và font Be Vietnam Pro/Noto Serif kèm giấy phép OFL. Thiếu media, media chưa giải mã xong hoặc chữ tràn sẽ khóa xuất HTML. Thời lượng ngoài 40–45 giây được cảnh báo; không tự kéo dài cảnh để đạt P1.

Khi nhận gói M2, phần **Hướng nội dung và kịch bản** hiển thị concept, đối tượng, hook và dàn ý theo cảnh. Mỗi cảnh có lời đọc theo `segment_id`, chữ trên hình, loại tư liệu, số từ, claim/fact refs và nút tua tới cảnh. Mục tiêu MP4, ước tính trước TTS và timeline bàn giao được trình bày riêng. Tỷ lệ thời lượng cảnh khai báo dùng clip/ảnh trang và hai cảnh chữ liên tiếp là gợi ý review, không thêm điều kiện chặn P1. Payload M2 và mapping/timeline giữ nguyên.

Kiểm riêng phần FE #94: `node tests/p1-requirements.browser.cjs`, `node tests/m2-contract.browser.cjs` (cần dev server). Báo cáo và phần chờ bàn giao được chuẩn bị tại repo BE: `docs/report/web-p1-content-review-2026-11-02.md`.

### Mapping và thời gian của bốn layout

- `feature_clip`: `title_claim_index` chọn tiêu đề; `note_claim_indices` tùy chọn, tối đa bốn chỉ số claim trong cảnh, lấy nguyên text có fact refs để làm ghi chú. Không có danh sách này thì dùng toàn vùng nội dung cho clip. Không tự tách hoặc sinh claim.
- `steps`: `step_claim_indices` chọn thứ tự bước (1–6, không trùng). Thời điểm hiện lấy từ segment đầu tiên được claim tham chiếu; thứ tự bước phải phù hợp timeline. Tua lùi khôi phục đúng trạng thái chưa hiện.
- `before_after`: hai panel `Trước`/`Sau`, mỗi panel có `claim_index` và `asset_id` ảnh. Không tự tạo kết quả so sánh.
- `highlight_zoom`: `image_asset_id` hoặc `clip_parts`, cùng `focus.rect=[x,y,w,h]` chuẩn hóa trên tư liệu gốc và `focus.at_s` theo cảnh. Không crop ngầm; tư liệu được fit đúng tỷ lệ trước khi zoom.
- `clip_parts[].start_s/end_s` thuộc clip nguồn. Các đoạn nối liên tiếp từ thời điểm 0 của cảnh, phát **tốc độ 1×**; nếu lời thoại dài hơn clip thì giữ khung cuối. Tổng đoạn cắt vượt thời lượng cảnh quá một khung 30 fps bị từ chối, không tự tăng tốc/cắt bỏ nội dung. Quy tắc FE này cần AI–BE xác nhận khi chốt mapping.
- Segment timing dùng giây tương đối trong cảnh. `measured` yêu cầu audio asset từng segment, nhưng FE không xác nhận phép đo của bên bàn giao và không coi target M2 là thời lượng MP4 đã đạt.

### Handoff cho renderer

Mở HTML xuất ra ở viewport 1920×1080 hoặc 1080×1920 theo tỷ lệ đã chọn. Với mỗi khung, gọi và **await** `window.CreatorTemplate.renderAt(frameIndex / fps)` (API version 1); chỉ chụp khi `mediaReady === true` và `textOverflow.length === 0`. `seek` là alias async của `renderAt`; không chụp ngay sau lời gọi chưa await. Các lời gọi được xử lý tuần tự để tránh tranh chấp khi giải mã/tua clip. `diagnostics()` chỉ đọc trạng thái hiện tại, không đợi media. Phụ đề là text của segment đang phát, không giả timing từng từ. Renderer tiếp tục chịu trách nhiệm ghép audio, chuyển cảnh và xác nhận thời lượng MP4 cuối.

JSON review đầy đủ bốn layout: `tests/fixtures/template-handoff.json`. Đây là fixture tổng hợp, không phải nội dung/nguồn sản phẩm thật. Nạp trong mục Kiểm tra bàn giao; bind file theo asset ID. Gói này giữ nguyên M2 và tách presentation, chưa phải API/render contract được nhóm phê duyệt.

Kiểm tra: `corepack pnpm test`, `corepack pnpm lint`, `corepack pnpm build`. Kiểm giao diện bằng cách đổi preset/tỷ lệ, tua cảnh, thử JSON lỗi và mở HTML xuất offline. Mẫu bốn layout nằm trong mục Kiểm tra bàn giao của trang đối chiếu.

### Thử cảnh s03 PDFCraft với clip và audio bàn giao

Đặt thư mục `2026-10-26_s03-feature-clip` vào `public` (giữ ngoài Git), mở `/creator/template-review`. Trang mở mặc định bản **Dọc 9:16**, có hai nút **Ngang 16:9 / Dọc 9:16** luôn ở phía trên và không tự cuộn che bộ chọn. Adapter riêng đọc `scene-handoff.v0`, giữ JSON gốc và bằng chứng F4/V1; không giả lập thành payload M2 hoặc gán Product/PKB version chưa được bàn giao.

- Đọc metadata clip/audio và kiểm timing trước khi hiển thị. Crop pixel được đổi theo kích thước clip gốc; focus được đổi sang tọa độ trong vùng crop.
- `focus.part` là chỉ số 0-based; `source_t` đổi qua các đoạn cắt thành mốc theo cảnh. Bộ này zoom từ 4,76 s, clip chạy 1× từ đầu cảnh, giữ khung cuối sau 6,46 s; cảnh dài 7,9 s.
- Preview vẽ phụ đề câu theo timing đo thật, không phát audio. HTML xuất từ giao diện nhúng media/font để xem offline.
- Lệnh renderer xuất HTML dùng file media tương đối, chụp 30 fps bằng `await renderAt(t)`, dừng nếu media/font lỗi hoặc chữ tràn; FFmpeg ghép audio và một lớp phụ đề ASS. Chỉ kiểm chứng một cảnh, không phải API/job hoặc MP4 P1 40–45 s.
- Bố cục `feature_clip` ngang mở bằng clip lớn ở giữa. Trong mỗi nhịp chỉ dẫn, clip thu nhỏ sang bên đối diện nội dung rồi mở lại ở giữa trước điểm cắt tiếp theo; bản dọc giữ clip ở giữa, chỉ dẫn vào/ra phía trên/dưới. Bản ngang dùng toàn clip 1920×1080; bản dọc dùng crop BE bàn giao. Vùng focus được quy đổi theo cách đặt nguồn, giữ đúng tỷ lệ hình. Với s03: tiêu đề mở đầu rút đi sau ~1,3 s; các nhịp Chọn vị trí / Bấm Apply / Định dạng / Kết quả bám điểm cắt 2,4 / 4,48 / 6,46 s. Nhịp kết quả trả về khung lớn. Không giữ cả danh sách bước trên màn hình.

```powershell
# Node 24, Chrome cài sẵn, FFmpeg có libass; sửa đường dẫn cho máy đang chạy.
$env:FFMPEG_BIN = 'C:\tools\ffmpeg\bin\ffmpeg.exe'
corepack pnpm render:scene --out D:\s03-review --ratio both --preset cinematic --preview-dir public/video-template/s03-centered
node tests/scene-handoff.browser.cjs
```

Có thể truyền `--input <scene-s03.json>`, `--ratio 16:9|9:16|both`, `--preset cinematic|animation|vintage`; đặt `CHROME_PATH` nếu không dùng Chrome mặc định. Kiểm giao diện cần dev server (`TEST_BASE_URL`, mặc định `http://127.0.0.1:3000`). Kết quả gồm HTML preview/render, media/font kèm license, MP4, phụ đề, mapped scene, hash tư liệu và `measurements.json`. Công cụ so khung renderer với preview tại 2 / 4,8 / 7 s, có tua lùi; kiểm codec, tỷ lệ, fps, thời lượng và giải mã đủ khung của MP4.

`--preview-dir` chép hai MP4 và poster vào thư mục local được ignore; trang hiển thị hai player có giọng đọc, ghi rõ Ngang 16:9 (1920×1080) và Dọc 9:16 (1080×1920). Bật `S03_REQUIRE_RENDERED=1` khi chạy kiểm trình duyệt để bắt buộc xác nhận metadata cả hai player. File media/output tiếp tục giữ ngoài Git.

Kiểm thử trình duyệt: chạy app, đặt `TEST_BASE_URL` theo server, rồi `node tests/video-template.browser.cjs`. Có thể đặt `PLAYWRIGHT_MODULE`, `CHROME_PATH`, `FFMPEG_BIN` theo máy; mặc định kế thừa môi trường Windows của các bài kiểm thử hiện có. Script tạo media tổng hợp trong `test-results/video-template`, kiểm 24 tổ hợp, mapping/tốc độ clip, tua lùi, export offline và mobile. `RENDER_FIXTURE=1` bật kiểm thử chụp khung và encode FFmpeg; kết quả này chỉ chứng minh cơ chế render fixture, không nghiệm thu P1 với sản phẩm thật.

[Mapping và cảnh chung s03](https://github.com/PotatoMine725/AI-review-BE/pull/87). Issue #15 còn chờ review thiết kế/mapping, media/audio thật, API và MP4 40–45 giây ở hai tỷ lệ. Chưa chốt renderer sản phẩm.

## Tài liệu

- [Template engine dùng chung](docs/template-engine.md): truyền project M2, cấu hình màu/font và timeline chỉ dẫn; render toàn bộ cảnh bằng `pnpm render:project --input <project.json> --assets <asset-files.json> --out <output> --ratio both`. PDFCraft s03 là dữ liệu demo; engine nhận dữ liệu của project khác qua cùng adapter và renderer.
- [CONTRIBUTING.md](CONTRIBUTING.md): Git flow, commit, PR, Definition of Done
- [AI-review-BE/docs](https://github.com/PotatoMine725/AI-review-BE/tree/dev/docs): PRD, API contract và tài liệu backend
