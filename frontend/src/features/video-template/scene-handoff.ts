import type { Project } from "./model.ts";
import { validateMotion } from "./motion.ts";

type ObjectValue = Record<string, unknown>;
function check(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(`Bàn giao cảnh: ${message}`);
}
function object(value: unknown): ObjectValue {
  check(value && typeof value === "object" && !Array.isArray(value), "thiếu object.");
  return value as ObjectValue;
}
function text(value: unknown, max = 500): string {
  check(typeof value === "string" && value.trim() && value.length <= max, "chữ rỗng hoặc quá dài.");
  return value;
}
function number(value: unknown, min = 0, max = 3600): number {
  check(typeof value === "number" && Number.isFinite(value) && value >= min && value <= max, "số/timing ngoài giới hạn.");
  return value;
}
function array(value: unknown, max = 100): unknown[] {
  check(Array.isArray(value) && value.length > 0 && value.length <= max, "danh sách rỗng hoặc quá dài.");
  return value;
}
export function handoffMediaPath(value: unknown): string {
  const path = text(value, 100);
  check(/^media\/[A-Za-z0-9_-]+\.(mp4|wav)$/.test(path), "chỉ nhận file mp4/wav trong thư mục media của gói.");
  return path;
}

// This adapter reads a standalone scene from the BE spike. It does not manufacture
// an M2 script, a Product UUID, PKB version or PKB source references.
export function fromSceneHandoff(raw: unknown, sourceSize: { width: number; height: number }): Project {
  const input = object(raw), scene = object(input.scene), clip = object(scene.clip), props = object(scene.props);
  check(typeof input.schema_version === "string" && input.schema_version.startsWith("scene-handoff.v0 ("), "schema chưa hỗ trợ.");
  check(input.fps === 30 && scene.layout === "feature_clip", "lần thử này hỗ trợ feature_clip ở 30 fps.");
  const sceneId = text(scene.scene_id, 20);
  check(/^s\d{2}$/.test(sceneId), "scene_id không hợp lệ.");
  const duration = number(input.scene_duration_s, .1, 120), facts = object(input.facts);
  const sourceRefs = new Set<string>();
  function refs(value: unknown): string[] {
    return array(value).map(value => {
      const id = text(value, 50);
      check(Object.hasOwn(facts, id), `thiếu bằng chứng ${id}.`);
      text(facts[id], 2000); sourceRefs.add(id); return id;
    });
  }
  const assets = new Map<string, "video" | "audio">();
  function asset(value: unknown, kind: "video" | "audio") {
    const path = handoffMediaPath(value);
    check(path.endsWith(kind === "video" ? ".mp4" : ".wav"), "media sai loại.");
    assets.set(path, kind); return path;
  }
  let previousEnd = number(input.lead_s, 0, duration);
  const gap = number(input.gap_s, 0, duration), tail = number(input.tail_s, 0, duration);
  const segments = array(scene.narration_segments).map((value, index) => {
    const segment = object(value), id = text(segment.segment_id, 30);
    check(new RegExp(`^${sceneId}-u\\d{2}$`).test(id), "segment không thuộc cảnh.");
    const start = number(segment.start_s, 0, duration), end = number(segment.end_s, start, duration);
    const expectedStart = previousEnd + (index ? gap : 0);
    check(Math.abs(start - expectedStart) < .001 && end > start, "timing không khớp lead/gap.");
    check(Math.abs(end - start - number(segment.duration_s, .01, duration)) < .001, "thời lượng câu không khớp timing.");
    previousEnd = end; refs(segment.fact_refs);
    text(segment.normalized);
    return { id, text: text(segment.text), start, end, audioId: asset(segment.voice, "audio") };
  });
  check(new Set(segments.map(s => s.id)).size === segments.length, "segment_id bị trùng.");
  check(Math.abs(previousEnd + tail - duration) < .001, "tổng audio/tail không khớp thời lượng cảnh.");
  const parts = array(clip.parts, 24).map(value => {
    const part = object(value), start = number(part.start_s), end = number(part.end_s, start);
    check(end > start, "điểm cắt clip rỗng.");
    return { assetId: asset(part.src, "video"), start, end };
  });
  check(new Set(parts.map(p => p.assetId)).size === 1, "lần thử này cần một clip nguồn.");
  check(parts.reduce((sum, p) => sum + p.end - p.start, 0) <= duration, "clip dài hơn cảnh; không tự tăng tốc.");
  refs(clip.clip_refs);
  const width = number(sourceSize.width, 1, 16384), height = number(sourceSize.height, 1, 16384);
  const crop = array(clip.crop, 4).map(value => number(value, 0, 16384));
  check(crop.length === 4 && crop[2] > 0 && crop[3] > 0 && crop[0] + crop[2] <= width && crop[1] + crop[3] <= height, "crop nằm ngoài clip gốc.");
  const focus = object(clip.focus), partIndex = number(focus.part, 0, parts.length - 1);
  check(Number.isInteger(partIndex), "focus.part phải là chỉ số 0-based.");
  const part = parts[partIndex], sourceTime = number(focus.source_t, part.start, part.end);
  const focusPixels = array(focus.rect, 4).map(value => number(value, 0, 16384));
  check(focusPixels.length === 4 && focusPixels[2] > 0 && focusPixels[3] > 0, "focus thiếu kích thước.");
  const rect = [(focusPixels[0] - crop[0]) / crop[2], (focusPixels[1] - crop[1]) / crop[3], focusPixels[2] / crop[2], focusPixels[3] / crop[3]];
  check(rect.every(v => v >= 0 && v <= 1) && rect[0] + rect[2] <= 1 && rect[1] + rect[3] <= 1, "focus nằm ngoài crop.");
  const at = parts.slice(0, partIndex).reduce((sum, p) => sum + p.end - p.start, 0) + sourceTime - part.start;
  const title = object(props.title); refs(title.fact_refs);
  const eyebrow = object(props.eyebrow), callout = object(props.callout);
  refs(eyebrow.fact_refs); refs(callout.fact_refs);
  const steps = array(props.steps, 4).map(value => { const step = object(value); refs(step.fact_refs); return { text: text(step.text, 160) }; });
  // Presentation timing follows the supplied cuts; it does not change narration.
  const introEnd = Math.min(1.2, duration * .18);
  let cutTime = 0;
  check(steps.length === parts.length, "cần mapping từng bước theo đoạn clip đã bàn giao.");
  const beats: { text: string; start: number; end: number; result?: boolean }[] = steps.map((step, i) => {
    const start = i === 0 ? introEnd : cutTime;
    cutTime += (parts[i]?.end ?? 0) - (parts[i]?.start ?? 0);
    return { text: step.text, start, end: Math.min(cutTime, duration) };
  });
  if (cutTime < duration) beats.push({ text: text(callout.text, 160), start: cutTime, end: duration, result: true });
  const product = text(input.product, 120), productId = `handoff:${product}`;
  const sourceUrl = new URL(`https://${text(props.url, 200)}`);
  check(!sourceUrl.username && !sourceUrl.password, "link nguồn không hợp lệ.");
  return {
    title: product, productId, sourceUrl: sourceUrl.href,
    source: `Bộ bàn giao một cảnh; ${text(input.written_by, 1000)}`,
    sourcePayload: structuredClone(raw), timing: "measured",
    assets: [...assets].map(([id, kind]) => ({ id, kind, productId, rights: kind === "video" ? "Theo README bàn giao: nhóm tự quay PDFCraft với PDF mẫu Acme Demo." : "Theo README bàn giao: giọng VieNeu Mai Anh, timing đo trên WAV." })),
    scenes: [{ id: sceneId, layout: "feature_clip", duration, subtitle: "", segments, refs: [], handoffRefs: [...sourceRefs],
      props: { title: { text: text(title.text, 180) }, eyebrow: { text: text(eyebrow.text, 120) }, callout: { text: text(callout.text, 160) }, steps }, parts,
      crop: { rect: [crop[0] / width, crop[1] / height, crop[2] / width, crop[3] / height], sourceSize: [width, height] },
      motion: validateMotion({ introEnd, beats }, duration),
      focus: { rect, at } }],
  };
}
