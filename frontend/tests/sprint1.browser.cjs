// Optional browser acceptance checks. No new application dependency is required.
// Set PLAYWRIGHT_MODULE to an installed Playwright module path and start the app first.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.TEST_BASE_URL || 'http://localhost:3000';
const output = process.env.TEST_OUTPUT_DIR || path.resolve('test-results');

async function waitCards(page, count) {
  await page.waitForFunction((count) => !document.querySelector('#review-results[aria-busy="true"]') && document.querySelectorAll('.review-card').length === count, count);
}

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    for (const route of ['/creator/library', '/creator/campaigns', '/admin', '/reviews']) {
      assert.equal((await page.goto(base + route)).status(), 200);
      await page.locator('.workspace-footer').waitFor();
      assert.equal(await page.locator('.factory-sidebar').count(), 1);
      assert.equal(await page.locator('.workspace-footer a[target="_blank"]').count(), 2);
      const bounds = await page.evaluate(() => ({ footer: document.querySelector('.workspace-footer').getBoundingClientRect().bottom, height: innerHeight }));
      assert.ok(bounds.footer >= bounds.height - 2, 'footer must reach bottom of short pages');
    }
    await waitCards(page, 3);
    await page.waitForFunction(() => [...document.querySelectorAll('.review-card img')].every((img) => img.complete && img.naturalWidth > 0));
    await page.screenshot({ path: path.join(output, 'reviews-desktop.png'), fullPage: true });

    const requests = [];
    page.on('request', (request) => { if (new URL(request.url()).pathname === '/search') requests.push({ q: new URL(request.url()).searchParams.get('q'), at: Date.now() }); });
    const search = page.getByRole('searchbox', { name: 'Tìm review video' });
    await search.fill('N'); await page.waitForTimeout(80);
    await search.fill('No'); await page.waitForTimeout(80);
    const start = Date.now(); await search.fill('Notion');
    await page.waitForTimeout(180);
    assert.equal(requests.length, 0, 'no request before debounce');
    await waitCards(page, 1);
    assert.deepEqual(requests.map((r) => r.q), ['Notion']);
    assert.ok(requests[0].at - start >= 280, 'request follows approximately 300ms debounce');
    assert.match(await page.locator('.review-card h2').innerText(), /Notion/);

    await search.fill('no-result-here'); await waitCards(page, 0);
    assert.ok(await page.getByText('Không tìm thấy review phù hợp.').isVisible());
    await page.getByRole('button', { name: 'Xóa tìm kiếm', exact: true }).last().click();
    await waitCards(page, 3);

    // Force out-of-order responses: a slower old request must not replace the latest query.
    await page.route('**/search?*', async (route) => {
      const q = new URL(route.request().url()).searchParams.get('q');
      if (q === 'Gamma') await new Promise((resolve) => setTimeout(resolve, 900));
      await route.continue().catch(() => {});
    });
    await search.fill('Gamma'); await page.waitForTimeout(380);
    await search.fill('Linear'); await waitCards(page, 1); await page.waitForTimeout(1000);
    assert.match(await page.locator('.review-card h2').innerText(), /Linear/);
    await page.unroute('**/search?*');

    await page.route('**/search?*', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"offline"}' }));
    await search.fill('Gamma'); await page.getByRole('button', { name: 'Thử lại', exact: true }).waitFor();
    await page.unroute('**/search?*');
    await page.getByRole('button', { name: 'Thử lại', exact: true }).click(); await waitCards(page, 1);
    await page.locator('.review-card').click(); await page.waitForURL('**/review/gamma-presentation');
    await page.locator('video').waitFor();
    await page.waitForFunction(() => document.querySelector('video')?.readyState >= 3);
    assert.equal(await page.locator('.video-loading').count(), 0);
    const duration = await page.locator('video').evaluate((video) => video.duration);
    assert.ok(duration >= 12, 'local demo has a playable duration');
    await page.getByRole('button', { name: /0:04/ }).click();
    await page.waitForFunction(() => Math.abs(document.querySelector('video').currentTime - 4) < 0.15);
    assert.match(await page.locator('.transcript-overlay').innerText(), /Review the information/);
    await page.locator('video').evaluate((video) => video.play());
    await page.waitForFunction(() => document.querySelector('video').currentTime >= 8.2);
    await page.locator('video').evaluate((video) => video.pause());
    assert.match(await page.locator('.transcript-overlay').innerText(), /Edit the draft/);
    await page.getByRole('button', { name: 'Ẩn transcript', exact: true }).click();
    assert.equal(await page.locator('.transcript-overlay').count(), 0);
    await page.getByRole('button', { name: 'Hiện transcript', exact: true }).click();
    await page.screenshot({ path: path.join(output, 'review-detail-desktop.png'), fullPage: true });

    // Video failure and retry recovery.
    await page.route('**/media/workspace-demo.webm', (route) => route.abort());
    await page.reload(); await page.locator('.video-error').waitFor();
    await page.unroute('**/media/workspace-demo.webm');
    await page.getByRole('button', { name: 'Thử tải video lại' }).click();
    await page.waitForFunction(() => document.querySelector('video')?.readyState >= 3);
    assert.equal(await page.locator('.video-error').count(), 0);

    await page.goto(base + '/review/does-not-exist');
    await page.getByRole('heading', { name: 'Không tìm thấy review', exact: true }).waitFor();
    assert.equal((await page.request.get(base + '/api/reviews/does-not-exist')).status(), 404);
    assert.equal((await page.request.get(base + '/search?q=' + 'a'.repeat(201))).status(), 400);

    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      await page.goto(base + '/reviews'); await waitCards(page, 3);
      assert.ok(!(await page.locator('#workspace-navigation').isVisible()));
      await page.getByRole('button', { name: 'Mở điều hướng', exact: true }).click();
      assert.ok(await page.locator('#workspace-navigation').isVisible());
      await page.keyboard.press('Escape');
      assert.ok(!(await page.locator('#workspace-navigation').isVisible()));
      await page.getByRole('button', { name: 'Mở điều hướng', exact: true }).click();
      await page.getByRole('link', { name: 'Campaigns', exact: true }).click();
      await page.waitForURL('**/creator/campaigns');
      assert.ok(!(await page.locator('#workspace-navigation').isVisible()));
      await page.goto(base + '/reviews'); await waitCards(page, 3);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'no mobile horizontal overflow');
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await page.waitForFunction(() => [...document.querySelectorAll('.review-card img')].every((img) => img.complete && img.naturalWidth > 0));
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: path.join(output, `reviews-mobile-${width}.png`), fullPage: true });
      await page.locator('.review-card').first().click();
      await page.waitForFunction(() => document.querySelector('video')?.readyState >= 3);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: path.join(output, `review-detail-mobile-${width}.png`), fullPage: true });
    }
    assert.deepEqual(errors, [], 'no unexpected client rendering errors');
    console.log('PASS: shared layout, debounce, cancellation, empty/error/retry, card routing, playback/transcript, video recovery, existing content workflow and 320/390px mobile.');
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exit(1); });
