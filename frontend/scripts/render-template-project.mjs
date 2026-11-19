// Render every supported scene in an M2 project using the shared scene template.
import { readFile, writeFile, mkdir, copyFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { fromM2 } from "../src/features/video-template/model.ts";

const root = fileURLToPath(new URL("../", import.meta.url)), args = {};
for (let i = 2; i < process.argv.length; i += 2) {
  assert.ok(["--input", "--assets", "--out", "--ratio", "--preset", "--workers", "--capture-format", "--decode", "--encoder"].includes(process.argv[i]) && process.argv[i + 1], "Use --input PROJECT_JSON --assets BINDINGS_JSON --out DIR --ratio both|16:9|9:16 --preset cinematic|animation|vintage [--workers 1..8 --capture-format jpeg|png --decode frames|video --encoder auto|cpu|nvenc]");
  args[process.argv[i].slice(2)] = process.argv[i + 1];
}
assert.ok(args.input && args.out, "An M2 project input and output directory are required");
const input = path.resolve(args.input), output = path.resolve(args.out), assets = path.resolve(args.assets || path.join(path.dirname(input), "asset-files.json"));
assert.ok(output !== path.dirname(input) && !output.startsWith(path.dirname(input) + path.sep), "Output must be outside the input bundle");
const inputBytes = await readFile(input), project = fromM2(JSON.parse(inputBytes.toString("utf8")));
const ratios = !args.ratio || args.ratio === "both" ? ["16:9", "9:16"] : [args.ratio], preset = args.preset || "cinematic";
assert.ok(ratios.every(r => ["16:9", "9:16"].includes(r)) && ["cinematic", "animation", "vintage"].includes(preset), "Unsupported ratio or preset");
const ffmpeg = process.env.FFMPEG_BIN || "ffmpeg";
function execute(binary, command, cwd = root) {
  const result = spawnSync(binary, command, { cwd, encoding: "utf8", windowsHide: true, maxBuffer: 16 * 1024 * 1024 });
  if (result.output?.[1]) process.stdout.write(result.output[1]);
  assert.ok(!result.error && result.status === 0, `${result.error?.message || binary + ' failed'}\n${result.stderr}`);
  return result;
}
await mkdir(output, { recursive: true });
await writeFile(path.join(output, "source-project.json"), inputBytes);
await writeFile(path.join(output, "normalized-project.json"), JSON.stringify(project, null, 2));
const sceneResults = [];
for (const scene of project.scenes) {
  const sceneOutput = path.join(output, "scenes", scene.id);
  const captureOptions = ["workers", "capture-format", "decode", "encoder"].flatMap(key => args[key] ? [`--${key}`, args[key]] : []);
  execute(process.execPath, [path.join(root, "scripts/render-template-scene.mjs"), "--input", input, "--assets", assets, "--scene", scene.id, "--out", sceneOutput, "--ratio", ratios.length === 2 ? "both" : ratios[0], "--preset", preset, ...captureOptions]);
  sceneResults.push(JSON.parse(await readFile(path.join(sceneOutput, "measurements.json"), "utf8")));
}
const duration = project.scenes.reduce((sum, scene) => sum + scene.duration, 0), results = [];
for (const ratio of ratios) {
  const ratioName = ratio.replace(":", "x"), ratioOutput = path.join(output, ratioName);
  await mkdir(ratioOutput, { recursive: true });
  // All scene outputs share codec, dimensions and frame rate. Copy their video
  // packets; only trim/concatenate audio to remove per-scene AAC padding.
  const list = project.scenes.map(scene => `file '../scenes/${scene.id}/${ratioName}/scene.mp4'\nduration ${Math.round(scene.duration * 30) / 30}`).join("\n") + "\n";
  await writeFile(path.join(ratioOutput, "scenes.ffconcat"), "ffconcat version 1.0\n" + list);
  const command = ["-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", "scenes.ffconcat"], filters = [];
  project.scenes.forEach((scene, i) => {
    command.push("-i", path.join(output, "scenes", scene.id, ratioName, "scene.mp4"));
    filters.push(`[${i + 1}:a]atrim=duration=${scene.duration},asetpts=PTS-STARTPTS[a${i}]`);
  });
  filters.push(`${project.scenes.map((s, i) => `[a${i}]`).join("")}concat=n=${project.scenes.length}:v=0:a=1[a]`);
  const video = path.join(ratioOutput, "project.mp4");
  command.push("-filter_complex", filters.join(";"), "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-t", String(duration), "-movflags", "+faststart", video);
  if (project.scenes.length === 1) await copyFile(path.join(output, "scenes", project.scenes[0].id, ratioName, "scene.mp4"), video);
  else execute(ffmpeg, command, ratioOutput);
  execute(ffmpeg, ["-v", "error", "-y", "-i", video, "-map", "0:v", "-f", "framemd5", "decoded-frames.md5"], ratioOutput);
  const frames = (await readFile(path.join(ratioOutput, "decoded-frames.md5"), "utf8")).split("\n").filter(s => s && !s.startsWith("#")).length;
  assert.ok(Math.abs(frames - duration * 30) <= 1, "Combined project lost or duplicated scene timing");
  const hashes = text => text.split("\n").filter(line => line && !line.startsWith("#")).map(line => line.split(",").at(-1).trim());
  const expectedHashes = (await Promise.all(project.scenes.map(scene => readFile(path.join(output, "scenes", scene.id, ratioName, "decoded-frames.md5"), "utf8")))).flatMap(hashes);
  assert.deepEqual(hashes(await readFile(path.join(ratioOutput, "decoded-frames.md5"), "utf8")), expectedHashes, "Stream-copy join changed, lost or reordered video frames");
  const probe = spawnSync(ffmpeg, ["-hide_banner", "-i", video], { encoding: "utf8", windowsHide: true }).stderr;
  const [width, height] = ratio === "16:9" ? [1920, 1080] : [1080, 1920];
  assert.ok(probe.includes(`${width}x${height}`) && /30 fps/.test(probe) && /Audio: aac/.test(probe), "Combined project metadata differs");
  const time = probe.match(/Duration: (\d+):(\d+):([\d.]+)/);
  assert.ok(time && Math.abs(Number(time[1]) * 3600 + Number(time[2]) * 60 + Number(time[3]) - duration) < .06, "Combined project duration differs from its timeline");
  results.push({ ratio, width, height, fps: 30, frames, duration, video, videoReencoded: false, decodedFramesMatchScenes: true });
}
const hash = value => createHash("sha256").update(value).digest("hex");
assert.equal(hash(await readFile(input)), hash(inputBytes), "Source M2 must remain unchanged");
await writeFile(path.join(output, "project-results.json"), JSON.stringify({ productId: project.productId, title: project.title, sceneIds: project.scenes.map(s => s.id), timing: project.timing, sourceSha256: hash(inputBytes), targetDuration: project.sourcePayload.target_duration_s, actualTimeline: duration, p1DurationSatisfied: duration >= 40 && duration <= 45, scenes: sceneResults, outputs: results }, null, 2));
console.log(`PASS: project ${project.productId}, ${project.scenes.length} scenes, ${duration}s; ${output}`);
