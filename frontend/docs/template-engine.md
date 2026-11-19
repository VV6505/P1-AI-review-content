# Template video dùng chung

Engine nằm trong `src/features/video-template/`, dùng cùng một `buildFrame` cho preview và `buildRenderFrame` cho HTML của renderer. PDFCraft s03 là bộ dữ liệu kiểm thử của engine; phần chuyển động không phụ thuộc tên sản phẩm, lời thoại hoặc các mốc 2,4/4,48/6,46 giây của s03.

## Đầu vào và cách gọi

`fromM2(envelope)` nhận gói `{script, presentation, assets, source_url, product_name, product_design?}`. `script` giữ nguyên contract M2 #83; các quyết định hiển thị nằm riêng trong `presentation`. Adapter trả `Project` có nhiều cảnh, IDs và fact refs gốc.

Schema FE đồng bộ nguyên bản từ BE #83 tại commit `67f68275c4e43e3e1266e3df91999968ee6d6f51`; đường dẫn và mã đối chiếu nằm trong [nguồn schema](../src/features/video-template/fixtures/SOURCE.md). Giữ `additionalProperties: false` ở các cấp theo contract.

`script.estimated_duration_s` có thể vắng mặt; nếu có phải là số lớn hơn 0 và không quá 600. Adapter giữ nguyên ước tính trong `Project.sourcePayload`, không thay thời lượng cảnh/segment hoặc dùng để xác nhận đạt P1. Preview và renderer vẫn dùng timeline từ `presentation`; `target_duration_s` tiếp tục là mục tiêu 40–45 giây. Visual kind `ai_generated_image` cũng được nhận theo schema mới; BE cần sinh/resolve media và bàn giao asset hợp lệ trước khi render ảnh đó.

Sau khi chạy FE local, dùng `node tests/m2-contract.browser.cjs` để kiểm nạp payload có/không có ước tính, timeline, preview ảnh và từ chối dữ liệu sai. Đặt `TEST_BASE_URL` nếu server khác `http://127.0.0.1:3000`. Bài kiểm dùng fixture và ảnh canvas tổng hợp, không cần bộ media s03 gửi riêng.

```tsx
const project = fromM2(m2Envelope);
// Media là bindings đã được caller kiểm quyền/resolve. Preview dùng data URL.
<VideoTemplatePreview
  key={`${project.productId}:${revision}`}
  initialProject={project}
  initialMedia={resolvedPreviewMedia}
  ratio="16:9"
  preset="cinematic"
  close={closePreview}
/>
```

Caller có thể là màn project hoặc adapter API. Không phải đổi code template khi thay sản phẩm/nội dung. Preview cũng cho nhập gói M2 và bind file trong phần Kiểm tra bàn giao. Truyền `initialProject` thì không chạy loader s03.

## Nhịp chỉ dẫn

Mỗi `presentation.scenes[]` của layout `feature_clip` có thể khai báo:

```json
{
  "scene_id": "s01",
  "layout": "feature_clip",
  "duration_s": 6,
  "motion": {
    "intro_end_s": 0.5,
    "mode": "adaptive",
    "beats": [
      {"claim_index": 0, "start_s": 0.8, "end_s": 2.6, "side": "left"},
      {"claim_index": 1, "start_s": 3, "end_s": 5.2, "side": "right"}
    ]
  }
}
```

Đây là phần trích minh họa; gói đầy đủ vẫn cần segments, clip parts, asset allowlist và các trường contract M2.

- `claim_index` chọn text đã có trong `script.scenes[].claims`; presentation không có trường để thêm claim tùy ý.
- Mốc thời gian là thời gian **của cảnh**, không phải clip gốc. Cần bàn giao theo timeline/audio thật khi `timing="measured"`.
- `adaptive`: bản ngang thu nhỏ clip sang phía đối diện chỉ dẫn, trở lại khung lớn khi nhịp kết thúc. `side` có thể chọn riêng từng nhịp.
- `centered`: giữ clip ở giữa kể cả khi hiện chỉ dẫn. Bản dọc luôn giữ clip ở giữa theo thiết kế hiện tại.
- `result:true` giữ khung lớn và dùng nhãn kết quả.
- Validator kiểm giới hạn thời gian, thứ tự, chồng lấn, mode/side và chỉ số claim.
- Nếu không khai báo `motion`, adapter lấy thời gian của claim được chọn trong `note_claim_indices` từ các narration segment mà claim tham chiếu. **Không tự chia đều thời lượng.** Nếu các chỉ dẫn chồng nhau, cần cung cấp mapping motion rõ ràng.

