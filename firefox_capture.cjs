const fs = require('node:fs');
const path = require('node:path');
const {Builder, By} = require('selenium-webdriver');
const firefox = require('selenium-webdriver/firefox');
const {capturePreview} = require('./capture_preview.js');

function findFirefox(explicit = process.env.FIREFOX_PATH) {
  if (explicit) {
    if (!fs.existsSync(explicit)) throw new Error(`Firefox not found: ${explicit}`);
    return explicit;
  }
  return [
    '/Applications/Firefox.app/Contents/MacOS/firefox',
    '/usr/bin/firefox', '/usr/bin/firefox-esr', '/snap/bin/firefox',
    'C:\\Program Files\\Mozilla Firefox\\firefox.exe',
    'C:\\Program Files (x86)\\Mozilla Firefox\\firefox.exe',
  ].find((candidate) => fs.existsSync(candidate));
}

async function startFirefox(options = {}) {
  const settings = new firefox.Options().setPageLoadStrategy('eager')
    .addArguments('-no-remote', '-new-instance');
  if (options.headless !== false) settings.addArguments('-headless');
  const binary = findFirefox(options.firefox);
  if (binary) settings.setBinary(binary);
  let builder = new Builder().forBrowser('firefox').setFirefoxOptions(settings);
  const driverPath = options.geckodriver ?? process.env.GECKODRIVER_PATH;
  if (driverPath) builder = builder.setFirefoxService(new firefox.ServiceBuilder(path.resolve(driverPath)));
  // Otherwise Selenium Manager finds/downloads Mozilla's driver, using its normal cache.
  const driver = await builder.build();
  try {
    await driver.manage().setTimeouts({pageLoad: options.timeoutMs ?? 120000, script: options.timeoutMs ?? 120000});
    await driver.manage().window().setRect({width: 1440, height: 1100});
    return driver;
  } catch (err) { await driver.quit(); throw err; }
}

async function captureInFirefox(driver, url, options = {}) {
  await driver.get(url);
  const end = Date.now() + (options.viewerTimeoutMs ?? 15000);
  async function findViewer(depth = 0) {
    if ((await driver.findElements(By.css('#page-container .pf'))).length) return true;
    if (depth >= 3) return false;
    for (const frame of await driver.findElements(By.css('iframe, frame'))) {
      let entered = false;
      try {
        await driver.switchTo().frame(frame);
        entered = true;
        if (await findViewer(depth + 1)) return true;
      } catch (err) {
        if (!/stale|no such frame|browsing context.*discarded/i.test(err.message)) throw err;
      }
      if (entered) await driver.switchTo().parentFrame();
    }
    return false;
  }
  do {
    await driver.switchTo().defaultContent();
    if (await findViewer()) {
      const result = await driver.executeAsyncScript(`
        const options = arguments[0], done = arguments[arguments.length - 1];
        (${capturePreview.toString()})(options).then(
          capture => done({capture}), error => done({error: error.message})
        );
      `, {reveal: options.reveal ?? true, pageTimeoutMs: options.pageTimeoutMs ?? 8000, download: false, quiet: true});
      if (result.error) throw new Error(result.error);
      return result.capture;
    }
    const blocked = await driver.executeScript(`return /access blocked|verify you are human/i.test(document.body?.innerText || '')`);
    if (blocked) throw Object.assign(new Error('Studocu returned an access block or a human-verification page.'), {code: 'ACCESS_BLOCKED'});
    await new Promise((resolve) => setTimeout(resolve, 150));
  } while (Date.now() < end);
  throw Object.assign(new Error('No supported preview frames were supplied in Firefox.'), {code: 'DOCUMENT_UNAVAILABLE'});
}

module.exports = {findFirefox, startFirefox, captureInFirefox};
