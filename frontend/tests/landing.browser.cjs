const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.TEST_BASE_URL || 'http://localhost:3000';
const output = process.env.TEST_OUTPUT_DIR || path.resolve('test-results/landing');

async function chooseSetting(page, name) {
  await page.locator('.public-settings-trigger').click();
  await page.getByRole('menuitemradio', { name, exact: true }).click();
  await page.keyboard.press('Escape');
  await page.getByRole('menu').waitFor({ state: 'hidden' });
}

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base);
    await page.getByRole('heading', { level: 1, name: /Creative/ }).waitFor();
    await page.waitForFunction(() => { const image = document.querySelector('.showcase-product'); return image?.complete && image.naturalWidth > 0; });
    const header = page.locator('.public-header');
    const footer = page.locator('.landing-footer');
    await header.locator('.public-settings-trigger').click();
    assert.equal(await page.getByRole('dialog').count(), 0);
    assert.equal(await page.getByRole('menuitemradio', { name: 'Tiếng Việt', exact: true }).getAttribute('aria-checked'), 'true');
    await page.screenshot({ path: path.join(output, 'settings-desktop.png') });
    await page.keyboard.press('Escape');
    assert.ok(await header.locator('.public-settings-trigger').evaluate(element => element === document.activeElement));
    await header.locator('.public-settings-trigger').click();
    await page.locator('.showcase-copy h2').click();
    await page.getByRole('menu').waitFor({ state: 'hidden' });
    assert.deepEqual(await header.locator('.public-nav a').allTextContents(), ['Trang chủ', 'Sáng tạo', 'Bảng giá', 'Giới thiệu']);
    assert.deepEqual(await header.locator('.public-nav a').evaluateAll(links => links.map(link => link.getAttribute('href'))), ['/', '/creator/create', '/price', '/about']);
    await header.getByRole('link', { name: 'Bảng giá', exact: true }).click();
    await page.waitForURL('**/price');
    await page.getByRole('heading', { name: /Một không gian/ }).waitFor();
    assert.ok(await page.locator('#price').isVisible());
    assert.equal(await page.locator('.landing-price-card').count(), 3);
    assert.equal(await header.getByRole('link', { name: 'Bảng giá', exact: true }).getAttribute('aria-current'), 'page');
    await page.getByText('Các gói này đã mở bán chưa?', { exact: true }).click();
    assert.ok(await page.getByText(/Chưa\. Giá và token/).isVisible());
    await page.screenshot({ path: path.join(output, 'price-desktop-vi.png'), fullPage: true });
    await header.getByRole('link', { name: 'Giới thiệu', exact: true }).click();
    await page.waitForURL('**/about');
    assert.ok(await page.locator('#about').isVisible());
    assert.equal(await header.getByRole('link', { name: 'Giới thiệu', exact: true }).getAttribute('aria-current'), 'page');
    await page.waitForFunction(() => document.querySelector('.public-about-image')?.naturalWidth > 0);
    await page.screenshot({ path: path.join(output, 'about-desktop-vi.png'), fullPage: true });
    await header.getByRole('link', { name: 'Trang chủ', exact: true }).click();
    assert.equal(await footer.getByRole('link', { name: 'Crawl4AI', exact: true }).getAttribute('href'), 'https://github.com/unclecode/crawl4ai');
    await page.screenshot({ path: path.join(output, 'landing-desktop-vi.png'), fullPage: true });

    await page.getByRole('combobox', { name: 'Khung hình minh họa', exact: true }).selectOption('16:9');
    const landscape = await page.locator('.showcase-film').boundingBox();
    assert.ok(landscape.width > landscape.height);
    await page.getByRole('combobox', { name: 'Khung hình minh họa', exact: true }).selectOption('9:16');
    await page.waitForFunction(() => { const r = document.querySelector('.showcase-film').getBoundingClientRect(); return r.height > r.width; });
    await page.getByRole('combobox', { name: 'Phong cách minh họa', exact: true }).selectOption('cinema');
    assert.equal(await page.getByRole('combobox', { name: 'Phong cách minh họa', exact: true }).inputValue(), 'cinema');
    await page.getByRole('button', { name: 'Xem chuyển động minh họa' }).click();
    assert.equal(await page.getByRole('button', { name: 'Dừng chuyển động minh họa' }).getAttribute('aria-pressed'), 'true');
    assert.equal(await page.locator('.showcase-playback').count(), 0);
    await page.getByRole('button', { name: 'Dừng chuyển động minh họa' }).click();

    await chooseSetting(page, 'English');
    await page.getByRole('heading', { level: 2, name: 'Your product. Reimagined with AI.', exact: true }).waitFor();
    assert.deepEqual(await header.locator('.public-nav a').allTextContents(), ['Home', 'Create', 'Price', 'About']);
    assert.equal(await page.locator('html').getAttribute('lang'), 'en');
    await header.getByRole('link', { name: 'Price', exact: true }).click();
    await page.getByRole('heading', { level: 1, name: /One creative space/ }).waitFor();
    await header.getByRole('link', { name: 'About', exact: true }).click();
    await page.getByRole('heading', { level: 1, name: /Your imagination/ }).waitFor();
    await page.reload();
    await page.getByRole('heading', { level: 1, name: /Your imagination/ }).waitFor();
    await header.getByRole('link', { name: 'Home', exact: true }).click();
    await header.getByRole('link', { name: 'Sign in', exact: true }).click();
    await page.getByRole('heading', { level: 1, name: 'Welcome back' }).waitFor();
    assert.equal(await page.locator('.auth-card a[href="/credits"]').count(), 0);
    assert.equal(await header.count(), 0);
    assert.equal(await footer.count(), 0);
    await page.reload();
    await page.getByRole('heading', { level: 1, name: 'Welcome back' }).waitFor();
    await page.waitForFunction(() => !document.querySelector('fieldset').disabled);
    await page.waitForFunction(() => { const image = document.querySelector('.auth-illustration'); return image?.complete && image.naturalWidth > 0; });
    await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); window.scrollTo(0, 0); });
    await page.screenshot({ path: path.join(output, 'login-desktop-en.png'), fullPage: true });
    await page.locator('.auth-home').click();
    await chooseSetting(page, 'Tiếng Việt');
    await header.getByRole('link', { name: 'Đăng nhập', exact: true }).click();
    await page.getByLabel('Tài khoản', { exact: true }).fill('creator');
    await page.getByLabel('Mật khẩu', { exact: true }).fill('123456');
    await page.getByRole('button', { name: 'Hiện mật khẩu', exact: true }).click();
    assert.equal(await page.getByLabel('Mật khẩu', { exact: true }).getAttribute('type'), 'text');
    assert.equal(await page.getByLabel('Mật khẩu', { exact: true }).inputValue(), '123456');
    await page.getByRole('button', { name: 'Ẩn mật khẩu', exact: true }).click();
    assert.equal(await page.getByLabel('Mật khẩu', { exact: true }).getAttribute('type'), 'password');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.waitForURL('**/creator/create');
    await page.goto(base);

    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Landing overflow at ${width}`);
    }
    // A separate visitor checks navigation and auth pages without an active session.
    const visitor = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const mobile = await visitor.newPage();
    mobile.on('pageerror', error => errors.push(error.message));
    await mobile.goto(base);
    await mobile.getByRole('button', { name: 'Mở menu', exact: true }).click();
    await mobile.getByRole('navigation', { name: 'Điều hướng di động' }).getByRole('link', { name: 'Bảng giá' }).click();
    assert.equal(await mobile.getByRole('navigation', { name: 'Điều hướng di động' }).count(), 0);
    await mobile.getByRole('button', { name: 'Mở menu' }).click();
    await mobile.keyboard.press('Escape');
    assert.equal(await mobile.getByRole('button', { name: 'Mở menu' }).getAttribute('aria-expanded'), 'false');
    await mobile.goto(base);
    await mobile.screenshot({ path: path.join(output, 'landing-mobile-vi.png'), fullPage: true });
    await chooseSetting(mobile, 'English');
    await chooseSetting(mobile, 'Dark');
    await mobile.screenshot({ path: path.join(output, 'landing-mobile-dark-en.png'), fullPage: true });
    await mobile.getByRole('button', { name: 'Open menu' }).click();
    await mobile.getByRole('navigation', { name: 'Mobile navigation' }).getByRole('link', { name: 'Sign in', exact: true }).click();
    await mobile.getByRole('heading', { name: 'Welcome back' }).waitFor();
    for (const route of ['/login?next=%2Fcreator%2Fcreate', '/signup', '/credits', '/price', '/about']) {
      await mobile.goto(base + route);
      await mobile.waitForFunction(() => document.documentElement.lang === 'en' && document.documentElement.classList.contains('dark'));
      if (route.startsWith('/login') || route === '/signup') {
        assert.equal(await mobile.locator('.public-header, .landing-footer').count(), 0);
      }
      for (const width of [320, 390, 768, 1024]) {
        await mobile.setViewportSize({ width, height: 900 });
        assert.ok(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${route} overflow at ${width}`);
      }
      if (route === '/signup') {
        await mobile.setViewportSize({ width: 1440, height: 1000 });
        await mobile.screenshot({ path: path.join(output, 'signup-desktop-dark-en.png'), fullPage: true });
        await mobile.setViewportSize({ width: 390, height: 844 });
        await mobile.screenshot({ path: path.join(output, 'signup-mobile-dark-en.png'), fullPage: true });
      }
      if (route === '/price' || route === '/about') {
        await mobile.setViewportSize({ width: 390, height: 844 });
        await mobile.screenshot({ path: path.join(output, `${route.slice(1)}-mobile-dark-en.png`), fullPage: true });
        assert.equal(await mobile.locator('.public-header').count(), 1);
        assert.equal(await mobile.locator('.landing-footer').count(), 1);
      }
    }
    await mobile.setViewportSize({ width: 390, height: 844 });
    await mobile.goto(base + '/login');
    await mobile.getByRole('heading', { name: 'Welcome back' }).waitFor();
    await mobile.waitForFunction(() => !document.querySelector('fieldset').disabled && document.documentElement.classList.contains('dark'));
    await mobile.evaluate(() => window.scrollTo(0, 0));
    await mobile.screenshot({ path: path.join(output, 'login-mobile-dark-en.png'), fullPage: true });
    assert.deepEqual(errors, []);
    console.log('PASS: landing controls, Settings, VI/EN persistence, theme, mobile menu, footer attribution, standalone auth pages, demo login and responsive layouts.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
