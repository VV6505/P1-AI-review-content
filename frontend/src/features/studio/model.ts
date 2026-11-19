export type Language = "vi" | "en";
export type Theme = "light" | "dark";
export const aspectRatios = ["16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "4:5", "5:4", "21:9", "9:21"] as const;
export const p1AspectRatios = ["16:9", "9:16"] as const;
export const p1Durations = [40, 42, 45] as const;
export const videoModels = [{ id: "veo", name: "Veo" }, { id: "kling", name: "Kling" }, { id: "sora", name: "Sora" }] as const;
export const videoTemplates = [
  { id: "short-countdown", vi: "Short đếm ngược", en: "Countdown short", descriptionVi: "Demo sản phẩm, chữ bật theo lời đọc.", descriptionEn: "Product demo with animated captions." },
  { id: "animation", vi: "Hoạt hình đồ họa", en: "Motion graphics", descriptionVi: "Đồ họa chuyển động, minh họa thông tin rõ ràng.", descriptionEn: "Animated graphics that explain information clearly." },
  { id: "cinematic", vi: "Điện ảnh tối giản", en: "Minimal cinematic", descriptionVi: "Hình ảnh tập trung vào sản phẩm, nhịp kể tinh gọn.", descriptionEn: "Product-focused visuals with restrained pacing." },
  { id: "vintage", vi: "Cổ điển", en: "Vintage", descriptionVi: "Chất liệu và nhịp kể gợi cảm giác cổ điển.", descriptionEn: "Textures and pacing with a vintage feel." },
] as const;
export type ReferenceFile = { id: string; name: string; type: string; size: number };
export type ProductReview = {
  sourceUrl: string; name: string; description: string; features: string;
  pricing: string; variant: string; sources: string; confirmedAt: string | null;
};
export type RequirementsReview = { version: 1; confirmedAt: string; snapshot: string };
export type Draft = {
  sourceUrl: string; preparedUrl: string; prompt: string; opening: string;
  notes: string; projectId: string | null;
  requirementsReview: RequirementsReview | null;
  model: typeof videoModels[number]["id"];
  references: ReferenceFile[];
  productReview: ProductReview | null;
  count: number; ratio: typeof aspectRatios[number]; resolution: "720p" | "1080p";
  style: "short-countdown" | "cinematic" | "animation" | "vintage" | "realistic" | "minimal";
  duration: number; outputLanguage: Language; camera: "auto" | "static" | "pan";
  negativePrompt: string;
};
// Keep saved legacy styles readable; new automatic requests use the three P1 presets.
export function templateForStyle(style: Draft["style"]) {
  return videoTemplates.find(template => template.id === style) ?? videoTemplates[1];
}
export function creatorDraft(draft: Draft): Draft {
  const [width, height] = draft.ratio.split(":").map(Number);
  return { ...draft, ratio: width > height ? "16:9" : "9:16", duration: p1Durations.some(duration => duration === draft.duration) ? draft.duration : 42 };
}
export type Request = Draft & { id: string; createdAt: string; estimatedTokens: number; status: "completed" };
export type User = { id: string; name: string; email: string; planId: string; tokens: number; active: boolean };
export type Plan = { id: string; name: string; price: number; tokens: number; active: boolean };
export type Transaction = { id: string; userId: string; amount: number; reason: string; createdAt: string };
export type StudioState = { schema: 1; revision: number; draft: Draft; requests: Request[]; users: User[]; plans: Plan[]; transactions: Transaction[] };
export const STUDIO_KEY = "reviewlab.studio.v1";
export const emptyDraft: Draft = { sourceUrl: "", preparedUrl: "", prompt: "", opening: "", notes: "", projectId: null, requirementsReview: null, model: "veo", references: [], productReview: null, count: 1, ratio: "9:16", resolution: "1080p", style: "cinematic", duration: 42, outputLanguage: "vi", camera: "auto", negativePrompt: "" };
export const initialStudio: StudioState = {
  schema: 1, revision: 0, draft: emptyDraft, requests: [], transactions: [],
  plans: [{ id: "free", name: "Free", price: 0, tokens: 2500, active: true }, { id: "creator", name: "Creator", price: 299000, tokens: 5000, active: true }, { id: "pro", name: "Pro", price: 799000, tokens: 15000, active: true }],
  users: [{ id: "demo", name: "Minh Anh", email: "minhanh@example.com", planId: "creator", tokens: 3200, active: true }, { id: "user-2", name: "Hoàng Nam", email: "hoangnam@example.com", planId: "pro", tokens: 12400, active: true }, { id: "user-3", name: "Thu Hà", email: "thuha@example.com", planId: "free", tokens: 350, active: false }],
};
export function normalizeSource(value: string): string {
  const url = new URL(value.trim());
  if (!["https:", "http:"].includes(url.protocol) || !url.hostname.includes(".") || url.username || url.password) throw new Error("url");
  url.hash = "";
  return url.toString().replace(/\/$/, "");
}
export function estimateTokens(draft: Draft): number {
  // UI illustration only; the backend must provide the authoritative quote.
  const modelFactor = { veo: 1, kling: 0.8, sora: 1.2 }[draft.model];
  return Math.ceil(draft.duration * (draft.resolution === "1080p" ? 12 : 8) * (templateForStyle(draft.style).id === "cinematic" ? 1.25 : 1) * modelFactor) * draft.count;
}
export function validDraft(value: Draft): boolean {
  if (value?.preparedUrl) { try { normalizeSource(value.preparedUrl); } catch { return false; } }
  return !!value && ["sourceUrl", "preparedUrl", "prompt", "opening", "negativePrompt", "notes"].every(key => typeof value[key as keyof Draft] === "string") && (value.projectId === null || typeof value.projectId === "string") &&
    Array.isArray(value.references) && value.references.length <= 6 && value.references.every(file => file && typeof file.id === "string" && typeof file.name === "string" && typeof file.type === "string" && Number.isSafeInteger(file.size) && file.size > 0 && file.size <= 10 * 1024 * 1024) &&
    (value.productReview === null || validProductReview(value.productReview)) &&
    (value.requirementsReview === null || !!value.requirementsReview && value.requirementsReview.version === 1 && typeof value.requirementsReview.snapshot === "string" && typeof value.requirementsReview.confirmedAt === "string" && Number.isFinite(Date.parse(value.requirementsReview.confirmedAt))) &&
    videoModels.some(model => model.id === value.model) && Number.isSafeInteger(value.count) && value.count > 0 && aspectRatios.includes(value.ratio) && ["720p", "1080p"].includes(value.resolution) &&
    ["short-countdown", "cinematic", "animation", "vintage", "realistic", "minimal"].includes(value.style) && [5, 10, 15, 30, 40, 42, 45, 60].includes(value.duration) &&
    ["vi", "en"].includes(value.outputLanguage) && ["auto", "static", "pan"].includes(value.camera);
}
function validProductReview(value: ProductReview): boolean {
  if (!value || !["sourceUrl", "name", "description", "features", "pricing", "variant", "sources"].every(key => typeof value[key as keyof ProductReview] === "string")) return false;
  try { normalizeSource(value.sourceUrl); } catch { return false; }
  return value.confirmedAt === null || (typeof value.confirmedAt === "string" && Number.isFinite(Date.parse(value.confirmedAt)));
}
export function productIsConfirmed(draft: Draft): boolean {
  const review = draft.productReview;
  if (!review?.confirmedAt || !Number.isFinite(Date.parse(review.confirmedAt)) || !review.name.trim() || !review.description.trim() || !review.sources.trim()) return false;
  try { return review.sourceUrl === normalizeSource(draft.sourceUrl) && review.sources.split("\n").filter(line => line.trim()).every(line => !!normalizeSource(line)); } catch { return false; }
}
/** UI approval only. The server must independently validate PKB, revisions and job ownership. */
export function requirementsSnapshot(draft: Draft): string {
  return JSON.stringify({ sourceUrl: normalizeSource(draft.sourceUrl), notes: draft.notes,
    productReview: draft.productReview, references: draft.references,
    model: draft.model, count: draft.count, ratio: draft.ratio, resolution: draft.resolution,
    style: templateForStyle(draft.style).id, duration: draft.duration, outputLanguage: draft.outputLanguage });
}
export function requirementsAreConfirmed(draft: Draft): boolean {
  const approval = draft.requirementsReview;
  if (!productIsConfirmed(draft) || !approval || approval.version !== 1 || !Number.isFinite(Date.parse(approval.confirmedAt))) return false;
  return approval.snapshot === requirementsSnapshot(draft);
}
export function approveRequirements(draft: Draft, confirmedAt: string): Draft {
  if (!productIsConfirmed(draft) || !Number.isFinite(Date.parse(confirmedAt))) throw new Error("requirements-review");
  return { ...draft, requirementsReview: { version: 1, confirmedAt, snapshot: requirementsSnapshot(draft) } };
}
export function parseStudio(raw: string): StudioState {
  const state = JSON.parse(raw) as StudioState;
  // Preserve drafts and history saved before projects and notes were added.
  if (state?.draft) { state.draft.notes ??= ""; state.draft.projectId ??= null; state.draft.model ??= "veo"; state.draft.references ??= []; state.draft.productReview ??= null; state.draft.requirementsReview ??= null; }
  if (Array.isArray(state?.requests)) for (const request of state.requests) { if (request) { request.notes ??= ""; request.projectId ??= request.id; request.model ??= "veo"; request.references ??= []; request.productReview ??= null; request.requirementsReview ??= null; } }
  if (!state || state.schema !== 1 || !Number.isSafeInteger(state.revision) || state.revision < 0 || !validDraft(state.draft) || !Array.isArray(state.requests) || !Array.isArray(state.users) || !Array.isArray(state.plans) || !Array.isArray(state.transactions)) throw new Error("storage");
  if (!state.plans.length || state.plans.some(p => !p || typeof p.id !== "string" || typeof p.name !== "string" || !p.name.trim() || !Number.isSafeInteger(p.price) || p.price < 0 || !Number.isSafeInteger(p.tokens) || p.tokens < 0 || typeof p.active !== "boolean")) throw new Error("plans");
  if (!state.users.some(u => u.id === "demo") || state.users.some(u => !u || typeof u.id !== "string" || typeof u.name !== "string" || typeof u.email !== "string" || !state.plans.some(p => p.id === u.planId) || !Number.isSafeInteger(u.tokens) || u.tokens < 0 || typeof u.active !== "boolean")) throw new Error("users");
  if (state.requests.some(r => !r || !validDraft(r) || typeof r.id !== "string" || !Number.isFinite(Date.parse(r.createdAt)) || !Number.isSafeInteger(r.estimatedTokens) || r.estimatedTokens < 0 || r.status !== "completed")) throw new Error("requests");
  for (const request of state.requests) if (normalizeSource(request.sourceUrl) !== request.preparedUrl || !request.prompt.trim() || !request.opening.trim()) throw new Error("request source");
  if (state.transactions.some(t => !t || typeof t.id !== "string" || !state.users.some(u => u.id === t.userId) || !Number.isSafeInteger(t.amount) || !t.amount || typeof t.reason !== "string" || !t.reason.trim() || !Number.isFinite(Date.parse(t.createdAt)))) throw new Error("transactions");
  for (const rows of [state.plans, state.users, state.requests, state.transactions]) if (new Set(rows.map(r => r.id)).size !== rows.length) throw new Error("ids");
  state.draft = creatorDraft(state.draft);
  return state;
}

/** Local brief only. Product analysis, design decisions and rendering require the backend. */
export function prepareAutomaticDraft(draft: Draft): Draft {
  draft = creatorDraft(draft);
  if (!productIsConfirmed(draft)) throw new Error("product-review-required");
  const sourceUrl = normalizeSource(draft.sourceUrl);
  const product = draft.productReview!;
  const template = templateForStyle(draft.style);
  const vi = draft.outputLanguage === "vi";
  const facts = [product.name, product.description, product.features, product.pricing, product.variant, product.sources].filter(Boolean).join("\n");
  const direction = vi
    ? `Phong cách: ${template.vi}. ${template.descriptionVi}\nAI cần phân tích đúng sản phẩm tại ${sourceUrl} để chọn bộ màu, kiểu chữ, bố cục từng cảnh, tư liệu, chuyển động và nhịp dựng. Giữ nhận diện sản phẩm; không áp một bộ màu hoặc quy tắc hiển thị cố định cho mọi link. Không suy ra màu chỉ từ tên miền. Khi nguồn thiếu, dùng phương án trung tính và ghi rõ phần chưa xác minh. Chỉ dùng tư liệu được phép sử dụng và claim có nguồn; không tự tạo số liệu, giá hoặc cam kết.`
    : `Style: ${template.en}. ${template.descriptionEn}\nAI must analyze the specific product at ${sourceUrl} to choose its palette, typography, scene layouts, media, motion and pacing. Respect the product identity; do not apply one fixed palette or display policy to every link. Do not infer colors from the domain name alone. If evidence is missing, use a neutral fallback and flag unverified details. Use permitted media and sourced claims; do not invent statistics, prices or promises.`;
  const prompt = [
    vi ? `Yêu cầu dựng video tự động từ ${sourceUrl}.` : `Automatic video brief for ${sourceUrl}.`,
    direction,
    vi ? `Thông tin đã xác nhận:\n${facts}` : `Confirmed information:\n${facts}`,
    vi ? `Đầu ra: ${draft.ratio}, ${draft.duration}s, ${draft.resolution}, ${draft.count} video.` : `Output: ${draft.ratio}, ${draft.duration}s, ${draft.resolution}, ${draft.count} videos.`,
    draft.notes.trim() ? `${vi ? "Mô tả / mong muốn về video (nguyên văn người dùng, không phải thông tin sản phẩm đã xác minh)" : "Video description / preferences (verbatim user input, not verified product facts)"}:\n${draft.notes.trim()}` : "",
    vi ? "Dùng mong muốn để định hướng nội dung, đối tượng, giọng điệu và CTA. Thông tin sản phẩm mới hoặc số liệu trong mô tả cần đối chiếu với PKB hoặc hỏi lại ở bước xác nhận; không tự coi là claim được duyệt. Nếu thiếu thông tin để chọn hướng/dàn ý, hỏi bổ sung, không tự bịa." : "Use preferences to guide the content, audience, tone and CTA. New product information or metrics in the description must be checked against the PKB or clarified during review; they are not approved claims. Ask for missing information before proposing a direction or outline.",
    draft.references.length ? `${vi ? "Tệp tham khảo" : "Reference files"}: ${draft.references.map(file => file.name).join(", ")}` : "",
  ].filter(Boolean).join("\n\n");
  const opening = vi
    ? `AI chọn cảnh mở đầu theo thông tin đã xác nhận của ${product.name}, phong cách ${template.vi} và tỷ lệ ${draft.ratio}; chưa có khung hình được AI tạo.`
    : `AI chooses the opening scene using confirmed information about ${product.name}, the ${template.en} style and ${draft.ratio} frame; no AI-generated frame is available yet.`;
  return { ...draft, sourceUrl, preparedUrl: sourceUrl, style: template.id, camera: "auto", negativePrompt: "", prompt, opening };
}
