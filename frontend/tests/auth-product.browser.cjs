const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:3000';
const output = process.env.TEST_OUTPUT_DIR || path.resolve('test-results/auth-product');

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base + '/creator/create');
    await page.waitForURL('**/login?**');
    assert.equal(await page.locator('.studio-sidebar').count(), 0);
    await page.screenshot({ path: path.join(output, 'login-desktop.png'), fullPage: true });
    await page.getByLabel('Tài khoản', { exact: true }).fill('creator');
    await page.getByLabel('Mật khẩu', { exact: true }).fill('WrongPassword');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Tài khoản hoặc mật khẩu chưa đúng' }).waitFor();

    await page.getByRole('link', { name: 'Đăng ký', exact: true }).click();
    await page.getByLabel('Họ và tên', { exact: true }).fill('Nguyễn Minh');
    await page.getByLabel('Email', { exact: true }).fill('minh@example.com');
    await page.getByLabel('Mật khẩu', { exact: true }).fill('DemoPass123');
    await page.getByLabel('Xác nhận mật khẩu', { exact: true }).fill('Different123');
    await page.getByRole('button', { name: 'Tạo tài khoản', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Mật khẩu xác nhận chưa khớp' }).waitFor();
    await page.getByLabel('Xác nhận mật khẩu', { exact: true }).fill('DemoPass123');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(output, 'signup-mobile.png'), fullPage: true });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.getByRole('button', { name: 'Tạo tài khoản', exact: true }).click();
    await page.waitForURL('**/creator/create');
    assert.equal(await page.evaluate(() => localStorage.getItem('reviewlab.mock-accounts.v1').includes('DemoPass123')), false);
    const accountId = await page.evaluate(() => localStorage.getItem('reviewlab.mock-session.v1'));
    await page.setViewportSize({ width: 1440, height: 1000 });

    await page.getByLabel('Link sản phẩm (bắt buộc)', { exact: true }).fill('https://gamma.app');
    await page.getByRole('button', { name: 'Chi tiết ↗', exact: true }).click();
    await page.getByRole('status').filter({ hasText: 'Đang thu thập nguồn' }).waitFor();
    assert.ok(await page.getByRole('tab', { name: 'Cấu hình', exact: true }).isDisabled());
    await page.screenshot({ path: path.join(output, 'product-processing.png'), fullPage: true });
    await page.getByRole('status').filter({ hasText: 'Đang chuẩn hóa thông tin' }).waitFor();
    await page.getByLabel('Tên sản phẩm', { exact: true }).waitFor();
    await page.getByLabel('Mô tả sản phẩm', { exact: true }).fill('');
    assert.ok(await page.getByRole('button', { name: 'Xác nhận sản phẩm', exact: true }).isDisabled());
    await page.getByLabel('Mô tả sản phẩm', { exact: true }).fill('Thông tin mẫu đã được kiểm tra.');
    await page.getByLabel('Nguồn thông tin', { exact: true }).fill('javascript:alert(1)');
    await page.getByRole('button', { name: 'Xác nhận sản phẩm', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Kiểm tra tên, mô tả' }).waitFor();
    await page.getByLabel('Nguồn thông tin', { exact: true }).fill('https://gamma.app');
    await page.screenshot({ path: path.join(output, 'product-review.png'), fullPage: true });
    await page.getByRole('button', { name: 'Xác nhận sản phẩm', exact: true }).click();
    assert.equal(await page.getByRole('tab', { name: 'Cấu hình', exact: true }).getAttribute('aria-selected'), 'true');
    await page.getByRole('button', { name: 'Xong', exact: true }).click();
    await page.reload();
    await page.getByRole('button', { name: 'Chi tiết ↗', exact: true }).click();
    assert.equal(await page.getByLabel('Mô tả sản phẩm', { exact: true }).inputValue(), 'Thông tin mẫu đã được kiểm tra.');
    assert.ok(await page.getByRole('button', { name: 'Xác nhận sản phẩm', exact: true }).isDisabled());
    await page.getByRole('button', { name: 'Đóng', exact: true }).click();

    // Closing a running preview must prevent stale results from replacing a new URL.
    await page.getByLabel('Link sản phẩm (bắt buộc)', { exact: true }).fill('https://example.com/item/one');
    await page.getByRole('button', { name: 'Chi tiết ↗', exact: true }).click();
    await page.getByRole('button', { name: 'Đóng', exact: true }).click();
    await page.getByLabel('Link sản phẩm (bắt buộc)', { exact: true }).fill('https://example.com/item/two');
    await page.getByRole('button', { name: 'Chi tiết ↗', exact: true }).click();
    await page.getByLabel('Tên sản phẩm', { exact: true }).waitFor();
    assert.equal(await page.locator('.product-review-source a').getAttribute('href'), 'https://example.com/item/two');
    await page.getByRole('button', { name: 'Đóng', exact: true }).click();

    await page.goto(base + '/admin/users');
    await page.getByRole('heading', { name: 'Dành cho Admin', exact: true }).waitFor();
    await page.getByRole('link', { name: 'Về dự án', exact: true }).click();
    await page.getByRole('button', { name: 'Cài đặt tài khoản', exact: true }).click();
    await page.getByRole('button', { name: 'Đăng xuất', exact: true }).click();
    await page.waitForURL(url => url.pathname === '/login');
    await page.getByRole('link', { name: 'Đăng ký', exact: true }).click();
    await page.getByLabel('Họ và tên', { exact: true }).fill('Duplicate');
    await page.getByLabel('Email', { exact: true }).fill('MINH@example.com');
    await page.getByLabel('Mật khẩu', { exact: true }).fill('DemoPass123');
    await page.getByLabel('Xác nhận mật khẩu', { exact: true }).fill('DemoPass123');
    await page.getByRole('button', { name: 'Tạo tài khoản', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Email này đã có tài khoản' }).waitFor();
    await page.locator('.auth-switch').getByRole('link', { name: 'Đăng nhập', exact: true }).click();
    await page.getByRole('heading', { name: 'Chào mừng trở lại', exact: true }).waitFor();
    await page.getByLabel('Tài khoản', { exact: true }).fill('creator');
    await page.getByLabel('Mật khẩu', { exact: true }).fill('123456');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.waitForURL('**/creator/create');
    assert.equal(await page.getByLabel('Link sản phẩm (bắt buộc)', { exact: true }).inputValue(), '');
    assert.ok(await page.evaluate(id => localStorage.getItem(`reviewlab.studio.v1.${id}`) !== null, accountId));

    // Login remains usable on small screens and respects saved preferences.
    await page.getByRole('button', { name: 'Cài đặt tài khoản', exact: true }).click();
    await page.getByRole('button', { name: 'English', exact: true }).click();
    await page.getByRole('button', { name: 'Dark', exact: true }).click();
    await page.getByRole('button', { name: 'Sign out', exact: true }).click();
    await page.waitForURL(url => url.pathname === '/login');
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      await page.getByRole('heading', { name: 'Welcome back', exact: true }).waitFor();
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: path.join(output, `login-dark-${width}.png`), fullPage: true });
    }
    assert.deepEqual(errors, []);
    console.log('PASS: mock signup/login/logout, wrong credentials, duplicate email, account isolation, processing stages, cancellation, review validation, saved confirmation, Creator/Admin preview, mobile and dark mode.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
