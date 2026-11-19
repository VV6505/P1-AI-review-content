import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fromSceneHandoff, handoffMediaPath } from "../src/features/video-template/scene-handoff.ts";
import { buildRenderFrame } from "../src/features/video-template/frame.ts";

const fixture = () => JSON.parse(readFileSync(new URL("./fixtures/s03-scene-handoff.json", import.meta.url), "utf8"));
const size = { width: 1920, height: 1080 };
test("BE source pixels and source time map through crop and cuts without inventing PKB references", () => {
  const raw = fixture(), original = structuredClone(raw), project = fromSceneHandoff(raw, size), scene = project.scenes[0];
  assert.deepEqual(raw, original); assert.deepEqual(project.sourcePayload, original);
  assert.equal(project.knowledgeVersion, undefined); assert.deepEqual(scene.refs, []);
  assert.deepEqual(scene.handoffRefs, ["F4", "V1"]);
  assert.equal(scene.duration, 7.9);
  assert.ok(Math.abs(scene.focus.at - 4.76) < 1e-9);
  assert.deepEqual(scene.crop.rect, [440 / 1920, 0, 1480 / 1920, 1]);
  assert.deepEqual(scene.focus.rect, [800 / 1480, 600 / 1080, 660 / 1480, 460 / 1080]);
  assert.deepEqual(scene.segments.map(s => [s.start, s.end]), [[.1, 1.78], [1.9, 4.62], [4.74, 7.3]]);
  assert.equal(scene.motion.introEnd, 1.2);
  assert.deepEqual(scene.motion.beats.map(b => b.text), ['Chọn vị trí', 'Bấm Apply', 'Định dạng, số bắt đầu', 'Đã có số trang']);
  assert.equal(scene.motion.beats.at(-1).result, true);
  scene.motion.beats.forEach((beat, i, beats) => {
    assert.ok(beat.end > beat.start);
    assert.ok(Math.abs(beat.start - (i ? beats[i - 1].end : scene.motion.introEnd)) < 1e-9);
  });
  assert.equal(scene.motion.beats.at(-1).end, scene.duration);
});
test("handoff rejects timing drift, out-of-crop focus, missing evidence and unsafe asset paths", () => {
  for (const mutate of [
    raw => raw.scene.narration_segments[1].start_s = 2,
    raw => raw.scene.clip.focus.rect = [100, 0, 660, 460],
    raw => raw.scene.clip.focus.source_t = 4,
    raw => raw.scene.narration_segments[0].fact_refs = ["missing"],
    raw => raw.scene.narration_segments[0].voice = "../../secret.wav",
  ]) { const raw = fixture(); mutate(raw); assert.throws(() => fromSceneHandoff(raw, size), /Bàn giao cảnh/); }
  assert.throws(() => handoffMediaPath("https://example.com/video.mp4"), /Bàn giao cảnh/);
});
test("renderer export keeps media external, subtitles in renderer and text inert", () => {
  const raw = fixture(); raw.scene.props.title.text = '</script><script>window.pwned=1</script>';
  const project = fromSceneHandoff(raw, size), files = Object.fromEntries(project.assets.map(a => [a.id, a.id]));
  const html = buildRenderFrame(project, project.scenes[0], "16:9", "cinematic", files, "");
  const data = JSON.parse(JSON.parse(html.match(/const DATA=JSON.parse\((.*?)\);DATA/)[1]));
  assert.equal(data.captions, false); assert.ok(!html.includes("data:video/"));
  assert.ok(!html.includes('</script><script>window.pwned'));
  assert.throws(() => buildRenderFrame(project, project.scenes[0], "16:9", "cinematic", { ...files, "media/pdfcraft-pagenum.mp4": "file:///secret.mp4" }, ""), /tương đối/);
  for (const directory of ["../secret", "media/../../secret", "https://example.com/frames", "media/decoded-0/../secret"]) {
    assert.throws(() => buildRenderFrame(project, project.scenes[0], "16:9", "cinematic", files, "", { clip: { directory, times: [0], width: 1920, height: 1080 } }), /Invalid decoded frame sequence/);
  }
});
