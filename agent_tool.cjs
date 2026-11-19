const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright-core');
const {capturePreview} = require('./capture_preview.js');

class CaptureError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}

function validateUrl(value) {
  let url;
  try { url = new URL(value); } catch { throw new CaptureError('INVALID_URL', 'Provide a Studocu document URL.'); }
  if (url.protocol !== 'https:' || !/(^|\.)studocu\.com$/.test(url.hostname)
      || !url.pathname.includes('/document/') || url.username || url.password || url.port) {
    throw new CaptureError('INVALID_URL', 'Expected an HTTPS Studocu document URL without credentials or a custom port.');
  }
  for (const key of [...url.searchParams.keys()]) {
    if (key.toLowerCase() === 'sid') url.searchParams.delete(key);
  }
  return url.href;
}

function findChrome(explicit = process.env.CHROME_PATH) {
  if (explicit) {
    if (!fs.existsSync(explicit)) throw new CaptureError('CHROME_NOT_FOUND', `Chrome not found: ${explicit}`);
    return explicit;
  }
  return [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  ].find((p) => fs.existsSync(p));
}

async function captureInPage(page, url, options = {}) {
  url = validateUrl(url);
  const response = await page.goto(url, {waitUntil: 'domcontentloaded', timeout: options.timeoutMs ?? 120000});
  if (response && response.status() >= 400) {
    throw new CaptureError('HTTP_ERROR', `The document returned HTTP ${response.status()}.`);
  }
  // The viewer may be in an iframe. Use DOM inspection rather than site internals.
  const end = Date.now() + (options.viewerTimeoutMs ?? 15000);
  do {
    for (const frame of page.frames()) {
      try {
        if (await frame.locator('#page-container .pf').count()) {
          return await frame.evaluate(capturePreview, {
            reveal: options.reveal ?? true, download: false, quiet: true,
            pageTimeoutMs: options.pageTimeoutMs ?? 8000,
          });
        }
      } catch (err) {
        // Retry frames detached during initial navigation, but retain real errors.
        if (!frame.isDetached() && !/context was destroyed/i.test(err.message)) throw err;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 150));
  } while (Date.now() < end);
  throw new CaptureError('DOCUMENT_UNAVAILABLE',
    'No supported preview frames were supplied. The page may require login, a challenge, or a different viewer.');
}

async function captureDocument(url, options = {}, launch = (opts) => chromium.launch(opts)) {
  url = validateUrl(url);
  const browserName = options.browser ?? 'firefox';
  if (!['firefox', 'chrome'].includes(browserName)) throw new CaptureError('INVALID_OPTIONS', 'browser must be firefox or chrome.');
  const timeoutMs = options.timeoutMs ?? 120000;
  for (const [key, value, max] of [
    ['timeoutMs', timeoutMs, 600000], ['pageTimeoutMs', options.pageTimeoutMs ?? 8000, 60000],
  ]) {
    if (!Number.isInteger(value) || value < 1 || value > max) {
      throw new CaptureError('INVALID_OPTIONS', `${key} must be an integer from 1 to ${max}.`);
    }
  }
  if (!Number.isInteger(options.maxTextChars ?? 20000) || (options.maxTextChars ?? 20000) < 0
      || (options.maxTextChars ?? 20000) > 100000) {
    throw new CaptureError('INVALID_OPTIONS', 'maxTextChars must be an integer from 0 to 100000.');
  }
  const outputRoot = path.resolve(options.outputDir ?? process.env.STUDOCU_OUTPUT_DIR ?? 'output/agent');
  await fsp.mkdir(outputRoot, {recursive: true});
  const directory = await fsp.mkdtemp(path.join(outputRoot, 'capture-'));
  const artifacts = {result: path.join(directory, 'result.json')};
  let browser;
  let driver;
  let page;
  let timer;
  let result;
  try {
    let captureWork;
    if (browserName === 'firefox') {
      const {startFirefox, captureInFirefox} = require('./firefox_capture.cjs');
      driver = await startFirefox({...options, timeoutMs});
      captureWork = captureInFirefox(driver, url, {...options, timeoutMs});
    } else {
      browser = await launch({
        executablePath: findChrome(options.chrome), headless: options.headless !== false,
        timeout: Math.min(timeoutMs, 30000),
      });
      const context = await browser.newContext({viewport: {width: 1440, height: 1000}, acceptDownloads: false});
      page = await context.newPage();
      captureWork = captureInPage(page, url, {...options, timeoutMs});
    }
    const capture = await Promise.race([
      captureWork,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new CaptureError('TIMEOUT', `Capture exceeded ${timeoutMs} ms.`)), timeoutMs);
      }),
    ]);
    clearTimeout(timer);
    const text = capture.pages.map((p) => `--- Page ${p.number} ---\n${p.text ?? ''}`).join('\n\n');
    artifacts.capture = path.join(directory, 'preview-export.json');
    artifacts.text = path.join(directory, 'document.txt');
    await fsp.writeFile(artifacts.capture, JSON.stringify(capture, null, 2));
    await fsp.writeFile(artifacts.text, text);
    const maxTextChars = options.maxTextChars ?? 20000;
    result = {
      status: !capture.pages.length ? 'unavailable' : capture.skippedPages.length ? 'partial' : 'captured',
      coverage: 'loaded_preview_frames', browser: browserName, url, title: capture.title,
      totalPages: capture.totalPages, capturedPages: capture.pages.length,
      skippedPages: capture.skippedPages, revealedPreview: capture.revealedPreview,
      text: text.slice(0, maxTextChars), textTruncated: text.length > maxTextChars, artifacts,
    };
  } catch (err) {
    result = {status: 'unavailable', browser: browserName, url, error: {code: err.code ?? 'CAPTURE_FAILED', message: err.message}, artifacts};
  } finally {
    clearTimeout(timer);
    if (page && !page.isClosed()) {
      // A screenshot records failures too; a screenshot failure must not hide the result.
      const screenshot = path.join(directory, 'preview.png');
      try { await page.screenshot({path: screenshot, timeout: 5000}); artifacts.screenshot = screenshot; } catch {}
    }
    if (browser) await browser.close();
    if (driver) {
      const screenshot = path.join(directory, 'preview.png');
      try { await fsp.writeFile(screenshot, await driver.takeScreenshot(), 'base64'); artifacts.screenshot = screenshot; } catch {}
      await driver.quit();
    }
  }
  await fsp.writeFile(artifacts.result, JSON.stringify(result, null, 2));
  return result;
}

module.exports = {CaptureError, validateUrl, findChrome, captureInPage, captureDocument};
