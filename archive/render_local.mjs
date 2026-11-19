import { chromium } from '/Users/keith/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core/index.mjs';
const browser = await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
try {
  const page = await browser.newPage();
  await page.goto(process.argv[2], {waitUntil:'load'});
  await page.evaluate(()=>document.fonts.ready);
  await page.pdf({path:process.argv[3],printBackground:true,preferCSSPageSize:true});
} finally { await browser.close(); }