`motion.ts` là contract chuẩn hóa dùng chung cho M2 và adapter bàn giao s03. Các hàm chuyển động nhận `t`, nên tua tiến/lùi và render không phụ thuộc đồng hồ máy.

## Màu và font theo video

`product_design` được kiểm đúng Product/link và độ tương phản; ví dụ:

```json
{
  "product_id": "b1000000-0000-4000-8000-000000000001",
  "source_url": "https://product.example.com",
  "background": "#111827",
  "foreground": "#f8fafc",
  "accent": "#8bdc65",
  "surface": "#182235",
  "border": "#51627f",
  "heading_font": "be-vietnam-pro",
  "body_font": "be-vietnam-pro"
}
```

Font hỗ trợ: `be-vietnam-pro`, `noto-serif`; font và giấy phép đã có trong project. AI/BE có thể cung cấp cấu hình này, template kiểm và áp dụng. Không nhận URL font hoặc CSS/JS từ đầu vào. Khi thiếu cấu hình, dùng thiết kế dự phòng của preset.

Phần này chưa tự gọi AI phân tích thương hiệu hay sinh màu/font; đó là bước upstream cung cấp cấu hình. Các trường bổ sung nằm trong wrapper presentation/design, chưa đổi schema script M2, API hoặc ERD phía BE.

## Render nhiều cảnh của một project

```powershell
$env:FFMPEG_BIN = 'C:\tools\ffmpeg\bin\ffmpeg.exe'
corepack pnpm render:project --input D:\bundle\project.json --assets D:\bundle\asset-files.json --out D:\output --ratio both --preset cinematic
```

Bindings là file riêng do caller tin cậy cung cấp, ví dụ `{"clip:1":"media/recording.mp4","voice:1":"media/voice.wav"}`. Tool chỉ đọc media trong bundle, kiểm đường dẫn thật để chặn thoát thư mục/symlink, loại file, dung lượng, điểm cắt và thời lượng audio. Asset ID từ M2 không được dùng trực tiếp làm đường dẫn hệ thống.

`render:project` chạy từng cảnh qua **cùng renderer**, rồi ghép theo thứ tự cảnh và timeline đã cung cấp. Kết quả:

- `16x9/project.mp4`, `9x16/project.mp4`.
- `scenes/<scene_id>/`: HTML preview/render, MP4 cảnh, media/fonts, log và số đo.
- `source-project.json`: input gốc, không bị sửa; `normalized-project.json`: dữ liệu engine sử dụng.
- `project-results.json`: Product, scene IDs, duration, frame count và kết quả render.

Chạy riêng một cảnh từ gói M2:

```powershell
corepack pnpm render:scene --input D:\bundle\project.json --assets D:\bundle\asset-files.json --scene s02 --out D:\scene-output --ratio both
```

Tool cũ đọc `scene-handoff.v0` vẫn hoạt động để hồi quy s03. M2 hỗ trợ bốn layout hiện có: `feature_clip`, `steps`, `before_after`, `highlight_zoom`. Layout/asset ngoài khả năng hỗ trợ phải qua adapter khác; không tự bịa tư liệu hoặc nội dung.

### Xuất nhanh

`render:scene` và `render:project` mặc định dùng tối đa 4 worker Chrome, chụp JPEG chất lượng 95 qua CDP, và thử encoder NVIDIA NVENC bằng một lần encode thật. Máy không có NVENC dùng `libx264` như trước. Giữ 1080p, 30 fps, cùng CSS, font, crop, focus và chuyển động; không cần LLM chỉnh template.

