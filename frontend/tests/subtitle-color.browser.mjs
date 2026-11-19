import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { chromium } from "playwright";
import { fromM2 } from "../src/features/video-template/model.ts";
import { buildFrame, buildRenderFrame } from "../src/features/video-template/frame.ts";
import { captionAssColor } from "../scripts/lib/subtitle-color.mjs";

const raw = JSON.parse(await readFile(new URL("./fixtures/template-handoff.json", import.meta.url), "utf8"));
const css = await readFile(new URL("../public/video-template.css", import.meta.url), "utf8");
const project = fromM2(raw);
const files = Object.fromEntries(project.assets.map((asset, index) => [asset.id, `media/asset-${index}.${asset.kind === "video" ? "mp4" : "png"}`]));
const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : { channel: "chrome" }) });
let cases = 0;
try {
  for (const ratio of ["16:9", "9:16"]) {
    for (const preset of ["cinematic", "animation", "vintage"]) {
      for (const scene of project.scenes) {
        for (const custom of [false, true]) {
          const input = custom ? { ...project, design: { background: "#102030", foreground: "#F1E2D3", accent: "#FFFFFF" } } : project;
          const page = await browser.newPage();
          try {
            await page.setContent(buildFrame(input, scene, ratio, preset, {}, css), { waitUntil: "domcontentloaded" });
            const previewInk = await captionAssColor(page);
            // A navigation creates a fresh JS realm for the standalone template runtime.
            await page.goto("about:blank");
            await page.setContent(buildRenderFrame(input, scene, ratio, preset, files, css), { waitUntil: "domcontentloaded" });
            const ink = await captionAssColor(page);
            assert.equal(ink, previewInk, `${scene.layout}/${preset}/${ratio}: preview and renderer differ`);
            const expected = custom ? "&H00D3E2F1" : scene.layout === "feature_clip"
              ? { cinematic: "&H001E2517", animation: "&H00622D17", vintage: "&H00262E43" }[preset]
              : preset === "vintage" ? "&H00152434" : "&H00FCF7F5";
            assert.equal(ink, expected, `${scene.layout}/${preset}/${ratio}: subtitle palette regressed`);
            assert.equal(await page.locator(".caption").evaluate(element => getComputedStyle(element).visibility), "hidden");
            cases++;
          } finally { await page.close(); }
        }
      }
    }
  }
  console.log(`PASS: ${cases} subtitle color cases (4 layouts, 3 presets, 2 ratios, default/custom colors).`);
} finally { await browser.close(); }
