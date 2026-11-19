import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { pathToFileURL, fileURLToPath } from "node:url";
import path from "node:path";
import assert from "node:assert/strict";
import { reusableProjects } from "./fixtures/reusable-projects.mjs";

export async function checkReusedProjects(output) {
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : { channel: "chrome" }) });
  const checks = [];
  await mkdir(path.join(output, "checks"), { recursive: true });
  try {
    for (const [index, raw] of reusableProjects().entries()) for (const scene of raw.presentation.scenes) for (const ratio of ["16x9", "9x16"]) {
      const page = await browser.newPage({ viewport: ratio === "16x9" ? { width: 1920, height: 1080 } : { width: 1080, height: 1920 } });
      await page.goto(pathToFileURL(path.join(output, `project-${index + 1}/scenes/${scene.scene_id}/${ratio}/scene.html`)).href);
      await page.waitForFunction(() => !!window.CreatorTemplate);
      const time = scene.motion.beats[0].start_s + .4;
      const actual = await page.evaluate(async t => {
        const state = await window.CreatorTemplate.renderAt(t), root = document.querySelector('#root');
        return { state, palette: root.style.getPropertyValue('--bg'), foreground: root.style.getPropertyValue('--fg'), font: getComputedStyle(document.querySelector('h1')).fontFamily, monogram: document.querySelector('.story-monogram').textContent, product: document.querySelector('.story-product').textContent, mode: root.dataset.motionMode, composition: root.dataset.composition, visible: [...document.querySelectorAll('.story-beat')].filter(n => getComputedStyle(n).visibility === 'visible' && Number(getComputedStyle(n).opacity) > .95).map(n => n.querySelector('h2').textContent) };
      }, time);
      assert.ok(actual.state.mediaReady && actual.state.fontsReady); assert.deepEqual(actual.state.textOverflow, []);
      assert.equal(actual.palette, raw.product_design.background); assert.equal(actual.foreground, raw.product_design.foreground);
      assert.ok(actual.font.includes(index ? 'TemplateSerif' : 'TemplateSans'));
      assert.equal(actual.monogram, raw.product_name[0]); assert.equal(actual.product, raw.product_name);
      assert.equal(actual.mode, scene.motion.mode);
      assert.equal(actual.composition, ratio === '9x16' ? 'portrait' : scene.motion.mode === 'adaptive' ? 'guide' : 'wide');
      assert.deepEqual(actual.visible, [raw.script.scenes.find(s => s.scene_id === scene.scene_id).claims[0].text]);
      await page.screenshot({ path: path.join(output, 'checks', `project-${index + 1}-${scene.scene_id}-${ratio}.png`) });
      checks.push({ productId: raw.script.product_id, scene: scene.scene_id, ratio, ...actual });
      await page.close();
    }
  } finally { await browser.close(); }
  await writeFile(path.join(output, 'checks', 'reuse-browser-checks.json'), JSON.stringify(checks, null, 2));
  console.log(`PASS: ${checks.length} product/scene/ratio checks — actual palette, font, identity and motion come from input`);
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await checkReusedProjects(path.resolve(process.env.REUSE_OUTPUT || 'test-results/template-reuse'));
