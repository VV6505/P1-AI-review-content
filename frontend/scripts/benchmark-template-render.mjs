// Reproducible local benchmark using an existing normalized template project.
// --seconds repeats the supplied clip; it is a benchmark, not new narration.
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { readFile, writeFile, mkdir, copyFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { performance } from "node:perf_hooks";
import { chromium } from "playwright";
import { buildRenderFrame, loadResources } from "../src/features/video-template/frame.ts";
import { captureFrames, decodeSources, defaultWorkers, ffmpegJob } from "./lib/template-capture.mjs";
import { comparePng, checkCaptureMode, acceptableFrame } from "./lib/frame-comparison.mjs";
import { selectEncoder } from "./lib/template-encoder.mjs";

const options = {};
for (let i = 2; i < process.argv.length; i += 2) {
  assert.ok(["--project", "--video", "--out", "--seconds", "--workers", "--capture-format"].includes(process.argv[i]) && process.argv[i + 1], "Use --project normalized-project.json --video source.mp4 --out directory [--seconds 60] [--workers 4] [--capture-format jpeg|png]");
  options[process.argv[i].slice(2)] = process.argv[i + 1];
}
assert.ok(options.project && options.video && options.out);
const root = fileURLToPath(new URL("../", import.meta.url)), ffmpeg = process.env.FFMPEG_BIN || "ffmpeg";
const out = path.resolve(options.out), source = path.resolve(options.video);
assert.notEqual(out, path.dirname(path.resolve(options.project)), "Benchmark output must be separate from the input project");
assert.notEqual(path.join(out, "media/source.mp4").toLowerCase(), source.toLowerCase(), "Benchmark output must not overwrite the input video");
const project = JSON.parse(await readFile(options.project, "utf8")), scene = project.scenes[0];
assert.equal(project.scenes.length, 1);
assert.equal(project.assets.length, 1);
assert.equal(project.assets[0].kind, "video");
assert.equal(scene.segments.length, 0, "Benchmark preserves source audio; narration segments need render:scene");
const assetId = project.assets[0].id, originalDuration = scene.duration;
if (options.seconds) {
  scene.duration = Number(options.seconds);
  assert.ok(scene.duration > 0 && scene.duration <= 120);
  scene.parts = [];
  for (let remaining = scene.duration; remaining > 1e-6; remaining -= originalDuration) scene.parts.push({ assetId, start: 0, end: Math.min(remaining, originalDuration) });
  const beats = scene.motion?.beats || [];
  if (scene.motion) scene.motion.beats = Array.from({ length: Math.ceil(scene.duration / originalDuration) }, (_, i) => beats.map(beat => ({ ...beat, start: beat.start + i * originalDuration, end: Math.min(beat.end + i * originalDuration, scene.duration) }))).flat().filter(beat => beat.start < beat.end);
}
const fps = 30, frameCount = Math.round(scene.duration * fps), width = 1920, height = 1080;
const workers = Number(options.workers || defaultWorkers), format = options["capture-format"] || "jpeg";
function run(args) {
  const result = spawnSync(ffmpeg, args, { cwd: out, encoding: "utf8", windowsHide: true, maxBuffer: 16 * 1024 * 1024 });
  assert.ok(!result.error && result.status === 0, result.error?.message || result.stderr);
  return result;
}
await mkdir(path.join(out, "media"), { recursive: true });
const mediaFile = path.join(out, "media/source.mp4");
if (options.seconds) {
  // Build an actual 60s input, rather than reusing a short decoded frame cache.
  // Input creation is upstream work and excluded from the template benchmark.
  run(["-v", "error", "-y", "-stream_loop", "-1", "-i", source, "-t", String(scene.duration), "-r", "30", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac", mediaFile]);
  scene.parts = [{ assetId, start: 0, end: scene.duration }];
} else await copyFile(source, mediaFile);
const started = performance.now();
const encoder = selectEncoder(ffmpeg);
const info = spawnSync(ffmpeg, ["-hide_banner", "-i", mediaFile], { encoding: "utf8", windowsHide: true }).stderr;
const match = info.match(/Video:.*?, (\d+)x(\d+)[ ,[]/);
assert.ok(match);
const meta = { duration: scene.duration, width: Number(match[1]), height: Number(match[2]), info };
const prepared = await decodeSources({ project, resolved: new Map([[assetId, { file: mediaFile, meta }]]), directory: out, ffmpeg });
assert.ok(prepared.sequences[assetId], "Benchmark source must support frame decoding");
const css = await loadResources(async resource => new Response(await readFile(path.join(root, "public", String(resource)))));
const files = { [assetId]: "media/source.mp4" };
await writeFile(path.join(out, "project.json"), JSON.stringify(project, null, 2));
await writeFile(path.join(out, "scene.html"), buildRenderFrame(project, scene, "16:9", "cinematic", files, css, prepared.sequences));
await writeFile(path.join(out, "reference.html"), buildRenderFrame(project, scene, "16:9", "cinematic", files, css));
const sampleFrames = [...new Set([0, 10, 30, 60, 143, 150, 180, 251, 270, 300, 362, 450, 562, 563, 564, 1125, 1126, frameCount - 1].filter(frame => frame < frameCount))];
const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : { channel: "chrome" }) });
let capture;
let modeCheck;
try {
  modeCheck = await checkCaptureMode({ browser, html: path.join(out, "scene.html"), reference: path.join(out, "reference.html"), width, height, frames: [30, Math.floor(frameCount / 3), Math.floor(frameCount * 2 / 3)].filter(frame => frame < frameCount), ffmpeg });
  if (!modeCheck.compatible) await copyFile(path.join(out, "reference.html"), path.join(out, "scene.html"));
  capture = await captureFrames({ browser, html: path.join(out, "scene.html"), directory: path.join(out, "frames"), width, height, fps, frameCount, workers, format, sampleFrames, onProgress: (done, total) => console.log(`Captured ${done}/${total}`) });
} finally { await browser.close(); }
const captureDone = performance.now(), output = path.join(out, "pdfcraft-template-optimized.mp4");
const audio = ["-i", mediaFile];
const log = await ffmpegJob(ffmpeg, ["-hide_banner", "-nostdin", "-y", "-framerate", "30", "-i", `frames/%05d.${format === "jpeg" ? "jpg" : "png"}`, ...audio, "-map", "0:v:0", "-map", "1:a:0", ...encoder.args, "-pix_fmt", "yuv420p", "-c:a", "copy", "-t", String(scene.duration), "-movflags", "+faststart", output], out);
const finished = performance.now();
await writeFile(path.join(out, "ffmpeg.log"), log);
const report = { output, duration: scene.duration, frameCount, width, height, workers, format, encoder: encoder.name, modeCheck, repeatedBenchmarkSource: !!options.seconds, prepareSeconds: prepared.seconds, captureSeconds: capture.seconds, encodeSeconds: (finished - captureDone) / 1000, totalExportSeconds: (finished - started) / 1000, comparisons: [], verified: false };
await writeFile(path.join(out, "benchmark.json"), JSON.stringify(report, null, 2));
console.log(JSON.stringify(report));
// Verification is separately timed so the report distinguishes export from QA.
const referenceBrowser = await chromium.launch({ headless: true, channel: "chrome" });
try {
  const page = await referenceBrowser.newPage({ viewport: { width, height } });
  await page.goto(pathToFileURL(path.join(out, "reference.html")).href);
  for (const frame of [...sampleFrames].reverse()) {
    const state = await page.evaluate(t => window.CreatorTemplate.renderAt(t), frame / fps);
    assert.ok(state.mediaReady && state.fontsReady); assert.deepEqual(state.textOverflow, []);
    const png = await page.screenshot();
    await writeFile(path.join(out, `reference-${frame}.png`), png);
    await writeFile(path.join(out, `optimized-${frame}.png`), capture.samples.get(frame));
    const comparison = comparePng(ffmpeg, capture.samples.get(frame), png);
    report.comparisons.push({ frame, ...comparison });
    console.log(`Compare ${frame}: ${JSON.stringify(comparison)}`);
  }
} finally { await referenceBrowser.close(); }
run(["-v", "error", "-y", "-i", output, "-map", "0:v:0", "-f", "framemd5", "decoded-frames.md5"]);
report.decodedFrames = (await readFile(path.join(out, "decoded-frames.md5"), "utf8")).split("\n").filter(line => line && !line.startsWith("#")).length;
assert.equal(report.decodedFrames, frameCount);
report.encodedComparisons = [];
const encodedSamples = [60, 180, 300].filter(frame => frame < frameCount);
await mkdir(path.join(out, "encoded-checks"), { recursive: true });
if (encodedSamples.length) {
  run(["-v", "error", "-y", "-i", output, "-vf", `select='${encodedSamples.map(frame => `eq(n,${frame})`).join("+")}'`, "-fps_mode", "passthrough", "encoded-checks/%d.png"]);
  for (const [index, frame] of encodedSamples.entries()) {
    const comparison = comparePng(ffmpeg, await readFile(path.join(out, `encoded-checks/${index + 1}.png`)), await readFile(path.join(out, `reference-${frame}.png`)));
    report.encodedComparisons.push({ frame, ...comparison });
    assert.ok(comparison.meanAbsoluteError <= 3 && comparison.ssim >= .94, `Encoded frame ${frame}: ${JSON.stringify(comparison)}`);
  }
}
{
  report.sourceAudioHash = run(["-v", "error", "-i", mediaFile, "-map", "0:a:0", "-c:a", "copy", "-f", "hash", "-hash", "sha256", "-"]).stdout.trim();
  report.outputAudioHash = run(["-v", "error", "-i", output, "-map", "0:a:0", "-c:a", "copy", "-f", "hash", "-hash", "sha256", "-"]).stdout.trim();
  assert.equal(report.outputAudioHash, report.sourceAudioHash);
}
report.verified = true;
assert.ok(report.comparisons.every(acceptableFrame), "Decoded-image output differs from preview; inspect comparison frames");
report.verificationSeconds = (performance.now() - finished) / 1000;
report.totalWallSeconds = (performance.now() - started) / 1000;
await writeFile(path.join(out, "benchmark.json"), JSON.stringify(report, null, 2));
console.log(`PASS: export ${report.totalExportSeconds.toFixed(2)}s; verification ${report.verificationSeconds.toFixed(2)}s; ${output}`);
