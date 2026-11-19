// Run after pnpm build. Uses a local BE stub to verify the production BFF adapter.
const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { once } = require('node:events');

(async () => {
  const { demoReviews } = await import('../src/features/reviews/demo.ts');
  let mode = 'normal';
  const calls = [];
  const backend = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    calls.push({ path: url.pathname, query: url.searchParams.get('q'), auth: req.headers.authorization });
    res.setHeader('Content-Type', 'application/json');
    if (mode === 'failure') { res.writeHead(503); res.end('{"detail":"Unavailable"}'); return; }
    if (mode === 'unauthorized') { res.writeHead(401); res.end('{"detail":"Missing auth"}'); return; }
    if (mode === 'malformed') { res.end('{"reviews":[{}],"total":1}'); return; }
    if (url.pathname === '/search') { res.end(JSON.stringify({ reviews: [demoReviews[0]], total: 1 })); return; }
    if (url.pathname === '/reviews/' + demoReviews[0].id) { res.end(JSON.stringify(demoReviews[0])); return; }
    res.writeHead(404); res.end('{"detail":"Missing"}');
  });
  backend.listen(0, '127.0.0.1'); await once(backend, 'listening');
  const port = process.env.TEST_PROXY_PORT || '3002';
  const base = `http://127.0.0.1:${port}`;
  const app = spawn(process.execPath, [require.resolve('next/dist/bin/next'), 'start', '--port', port], {
    cwd: path.resolve(__dirname, '..'),
    env: { ...process.env, REVIEW_API_BASE_URL: `http://127.0.0.1:${backend.address().port}` },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let logs = ''; app.stdout.on('data', (data) => { logs += data; }); app.stderr.on('data', (data) => { logs += data; });
  try {
    let ready = false;
    for (let i = 0; i < 50; i++) {
      try { if ((await fetch(base + '/search')).ok) { ready = true; break; } } catch {}
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    assert.ok(ready, 'production test server must start: ' + logs);
    const query = 'Notion & ghi chú';
    const response = await fetch(base + '/search?' + new URLSearchParams({ q: query }), { headers: { Authorization: 'Bearer local-test-token' } });
    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.source, 'backend'); assert.equal(result.total, 1);
    assert.equal(calls.at(-1).query, query); assert.equal(calls.at(-1).auth, 'Bearer local-test-token');
    const detail = await (await fetch(base + '/api/reviews/' + demoReviews[0].id)).json();
    assert.equal(detail.source, 'backend'); assert.equal(detail.review.id, demoReviews[0].id);
    assert.equal((await fetch(base + '/api/reviews/missing')).status, 404);
    mode = 'malformed'; assert.equal((await fetch(base + '/search?q=a')).status, 502);
    mode = 'failure'; assert.equal((await fetch(base + '/search?q=a')).status, 502);
    mode = 'unauthorized'; assert.equal((await fetch(base + '/search?q=a')).status, 401);
    console.log('PASS: upstream query/auth forwarding, validated backend results, detail lookup, 404/401/502, and no silent fallback to demo on failure.');
  } finally {
    app.kill();
    await new Promise((resolve) => backend.close(resolve));
  }
})().catch((error) => { console.error(error); process.exit(1); });
