// Print a saved local HTML file to PDF with headless Chrome.
// Usage: node render_preview.cjs <file:// URL> <output.pdf> [chrome executable]
// This only opens the local file; it never controls a signed-in browser.
const fs = require('node:fs');
const path = require('node:path');

function loadPlaywright() {
  const candidates = ['playwright-core', 'playwright'];
  if (process.env.CODEX_NODE_MODULES) candidates.push(path.join(process.env.CODEX_NODE_MODULES, 'playwright-core'));
  for (const name of candidates) {
    try { return require(name); } catch {}
  }
  throw new Error('playwright-core is not installed. Run `npm install` in this folder.');
}

function findChrome(explicit) {
  const candidates = [
    explicit,
    process.env.CHROME_PATH,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  ].filter(Boolean);
  if (explicit && !fs.existsSync(explicit)) throw new Error(`Chrome not found at ${explicit}`);
  return candidates.find((p) => fs.existsSync(p)); // undefined → Playwright's own Chromium, if installed
}

(async () => {
  const [url, out, chromeArg] = process.argv.slice(2);
  if (!url || !out) {
    console.error('Usage: node render_preview.cjs <file:// URL> <output.pdf> [chrome executable]');
    process.exit(2);
  }
  const {chromium} = loadPlaywright();
  const executablePath = findChrome(chromeArg);
  let browser;
  try {
    browser = await chromium.launch({executablePath, headless: true});
  } catch (e) {
    throw new Error('Could not start Chrome. Install Google Chrome, set CHROME_PATH, or pass --chrome.\n' + e.message);
  }
  try {
    const page = await browser.newPage();
    await page.goto(url, {waitUntil: 'load'});
    const broken = await page.evaluate(async () => {
      await document.fonts.ready;
      const imgs = [...document.images];
      await Promise.all(imgs.map((img) => img.decode().catch(() => {})));
      return imgs.filter((img) => !img.complete || img.naturalWidth === 0).map((img) => img.src);
    });
    if (broken.length) throw new Error(`${broken.length} image(s) failed to load, e.g. ${broken[0]}`);
    await page.pdf({path: out, printBackground: true, preferCSSPageSize: true});
  } finally {
    await browser.close();
  }
})().catch((e) => { console.error(e.message || e); process.exit(1); });
