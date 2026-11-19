// Reusable scene renderer: M2 project + asset bindings, or the legacy BE handoff.
import { readFile, writeFile, mkdir, copyFile, realpath, stat } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { performance } from "node:perf_hooks";
import assert from "node:assert/strict";
import { chromium } from "playwright";
import { fromSceneHandoff } from "../src/features/video-template/scene-handoff.ts";
import { fromM2 } from "../src/features/video-template/model.ts";
import { buildFrame, buildRenderFrame, loadResources } from "../src/features/video-template/frame.ts";
import { captionAssColor } from "./lib/subtitle-color.mjs";
import { captureFrames, decodeSources, defaultWorkers } from "./lib/template-capture.mjs";
import { comparePng, checkCaptureMode, acceptableFrame } from "./lib/frame-comparison.mjs";
import { selectEncoder } from "./lib/template-encoder.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const options = {};
for (let i = 2; i < process.argv.length; i += 2) {
  assert.ok(["--input", "--out", "--ratio", "--preset", "--preview-dir", "--assets", "--scene", "--workers", "--capture-format", "--decode", "--encoder"].includes(process.argv[i]) && process.argv[i + 1], "Options: --input JSON --assets BINDINGS_JSON --scene ID --out DIR --ratio both|16:9|9:16 --preset cinematic|animation|vintage --preview-dir LOCAL_PUBLIC_DIR --workers 1..8 --capture-format jpeg|png --decode frames|video --encoder auto|cpu|nvenc");
  options[process.argv[i].slice(2)] = process.argv[i + 1];
}
const input = path.resolve(options.input || path.join(root, "public/2026-10-26_s03-feature-clip/scene-s03.json"));
const inputDir = path.dirname(input), output = path.resolve(options.out || path.join(root, "test-results/s03-handoff"));
assert.ok(output !== inputDir && !output.startsWith(inputDir + path.sep), "Output must be outside the original handoff directory");
const ratios = !options.ratio || options.ratio === "both" ? ["16:9", "9:16"] : [options.ratio];
assert.ok(ratios.every(r => ["16:9", "9:16"].includes(r)), "Unsupported ratio");
const preset = options.preset || "cinematic", ffmpeg = process.env.FFMPEG_BIN || "ffmpeg";
const workers = Number(options.workers || defaultWorkers), captureFormat = options["capture-format"] || "jpeg", decode = options.decode || "frames";
assert.ok(Number.isInteger(workers) && workers >= 1 && workers <= 8 && ["jpeg", "png"].includes(captureFormat) && ["frames", "video"].includes(decode), "Invalid capture options");
assert.ok(["cinematic", "animation", "vintage"].includes(preset), "Unsupported preset");
const previewDir = options["preview-dir"] ? path.resolve(options["preview-dir"]) : null;
if (previewDir) {
  assert.equal(ratios.length, 2, "Preview publishing requires both ratios");
  assert.ok(previewDir.startsWith(path.join(root, "public/video-template") + path.sep), "Preview output must stay under this FE's public/video-template directory");
}
function run(args, cwd) {
  const result = spawnSync(ffmpeg, args, { cwd, encoding: "utf8", maxBuffer: 16 * 1024 * 1024, windowsHide: true });
  if (result.error || result.status !== 0) throw new Error(`${result.error?.message || "FFmpeg failed"}\n${result.stderr}`);
  return result;
}
function probe(file, image = false) {
  const result = spawnSync(ffmpeg, ["-hide_banner", "-i", file], { encoding: "utf8", windowsHide: true });
  if (result.error) throw result.error;
  const info = result.stderr, duration = info.match(/Duration: (\d+):(\d+):([\d.]+)/);
  assert.ok(duration || image, `Cannot read media duration: ${file}\n${info}`);
  const size = info.match(/Video:.*?, (\d+)x(\d+)[ ,[]/);
  return { duration: duration ? Number(duration[1]) * 3600 + Number(duration[2]) * 60 + Number(duration[3]) : 0, width: size ? Number(size[1]) : 0, height: size ? Number(size[2]) : 0, info };
}
const sha = value => createHash("sha256").update(value).digest("hex");
const inputBytes = await readFile(input), raw = JSON.parse(inputBytes.toString("utf8"));
const m2Input = !!raw.script;
let project;
if (m2Input) {
  const source = fromM2(raw), scene = source.scenes.find(s => s.id === options.scene) || (!options.scene && source.scenes.length === 1 ? source.scenes[0] : null);
  assert.ok(scene, "M2: choose a valid --scene ID, or use render:project to render every scene");
  const used = new Set([...scene.parts.map(p => p.assetId), ...scene.segments.map(s => s.audioId).filter(Boolean), scene.imageId, ...(scene.compareIds || [])].filter(Boolean));
  project = { ...source, scenes: [scene], assets: source.assets.filter(a => used.has(a.id)) };
} else {
  const preliminary = fromSceneHandoff(raw, { width: 1920, height: 1080 });
  const clipInfo = probe(path.join(inputDir, preliminary.assets.find(a => a.kind === "video").id));
  project = fromSceneHandoff(raw, clipInfo);
}
const scene = project.scenes[0], videoName = m2Input ? "scene.mp4" : "s03-feature-clip.mp4";
const suppliedBindings = m2Input ? JSON.parse(await readFile(path.resolve(options.assets || path.join(inputDir, "asset-files.json")), "utf8")) : Object.fromEntries(project.assets.map(a => [a.id, a.id]));
const inputRoot = await realpath(inputDir), resolved = new Map();
let totalBytes = 0;
const mediaTypes = { ".mp4": "video/mp4", ".webm": "video/webm", ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp" };
for (const [index, asset] of project.assets.entries()) {
  const binding = suppliedBindings[asset.id];
  assert.ok(typeof binding === "string" && binding.startsWith("media/") && !binding.includes("\\") && !binding.split("/").includes(".."), `Asset must resolve inside the bundle's media directory: ${asset.id}`);
  const file = await realpath(path.resolve(inputDir, binding));
  assert.ok(file.startsWith(inputRoot + path.sep), `Asset escapes the bundle: ${asset.id}`);
  const size = (await stat(file)).size, extension = path.extname(file).toLowerCase(), mime = mediaTypes[extension];
  totalBytes += size;
  assert.ok(size > 0 && size <= 25 * 1024 * 1024 && totalBytes <= 50 * 1024 * 1024, "Asset package exceeds size limits");
  assert.ok(mime && mime.startsWith(asset.kind + "/"), `Asset has the wrong file type: ${asset.id}`);
  const meta = probe(file, asset.kind === "image");
  if (asset.kind === "video") assert.ok(meta.width && meta.height && scene.parts.filter(p => p.assetId === asset.id).every(p => p.end <= meta.duration + .01), "Clip cuts exceed actual media duration");
  resolved.set(asset.id, { file, mime, meta, target: m2Input ? `media/asset-${index}${extension === ".jpeg" ? ".jpg" : extension}` : asset.id });
}
await mkdir(output, { recursive: true });
await writeFile(path.join(output, "source-scene.json"), inputBytes);
await writeFile(path.join(output, "mapped-scene.json"), JSON.stringify(project, null, 2));
const css = await loadResources(async resource => new Response(await readFile(path.join(root, "public", String(resource)))));
const mediaBytes = Object.create(null), files = Object.create(null), embedded = Object.create(null), mediaInfo = [];
for (const asset of project.assets) {
  const { file, mime, meta, target } = resolved.get(asset.id), bytes = await readFile(file);
  if (asset.kind === "audio") {
    for (const segment of scene.segments.filter(s => s.audioId === asset.id)) assert.ok(Math.abs(meta.duration - (segment.end - segment.start)) <= .02, `Audio timing differs: ${asset.id}`);
  }
  mediaBytes[asset.id] = bytes; files[asset.id] = target;
  embedded[asset.id] = `data:${mime};base64,${bytes.toString("base64")}`;
  mediaInfo.push({ id: asset.id, sha256: sha(bytes), duration: meta.duration, width: meta.width, height: meta.height });
}
function assTime(value) {
  const cs = Math.round(value * 100);
  return `${Math.floor(cs / 360000)}:${String(Math.floor(cs / 6000) % 60).padStart(2, "0")}:${String(Math.floor(cs / 100) % 60).padStart(2, "0")}.${String(cs % 100).padStart(2, "0")}`;
}
function subtitles(width, height, ink) {
  const portrait = width < height;
  const font = project.design?.body_font === "noto-serif" ? "Noto Serif" : "Be Vietnam Pro";
  const lines = ["[Script Info]", "ScriptType: v4.00+", `PlayResX: ${width}`, `PlayResY: ${height}`, "WrapStyle: 0", "ScaledBorderAndShadow: yes", "", "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding", `Style: Default,${font},${portrait ? 38 : 36},${ink},${ink},&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,0,0,2,${portrait ? 84 : 160},${portrait ? 84 : 160},${portrait ? 136 : 14},1`, "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"];
  for (const s of scene.segments) {
    const text = s.text.replace(/[\\\r\n]/g, " ").replaceAll("{", "(").replaceAll("}", ")");
    lines.push(`Dialogue: 0,${assTime(s.start)},${assTime(s.end)},Default,,0,0,0,,${text}`);
  }
  return lines.join("\n") + "\n";
}
const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : { channel: "chrome" }) });
const encoder = selectEncoder(ffmpeg, options.encoder || "auto");
const measurements = [];
try {
  for (const ratio of ratios) {
    const totalStarted = performance.now();
    const ratioDir = path.join(output, ratio.replace(":", "x"));
    await mkdir(path.join(ratioDir, "frames"), { recursive: true });
    await mkdir(path.join(ratioDir, "media"), { recursive: true });
    await mkdir(path.join(ratioDir, "fonts"), { recursive: true });
    for (const [id, bytes] of Object.entries(mediaBytes)) await writeFile(path.join(ratioDir, files[id]), bytes);
    for (const font of ["BeVietnamPro-Regular.ttf", "BeVietnamPro-Bold.ttf", "BeVietnamPro-OFL.txt", "NotoSerif.ttf", "NotoSerif-OFL.txt"]) await copyFile(path.join(root, "public/fonts/video-template", font), path.join(ratioDir, "fonts", font));
    const prepared = decode === "frames" ? await decodeSources({ project, resolved, directory: ratioDir, ffmpeg }) : { sequences: {}, seconds: 0 };
    const html = buildRenderFrame(project, scene, ratio, preset, files, css, prepared.sequences);
    assert.ok(!html.includes("data:video/"), "Renderer HTML must use resolved media files");
    await writeFile(path.join(ratioDir, "scene.html"), html);
    await writeFile(path.join(ratioDir, "preview.html"), buildFrame(project, scene, ratio, preset, embedded, css));
    await writeFile(path.join(ratioDir, "comparison.html"), buildFrame(project, scene, ratio, preset, embedded, css, { captions: false }));
    const [width, height] = ratio === "16:9" ? [1920, 1080] : [1080, 1920];
    const frameCount = Math.round(scene.duration * 30);
    const modeCheck = Object.keys(prepared.sequences).length ? await checkCaptureMode({ browser, html: path.join(ratioDir, "scene.html"), reference: path.join(ratioDir, "comparison.html"), width, height, frames: [...new Set([Math.min(30, frameCount - 1), Math.floor(frameCount / 3), Math.floor(frameCount * 2 / 3)])], ffmpeg }) : { compatible: false, comparisons: [] };
    if (!modeCheck.compatible && Object.keys(prepared.sequences).length) {
      console.log(`${ratio}: image resampling exceeds tolerance; using native video capture`);
      await writeFile(path.join(ratioDir, "scene.html"), buildRenderFrame(project, scene, ratio, preset, files, css));
    }
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
    const errors = [], network = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route(/^https?:/, route => { network.push(route.request().url()); return route.abort(); });
    await page.goto(pathToFileURL(path.join(ratioDir, "scene.html")).href);
    await page.waitForFunction(() => !!window.CreatorTemplate);
    const comparisonFrames = [60, 144, 210].filter(i => i < frameCount);
    if (!comparisonFrames.length) comparisonFrames.push(Math.floor(frameCount / 2));
    assert.equal(await page.locator(".caption").textContent(), "", "Renderer template must not draw captions");
    const capture = await captureFrames({ browser, html: path.join(ratioDir, "scene.html"), directory: path.join(ratioDir, "frames"), width, height, frameCount, workers, format: captureFormat, sampleFrames: comparisonFrames, onProgress: (done, total) => console.log(`${ratio}: captured ${done}/${total}`) });
    const captureSeconds = capture.seconds;
    // A second path uses the exact browser-preview document with embedded media.
    // Compare pixels before renderer-owned subtitles, including after backward seek.
    await page.goto(pathToFileURL(path.join(ratioDir, "comparison.html")).href);
    await page.waitForFunction(() => !!window.CreatorTemplate);
    const comparisons = [];
    for (const i of [...comparisonFrames].reverse()) {
      const state = await page.evaluate(t => window.CreatorTemplate.renderAt(t), i / 30);
      assert.ok(state.mediaReady && state.fontsReady); assert.deepEqual(state.textOverflow, []);
      const png = await page.screenshot({ path: path.join(ratioDir, `comparison-${i}.png`) });
      const comparison = comparePng(ffmpeg, capture.samples.get(i), png);
      comparisons.push({ time: i / 30, ...comparison });
      // Chromium resamples video YUV and image RGB differently at scaled sizes.
      // Check both average error and structural similarity, not PNG byte hashes.
      assert.ok(acceptableFrame(comparison), `${ratio}: exported renderer differs from preview at ${i / 30}s: ${JSON.stringify(comparison)}`);
    }
    // Resolve the actual caption style, including layout/preset and product overrides.
    // The renderer hides HTML captions but retains their computed color.
    const subtitleInk = await captionAssColor(page);
    await page.close();
    assert.deepEqual(errors, []); assert.deepEqual(network, []);
    await writeFile(path.join(ratioDir, "subtitles.ass"), subtitles(width, height, subtitleInk));
    const args = ["-hide_banner", "-y", "-framerate", "30", "-i", `frames/%05d.${captureFormat === "jpeg" ? "jpg" : "png"}`];
    const audioSegments = scene.segments.filter(s => s.audioId);
    audioSegments.forEach(s => args.push("-i", files[s.audioId]));
    const delays = audioSegments.map((s, i) => `[${i + 1}:a]adelay=${Math.round(s.start * 1000)}:all=1[a${i}]`);
    const mix = audioSegments.length ? `${audioSegments.map((s, i) => `[a${i}]`).join("")}amix=inputs=${audioSegments.length}:normalize=0,apad,atrim=duration=${scene.duration}[a]` : `anullsrc=r=48000:cl=stereo,atrim=duration=${scene.duration}[a]`;
    args.push("-filter_complex", [...delays, mix, "[0:v]subtitles=filename=subtitles.ass:fontsdir=fonts[v]"].join(";"), "-map", "[v]", "-map", "[a]", ...encoder.args, "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-t", String(scene.duration), "-movflags", "+faststart", videoName);
    const encodeStart = performance.now(), encoded = run(args, ratioDir);
    await writeFile(path.join(ratioDir, "ffmpeg.log"), encoded.stderr);
    const encodeSeconds = (performance.now() - encodeStart) / 1000;
    const result = probe(path.join(ratioDir, videoName));
    assert.equal(result.width, width); assert.equal(result.height, height);
    assert.ok(Math.abs(result.duration - scene.duration) < .05);
    assert.match(result.info, /Video: h264/); assert.match(result.info, /Audio: aac/); assert.match(result.info, /30 fps/);
    run(["-v", "error", "-y", "-i", videoName, "-map", "0:v", "-f", "framemd5", "decoded-frames.md5"], ratioDir);
    const decoded = (await readFile(path.join(ratioDir, "decoded-frames.md5"), "utf8")).split("\n").filter(line => line && !line.startsWith("#")).length;
    assert.equal(decoded, frameCount);
    run(["-v", "error", "-y", "-ss", String(Math.min(5.5, Math.max(0, scene.duration - .1))), "-i", videoName, "-frames:v", "1", "final-frame.png"], ratioDir);
    measurements.push({ ratio, preset, width, height, fps: 30, frameCount, decodedFrames: decoded, duration: result.duration, prepareSeconds: prepared.seconds, captureSeconds, encodeSeconds, totalSeconds: (performance.now() - totalStarted) / 1000, encoder: encoder.name, workers: capture.workers, captureFormat, decodedAssets: modeCheck.compatible ? Object.keys(prepared.sequences) : [], modeCheck, comparisons, errors: [...errors, ...capture.errors], remoteRequests: [...network, ...capture.network], subtitles: "renderer ASS only; whole measured narration segments", output: path.join(ratioDir, videoName) });
    console.log(`${ratio}: PASS — ${frameCount} frames; capture ${captureSeconds.toFixed(2)}s, encode ${encodeSeconds.toFixed(2)}s`);
  }
} finally { await browser.close(); }
assert.equal(sha(await readFile(input)), sha(inputBytes), "Original handoff must remain unchanged");
await writeFile(path.join(output, "measurements.json"), JSON.stringify({ input, inputSha256: sha(inputBytes), measuredAt: new Date().toISOString(), source: project.source, productId: project.productId, sceneId: scene.id, inputType: m2Input ? "m2" : "scene-handoff", timing: project.timing, media: mediaInfo, mapping: { crop: scene.crop, focus: scene.focus, clipStartsAtSceneTime: 0, focusPartIndexBase: 0, fps: 30 }, measurements }, null, 2));
if (previewDir) {
  await mkdir(previewDir, { recursive: true });
  for (const ratio of ratios) {
    const name = ratio.replace(":", "x");
    await copyFile(path.join(output, name, videoName), path.join(previewDir, `${name}.mp4`));
    await copyFile(path.join(output, name, "final-frame.png"), path.join(previewDir, `${name}.png`));
  }
  await writeFile(path.join(previewDir, "manifest.json"), JSON.stringify({ renderedAt: new Date().toISOString(), sourceSha256: sha(inputBytes), preset, variants: measurements.map(m => ({ ratio: m.ratio, width: m.width, height: m.height, duration: m.duration })) }, null, 2));
  console.log(`Local preview videos: ${previewDir}`);
}
console.log(`Results: ${output}`);
