import type { Asset, Project, Scene } from "./model";

const productId = "fixture:layouts";
const assets: Asset[] = [
  { id: "fixture:clip", kind: "video", productId, rights: "Media mẫu do người review chọn; chưa xác minh quyền sử dụng." },
  ...["before", "after", "focus"].map(id => ({ id: `fixture:${id}`, kind: "image" as const, productId, rights: "Ảnh mẫu kiểm tra bố cục, không phải bằng chứng sản phẩm." })),
];
const base = { duration: 6, segments: [], refs: [], parts: [] };
const scenes: Scene[] = [
  { ...base, id: "s01", layout: "feature_clip", subtitle: "Clip mẫu để review bố cục.", props: { title: { text: "Clip kết hợp thông tin" }, steps: [{ text: "Nội dung có nguồn" }, { text: "Tư liệu đúng sản phẩm" }] }, parts: [{ assetId: "fixture:clip", start: 1, end: 7 }], motion: { introEnd: .8, beats: [{ text: "Nội dung có nguồn", start: 1, end: 3 }, { text: "Tư liệu đúng sản phẩm", start: 3.3, end: 5.8 }] } },
  { ...base, id: "s02", layout: "steps", subtitle: "Các bước minh họa, chưa phải nội dung M2.", props: { title: { text: "Trình bày từng bước" }, items: [{ number: "1", text: "Chọn tư liệu mẫu" }, { number: "2", text: "Kiểm tra vị trí chữ" }, { number: "3", text: "Xem bản trình bày" }] } },
  { ...base, id: "s03", layout: "before_after", subtitle: "Hai phía để kiểm bố cục, không chứng minh kết quả sản phẩm.", props: { title: { text: "Hai trạng thái để đối chiếu" }, panels: [{ label: "Trước", text: "Tư liệu trước" }, { label: "Sau", text: "Tư liệu sau" }] }, compareIds: ["fixture:before", "fixture:after"] },
  { ...base, id: "s04", layout: "highlight_zoom", subtitle: "Vùng focus minh họa.", props: { title: { text: "Nhấn vùng quan trọng" } }, imageId: "fixture:focus", focus: { rect: [.4, .3, .3, .3], at: 2 } },
];
export const sample: Project = {
  title: "Bản thử bốn layout", productId, sourceUrl: "https://example.com",
  source: "Dữ liệu giả để review FE; chưa phân tích link hoặc có timing giọng thật.",
  sourcePayload: { origin: "fixture" }, timing: "fixture", scenes, assets,
};
