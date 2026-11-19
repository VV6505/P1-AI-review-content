import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fromM2, safeMedia, sceneAt } from "../src/features/video-template/model.ts";
import { buildFrame } from "../src/features/video-template/frame.ts";

const fixture = () => JSON.parse(readFileSync(new URL("./fixtures/template-handoff.json", import.meta.url), "utf8"));

test("M2 accepts an optional duration estimate without replacing the authored timeline or source payload", () => {
  const baseline = fromM2(fixture());
  assert.equal(Object.hasOwn(baseline.sourcePayload, "estimated_duration_s"), false);
  for (const estimate of [.1, 19.5, 42, 600]) {
    const raw = fixture();
    raw.script.estimated_duration_s = estimate;
    const original = structuredClone(raw), project = fromM2(raw);
    assert.deepEqual(raw, original);
    assert.deepEqual(project.sourcePayload, original.script);
    assert.notEqual(project.sourcePayload, raw.script);
    assert.deepEqual(project.scenes, baseline.scenes);
    assert.equal(project.timing, "fixture");
    assert.equal(project.sourcePayload.target_duration_s, baseline.sourcePayload.target_duration_s);
    assert.equal(project.scenes.reduce((sum, scene) => sum + scene.duration, 0), 21);
  }
});

test("M2 rejects invalid estimates while keeping the target duration and additional-property rules strict", () => {
  for (const value of [0, -1, 600.1, null, "42", true, {}, []]) {
    const raw = fixture();
    raw.script.estimated_duration_s = value;
    assert.throws(() => fromM2(raw), /M2 không khớp schema #83/, `estimate ${JSON.stringify(value)}`);
  }
  for (const mutate of [
    raw => raw.script.target_duration_s = 39,
    raw => raw.script.target_duration_s = 46,
    raw => raw.script.unrecognized_field = true,
    raw => raw.script.scenes[0].estimated_duration_s = 42,
    raw => raw.script.scenes[0].visual_plan.unrecognized_field = true,
  ]) {
    const raw = fixture();
    raw.script.estimated_duration_s = 42;
    mutate(raw);
    assert.throws(() => fromM2(raw), /M2 không khớp schema #83/);
  }
});

test("M2 accepts the AI image visual kind from BE #83 and still requires an allowed existing asset", () => {
  const raw = fixture();
  raw.script.scenes[3].visual_plan.kind = "ai_generated_image";
  const project = fromM2(raw);
  assert.equal(project.scenes[3].imageId, "fixture:focus");
  assert.deepEqual(project.sourcePayload, raw.script);
  raw.script.scenes[3].visual_plan.asset_id = "image:not-allowed";
  assert.throws(() => fromM2(raw), /allowlist/);
  delete raw.script.scenes[3].visual_plan.asset_id;
  assert.throws(() => fromM2(raw), /M2 không khớp schema #83/);
});

test("M2 adapter preserves payload, identity and fact references without inventing feature notes", () => {
  const raw = fixture();
  const project = fromM2(raw);
  assert.deepEqual(project.sourcePayload, raw.script);
  assert.notEqual(project.sourcePayload, raw.script);
  assert.equal(project.knowledgeVersion, raw.script.knowledge_version);
  assert.deepEqual(project.scenes[0].props.steps, []);
  raw.presentation.scenes[0].note_claim_indices = [0];
  const updated = fromM2(raw);
  assert.deepEqual(updated.scenes[0].props.steps, [{ text: raw.script.scenes[0].claims[0].text, at: 0 }]);
  assert.deepEqual(updated.scenes[0].refs, raw.script.scenes[0].claims[0].fact_refs);
});

test("steps use authored order and the referenced speech timing, rejecting ambiguous/reversed mappings", () => {
  const raw = fixture();
  assert.deepEqual(fromM2(raw).scenes[1].props.items.map(item => item.at), [0, 3, 6]);
  raw.presentation.scenes[1].step_claim_indices = [1, 0];
  assert.throws(() => fromM2(raw), /Thứ tự bước/);
  raw.presentation.scenes[1].step_claim_indices = [0, 0];
  assert.throws(() => fromM2(raw), /trùng/);
});

test("source cuts cannot be silently compressed to fit a shorter scene", () => {
  const raw = fixture();
  raw.presentation.scenes[0].clip_parts[0].end_s = 5;
  assert.throws(() => fromM2(raw), /dài hơn cảnh/);
  raw.presentation.scenes[0].duration_s = 6;
  assert.equal(fromM2(raw).scenes[0].duration, 6);
});

test("reject incorrect products, missing measured audio, malformed focus and absent claim indices", () => {
  for (const [mutate, error] of [
    [raw => raw.assets[0].product_id = "another", /sản phẩm khác/],
    [raw => raw.presentation.timing = "measured", /audio asset/],
    [raw => raw.presentation.scenes[3].focus.rect = [.9, 0, .3, .3], /ngoài ảnh/],
    [raw => raw.presentation.scenes[0].note_claim_indices = [10], /không hợp lệ/],
    [raw => raw.presentation.scenes[0].segments[0].end_s = 9, /không hợp lệ/],
    [raw => raw.script.scenes[0].claims[0].fact_refs = [], /fact ref/],
  ]) { const raw = fixture(); mutate(raw); assert.throws(() => fromM2(raw), error); }
});

test("scene boundary belongs to the next scene and a shorter review timeline is not padded to P1", () => {
  const project = fromM2(fixture());
  assert.equal(sceneAt(project, 2.999).scene.id, "s01");
  assert.equal(sceneAt(project, 3).scene.id, "s02");
  assert.equal(project.scenes.reduce((sum, scene) => sum + scene.duration, 0), 21);
});

test("export escapes script-breaking text and refuses executable media and unsupported ratios", () => {
  const raw = fixture(); raw.script.scenes[0].claims[0].text = '</script><script>window.pwned=1</script>';
  const project = fromM2(raw);
  const html = buildFrame(project, project.scenes[0], "16:9", "cinematic", {}, "");
  assert.equal(html.includes('</script><script>window.pwned'), false);
  assert.throws(() => safeMedia("https://example.com/a.mp4"), /cục bộ/);
  assert.throws(() => safeMedia("data:image/svg+xml;base64,PHN2Zz4="), /cục bộ/);
  assert.throws(() => buildFrame(project, project.scenes[0], "1:1", "cinematic", {}, ""), /Tỷ lệ/);
});
