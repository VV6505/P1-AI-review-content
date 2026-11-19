const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:3000';
const output = process.env.TEST_OUTPUT_DIR || path.resolve('test-results/chat-studio');
(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base + '/login');
    await page.getByLabel('Tài khoản', { exact: true }).fill('admin');
    await page.getByLabel('Mật khẩu', { exact: true }).fill('123456');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.waitForURL('**/admin/users');
    await page.goto(base + '/creator/create');
    await page.getByLabel('Link sản phẩm (bắt buộc)', { exact: true }).fill('https://gamma.app');
    await page.getByLabel('Ghi chú', { exact: true }).fill('Nhấn mạnh khả năng tạo slide cho sinh viên.');
    assert.equal(await page.locator('.studio-page-heading').count(), 0);
    assert.equal(await page.locator('.project-sidebar nav a').count(), 0);
    assert.equal(await page.getByLabel('Tỷ lệ khung hình', { exact: true }).locator('option').count(), 11);
    await page.getByLabel('Tỷ lệ khung hình', { exact: true }).selectOption('4:5');
    await page.getByLabel('Số lượng', { exact: true }).fill('2');
    await page.getByLabel('Thời gian', { exact: true }).selectOption('30');
    assert.equal(await page.locator('.composer-strip-cost').innerText(), '900 token');
    assert.ok(await page.evaluate(() => {
      const top = document.querySelector('.composer-top-strip').getBoundingClientRect();
      const input = document.querySelector('.composer-input-surface').getBoundingClientRect();
      const bottom = document.querySelector('.composer-bottom-strip').getBoundingClientRect();
      return top.width < input.width && bottom.width < input.width && top.bottom <= input.top + 5 && bottom.top >= input.bottom - 5;
    }));
    assert.equal(await page.locator('.compact-build-controls select').count(), 1);
    await page.getByRole('button', { name: 'Nhập bằng giọng nói', exact: true }).click();
    await page.getByLabel('Ngôn ngữ nói', { exact: true }).selectOption('vi');
    await page.getByRole('button', { name: 'Thử đoạn nói mẫu', exact: true }).click();
    await page.getByRole('button', { name: 'Thêm vào ghi chú', exact: true }).click();
    assert.ok((await page.getByLabel('Ghi chú', { exact: true }).inputValue()).includes('ánh sáng tự nhiên'));
    await page.getByLabel('Ghi chú', { exact: true }).fill('Nhấn mạnh khả năng tạo slide cho sinh viên.');
    await page.getByLabel('Link sản phẩm (bắt buộc)', { exact: true }).fill('');
    assert.ok(await page.getByRole('button', { name: 'Chi tiết ↗', exact: true }).isDisabled());
    assert.ok(await page.getByRole('button', { name: 'Tạo video', exact: true }).isDisabled());
    await page.getByLabel('Link sản phẩm (bắt buộc)', { exact: true }).fill('invalid-link');
    assert.ok(await page.getByRole('button', { name: 'Chi tiết ↗', exact: true }).isDisabled());
    await page.getByLabel('Link sản phẩm (bắt buộc)', { exact: true }).fill('https://gamma.app');
    await page.screenshot({ path: path.join(output, 'creator-empty-light.png'), fullPage: true });
    await page.getByRole('button', { name: 'Chi tiết ↗', exact: true }).click();
    await page.getByRole('button', { name: 'Xác nhận sản phẩm', exact: true }).click();
    await page.getByRole('tab', { name: 'Cấu hình', exact: true }).click();
    await page.getByRole('button', { name: 'Tạo prompt từ link', exact: true }).click();
    assert.ok((await page.getByLabel('Prompt', { exact: true }).inputValue()).includes('Nhấn mạnh khả năng'));
    await page.getByLabel('Prompt', { exact: true }).fill('Prompt chỉnh tay cho dự án Gamma.');
    await page.getByRole('button', { name: 'Xong', exact: true }).click();
    await page.getByRole('button', { name: 'Tạo video', exact: true }).click();
    await page.waitForURL('**/creator/project/*');
    await page.locator('.conversation-turn').waitFor();
    const projectUrl = page.url();
    assert.equal(await page.locator('.result-videos video').count(), 2);
    assert.equal(await page.locator('.project-list button').count(), 1);
    let state = await page.evaluate(() => JSON.parse(localStorage.getItem('reviewlab.studio.v1')));
    assert.equal(state.users.find(u => u.id === 'demo').tokens, 2300);
    assert.equal(state.requests[0].notes, 'Nhấn mạnh khả năng tạo slide cho sinh viên.');
    assert.equal(state.requests[0].ratio, '4:5');
    await page.getByLabel('Thời gian', { exact: true }).selectOption('15');
    await page.getByRole('button', { name: 'Tạo video', exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll('.conversation-turn').length === 2);
    assert.equal(page.url(), projectUrl);
    assert.equal(await page.locator('.project-list button').count(), 1);
    await page.screenshot({ path: path.join(output, 'creator-project-light.png'), fullPage: true });
    await page.getByRole('button', { name: 'Tạo dự án mới', exact: true }).click();
    await page.waitForURL('**/creator/create');
    await page.waitForFunction(() => document.querySelector('#source-url').value === '');
    assert.equal(await page.getByLabel('Ghi chú', { exact: true }).inputValue(), '');
    await page.locator('.project-list button').click();
    await page.waitForURL('**/creator/project/*');
    await page.reload();
    await page.waitForFunction(() => document.querySelectorAll('.conversation-turn').length === 2);
    assert.equal(await page.getByLabel('Tỷ lệ khung hình', { exact: true }).inputValue(), '4:5');
    await page.getByRole('button', { name: 'Cài đặt tài khoản', exact: true }).click();
    await page.getByRole('button', { name: 'English', exact: true }).click();
    await page.getByRole('button', { name: 'Dark', exact: true }).click();
    await page.getByRole('button', { name: 'List', exact: true }).click();
    await page.getByRole('button', { name: 'Close', exact: true }).click();
    // Native select menus must not pair a light OS popup with inherited light text.
    const dropdownColors = await page.locator('.chat-composer select').evaluateAll(selects => selects.map(select => {
      const style = getComputedStyle(select);
      return { label: select.getAttribute('aria-label'), scheme: style.colorScheme, options: [...select.options].map(option => ({ background: getComputedStyle(option).backgroundColor, color: getComputedStyle(option).color })) };
    }));
    assert.equal(dropdownColors.length, 4);
    for (const dropdown of dropdownColors) {
      assert.equal(dropdown.scheme, 'dark', `${dropdown.label}: native popup follows dark mode`);
      for (const option of dropdown.options) {
        assert.notEqual(option.background, 'rgba(0, 0, 0, 0)', `${dropdown.label}: option has an explicit background`);
        assert.notEqual(option.background, option.color, `${dropdown.label}: option text is visible`);
      }
    }
    await page.getByRole('combobox', { name: 'Aspect ratio', exact: true }).click();
    await page.mouse.move(1400, 850);
    await page.screenshot({ path: path.join(output, 'creator-ratio-dropdown-dark.png') });
    await page.keyboard.press('Escape');
    await page.locator('.video-view-list').first().waitFor();
    await page.getByRole('button', { name: 'Hide sidebar', exact: true }).click();
    await page.reload();
    await page.getByRole('button', { name: 'Show sidebar', exact: true }).waitFor();
    await page.locator('.video-view-list').first().waitFor();
    await page.getByRole('button', { name: 'Show sidebar', exact: true }).click();
    await page.getByRole('searchbox', { name: 'Search projects and videos', exact: true }).fill('gamma');
    const searchResult = page.getByRole('region', { name: 'Search results', exact: true }).getByRole('button', { name: /^gamma\.app/ });
    await searchResult.waitFor();
    const assertDarkSearch = async phase => {
      const colors = await page.locator('.navigation-search').evaluate(search => {
        const input = search.querySelector('input');
        const row = search.querySelector('.navigation-search-results > button');
        const fieldStyle = getComputedStyle(input);
        const rowStyle = getComputedStyle(row);
        // An inset shadow covers Chrome's native autofill background.
        const fieldBackground = fieldStyle.boxShadow.includes('inset') ? fieldStyle.boxShadow.match(/rgba?\([^)]+\)/)?.[0] : fieldStyle.backgroundColor;
        const brightness = color => {
          const channels = color.match(/[\d.]+/g).slice(0, 3).map(Number);
          return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2];
        };
        return { fieldBackground: brightness(fieldBackground), fieldText: brightness(fieldStyle.webkitTextFillColor), rowBackground: brightness(rowStyle.backgroundColor), rowText: brightness(getComputedStyle(row.querySelector('strong')).color) };
      });
      assert.ok(colors.fieldBackground < 80 && colors.rowBackground < 80, `Search retains dark backgrounds: ${phase}`);
      assert.ok(colors.fieldText > 200 && colors.rowText > 200, `Search text stays visible: ${phase}`);
    };
    await searchResult.hover();
    await assertDarkSearch('hover');
    await page.mouse.move(1400, 850);
    await assertDarkSearch('pointer outside');
    const searchSession = await context.newCDPSession(page);
    await searchSession.send('DOM.enable');
    await searchSession.send('CSS.enable');
    const { root: searchDocument } = await searchSession.send('DOM.getDocument');
    const { nodeId: searchInputId } = await searchSession.send('DOM.querySelector', { nodeId: searchDocument.nodeId, selector: '.navigation-search input' });
    await searchSession.send('CSS.forcePseudoState', { nodeId: searchInputId, forcedPseudoClasses: ['autofill'] });
    await searchResult.hover();
    await assertDarkSearch('Chrome autofill with pointer inside');
    await page.mouse.move(1400, 850);
    await assertDarkSearch('Chrome autofill with pointer outside');
    await page.screenshot({ path: path.join(output, 'creator-search-dark-autofill.png') });
    await searchSession.send('CSS.forcePseudoState', { nodeId: searchInputId, forcedPseudoClasses: [] });
    await searchSession.detach();
    await searchResult.click();
    assert.equal(page.url(), projectUrl);
    await page.screenshot({ path: path.join(output, 'creator-project-dark-en.png'), fullPage: true });
    await page.goto(base + '/admin/pkb');
    await page.getByLabel('Search PKB', { exact: true }).waitFor();
    assert.equal(await page.locator('.studio-page-heading').count(), 0);
    await page.screenshot({ path: path.join(output, 'admin-pkb-dark-en.png'), fullPage: true });
    await page.getByRole('link', { name: 'View details', exact: true }).first().click();
    await page.locator('.pkb-detail-bar').waitFor();
    assert.equal(await page.locator('.studio-page-heading').count(), 0);
    const detailUrl = page.url();
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      for (const url of [projectUrl, base + '/creator/create', base + '/admin/users', base + '/admin/tokens', base + '/admin/plans', base + '/admin/pkb', detailUrl]) {
        await page.goto(url);
        await page.waitForFunction(() => document.documentElement.lang === 'en');
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `No overflow: ${url} at ${width}`);
        assert.equal(await page.locator('.studio-page-heading').count(), 0);
        await page.screenshot({ path: path.join(output, `${new URL(url).pathname.replaceAll('/', '-')}-${width}.png`), fullPage: true });
      }
      await page.goto(projectUrl);
      await page.getByRole('button', { name: 'Show sidebar', exact: true }).click();
      await page.locator('.project-sidebar.sidebar-open').waitFor();
      await page.getByRole('button', { name: 'New project', exact: true }).click();
      await page.waitForURL('**/creator/create');
      await page.getByRole('button', { name: 'Account settings', exact: true }).click();
      await page.getByRole('dialog').waitFor();
      assert.ok(await page.evaluate(() => document.querySelector('dialog').getBoundingClientRect().right <= innerWidth));
      await page.keyboard.press('Escape');
    }
    assert.deepEqual(errors, []);
    console.log('PASS: compact configuration strips, required link, mock voice notes, Custom, 11 ratios, token estimate, project continuation, search, list view, sidebar persistence, settings, mobile 390/320.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