Với nguồn SDR `yuv420p` tối đa 1080p/120 giây, renderer giải mã nguồn một lần thành PNG kèm timestamp PTS chính xác. Chrome đọc frame đã giải mã thay vì tua lại video cho từng ảnh. Trước khi xuất, renderer đối chiếu ba thời điểm với preview; nguồn có sai khác lớn do cách nội suy ảnh/video sẽ tự dùng video native. Nguồn ngoài giới hạn cũng dùng video native. Các PNG/JPEG trung gian nằm trong output để kiểm tra và cần dung lượng đĩa; chúng không sửa file nguồn.

Đây là chế độ tương đương về bố cục/chuyển động, không phải pixel-identical: trình duyệt nội suy RGB và YUV khác nhau, JPEG và MP4 cũng có nén mất dữ liệu. Báo cáo lưu MAE, PSNR, SSIM; kiểm pre-encode yêu cầu MAE ≤ 2/255, PSNR ≥ 32 dB và SSIM ≥ 0.95. Khi cần đường media/capture cũ, dùng `--decode video --capture-format png --encoder cpu`; vẫn có thể chạy song song.

```powershell
corepack pnpm render:project --input D:\bundle\project.json --assets D:\bundle\asset-files.json --out D:\output --ratio 16:9 --workers 4 --encoder auto
```

Tùy chọn dùng chung: `--workers 1..8`, `--capture-format jpeg|png`, `--decode frames|video`, `--encoder auto|cpu|nvenc`. Ghép project copy stream video đã encode, chỉ nối/encode audio để xử lý padding AAC. Hash của toàn bộ frame sau ghép được đối chiếu với các scene theo đúng thứ tự.

Đo trên một video có sẵn và project chuẩn hóa một scene không có narration riêng:

```powershell
node scripts/benchmark-template-render.mjs --project D:\demo\project.json --video D:\demo\source.mp4 --out D:\benchmark\original
node scripts/benchmark-template-render.mjs --project D:\demo\project.json --video D:\demo\source.mp4 --out D:\benchmark\one-minute --seconds 60
```

Lệnh thứ hai tạo file nguồn đủ 60 giây bằng cách lặp nội dung demo, rồi giải mã đủ 1800 frame; thời gian tạo nguồn không tính vào bước ghép template. `benchmark.json` phân biệt thời gian xuất MP4, thời gian QA bổ sung và tổng thời gian. QA kiểm cả frame trong MP4 đã encode, thời lượng/frame count và AAC gốc của bản không lặp. Số đo phụ thuộc máy, nguồn, layout và số worker; không dùng thời gian demo làm SLA cho mọi project.

Đo ngày 2026-11-16 trên i5-12450HX / RTX 3050 Laptop: nguồn PDFCraft lặp thành file thật 60 giây, 1920×1080, 30 fps; giải mã 15.74s, capture 61.62s, encode NVENC 7.98s, tổng xuất gồm khởi tạo và kiểm tra trước xuất **93.25s**. QA mở rộng thêm 23.07s, tổng **116.32s**. Đủ 1800 frame, kiểm 18 thời điểm trước encode và 3 thời điểm trong MP4, hash AAC nguồn/đầu ra trùng nhau. Mốc cũ 7–8 phút là ngoại suy từ lần render 18.77 giây, không phải benchmark 60 giây chạy đối chứng trong cùng lượt.

## Kiểm chứng tái sử dụng

```powershell
corepack pnpm test
node tests/template-reuse.render.mjs
```

Phép kiểm dùng hai Product/PKB khác nhau, tổng cộng bốn cảnh, các độ dài/điểm cắt/timing khác nhau, hai bộ màu/font và mode khác nhau; xuất cả ngang/dọc bằng cùng mã renderer. Clip là test pattern, audio là tone tổng hợp, nội dung fixture; không dùng kết quả này làm bằng chứng M2/LLM/TTS thật hoặc P1 đã nghiệm thu.

## Phần tích hợp còn lại

Luồng Tạo trong Creator vẫn là mock. BE cần cung cấp payload M2, asset đã kiểm quyền và timeline/audio thực tế, rồi gọi adapter/renderer dùng chung qua job. CLI hiện là công cụ local, chưa phải hàng đợi, Storage hoặc API production. Các bổ sung presentation/design cần được nhóm FE–AI–BE review để chốt contract.
