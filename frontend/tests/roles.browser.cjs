const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.TEST_BASE_URL || 'http://localhost:3000';
const output = process.env.TEST_OUTPUT_DIR || path.resolve('test-results/roles');

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
    const page = await context.newPage();
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto(base + '/merchant');
    await page.getByRole('heading', { name: 'Dashboard Merchant' }).waitFor();
    await page.getByRole('link', { name: 'Chuyển sang Admin' }).click();
    await page.waitForURL('**/admin');
    await page.getByRole('heading', { name: 'Tổng quan QA' }).waitFor();
    assert.equal(await page.locator('.workspace-sidebar').getByRole('link', { name: 'Onboarding' }).count(), 0);
    await page.goto(base + '/admin/videos/notion-workspace');
    await page.getByRole('heading', { name: 'Quyết định QA' }).waitFor();
    for (const checkbox of await page.getByRole('checkbox').all()) await checkbox.check();
    assert.ok(await page.getByRole('button', { name: 'Duyệt video', exact: true }).isDisabled(), 'PKB draft blocks video approval');
    assert.ok(await page.getByRole('button', { name: 'Từ chối video', exact: true }).isDisabled(), 'rejection requires a reason');

    await page.goto(base + '/merchant/products/notion');
    await page.getByRole('button', { name: 'Gửi review', exact: true }).click();
    assert.equal(await page.getByRole('button', { name: 'Từ chối PKB', exact: true }).count(), 0);
    assert.equal(await page.getByLabel('Vai trò demo').count(), 0);
    await page.goto(base + '/admin/pkb/notion');
    await page.getByRole('heading', { name: 'Product Knowledge Base' }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Merchant duyệt PKB', exact: true }).count(), 0);
    assert.equal(await page.getByRole('textbox', { name: 'Mô tả sản phẩm', exact: true }).count(), 0);
    await page.goto(base + '/merchant/products/notion');
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: 'Merchant duyệt PKB', exact: true }).click();
    await page.getByRole('button', { name: 'Tạo draft mới' }).waitFor();
    await page.goto(base + '/admin/videos/notion-workspace');
    await page.getByRole('checkbox').first().waitFor();
    assert.ok(await page.getByRole('button', { name: 'Duyệt video', exact: true }).isDisabled(), 'unchecked QA blocks approval');
    for (const checkbox of await page.getByRole('checkbox').all()) await checkbox.check();
    await page.getByRole('button', { name: 'Duyệt video', exact: true }).click();
    await page.getByText('Video đã được xử lý.', { exact: false }).waitFor();
    await page.reload();
    await page.getByText('Video đã được xử lý.', { exact: false }).waitFor();
    const approval = await page.evaluate(() => JSON.parse(localStorage.getItem('reviewlab.video-qa.mock.v1')).assets.find(a => a.review.id === 'notion-workspace'));
    assert.ok(approval.firstApprovedAt && approval.reviewedAt && approval.reviewedBy);
    await page.goto(base + '/merchant/library');
    await page.waitForFunction(() => document.querySelectorAll('.asset-card').length === 2);
    await page.goto(base + '/merchant/library/notion-workspace');
    const videoDownload = page.waitForEvent('download');
    await page.getByRole('link', { name: 'Tải video demo', exact: true }).click();
    assert.match((await videoDownload).suggestedFilename(), /demo.mp4$/);
    const captionDownload = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Tải caption', exact: true }).click();
    assert.match((await captionDownload).suggestedFilename(), /caption-demo.txt$/);
    await page.getByRole('button', {name:'Báo sai video',exact:true}).click();
    await page.getByLabel('Nội dung cần kiểm tra').fill('Pricing claim needs another review.');
    // A storage failure must preserve the reason and leave the video unflagged.
    await page.evaluate(() => {
      const original = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key, value) { if (key === 'reviewlab.video-qa.mock.v1') throw new DOMException('Quota', 'QuotaExceededError'); return original.call(this, key, value); };
      window.restoreVideoStorage = () => { Storage.prototype.setItem = original; };
    });
    await page.getByRole('button', { name: 'Gửi báo sai' }).click();
    await page.getByText('Không thể lưu thư viện vào trình duyệt.', { exact: false }).first().waitFor();
    assert.equal(await page.getByLabel('Nội dung cần kiểm tra').inputValue(), 'Pricing claim needs another review.');
    await page.evaluate(() => window.restoreVideoStorage());
    await page.getByRole('button', { name: 'Gửi báo sai' }).click();
    await page.getByText('Báo sai đã gửi;', { exact: false }).waitFor();
    await page.goto(base + '/admin/videos');
    await page.getByRole('link', { name: 'Notion: organize notes and work', exact: true }).waitFor();
    await page.goto(base + '/admin/videos/notion-workspace');
    assert.equal(await page.getByRole('button', { name: 'Từ chối video', exact: true }).count(), 0);
    await page.getByRole('button', { name: 'Giữ duyệt, đóng báo sai', exact: true }).click();
    await page.getByText('Video đã được xử lý.', { exact: false }).waitFor();
    const retained = await page.evaluate(() => JSON.parse(localStorage.getItem('reviewlab.video-qa.mock.v1')).assets.find(a => a.review.id === 'notion-workspace'));
    for (const field of ['firstApprovedAt', 'reviewedAt', 'reviewedBy', 'caption', 'review', 'checklist', 'knowledgeVersion']) assert.deepEqual(retained[field], approval[field], `${field} stays locked after closing a report`);
    assert.equal(retained.status, 'approved'); assert.equal(retained.flaggedAt, null);
    await page.goto(base + '/merchant/library/notion-workspace');
    await page.getByRole('button', {name:'Báo sai video',exact:true}).click();
    await page.getByLabel('Nội dung cần kiểm tra').fill('Price still needs correction.');
    await page.getByRole('button', { name: 'Gửi báo sai' }).click();
    await page.getByText('Báo sai đã gửi;', { exact: false }).waitFor();
    await page.goto(base + '/admin/videos/notion-workspace');
    assert.ok(await page.getByRole('button', { name: 'Lưu trữ video', exact: true }).isDisabled());
    await page.getByRole('checkbox').first().uncheck();
    await page.getByLabel('Lý do lưu trữ', { exact: true }).fill('Price in the sample caption needs correction.');
    await page.getByRole('button', { name: 'Lưu trữ video', exact: true }).click();
    await page.getByText('Lý do lưu trữ: Price in the sample caption needs correction.').waitFor();
    await page.reload();
    await page.getByText('Video đã lưu trữ, không thể duyệt lại.', { exact: false }).waitFor();
    const archived = await page.evaluate(() => JSON.parse(localStorage.getItem('reviewlab.video-qa.mock.v1')).assets.find(a => a.review.id === 'notion-workspace'));
    assert.equal(archived.status, 'archived'); assert.equal(archived.flaggedAt, null);
    for (const field of ['firstApprovedAt', 'reviewedAt', 'reviewedBy', 'caption', 'review', 'checklist', 'knowledgeVersion']) assert.deepEqual(archived[field], approval[field], `${field} stays locked after archive`);
    assert.equal(await page.getByRole('button', { name: 'Duyệt video', exact: true }).count(), 0);
    await page.goto(base + '/merchant/library');
    await page.waitForFunction(() => document.querySelectorAll('.asset-card').length === 1);
    await page.goto(base + '/merchant/library/notion-workspace');
    await page.getByText('Video đã lưu trữ, không thể tải để phát hành mới.').waitFor();
    assert.equal(await page.getByRole('link', { name: 'Tải video demo', exact: true }).count(), 0);

    await page.goto(base + '/merchant/onboarding');
    await page.getByLabel('Website URL').fill('https://portal.example/tool');
    await page.getByLabel('Merchant affiliate URL').fill('https://portal.example/?ref=merchant');
    await page.getByRole('button', { name: 'Bắt đầu phân tích', exact: true }).click();
    await page.getByRole('button', { name: 'Bước tiếp theo (mock)', exact: true }).click();
    await page.getByRole('button', { name: 'Bước tiếp theo (mock)', exact: true }).click();
    await page.getByRole('button', { name: 'Hoàn tất và review PKB', exact: true }).click();
    await page.waitForURL('**/merchant/products/*');
    await page.getByRole('button', { name: 'Gửi review', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Gửi review', exact: true }).click();
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: 'Merchant duyệt PKB', exact: true }).click();
    await page.getByRole('link', { name: 'Mở Content Factory' }).click();
    await page.waitForURL('**/merchant/content');
    await page.getByLabel('Sản phẩm', { exact: true }).selectOption({ label: 'portal.example' });
    await page.getByRole('button', { name: 'Tạo template', exact: true }).click();
    await page.getByRole('textbox', { name: 'Chỉnh sửa Kịch bản' }).waitFor();
    assert.match(await page.getByRole('link', { name: 'Review PKB' }).getAttribute('href'), /^\/merchant\/products\//);

    // Separate clean context for stable screenshots of all five requested screens.
    const visuals = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const preview = await visuals.newPage();
    const screens = [['merchant','/merchant'], ['onboarding','/merchant/onboarding'], ['pkb','/merchant/products/gamma'], ['library','/merchant/library'], ['admin-qa','/admin/videos'], ['admin-detail','/admin/videos/notion-workspace']];
    for (const [name, route] of screens) {
      await preview.goto(base + route); await preview.locator('.workspace-footer').waitFor();
      await preview.waitForTimeout(250);
      await preview.evaluate(() => document.fonts.ready);
      await preview.waitForFunction(() => !document.querySelector('video') || document.querySelector('video').readyState >= 4);
      await preview.screenshot({ path: path.join(output, `${name}-desktop.png`), fullPage: true });
    }
    for (const width of [390, 320]) {
      await preview.setViewportSize({ width, height: 844 });
      for (const [name, route] of screens) {
        await preview.goto(base + route); await preview.waitForTimeout(200);
        await preview.evaluate(() => document.fonts.ready);
        await preview.waitForFunction(() => !document.querySelector('video') || document.querySelector('video').readyState >= 4);
        assert.ok(await preview.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${route} has no overflow at ${width}px`);
        await preview.screenshot({ path: path.join(output, `${name}-${width}.png`), fullPage: true });
      }
      await preview.getByRole('button', { name: 'Mở điều hướng', exact: true }).click();
      await preview.getByRole('link', { name: 'Chuyển sang Merchant' }).click();
      await preview.waitForURL('**/merchant');
      assert.ok(!(await preview.locator('#workspace-navigation').isVisible()));
    }
    assert.deepEqual(errors, [], 'no client rendering errors');
    // Legacy role-switch route must enforce the same PKB rejection permissions.
    const legacy = await browser.newPage();
    await legacy.goto(base + '/products/notion');
    await legacy.getByRole('button', { name: 'Gửi review', exact: true }).click();
    assert.equal(await legacy.getByRole('button', { name: 'Từ chối PKB', exact: true }).count(), 0);
    await legacy.getByLabel('Vai trò demo').selectOption('admin');
    await legacy.getByLabel('Lý do từ chối', { exact: true }).fill('Policy violation');
    await legacy.getByRole('button', { name: 'Từ chối PKB', exact: true }).click();
    await legacy.getByText('Lý do từ chối: Policy violation').waitFor();
    await legacy.close();
    console.log('PASS: role permissions including legacy routes, approval audit locks, report -> retain/archive, terminal archive, persistence/download guards, storage failure, five screens at desktop/390/320px.');
    await context.close(); await visuals.close();
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
