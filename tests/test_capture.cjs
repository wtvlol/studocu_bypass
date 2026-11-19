const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright-core');
const {capturePreview} = require('../capture_preview.js');

const source = fs.readFileSync(path.join(__dirname, '..', 'capture_preview.js'), 'utf8');
const css = `
  .blurred { filter: blur(6px) !important; }
  .pc { display: none; }
  .text { transform: scale(0.8); position: absolute; left: 15px; }
`;
let browser;
before(async () => {
  const executablePath = process.env.CHROME_PATH || [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
  ].find((p) => fs.existsSync(p));
  browser = await chromium.launch({executablePath, headless: true});
});
after(async () => { if (browser) await browser.close(); });

async function capture(page, html, reveal = true) {
  await page.setContent(`<link rel="stylesheet" href="https://doc-assets.example.com/html/doc.css">
    <style>${css}</style>${html}`, {waitUntil: 'domcontentloaded'});
  await page.evaluate(() => {
    URL.createObjectURL = (blob) => { window.capturedBlob = blob; return 'blob:preview'; };
    HTMLAnchorElement.prototype.click = function () {};
  });
  await page.evaluate(capturePreview, {reveal, pageTimeoutMs: 300});
  return page.evaluate(async () => JSON.parse(await window.capturedBlob.text()));
}

test('reveals loaded pages, covers and ancestors; export remains unblurred with source CSS', async () => {
  const page = await browser.newPage();
  try {
    const data = await capture(page, `
      <main class="blurred" style="visibility:hidden;opacity:0">
        <div id="page-container"><div class="pf w0 h0">
          <div class="pc blurred"><span class="text blurred">Question 1</span></div>
          <div id="cover">Subscribe</div>
        </div></div>
      </main><aside id="sidebar" class="blurred">Outside preview</aside>`);
    assert.equal(data.pages.length, 1);
    assert.deepEqual(data.skippedPages, []);
    assert.equal(data.revealedPreview, true);
    const visible = await page.evaluate(() => ({
      rootFilter: getComputedStyle(document.querySelector('main')).filter,
      rootOpacity: getComputedStyle(document.querySelector('main')).opacity,
      rootVisibility: getComputedStyle(document.querySelector('main')).visibility,
      cover: getComputedStyle(document.querySelector('#cover')).display,
      sidebar: getComputedStyle(document.querySelector('#sidebar')).filter,
    }));
    assert.deepEqual(visible, {
      rootFilter: 'none', rootOpacity: '1', rootVisibility: 'visible', cover: 'none', sidebar: 'blur(6px)',
    });
    assert.ok(!data.pages[0].html.includes('Subscribe'));
    await page.setContent(`<style>${css}</style>${data.pages[0].html}`);
    const restored = await page.evaluate(() => {
      const text = document.querySelector('.text');
      return {
        text: text.textContent, filter: getComputedStyle(text).filter,
        display: getComputedStyle(document.querySelector('.pc')).display,
        transform: getComputedStyle(text).transform, left: getComputedStyle(text).left,
      };
    });
    assert.deepEqual(restored, {
      text: 'Question 1', filter: 'none', display: 'block',
      transform: 'matrix(0.8, 0, 0, 0.8, 0, 0)', left: '15px',
    });
  } finally { await page.close(); }
});

test('standalone console snippet still downloads a capture', async () => {
  const page = await browser.newPage();
  try {
    await capture(page, '<div id="page-container"><div class="pf"><div class="pc">Snippet</div></div></div>');
    const data = await page.evaluate(source);
    assert.equal(data.pages[0].text, 'Snippet');
    assert.deepEqual(await page.evaluate(async () => JSON.parse(await window.capturedBlob.text())), data);
  } finally { await page.close(); }
});

test('preserves pages that are unloaded when scrolling to later pages', async () => {
  const page = await browser.newPage();
  try {
    const data = await capture(page, `<div id="page-container">
      <div id="first" class="pf"><div class="pc"><div class="t">First line</div></div></div>
      <div id="second" class="pf"><div class="pc">Second</div></div></div>
      <script>
        document.querySelector('#second').scrollIntoView = function () {
          document.querySelector('#first').innerHTML = '';
        };
      </script>`);
    assert.deepEqual(data.pages.map((p) => p.text), ['First line', 'Second']);
    assert.deepEqual(data.skippedPages, []);
  } finally { await page.close(); }
});

test('captures lazy-loaded content and reports genuinely missing pages', async () => {
  const page = await browser.newPage();
  try {
    const data = await capture(page, `<div id="page-container">
      <div id="lazy" class="pf w1 h1"></div><div class="pf w0 h0"></div></div>
      <script>
        document.querySelector('#lazy').scrollIntoView = function () {
          setTimeout(() => { this.innerHTML = '<div class="pc blurred">Late page</div>'; }, 30);
        };
      </script>`);
    assert.equal(data.totalPages, 2);
    assert.equal(data.pages[0].number, 1);
    assert.equal(data.pages[0].className, 'pf w1 h1');
    assert.match(data.pages[0].html, /Late page/);
    assert.deepEqual(data.skippedPages, [{number: 2, reason: 'not loaded'}]);
  } finally { await page.close(); }
});

test('readable-only capture preserves blur and reports skipped pages', async () => {
  const page = await browser.newPage();
  try {
    const data = await capture(page, `<div id="page-container">
      <div class="pf"><div class="pc" style="display:block">Readable</div></div>
      <div class="pf blurred"><div class="pc" style="display:block">Blurred</div></div>
      </div>`, false);
    assert.equal(data.pages.length, 1);
    assert.equal(data.revealedPreview, false);
    assert.deepEqual(data.skippedPages, [{number: 2, reason: 'blurred'}]);
    assert.equal(await page.locator('#preview-unblur-style').count(), 0);
    assert.equal(await page.locator('.blurred').getAttribute('style'), null);
  } finally { await page.close(); }
});
