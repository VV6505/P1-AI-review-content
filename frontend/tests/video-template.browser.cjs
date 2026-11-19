const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');
const base = process.env.TEST_BASE_URL || 'http://localhost:3000';
const output = path.resolve('test-results/video-template');
const ffmpeg = process.env.FFMPEG_BIN || 'D:/1.HKDN/previews/tooling/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe';
const fixture = () => JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/template-handoff.json'), 'utf8'));
(async () => {
  fs.mkdirSync(output, { recursive: true });
  const clip = path.join(output, 'synthetic-grid.mp4');
  if (!fs.existsSync(clip)) {
    const result = spawnSync(ffmpeg, ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=0x19394d:s=1920x1080:r=10:d=20,drawgrid=w=160:h=120:t=4:c=white@0.3', '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-g', '5', clip], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
  }
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
    const errors = [], requests = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => { if (/^https?:/.test(r.url()) && !r.url().startsWith(base)) requests.push(r.url()); });
    await page.goto(base + '/login');
    await page.getByLabel('Tài khoản', { exact: true }).fill('admin');
    await page.getByLabel('Mật khẩu', { exact: true }).fill('123456');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.waitForURL('**/admin/users');
    await page.goto(base + '/creator/create');
    await page.getByLabel('Link sản phẩm (bắt buộc)', { exact: true }).fill('https://gamma.app');
    await page.getByRole('button', { name: 'Xem mẫu tích hợp từ AI', exact: true }).click();
    const iframe = page.locator('iframe[title="Khung hình template"]');
    async function frame() { const f = await (await iframe.elementHandle()).contentFrame(); await f.waitForFunction(() => !!window.CreatorTemplate); return f; }
    async function seek(t) { return (await frame()).evaluate(t => window.CreatorTemplate.renderAt(t), t); }
    const reviewDiagnostics = [];
    let diagnostic = await seek(2);
    assert.equal(diagnostic.missingMedia,true);
    await page.locator('.template-handoff-details summary').click();
    assert.equal(await page.getByRole('button', { name: 'Xuất HTML cảnh', exact: true }).isDisabled(), true, 'missing media blocks export');
    // Fixture images are drawn by the test, not AI or product evidence.
    const images = await page.evaluate(() => ['BEFORE · FIXTURE', 'AFTER · FIXTURE', 'FOCUS · FIXTURE'].map((label, i) => { const c = document.createElement('canvas'); c.width = 1200; c.height = 800; const x = c.getContext('2d'); x.fillStyle = ['#284254', '#3c5040', '#573f38'][i]; x.fillRect(0, 0, 1200, 800); x.fillStyle = '#fff'; x.font = '48px Arial'; x.fillText(label, 100, 150); x.strokeStyle = '#fff'; x.lineWidth = 5; x.strokeRect(540, 280, 360, 240); return c.toDataURL('image/png').split(',')[1]; }));
    const ids = ['before', 'after', 'focus'];
    for (let i = 0; i < images.length; i++) { const file = path.join(output, `${ids[i]}.png`); fs.writeFileSync(file, Buffer.from(images[i], 'base64')); await page.getByLabel(`Asset fixture:${ids[i]}`, { exact: true }).setInputFiles(file); }
    await page.getByLabel('Asset fixture:clip', { exact: true }).setInputFiles(clip);
    for (const ratio of ['16:9', '9:16']) {
      await page.getByLabel('Tỷ lệ khung hình', { exact: true }).selectOption(ratio);
      for (const preset of ['cinematic', 'animation', 'vintage']) {
        await page.getByLabel('Template', { exact: true }).selectOption(preset);
        for (const [id, layout] of [['s01', 'feature_clip'], ['s02', 'steps'], ['s03', 'before_after'], ['s04', 'highlight_zoom']]) {
          await page.getByRole('button', { name: `${id} · ${layout}`, exact: true }).click();
          await (await frame()).locator(`[data-scene="${id}"]`).waitFor();
          diagnostic = await seek(2.6);
          reviewDiagnostics.push({ source: 'layout-fixture', ratio, preset, id, ...diagnostic });
          assert.equal(diagnostic.mediaReady, true, `${ratio}/${preset}/${layout}: media ready`);
          if(diagnostic.textOverflow.length) { console.log(await (await frame()).evaluate(()=>[...document.querySelectorAll('#root,.content,.comparison,.card,.picture,img,.caption')].map(n=>({cls:n.className,rect:n.getBoundingClientRect().toJSON(),scroll:[n.scrollWidth,n.scrollHeight],client:[n.clientWidth,n.clientHeight]})))); await iframe.screenshot({path:path.join(output,'overflow-debug.png')}); }
          assert.deepEqual(diagnostic.textOverflow, [], `${ratio}/${preset}/${layout}: no text overflow`);
          await iframe.screenshot({ path: path.join(output, `${layout}-${preset}-${ratio.replace(':', 'x')}.png`) });
        }
      }
    }
    // Import an actual M2 envelope with text that must remain inert in both live and exported HTML.
    const envelope = fixture('layout-review');
    envelope.presentation.scenes[0].duration_s = 6;
    envelope.presentation.scenes[0].note_claim_indices = [0];
    envelope.presentation.scenes[0].clip_parts = [{asset_id:'fixture:clip',start_s:1,end_s:2},{asset_id:'fixture:clip',start_s:9,end_s:11}];
    envelope.script.scenes[0].claims[0].text = 'Nội dung thử </script><script>window.pwned=1</script>';
    const input = path.join(output, 'm2-inert-text.json'); fs.writeFileSync(input, JSON.stringify(envelope));
    await page.getByLabel('Nạp gói M2', { exact: true }).setInputFiles(input);
    await page.getByRole('button', { name: /^s01 ·/ }).click();
    await (await frame()).locator('[data-scene="s01"]').waitFor();
    await seek(2);
    assert.equal(await (await frame()).evaluate(() => window.pwned), undefined);
    await page.getByLabel('Asset fixture:clip',{exact:true}).setInputFiles(clip);
    await seek(.5); assert.ok(Math.abs((await (await frame()).locator('video').evaluate(v=>v.currentTime))-1.5)<.04,'source speed is preserved');
    await seek(2); assert.ok(Math.abs((await (await frame()).locator('video').evaluate(v=>v.currentTime))-10)<.04,'second cut at source speed');
    await seek(5); assert.ok(Math.abs((await (await frame()).locator('video').evaluate(v=>v.currentTime))-10.999)<.04,'hold last frame without stretching');
    assert.ok((await (await frame()).locator('h1').textContent()).includes('</script>'));
    assert.ok((await (await frame()).locator('.notes').textContent()).includes('</script>'), 'feature notes are mapped from selected claims');
    await page.getByRole('button', { name: 's02 · steps', exact: true }).click();
    await (await frame()).locator('[data-scene="s02"]').waitFor();
    await seek(1);
    assert.deepEqual(await (await frame()).locator('.steps .card').evaluateAll(nodes=>nodes.map(n=>Number(n.style.opacity))), [1,0,0]);
    await seek(7);
    assert.deepEqual(await (await frame()).locator('.steps .card').evaluateAll(nodes=>nodes.map(n=>Number(n.style.opacity))), [1,1,1]);
    await seek(1);
    assert.deepEqual(await (await frame()).locator('.steps .card').evaluateAll(nodes=>nodes.map(n=>Number(n.style.opacity))), [1,0,0], 'backward seek resets motion');
    envelope.product_design = { product_id: envelope.script.product_id, source_url: envelope.source_url, background: '#ffffff', foreground: '#202020', accent: '#246235' };
    fs.writeFileSync(input, JSON.stringify(envelope));
    await page.getByLabel('Nạp gói M2', { exact: true }).setInputFiles(input);
    await page.getByRole('button', { name: /^s01 ·/ }).click();
    await seek(2);
    assert.equal(await (await frame()).locator('#root').evaluate(n => getComputedStyle(n).getPropertyValue('--accent').trim()), '#246235');
    const bad = structuredClone(envelope); bad.assets[0].product_id = 'another-product';
    const invalid = path.join(output, 'invalid-asset.json'); fs.writeFileSync(invalid, JSON.stringify(bad));
    await page.getByLabel('Nạp gói M2', { exact: true }).setInputFiles(invalid);
    await page.getByRole('alert').filter({ hasText: 'Asset thuộc sản phẩm khác' }).waitFor();
    // The previously valid project remains mounted after a bad import.
    assert.ok((await (await frame()).locator('h1').textContent()).includes('</script>'));
    await page.getByRole('button', {name:'Về mẫu bốn layout',exact:true}).click();
    await page.getByLabel('Asset fixture:clip', { exact: true }).setInputFiles(clip);
    await page.getByRole('button', { name: 's01 · feature_clip', exact: true }).click();
    await seek(2);
    const download = page.waitForEvent('download'); await page.getByRole('button', { name: 'Xuất HTML cảnh', exact: true }).click();
    const html = path.join(output, 'feature-clip-handoff.html'); await (await download).saveAs(html);
    assert.equal(fs.readFileSync(html, 'utf8'), await iframe.getAttribute('srcdoc'), 'export preserves the exact live scene document');
    const standalone = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
    await standalone.route('http**/*', route => route.abort());
    await standalone.goto(pathToFileURL(html).href);
    diagnostic = await standalone.evaluate(() => window.CreatorTemplate.renderAt(2));
    assert.equal(diagnostic.mediaReady, true);
    assert.deepEqual(diagnostic.textOverflow, []);
    assert.equal(await standalone.locator('[data-layout]').getAttribute('data-layout'), 'feature_clip');
    assert.equal(await standalone.evaluate(() => document.fonts.check('400 36px TemplateSans') && document.fonts.check('700 72px TemplateSans')), true);
    assert.ok(fs.readFileSync(html,'utf8').includes('SIL OPEN FONT LICENSE'), 'font license travels with export');
    const firstFrame = await standalone.screenshot();
    await standalone.evaluate(() => window.CreatorTemplate.renderAt(4));
    await standalone.evaluate(() => window.CreatorTemplate.renderAt(2));
    const repeatedFrame = await standalone.screenshot();
    fs.writeFileSync(path.join(output,'repeat-first.png'),firstFrame);
    fs.writeFileSync(path.join(output,'repeat-second.png'),repeatedFrame);
    assert.equal(repeatedFrame.equals(firstFrame), true, 'same timestamp produces same PNG after seeking backwards; see repeat-first/second.png');
    await standalone.screenshot({ path: path.join(output, 'offline-render-9x16.png') });
    if (process.env.RENDER_FIXTURE === '1') {
      for (const ratio of ['16:9','9:16']) {
        await page.getByLabel('Tỷ lệ khung hình', { exact: true }).selectOption(ratio);
        await (await frame()).waitForFunction(portrait => document.querySelector('#root').classList.contains('portrait') === portrait, ratio === '9:16');
        const exported = path.join(output, `feature-clip-${ratio.replace(':','x')}.html`);
        fs.writeFileSync(exported, await iframe.getAttribute('srcdoc'));
        await standalone.setViewportSize(ratio === '16:9' ? {width:1920,height:1080} : {width:1080,height:1920});
        await standalone.goto(pathToFileURL(exported).href);
        const frames = path.join(output, `render-${ratio.replace(':','x')}`); fs.mkdirSync(frames, { recursive: true });
        for (let i = 0; i < 120; i++) {
          const status = await standalone.evaluate(t => window.CreatorTemplate.renderAt(t), i / 30);
          assert.equal(status.mediaReady,true); assert.deepEqual(status.textOverflow,[]);
          await standalone.screenshot({ path: path.join(frames, `${String(i).padStart(4, '0')}.png`) });
        }
        const result = spawnSync(ffmpeg, ['-v', 'error', '-y', '-framerate', '30', '-i', path.join(frames, '%04d.png'), '-frames:v', '120', '-an', '-c:v', 'libx264', '-preset', 'fast', '-pix_fmt', 'yuv420p', path.join(output, `fixture-render-${ratio.replace(':','x')}-4s.mp4`)], { encoding: 'utf8' }); assert.equal(result.status, 0, result.stderr);
      }
    }
    for (const width of [390, 320]) { await page.setViewportSize({ width, height: 844 }); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `No horizontal overflow at ${width}`); await page.screenshot({ path: path.join(output, `creator-preview-${width}.png`), fullPage: true }); }
    assert.deepEqual(errors, []); assert.deepEqual(requests, []);
    fs.writeFileSync(path.join(output, 'diagnostics.json'), JSON.stringify(reviewDiagnostics, null, 2));
    console.log('PASS: M2 import, four FE layouts x three presets x two ratios, local media cuts, inert text, invalid import preservation, offline HTML renderer and mobile.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
