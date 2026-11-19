import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";

// A small resampling difference is expected when a CSS-scaled YUV video is
// replaced by decoded RGB pixels. This is visual equivalence, not pixel identity.
export const acceptableFrame = comparison => comparison.meanAbsoluteError <= 2 && comparison.ssim >= .95 && (comparison.psnr === null || comparison.psnr >= 32);

export async function checkCaptureMode({ browser, html, reference, width, height, frames, ffmpeg }) {
  const pages = await Promise.all([html, reference].map(async file => {
    const page = await browser.newPage({ viewport: { width, height } });
    await page.route(/^https?:/, route => route.abort());
    await page.goto(pathToFileURL(file).href);
    return page;
  }));
  const comparisons = [];
  try {
    for (const frame of frames) {
      const pngs = await Promise.all(pages.map(async page => {
        const state = await page.evaluate(t => window.CreatorTemplate.renderAt(t), frame / 30);
        assert.ok(state.mediaReady && state.fontsReady); assert.deepEqual(state.textOverflow, []);
        return page.screenshot();
      }));
      comparisons.push({ frame, ...comparePng(ffmpeg, pngs[0], pngs[1]) });
    }
    return { compatible: comparisons.every(acceptableFrame), comparisons };
  } finally { await Promise.all(pages.map(page => page.close())); }
}

export function comparePng(ffmpeg, actual, expected) {
  const decode = input => {
    const result = spawnSync(ffmpeg, ["-v", "error", "-i", "pipe:0", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], { input, maxBuffer: 64 * 1024 * 1024, windowsHide: true });
    assert.ok(!result.error && result.status === 0, result.error?.message || result.stderr.toString());
    return result.stdout;
  };
  const a = decode(actual), b = decode(expected);
  assert.equal(a.length, b.length);
  let sum = 0, squared = 0, maximum = 0, changed = 0;
  for (let i = 0; i < a.length; i++) {
    const delta = Math.abs(a[i] - b[i]);
    sum += delta; squared += delta * delta; maximum = Math.max(maximum, delta);
    if (delta) changed++;
  }
  const width = actual.readUInt32BE(16), height = actual.readUInt32BE(20);
  const result = spawnSync(ffmpeg, ["-hide_banner", "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", `${width}x${height}`, "-i", "pipe:0", "-filter_complex", "[0:v]split[x][y];[x]trim=end_frame=1,setpts=PTS-STARTPTS[a];[y]trim=start_frame=1,setpts=PTS-STARTPTS[b];[a][b]ssim", "-f", "null", "-"], { input: Buffer.concat([a, b]), maxBuffer: 1024 * 1024, windowsHide: true });
  assert.ok(!result.error && result.status === 0, result.error?.message || result.stderr.toString());
  const ssim = Number(result.stderr.toString().match(/All:([\d.]+)/)?.[1]);
  assert.ok(Number.isFinite(ssim));
  return { identicalPixels: changed === 0, meanAbsoluteError: sum / a.length, maxChannelDelta: maximum, psnr: squared ? 10 * Math.log10(255 ** 2 / (squared / a.length)) : null, ssim };
}
