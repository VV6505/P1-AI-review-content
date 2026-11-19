const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:3000';
const fixture = () => JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/template-handoff.json'), 'utf8'));

(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : { channel: 'chrome' }) });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // Test the M2 importer without requiring the separately shared s03 media bundle.
    await page.route('**/2026-10-26_s03-feature-clip/scene-s03.json', route => route.fulfill({ status: 404, body: '' }));
    await page.goto(base + '/login');
    await page.getByLabel('Tài khoản', { exact: true }).fill('creator');
    await page.getByLabel('Mật khẩu', { exact: true }).fill('123456');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.waitForURL('**/creator/create');
    await page.goto(base + '/creator/template-review');
    await page.getByRole('alert').filter({ hasText: 'Chưa có bộ s03' }).waitFor();
    await page.locator('.template-handoff-details summary').click();

    const input = page.getByLabel('Nạp gói M2', { exact: true });
    const preview = page.locator('.creator-template-preview');
    const warning = page.getByText('Timeline này nằm ngoài 40–45 giây; chỉ dùng review cảnh, chưa đạt thời lượng video P1.', { exact: true });
    let revision = 0;
    async function upload(raw) {
      await input.setInputFiles({ name: 'm2-contract.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(raw)) });
    }
    async function importValid(estimate) {
      const raw = fixture();
      raw.product_name = `Contract fixture ${++revision}`;
      if (estimate !== undefined) raw.script.estimated_duration_s = estimate;
      raw.script.scenes[3].visual_plan.kind = 'ai_generated_image';
      await upload(raw);
      await page.waitForFunction(title => document.querySelector('.template-preview-heading strong')?.textContent.startsWith(title), raw.product_name);
      assert.equal(await preview.getByRole('alert').count(), 0);
      assert.match(await page.locator('.template-preview-toolbar').textContent(), /21\.00s/);
      assert.equal(await page.locator('.template-timeline output').textContent(), '0.00 / 21.00s');
      assert.equal(await warning.count(), 1, 'the estimate cannot turn a 21s fixture into an accepted P1 timeline');
      return raw;
    }

    await importValid(undefined);
    const raw = await importValid(42);
    const contentReview = page.locator('.content-review-panel');
    assert.ok(await contentReview.isVisible());
    assert.match(await contentReview.textContent(), /Ước tính trước giọng đọc/);
    assert.match(await contentReview.textContent(), /42\.00s/);
    assert.equal(await contentReview.locator('.content-review-scenes > li').count(), 4);
    assert.ok((await contentReview.textContent()).includes(raw.script.scenes[0].narration_segments[0].text));
    await contentReview.locator('.content-review-scenes > li').first().getByText('Thông tin sản phẩm và nguồn fact', { exact: true }).click();
    const firstClaim = raw.script.scenes[0].claims[0];
    assert.ok(await contentReview.getByText(firstClaim.text, { exact: true }).first().isVisible());
    assert.ok((await contentReview.locator('.content-review-scenes > li').first().textContent()).includes(firstClaim.fact_refs[0].field_path));
    await contentReview.locator('.content-scene-seek').last().click();
    assert.equal(await contentReview.locator('li[aria-current="step"] > button > strong').textContent(), 's04 · Minh họa');
    fs.mkdirSync(path.resolve('test-results/p1-content-review'), { recursive: true });
    await page.screenshot({ path: path.resolve('test-results/p1-content-review/m2-scene-review.png'), fullPage: true });
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `content review fits ${width}px`);
      await page.screenshot({ path: path.resolve(`test-results/p1-content-review/m2-scene-review-${width}.png`), fullPage: true });
    }
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.getByRole('button', { name: 's04 · highlight_zoom', exact: true }).click();
    const image = await page.evaluate(() => {
      const canvas = document.createElement('canvas'); canvas.width = 1200; canvas.height = 800;
      const context = canvas.getContext('2d'); context.fillStyle = '#284254'; context.fillRect(0, 0, 1200, 800);
      return canvas.toDataURL('image/png').split(',')[1];
    });
    await page.getByLabel('Asset fixture:focus', { exact: true }).setInputFiles({ name: 'focus.png', mimeType: 'image/png', buffer: Buffer.from(image, 'base64') });
    await page.waitForFunction(() => [...document.querySelectorAll('.template-asset span')].some(label => label.textContent.includes('fixture:focus · image ✓')));
    const iframe = page.locator('iframe[title="Khung hình template"]');
    const frame = await (await iframe.elementHandle()).contentFrame();
    await frame.waitForFunction(() => !!window.CreatorTemplate && document.querySelector('[data-scene="s04"] img')?.naturalWidth > 0);
    const state = await frame.evaluate(() => window.CreatorTemplate.renderAt(2));
    assert.equal(state.mediaReady, true);
    assert.deepEqual(state.textOverflow, []);

    for (const mutate of [
      r => r.script.estimated_duration_s = '42',
      r => r.script.unrecognized_field = true,
    ]) {
      const invalid = structuredClone(raw); mutate(invalid); await upload(invalid);
      await page.getByRole('alert').filter({ hasText: 'M2 không khớp schema #83' }).waitFor();
      assert.ok((await page.locator('.template-preview-heading strong').textContent()).startsWith(raw.product_name), 'a bad import preserves the last valid project');
    }
    await importValid(undefined);
    assert.deepEqual(errors, []);
    console.log('PASS: M2 import with/without estimate, unchanged 21s timeline, AI image preview, strict rejection and recovery.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
