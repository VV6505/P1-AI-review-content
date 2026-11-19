// Presentation adapter, not a replacement for the M2 contract. Keep source payloads intact.
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import m2Schema from "./fixtures/m2-script.schema.json" with { type: "json" };
import { validateMotion, type SceneMotion } from "./motion.ts";
const validator = new Ajv2020({ allErrors: true, strict: false });
addFormats(validator);
const validM2 = validator.compile(m2Schema);
export const layouts = ["feature_clip", "steps", "before_after", "highlight_zoom"] as const;
export type Layout = typeof layouts[number];
export type Ratio = "16:9" | "9:16";
export type FactRef = { source_id?: string; field_path: string };
export type Asset = { id: string; kind: "video" | "image" | "audio"; productId: string; rights: string };
export type ClipPart = { assetId: string; start: number; end: number };
export type Focus = { rect: number[]; at: number };
export type Cue = { id: string; text: string; start: number; end: number; audioId?: string };
export type Scene = {
  id: string; layout: Layout; props: Record<string, unknown>; subtitle: string;
  duration: number; segments: Cue[]; refs: FactRef[]; parts: ClipPart[];
  focus?: Focus; imageId?: string; compareIds?: string[];
  crop?: { rect: number[]; sourceSize: number[] };
  handoffRefs?: string[];
  motion?: SceneMotion;
};
export type TemplateFont = "be-vietnam-pro" | "noto-serif";
export type Design = { product_id: string; source_url: string; background: string; foreground: string; accent: string; surface?: string; border?: string; heading_font?: TemplateFont; body_font?: TemplateFont };
export type Project = {
  title: string; productId: string; sourceUrl: string; source: string; sourcePayload: unknown;
  knowledgeVersion?: number; pkbSchemaVersion?: string; timing: "fixture" | "measured";
  scenes: Scene[]; assets: Asset[]; design?: Design;
};
type Obj = Record<string, unknown>;
function requireValue(value: unknown, message: string): asserts value { if (!value) throw new Error(message); }
function obj(value: unknown): Obj { requireValue(value && typeof value === "object" && !Array.isArray(value), "Dữ liệu phải là object."); return value as Obj; }
function list(value: unknown, max = 24): unknown[] { requireValue(Array.isArray(value) && value.length <= max, "Danh sách thiếu hoặc vượt giới hạn."); return value; }
function text(value: unknown, max = 500): string { requireValue(typeof value === "string" && value.trim() && value.length <= max, `Nội dung cần có chữ và tối đa ${max} ký tự.`); return value; }
function num(value: unknown, min = 0, max = 3600): number { requireValue(typeof value === "number" && Number.isFinite(value) && value >= min && value <= max, "Mốc thời gian hoặc tọa độ không hợp lệ."); return value; }
function unique(ids: string[]) { requireValue(new Set(ids).size === ids.length, "ID bị trùng."); }
function rectangle(value: unknown): number[] {
  const result = list(value, 4).map(x => num(x, 0, 1));
  requireValue(result.length === 4 && result[2] > 0 && result[3] > 0 && (result[0] + result[2] <= 1 && result[1] + result[3] <= 1), "Vùng focus nằm ngoài ảnh.");
  return result;
}
function refs(value: unknown): FactRef[] {
  return list(value, 100).map(item => { const ref = obj(item); const path = text(ref.field_path); requireValue(/^[A-Za-z_]\w*(?:\.\w+|\[\d+\])*$/.test(path), "Fact ref sai định dạng."); if (ref.source_id !== undefined) requireValue(/^src_\d{2,}$/.test(text(ref.source_id)), "Source ID không hợp lệ."); return { ...ref } as FactRef; });
}
function safeUrl(value: unknown): string { const raw = text(value, 2000); const url = new URL(raw); requireValue(["http:", "https:"].includes(url.protocol) && !url.username && !url.password, "Link nguồn không hợp lệ."); url.hash = ""; return url.toString().replace(/\/$/, ""); }
function luminance(hex: string) { return hex.match(/\w\w/g)!.map(n => parseInt(n, 16) / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0); }
function validateDesign(value: unknown, productId: string, sourceUrl: string): Design | undefined {
  if (value === undefined) return;
  const d = obj(value); requireValue(d.product_id === productId && safeUrl(d.source_url) === sourceUrl, "Nhận diện thuộc sản phẩm/link khác.");
  for (const key of ["background", "foreground", "accent"]) requireValue(/^#[0-9a-f]{6}$/i.test(text(d[key])), "Màu phải có định dạng #RRGGBB.");
  const bg = luminance(d.background as string);
  for (const key of ["foreground", "accent"]) { const fg = luminance(d[key] as string); requireValue((Math.max(bg, fg) + .05) / (Math.min(bg, fg) + .05) >= 4.5, "Màu chưa đủ tương phản."); }
  for (const key of ["surface", "border"]) if (d[key] !== undefined) requireValue(/^#[0-9a-f]{6}$/i.test(text(d[key])), "Màu phải có định dạng #RRGGBB.");
  if (d.surface) for (const key of ["foreground", "accent"]) { const surface = luminance(d.surface as string), color = luminance(d[key] as string); requireValue((Math.max(surface, color) + .05) / (Math.min(surface, color) + .05) >= 4.5, "Màu trên thẻ chưa đủ tương phản."); }
  for (const key of ["heading_font", "body_font"]) if (d[key] !== undefined) requireValue(["be-vietnam-pro", "noto-serif"].includes(String(d[key])), "Font chưa nằm trong thư viện hỗ trợ.");
  return { ...d, product_id: productId, source_url: sourceUrl } as Design;
}

/** Input: unchanged M2 script + presentation/timing/allowlist supplied separately by AI–BE. */
export function fromM2(raw: unknown): Project {
  const envelope = obj(raw); const script = obj(envelope.script); const presentation = obj(envelope.presentation);
  requireValue(validM2(script), `M2 không khớp schema #83: ${validator.errorsText(validM2.errors, { separator: "; " })}`);
  requireValue(script.schema_version === "p1-ac-03.v1-draft", "Phiên bản M2 chưa hỗ trợ.");
  const productId = text(script.product_id); requireValue(/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(productId), "Product ID không hợp lệ.");
  requireValue(["0.2", "0.3"].includes(text(script.pkb_schema_version)), "Phiên bản PKB chưa hỗ trợ.");
  const knowledgeVersion = num(script.knowledge_version, 1); requireValue(Number.isInteger(knowledgeVersion), "Phiên bản knowledge không hợp lệ.");
  num(script.target_duration_s, 40, 45);
  const sourceUrl = safeUrl(envelope.source_url); const title = text(envelope.product_name, 120);
  requireValue(presentation.product_id === productId && presentation.knowledge_version === knowledgeVersion, "Cấu hình trình bày lệch Product/knowledge version.");
  requireValue(["fixture", "measured"].includes(String(presentation.timing)), "Cần ghi rõ timeline fixture hay đo từ audio.");
  const assets: Asset[] = list(envelope.assets, 64).map(rawAsset => { const a = obj(rawAsset); requireValue(a.product_id === productId, "Asset thuộc sản phẩm khác."); requireValue(["video", "image", "audio"].includes(String(a.kind)), "Loại asset chưa hỗ trợ."); return { id: text(a.asset_id), kind: a.kind as Asset["kind"], productId, rights: text(a.rights_basis) }; });
  unique(assets.map(a => a.id));
  function asset(id: unknown, kind?: Asset["kind"]) { const key = text(id); requireValue(assets.some(a => a.id === key && (!kind || a.kind === kind)), "Asset chưa có trong allowlist hoặc sai loại."); return key; }
  const mapping = list(presentation.scenes, 12).map(obj); unique(mapping.map(p => text(p.scene_id)));
  const allSegmentIds: string[] = [];
  const scenes = list(script.scenes, 12).map((rawScene): Scene => {
    const s = obj(rawScene); const id = text(s.scene_id); requireValue(/^s\d{2}$/.test(id), "Scene ID không hợp lệ.");
    const p = mapping.find(p => p.scene_id === id); requireValue(p, `Thiếu mapping cho ${id}.`);
    const layout = text(p.layout) as Layout; requireValue(layouts.includes(layout), "Layout chưa hỗ trợ.");
    const duration = num(p.duration_s, .1, 120); const segmentInput = list(s.narration_segments, 100).map(obj); requireValue(segmentInput.length, "Cảnh thiếu câu thoại.");
    const timing = list(p.segments, 100).map(obj); requireValue(timing.length === segmentInput.length, "Timeline không đủ segment."); unique(timing.map(t => text(t.segment_id)));
    let previousEnd = 0;
    const segments: Cue[] = segmentInput.map(input => { const segmentId = text(input.segment_id); requireValue(new RegExp(`^${id}-u\\d{2}$`).test(segmentId), "Segment không thuộc cảnh."); allSegmentIds.push(segmentId); const t = timing.find(t => t.segment_id === segmentId); requireValue(t, "Thiếu timing segment."); const start = num(t.start_s, previousEnd, duration); const end = num(t.end_s, start, duration); requireValue(end > start, "Segment không có thời lượng."); previousEnd = end; const audioId = t.audio_asset_id ? asset(t.audio_asset_id, "audio") : undefined; requireValue(presentation.timing !== "measured" || audioId, "Timing đo thật cần audio asset từng segment."); return { id: segmentId, text: text(input.text), start, end, audioId }; });
    const claims = list(s.claims, 40).map(obj);
    const factRefs: FactRef[] = [];
    claims.forEach(c => { text(c.text); const r = refs(c.fact_refs); requireValue(r.length, "Claim thiếu fact ref."); factRefs.push(...r); const ids = list(c.segment_ids).map(id => text(id)); requireValue(ids.length && ids.every(id => segments.some(s => s.id === id)), "Claim tham chiếu segment ngoài cảnh."); });
    const visual = obj(s.visual_plan); if (visual.source_type === "existing_asset") asset(visual.asset_id);
    function claim(index: unknown) { const n = num(index, 0, claims.length - 1); requireValue(Number.isInteger(n), "Claim index không hợp lệ."); return claims[n]; }
    const selected = p.title_claim_index === undefined ? undefined : claim(p.title_claim_index);
    const subtitle = text(s.subtitle_text); const heading = selected ? text(selected.text, 180) : subtitle;
    const props: Obj = { title: { text: heading }, steps: [] };
    function displayClaim(index: unknown) {
      const c = claim(index);
      const cue = segments.filter(segment => (c.segment_ids as string[]).includes(segment.id));
      return { text: text(c.text, 160), at: Math.min(...cue.map(segment => segment.start)) };
    }
    // Select existing claims explicitly. Never infer bullets or procedural order from narration.
    if (layout === "feature_clip" && p.note_claim_indices !== undefined) {
      const indices = list(p.note_claim_indices, 4); unique(indices.map(String));
      props.steps = indices.map(displayClaim);
    }
    let motion: SceneMotion | undefined;
    if (layout === "feature_clip") {
      if (p.motion !== undefined) {
        const m = obj(p.motion);
        motion = validateMotion({ introEnd: num(m.intro_end_s, 0, duration), mode: m.mode as SceneMotion["mode"], beats: list(m.beats, 24).map(value => {
          const b = obj(value);
          return { text: text(claim(b.claim_index).text, 160), start: num(b.start_s, 0, duration), end: num(b.end_s, 0, duration), result: b.result as boolean | undefined, side: b.side as "left" | "right" | undefined };
        }) }, duration);
      } else {
        // Use the referenced narration intervals, never evenly distribute notes.
        const indices = p.note_claim_indices === undefined ? [] : list(p.note_claim_indices, 4);
        const beats = indices.map(index => {
          const c = claim(index), cues = segments.filter(segment => (c.segment_ids as string[]).includes(segment.id));
          return { text: text(c.text, 160), start: Math.min(...cues.map(c => c.start)), end: Math.max(...cues.map(c => c.end)) };
        });
        motion = validateMotion({ introEnd: beats.length ? Math.min(1.2, beats[0].start) : Math.min(1.2, duration * .18), beats }, duration);
      }
    }
    if (layout === "steps") {
      const indices = list(p.step_claim_indices, 6); requireValue(indices.length > 0, "Steps cần danh sách claim theo thứ tự đã bàn giao."); unique(indices.map(String));
      const items = indices.map((index, i) => ({ ...displayClaim(index), number: String(i + 1) }));
      requireValue(items.every((item, i) => i === 0 || item.at >= items[i - 1].at), "Thứ tự bước không khớp timeline lời thoại.");
      props.items = items;
    }
    let compareIds: string[] | undefined;
    if (layout === "before_after") { const panels = list(p.panels, 2).map(obj); requireValue(panels.length === 2 && panels[0].label === "Trước" && panels[1].label === "Sau", "Before/after cần hai phía Trước/Sau đã bàn giao."); props.panels = panels.map(panel => ({ label: panel.label, text: text(claim(panel.claim_index).text, 160) })); compareIds = panels.map(panel => asset(panel.asset_id, "image")); }
    const parts: ClipPart[] = p.clip_parts === undefined ? [] : list(p.clip_parts).map(rawPart => { const part = obj(rawPart); const start = num(part.start_s); const end = num(part.end_s); requireValue(end > start, "Clip cut không hợp lệ."); return { assetId: asset(part.asset_id, "video"), start, end }; });
    requireValue(parts.reduce((sum, part) => sum + part.end - part.start, 0) <= duration + 1 / 30, "Các đoạn clip dài hơn cảnh; cần bàn giao lại điểm cắt, không tự tăng tốc hoặc cắt mất nội dung.");
    if (layout === "feature_clip") requireValue(parts.length, "Feature clip cần asset và điểm cắt đã bàn giao.");
    const imageId = p.image_asset_id ? asset(p.image_asset_id, "image") : undefined;
    const focus = p.focus ? { rect: rectangle(obj(p.focus).rect), at: num(obj(p.focus).at_s, 0, duration) } : undefined;
    if (layout === "highlight_zoom") requireValue(focus && (imageId || parts.length), "Highlight zoom cần asset và vùng focus.");
    return { id, layout, props, subtitle, duration, segments, refs: factRefs, parts, imageId, focus, compareIds, motion };
  });
  requireValue(scenes.length && scenes.length === mapping.length, "Số cảnh/mapping không khớp."); unique(scenes.map(s => s.id)); unique(allSegmentIds);
  return { title, productId, sourceUrl, source: "M2 #83 · payload giữ nguyên; presentation là mapping FE đang chờ review.", sourcePayload: structuredClone(script), knowledgeVersion, pkbSchemaVersion: String(script.pkb_schema_version), timing: presentation.timing as Project["timing"], scenes, assets, design: validateDesign(envelope.product_design, productId, sourceUrl) };
}

export function safeMedia(value: string | undefined): string | undefined {
  if (value === undefined) return;
  requireValue(/^data:(?:video\/(?:mp4|webm)|audio\/(?:wav|x-wav|mpeg|mp4|ogg|webm)|image\/(?:png|jpeg|webp));base64,[A-Za-z0-9+/=]+$/.test(value), "Media phải là file cục bộ được chọn, không nhận URL/path từ nội dung.");
  return value;
}
export function sceneAt(project: Project, time: number) {
  let offset = 0;
  for (let index = 0; index < project.scenes.length; index++) {
    const scene = project.scenes[index];
    if (time < offset + scene.duration || index === project.scenes.length - 1) return { index, scene, localTime: Math.max(0, Math.min(scene.duration, time - offset)) };
    offset += scene.duration;
  }
  throw new Error("Chưa có cảnh để preview.");
}
