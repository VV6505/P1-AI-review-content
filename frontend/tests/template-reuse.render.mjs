import { mkdir, writeFile, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import { reusableProjects } from "./fixtures/reusable-projects.mjs";
import { checkReusedProjects } from "./template-reuse.check.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const output = path.resolve(process.env.REUSE_OUTPUT || path.join(root, "test-results/template-reuse"));
const ffmpeg = process.env.FFMPEG_BIN || "ffmpeg";
function run(binary, args) {
  const result = spawnSync(binary, args, { cwd: root, encoding: "utf8", windowsHide: true, maxBuffer: 16 * 1024 * 1024 });
  if (result.stdout) process.stdout.write(result.stdout);
  assert.ok(!result.error && result.status === 0, `${result.error?.message || 'Command failed'}\n${result.stderr}`);
}
const results = [];
for (const [index, raw] of reusableProjects().entries()) {
  const bundle = path.join(output, `input-${index + 1}`), rendered = path.join(output, `project-${index + 1}`);
  await mkdir(path.join(bundle, "media"), { recursive: true });
  run(ffmpeg, ["-v", "error", "-y", "-f", "lavfi", "-i", `testsrc2=s=1280x720:r=30:d=8`, "-an", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", path.join(bundle, "media", "test.mp4")]);
  run(ffmpeg, ["-v", "error", "-y", "-f", "lavfi", "-i", `sine=frequency=${index ? 660 : 440}:duration=1:sample_rate=48000`, "-c:a", "pcm_s16le", path.join(bundle, "media", "tone.wav")]);
  await writeFile(path.join(bundle, "project.json"), JSON.stringify(raw, null, 2));
  const bindings = Object.fromEntries(raw.assets.map(a => [a.asset_id, a.kind === "video" ? "media/test.mp4" : "media/tone.wav"]));
  await writeFile(path.join(bundle, "asset-files.json"), JSON.stringify(bindings, null, 2));
  run(process.execPath, ["scripts/render-template-project.mjs", "--input", path.join(bundle, "project.json"), "--assets", path.join(bundle, "asset-files.json"), "--out", rendered, "--ratio", "both", "--preset", "cinematic"]);
  const report = JSON.parse(await readFile(path.join(rendered, "project-results.json"), "utf8"));
  assert.equal(report.productId, raw.script.product_id); assert.equal(report.outputs.length, 2); assert.equal(report.sceneIds.length, 2);
  assert.equal(report.p1DurationSatisfied, false, "Short fixtures must never be reported as completed P1 videos");
  assert.equal(report.actualTimeline, index ? 6.5 : 6);
  results.push(report);
}
await writeFile(path.join(output, "reuse-results.json"), JSON.stringify({ fixtureOnly: true, syntheticVideoAndTone: true, results }, null, 2));
await checkReusedProjects(output);
console.log(`PASS: two M2 products, four independent scenes, two aspect ratios; ${output}`);
