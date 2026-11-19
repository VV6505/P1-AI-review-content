import test from "node:test";
import assert from "node:assert/strict";
import { fromM2 } from "../src/features/video-template/model.ts";
import { reusableProjects } from "./fixtures/reusable-projects.mjs";

test("different products and multi-scene timelines use the same M2 adapter without changing source payload", () => {
  const projects = reusableProjects();
  for (const raw of projects) {
    const original = structuredClone(raw), project = fromM2(raw);
    assert.deepEqual(raw, original); assert.deepEqual(project.sourcePayload, original.script);
    assert.equal(project.scenes.length, 2);
    for (let i = 0; i < 2; i++) {
      assert.deepEqual(project.scenes[i].motion.beats.map(b => b.start), raw.presentation.scenes[i].segments.map(s => s.start_s));
      assert.deepEqual(project.scenes[i].motion.beats.map(b => b.text), raw.script.scenes[i].claims.map(c => c.text));
    }
    assert.equal(project.design.heading_font, raw.product_design.heading_font);
  }
  assert.notEqual(fromM2(projects[0]).scenes[0].duration, fromM2(projects[1]).scenes[0].duration);
});
test("default M2 motion follows referenced narration instead of dividing the scene into equal slots", () => {
  const raw = reusableProjects()[0]; delete raw.presentation.scenes[0].motion;
  const scene = fromM2(raw).scenes[0];
  assert.deepEqual(scene.motion.beats.map(b => [b.start, b.end]), [[.5, 1.5], [1.7, 2.7]]);
});
test("presentation cannot inject claims, overlapping beats, unlicensed fonts or unreadable surfaces", () => {
  for (const mutate of [
    r => r.presentation.scenes[0].motion.beats[0].claim_index = 999,
    r => r.presentation.scenes[0].motion.beats[1].start_s = 1,
    r => r.presentation.scenes[0].motion.beats[0].end_s = 100,
    r => r.presentation.scenes[0].motion.mode = 'execute-js',
    r => r.product_design.heading_font = 'https://outside.example/font.ttf',
    r => r.product_design.surface = '#f8fafc',
  ]) { const raw = reusableProjects()[0]; mutate(raw); assert.throws(() => fromM2(raw)); }
});
