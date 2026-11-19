import { readFileSync } from "node:fs";
const base = () => JSON.parse(readFileSync(new URL("./template-handoff.json", import.meta.url), "utf8"));

export function reusableProjects() {
  return [0, 1].map(variant => {
    const raw = base(), productId = variant ? "b2000000-0000-4000-8000-000000000002" : "b1000000-0000-4000-8000-000000000001";
    raw.product_name = variant ? "StoreBoard · fixture" : "TaskFlow · fixture";
    raw.source_url = variant ? "https://storeboard.example.com" : "https://taskflow.example.com";
    raw.script.product_id = productId; raw.script.audience = "Người kiểm tra template với dữ liệu giả";
    raw.script.concept = { title: "Project fixture nhiều cảnh", angle: "tutorial" };
    raw.script.hook.text = "Dữ liệu tổng hợp để kiểm thử engine dùng chung.";
    const texts = variant ? [["Mở danh mục mẫu", "Chọn thẻ mẫu"], ["Đổi vị trí thẻ", "Xem bảng mẫu"]] : [["Mở bảng làm việc", "Chọn mục mẫu"], ["Xếp các thẻ mẫu", "Xem bố cục"]];
    const durations = variant ? [4, 2.5] : [3, 3];
    const starts = variant ? [[.6, 2.3], [.25, 1.4]] : [[.5, 1.7], [.2, 1.6]];
    raw.script.scenes = texts.map((lines, i) => {
      const sceneId = `s0${i + 1}`;
      return { scene_id: sceneId, role: "demo", narration_segments: lines.map((text, j) => ({ segment_id: `${sceneId}-u0${j + 1}`, text })), subtitle_text: lines[0],
        visual_plan: { kind: "screen_recording", source_type: "existing_asset", asset_id: `clip:${i + 1}`, purpose: "Synthetic test footage, not real product evidence." },
        claims: lines.map((text, j) => ({ text, type: "other", segment_ids: [`${sceneId}-u0${j + 1}`], fact_refs: [{ source_id: "src_01", field_path: `features[${j}]` }] })) };
    });
    raw.assets = [1, 2].map(i => ({ asset_id: `clip:${i}`, product_id: productId, kind: "video", rights_basis: "Generated test pattern; fixture only." }));
    raw.assets.push({ asset_id: "voice:fixture", product_id: productId, kind: "audio", rights_basis: "Generated sine tone; not speech or real TTS." });
    raw.presentation = { product_id: productId, knowledge_version: 1, timing: "fixture", scenes: texts.map((lines, i) => {
      const sceneId = `s0${i + 1}`, duration = durations[i];
      return { scene_id: sceneId, layout: "feature_clip", title_claim_index: 0, duration_s: duration, note_claim_indices: [0, 1],
        segments: lines.map((text, j) => ({ segment_id: `${sceneId}-u0${j + 1}`, start_s: starts[i][j], end_s: starts[i][j] + 1, audio_asset_id: "voice:fixture" })),
        clip_parts: [{ asset_id: `clip:${i + 1}`, start_s: 0, end_s: duration / 2 }, { asset_id: `clip:${i + 1}`, start_s: 4, end_s: 4 + duration / 2 }],
        motion: { intro_end_s: Math.min(.3, starts[i][0]), mode: i === 1 && variant ? "centered" : "adaptive", beats: lines.map((text, j) => ({ claim_index: j, start_s: starts[i][j], end_s: starts[i][j] + 1, side: j === 0 ? "right" : "left" })) } };
    }) };
    raw.product_design = variant
      ? { product_id: productId, source_url: raw.source_url, background: "#fff8ed", foreground: "#342722", accent: "#9a3412", surface: "#fffefd", border: "#c3aa91", heading_font: "noto-serif", body_font: "be-vietnam-pro" }
      : { product_id: productId, source_url: raw.source_url, background: "#111827", foreground: "#f8fafc", accent: "#8bdc65", surface: "#182235", border: "#51627f", heading_font: "be-vietnam-pro", body_font: "be-vietnam-pro" };
    return raw;
  });
}
