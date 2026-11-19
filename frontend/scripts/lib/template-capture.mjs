import assert from "node:assert/strict";
import path from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { availableParallelism } from "node:os";
import { pathToFileURL } from "node:url";
import { performance } from "node:perf_hooks";

export const defaultWorkers = Math.min(4, Math.max(1, Math.floor(availableParallelism() / 2)));

export function ffmpegJob(binary, args, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(binary, args, { cwd, windowsHide: true, stdio: ["ignore", "ignore", "pipe"] });
    let stderr = "";
    child.stderr.on("data", data => { stderr += data; });
    child.on("error", reject);
    child.on("close", code => code === 0 ? resolve(stderr) : reject(new Error(`FFmpeg exited ${code}: ${stderr.slice(-8000)}`)));
  });
}

// Native timestamps support variable-rate sources and cuts between source frames.
// Keep long/unusual sources on the existing video path instead of expanding them
// without a bound. The intermediate PNGs are lossless and never alter the source.
export function decodedFrameTimes(log) {
  const timeBase = log.match(/config in time_base:\s*(\d+)\/(\d+)/);
  assert.ok(timeBase && Number(timeBase[2]) > 0, "Missing decoder time base");
  const times = [...log.matchAll(/\bn:\s*\d+\s+pts:\s*(-?\d+)\s+pts_time:/g)].map(match => Number(match[1]) * Number(timeBase[1]) / Number(timeBase[2]));
  assert.ok(times.length && times.every((t, i) => t >= 0 && (!i || t > times[i - 1])), "Invalid decoded frame timestamps");
  return times;
}

export async function decodeSources({ project, resolved, directory, ffmpeg }) {
  const sequences = Object.create(null), start = performance.now();
  for (const [index, asset] of project.assets.entries()) {
    if (asset.kind !== "video") continue;
    const { file, meta } = resolved.get(asset.id);
    if (meta.duration > 120 || meta.width * meta.height > 1920 * 1080 || !/yuv420p\(/.test(meta.info)) continue;
    const relative = `media/decoded-${index}`;
    await mkdir(path.join(directory, relative), { recursive: true });
    const log = await ffmpegJob(ffmpeg, ["-hide_banner", "-nostdin", "-y", "-i", file, "-an", "-vf", "showinfo", "-fps_mode", "passthrough", "-c:v", "png", "-threads", "2", "-compression_level", "1", `${relative}/%06d.png`], directory);
    // pts_time is rounded in FFmpeg logs; using it can select the previous
    // frame at exact 30 fps boundaries. Integer PTS preserves those boundaries.
    const times = decodedFrameTimes(log);
    sequences[asset.id] = { directory: relative, times, width: meta.width, height: meta.height };
  }
  return { sequences, seconds: (performance.now() - start) / 1000 };
}

export async function captureFrames({ browser, html, directory, width, height, frameCount, fps = 30, workers = defaultWorkers, format = "jpeg", sampleFrames = [], onProgress = () => {} }) {
  assert.ok(Number.isInteger(workers) && workers >= 1 && workers <= 8, "workers must be 1..8");
  assert.ok(["jpeg", "png"].includes(format), "format must be jpeg or png");
  await mkdir(directory, { recursive: true });
  const start = performance.now(), samples = new Map(), errors = [], network = [];
  const count = Math.min(workers, frameCount), size = Math.ceil(frameCount / count);
  let completed = 0, failed;
  const results = await Promise.allSettled(Array.from({ length: count }, async (_, worker) => {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
    page.on("pageerror", error => errors.push(error.message));
    await page.route(/^https?:/, route => { network.push(route.request().url()); return route.abort(); });
    try {
      await page.goto(pathToFileURL(html).href);
      await page.waitForFunction(() => !!window.CreatorTemplate);
      const cdp = await page.context().newCDPSession(page);
      for (let i = worker * size; i < Math.min(frameCount, (worker + 1) * size); i++) {
        if (failed) throw failed;
        const state = await page.evaluate(t => window.CreatorTemplate.renderAt(t, { capture: true }), i / fps);
        assert.ok(state.fontsReady && state.mediaReady && !state.missingMedia, `Frame ${i}: media/fonts unavailable`);
        assert.deepEqual(state.textOverflow, [], `Frame ${i}: text overflow`);
        const { data } = await cdp.send("Page.captureScreenshot", { format, ...(format === "jpeg" ? { quality: 95 } : {}), optimizeForSpeed: true });
        await writeFile(path.join(directory, `${String(i).padStart(5, "0")}.${format === "jpeg" ? "jpg" : "png"}`), Buffer.from(data, "base64"));
        if (sampleFrames.includes(i)) {
          const png = format === "png" ? data : (await cdp.send("Page.captureScreenshot", { format: "png", optimizeForSpeed: true })).data;
          samples.set(i, Buffer.from(png, "base64"));
        }
        completed++;
        if (completed % 120 === 0 || completed === frameCount) onProgress(completed, frameCount);
      }
    } catch (error) { failed = error; throw error; }
    finally { await page.close(); }
  }));
  const rejection = results.find(result => result.status === "rejected");
  if (rejection) throw rejection.reason;
  assert.deepEqual(errors, []); assert.deepEqual(network, []);
  return { seconds: (performance.now() - start) / 1000, samples, errors, network, workers: count, format };
}
