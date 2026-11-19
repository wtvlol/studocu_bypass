// Render the saved local HTML only; this does not control a signed-in browser.
const path = require('node:path');
const os = require('node:os');
let chromium;
try { ({chromium} = require('playwright-core')); }
catch {
  const bundled = process.env.CODEX_NODE_MODULES || path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
  ({chromium} = require(path.join(bundled, 'playwright-core')));
}
(async () => {
  const chrome = process.argv[4] || process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  const browser = await chromium.launch({executablePath:chrome, headless:true});
  try {
    const page = await browser.newPage();
    await page.goto(process.argv[2], {waitUntil:'load'});
    await page.evaluate(() => document.fonts.ready);
    await page.pdf({path:process.argv[3], printBackground:true, preferCSSPageSize:true});
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
