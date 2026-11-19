const {test} = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const {findFirefox, startFirefox, captureInFirefox} = require('../firefox_capture.cjs');

test('Firefox captures an iframe viewer, reveals hidden pages and reports an access block', {
  skip: !process.env.GECKODRIVER_PATH || !findFirefox() ? 'set GECKODRIVER_PATH and install Firefox' : false,
}, async () => {
  const server = http.createServer((req, res) => {
    if (req.url === '/blocked') { res.writeHead(403, {'Content-Type': 'text/html'}); res.end('Access Blocked'); return; }
    if (req.url.endsWith('.css')) {
      res.writeHead(200, {'Content-Type': 'text/css'});
      res.end('.pc {filter:blur(6px)}'); return;
    }
    res.writeHead(200, {'Content-Type': 'text/html'});
    if (req.url === '/viewer') {
      res.end(`<title>Firefox fixture</title>
        <link rel="preload stylesheet" href="/html/doc-assets.fixture.css">
        <div id="page-container"><div class="pf w0 h0"><div class="pc">First page</div></div>
        <div class="page-content" style="display:none"><div class="pf w0 h0"><div class="pc">Hidden second page</div></div></div></div>`);
    } else res.end('<iframe src="/viewer"></iframe>');
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  let driver;
  try {
    driver = await startFirefox({timeoutMs: 15000});
    const capture = await captureInFirefox(driver, origin, {pageTimeoutMs: 100});
    assert.equal(capture.totalPages, 2);
    assert.deepEqual(capture.pages.map(p => p.text), ['First page', 'Hidden second page']);
    assert.deepEqual(capture.skippedPages, []);
    assert.equal(capture.stylesheets[0], origin + '/html/doc-assets.fixture.css');
    assert.equal(await driver.executeScript("return getComputedStyle(document.querySelector('.page-content')).display"), 'block');
    assert.deepEqual(await driver.executeScript("return [...document.querySelectorAll('.pc')].map(el => getComputedStyle(el).filter)"), ['none', 'none']);
    await assert.rejects(captureInFirefox(driver, origin + '/blocked'), {code: 'ACCESS_BLOCKED'});
  } finally {
    if (driver) await driver.quit();
    await new Promise(resolve => server.close(resolve));
  }
});
