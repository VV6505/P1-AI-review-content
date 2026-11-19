const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const base = process.env.TEST_BASE_URL || 'http://localhost:3000';

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    async function logout() {
      await page.getByRole('button', { name: 'Cài đặt tài khoản', exact: true }).click();
      await page.getByRole('button', { name: 'Đăng xuất', exact: true }).click();
      await page.waitForURL('**/login**');
    }
    async function login(identifier, password, path) {
      await page.getByLabel('Tài khoản', { exact: true }).fill(identifier);
      await page.getByLabel('Mật khẩu', { exact: true }).fill(password);
      await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
      await page.waitForURL(url => url.pathname === path);
      if (path.startsWith('/creator/')) await page.waitForFunction(() => document.querySelector('.chat-composer fieldset')?.disabled === false);
    }
    await page.goto(base + '/signup');
    await page.getByLabel('Họ và tên', { exact: true }).fill('Regression Creator');
    await page.getByLabel('Email', { exact: true }).fill('regression@example.com');
    await page.getByLabel('Mật khẩu', { exact: true }).fill('TestPass123');
    await page.getByLabel('Xác nhận mật khẩu', { exact: true }).fill('TestPass123');
    await page.getByRole('button', { name: 'Tạo tài khoản', exact: true }).click();
    await page.waitForURL('**/creator/create');
    await page.getByLabel('Link sản phẩm (bắt buộc)', { exact: true }).fill('https://gamma.app');
    assert.equal(await page.locator('.header-tokens').innerText(), '2.500 token');
    assert.equal(await page.getByRole('button', { name: 'Tạo video', exact: true }).isEnabled(), true);
    await logout();
    await login('admin', '123456', '/admin/users');
    const row = page.getByRole('row').filter({ hasText: 'regression@example.com' });
    await row.getByRole('button', { name: 'Chỉnh sửa', exact: true }).click();
    await page.getByLabel('Họ tên', { exact: true }).fill('Admin Edited Creator');
    await page.getByLabel('Email', { exact: true }).fill('edited@example.com');
    await page.getByRole('button', { name: 'Lưu thay đổi', exact: true }).click();
    await page.goto(base + '/admin/tokens');
    await page.getByRole('row').filter({ hasText: 'edited@example.com' }).getByRole('button', { name: 'Điều chỉnh', exact: true }).click();
    await page.getByLabel('Số token thay đổi', { exact: true }).fill('400');
    await page.getByLabel('Lý do', { exact: true }).fill('Regression credit');
    await page.getByRole('button', { name: 'Lưu điều chỉnh', exact: true }).click();
    await logout();
    await login('edited@example.com', 'TestPass123', '/creator/create');
    assert.equal(await page.locator('.header-user-name').innerText(), 'Admin Edited Creator');
    assert.equal(await page.locator('.header-tokens').innerText(), '2.900 token');
    await page.getByRole('button', { name: 'Chi tiết ↗', exact: true }).click();
    await page.getByRole('button', { name: 'Xác nhận sản phẩm', exact: true }).click();
    await page.getByRole('button', { name: 'Xong', exact: true }).click();
    await page.getByRole('button', { name: 'Tạo video', exact: true }).click();
    await page.getByRole('button', { name: 'Xác nhận và xem mẫu', exact: true }).click();
    await page.waitForURL('**/creator/project/*');
    await page.locator('.conversation-turn').waitFor();
    assert.equal(await page.locator('.header-tokens').innerText(), '2.270 token');
    await page.reload();
    await page.locator('.conversation-turn').waitFor();
    assert.equal(await page.locator('.header-user-name').innerText(), 'Admin Edited Creator');
    await logout();
    await login('admin', '123456', '/admin/users');
    const edited = page.getByRole('row').filter({ hasText: 'edited@example.com' });
    assert.match(await edited.innerText(), /Admin Edited Creator/);
    assert.match(await edited.innerText(), /2.270/);
    await page.goto(base + '/creator/create');
    assert.equal(await page.locator('.conversation-turn').count(), 0);
    assert.deepEqual(errors, []);
    console.log('PASS: welcome balance, Admin registration visibility, profile/email edits, token adjustments, spending, reload and project isolation.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
