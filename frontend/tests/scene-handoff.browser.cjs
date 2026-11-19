const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:3000';
const output = path.resolve(process.env.S03_UI_OUTPUT || 'test-results/s03-ui');

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : { channel: 'chrome' }) });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1080 }, acceptDownloads: true });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base + '/login');
    await page.getByLabel('Tài khoản', { exact: true }).fill('creator');
    await page.getByLabel('Mật khẩu', { exact: true }).fill('123456');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.waitForURL('**/creator/create');
    await page.goto(base + '/creator/template-review');
    await page.getByRole('button', { name: 's03 · feature_clip', exact: true }).waitFor();
    const iframe = page.locator('iframe[title="Khung hình template"]');
    async function frame() {
      const current = await (await iframe.elementHandle()).contentFrame();
      await current.waitForFunction(() => !!window.CreatorTemplate && document.querySelector('[data-scene="s03"]'));
      return current;
    }
    const diagnostics = [];
    for (const ratio of ['16:9', '9:16']) {
      await page.getByRole('button', { name: ratio === '16:9' ? 'Ngang 16:9' : 'Dọc 9:16', exact: true }).click();
      for (const preset of ['cinematic', 'animation', 'vintage']) {
        await page.getByLabel('Phong cách cảnh', { exact: true }).selectOption(preset);
        const f = await frame();
        await f.waitForFunction(({ ratio, preset }) => document.querySelector('#root').classList.contains(preset) && document.querySelector('#root').classList.contains('portrait') === (ratio === '9:16'), { ratio, preset });
        for (const t of [0, 1, 2.4, 4.76, 5.5, 7.6, 1]) {
          const state = await f.evaluate(t => window.CreatorTemplate.renderAt(t), t);
          assert.ok(state.fontsReady && state.mediaReady && !state.missingMedia, JSON.stringify({ ratio, preset, t, state }));
          assert.deepEqual(state.textOverflow, [], `${ratio}/${preset}/${t}`);
          diagnostics.push({ ratio, preset, t, ...state });
        }
        for (const [time, expected] of [[.8, []], [1.6, ['1']], [2.4, []], [3.1, ['2']], [4.48, []], [5.5, ['3']], [6.46, []], [7.2, ['4']], [.8, []]]) {
          await f.evaluate(t => window.CreatorTemplate.renderAt(t), time);
          const visible = await f.locator('.story-beat').evaluateAll(nodes => nodes.filter(n => getComputedStyle(n).visibility === 'visible' && Number(getComputedStyle(n).opacity) > .95).map(n => n.dataset.beat));
          assert.deepEqual(visible, expected, `${ratio}/${preset}/${time}: only the current action is shown`);
          if (time > 1.6) assert.equal(await f.locator('.story-intro').evaluate(n => getComputedStyle(n).visibility), 'hidden', 'intro leaves after opening');
          if (preset === 'cinematic') await iframe.screenshot({ path: path.join(output, `story-${time}-${ratio.replace(':', 'x')}.png`) });
        }
        async function geometryAt(time) {
          await f.evaluate(t => window.CreatorTemplate.renderAt(t), time);
          return f.evaluate(() => {
          const root = document.querySelector('#root').getBoundingClientRect(), screen = document.querySelector('.story-screen').getBoundingClientRect(), video = document.querySelector('video'), rendered = video.getBoundingClientRect();
          return { widthFraction: screen.width / root.width, offsetX: (screen.x + screen.width / 2 - (root.x + root.width / 2)) / root.width, centerY: Math.abs(screen.y + screen.height / 2 - (root.y + root.height / 2)) / root.height, aspectError: Math.abs(rendered.width / rendered.height - video.videoWidth / video.videoHeight) };
          });
        }
        const compositions = [];
        for (const time of [.8, 1.6, 2.4, 3.1, 4.48, 5.5, 6.46, 7.2, 1.6, 2.4]) {
          const geometry = await geometryAt(time), instruction = [1.6, 3.1, 5.5].includes(time);
          if (ratio === '16:9' && instruction) {
            assert.ok(geometry.widthFraction > .50 && geometry.widthFraction < .65, `${ratio}/${preset}/${time}: make room for instruction`);
            assert.ok(time === 3.1 ? geometry.offsetX < -.12 : geometry.offsetX > .12, `${ratio}/${preset}/${time}: move opposite the instruction`);
          } else {
            assert.ok(geometry.widthFraction > .82 && Math.abs(geometry.offsetX) < .03, `${ratio}/${preset}/${time}: return to large centered video`);
          }
          assert.ok(geometry.centerY < .08 && geometry.aspectError < .01, `${ratio}/${preset}/${time}: preserve vertical alignment and source aspect ratio`);
          compositions.push({ time, ...geometry });
        }
        diagnostics.push({ ratio, preset, compositions });
        await f.evaluate(() => window.CreatorTemplate.renderAt(5.5));
        await iframe.screenshot({ path: path.join(output, `${preset}-${ratio.replace(':', 'x')}.png`) });
      }
    }
    await page.getByRole('button', { name: 'Ngang 16:9', exact: true }).click();
    await page.getByLabel('Phong cách cảnh', { exact: true }).selectOption('cinematic');
    // Use the page's seek request so export readiness refers to the displayed timestamp.
    await page.getByLabel('Timeline preview', { exact: true }).fill('2');
    await page.locator('.template-handoff-details summary').click();
    await page.getByRole('button', { name: 'Xuất HTML cảnh', exact: true }).waitFor();
    await page.waitForFunction(() => [...document.querySelectorAll('button')].some(b => b.textContent === 'Xuất HTML cảnh' && !b.disabled));
    const downloaded = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Xuất HTML cảnh', exact: true }).click();
    const html = path.join(output, 's03-preview-offline.html');
    await (await downloaded).saveAs(html);
    const standalone = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    await standalone.goto(pathToFileURL(html).href);
    const state = await standalone.evaluate(() => window.CreatorTemplate.renderAt(2));
    assert.ok(state.mediaReady && state.fontsReady); assert.deepEqual(state.textOverflow, []);
    assert.equal(await standalone.locator('.caption').textContent(), 'Chọn vị trí, bấm áp dụng là có số trang.');
    await standalone.close();
    const renderedVideos = page.locator('video[data-output-ratio]');
    if (process.env.S03_REQUIRE_RENDERED === '1') assert.equal(await renderedVideos.count(), 2, 'Both exported MP4 players must be on the review page');
    if (await renderedVideos.count()) {
      assert.equal(await renderedVideos.count(), 2);
      for (const outputRatio of ['16x9', '9x16']) {
        const element = page.locator(`video[data-output-ratio="${outputRatio}"]`);
        await element.evaluate(video => video.readyState >= 1 ? Promise.resolve() : new Promise((resolve, reject) => { video.addEventListener('loadedmetadata', resolve, { once: true }); video.addEventListener('error', reject, { once: true }); video.load(); }));
        const size = await element.evaluate(video => [video.videoWidth, video.videoHeight]);
        assert.deepEqual(size, outputRatio === '16x9' ? [1920, 1080] : [1080, 1920]);
      }
    }
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No horizontal mobile overflow');
    await page.screenshot({ path: path.join(output, 'review-mobile.png'), fullPage: true });
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(output, 'diagnostics.json'), JSON.stringify(diagnostics, null, 2));
    console.log(`PASS: six ratio/preset combinations, backward seek, export offline and mobile; ${output}`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
