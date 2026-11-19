const {test} = require('node:test');
const assert = require('node:assert/strict');
const fsp = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const {chromium} = require('playwright-core');
const {Client} = require('@modelcontextprotocol/sdk/client/index.js');
const {InMemoryTransport} = require('@modelcontextprotocol/sdk/inMemory.js');
const {StdioClientTransport} = require('@modelcontextprotocol/sdk/client/stdio.js');
const {validateUrl, findChrome, captureDocument} = require('../agent_tool.cjs');
const {createServer, captureScript} = require('../mcp_server.cjs');

const URL = 'https://www.studocu.com/sg/document/university/course/paper/12345';
const cli = path.join(__dirname, '..', 'studocu-agent.cjs');

test('rejects non-Studocu URLs and malformed options before browser launch', async () => {
  for (const url of ['file:///tmp/a', 'http://www.studocu.com/document/a', 'https://studocu.com.evil.org/document/a',
    'https://evil.org/document/a', 'https://user:password@studocu.com/document/a', 'https://studocu.com:999/document/a']) {
    assert.throws(() => validateUrl(url), {code: 'INVALID_URL'});
  }
  assert.equal(validateUrl(URL), URL);
  assert.equal(validateUrl(URL + '?sid=private&keep=yes&SID=other&sid=again'), URL + '?keep=yes');
  assert.equal(validateUrl(URL + '?sid=private'), URL);
  await assert.rejects(captureDocument(URL, {timeoutMs: NaN}), {code: 'INVALID_OPTIONS'});
});

async function fixtureCapture(html, options = {}, responseStatus = 200) {
  const directory = await fsp.mkdtemp(path.join(os.tmpdir(), 'studocu-test-'));
  const requests = [];
  const launch = async (opts) => {
    const browser = await chromium.launch({...opts, executablePath: findChrome()});
    const newContext = browser.newContext.bind(browser);
    browser.newContext = async (...args) => {
      const context = await newContext(...args);
      await context.route('**/*', (route) => {
        requests.push(route.request().url());
        const isCss = route.request().url().endsWith('.css');
        return route.fulfill({status: responseStatus, contentType: isCss ? 'text/css' : 'text/html',
          body: isCss ? '.pc{filter:blur(6px)}' : html});
      });
      return context;
    };
    return browser;
  };
  const result = await captureDocument(URL + '?sid=private', {
    outputDir: directory, timeoutMs: 10000, pageTimeoutMs: 100, ...options,
  }, launch);
  return {result, requests, cleanup: () => fsp.rm(directory, {recursive: true, force: true})};
}

const documentHtml = `<title>Fixture paper</title>
  <link rel="stylesheet" href="https://doc-assets.studocu.com/html/paper.css">
  <div id="page-container"><div class="pf w0 h0"><div class="pc"><div class="t">Known text</div></div></div>
  <div class="pf w0 h0"></div></div>`;

test('saves partial artifacts and exposes truncation without presenting a full document', async () => {
  const {result, requests, cleanup} = await fixtureCapture(documentHtml, {maxTextChars: 5});
  try {
    assert.equal(result.status, 'partial');
    assert.equal(requests[0], URL);
    assert.equal(result.url, URL);
    assert.equal(result.coverage, 'loaded_preview_frames');
    assert.equal(result.totalPages, 2);
    assert.equal(result.capturedPages, 1);
    assert.equal(result.text.length, 5);
    assert.equal(result.textTruncated, true);
    assert.deepEqual(result.skippedPages, [{number: 2, reason: 'not loaded'}]);
    const capture = JSON.parse(await fsp.readFile(result.artifacts.capture, 'utf8'));
    assert.equal(capture.pageUrl, URL);
    assert.equal(capture.pages[0].text, 'Known text');
    assert.match(await fsp.readFile(result.artifacts.text, 'utf8'), /Known text/);
    assert.deepEqual(JSON.parse(await fsp.readFile(result.artifacts.result, 'utf8')), result);
    assert.ok((await fsp.stat(result.artifacts.screenshot)).size > 0);
  } finally { await cleanup(); }
});

test('finds the viewer inside an iframe', async () => {
  const inner = documentHtml.replace('<div class="pf w0 h0"></div>', '');
  const {result, cleanup} = await fixtureCapture(`<iframe srcdoc="${inner.replaceAll('"', '&quot;')}"></iframe>`);
  try {
    assert.equal(result.status, 'captured');
    assert.equal(result.capturedPages, 1);
    assert.match(result.text, /Known text/);
  } finally { await cleanup(); }
});

test('writes unavailable diagnostics for an HTTP failure', async () => {
  const {result, cleanup} = await fixtureCapture('Blocked', {}, 403);
  try {
    assert.equal(result.status, 'unavailable');
    assert.equal(result.error.code, 'HTTP_ERROR');
    assert.ok(result.artifacts.screenshot);
    assert.equal(result.artifacts.capture, undefined);
  } finally { await cleanup(); }
});

test('CLI returns one parseable JSON error and a nonzero exit code', () => {
  const child = spawnSync(process.execPath, [cli, 'capture', 'https://example.com/document/a'], {encoding: 'utf8'});
  assert.equal(child.status, 1);
  assert.equal(JSON.parse(child.stdout).error.code, 'INVALID_URL');
});

test('MCP protocol exposes the schema, validates inputs and flags partial results', async () => {
  const server = createServer(async (url, options) => ({status: 'partial', url, reveal: options.reveal}));
  const client = new Client({name: 'test-client', version: '1.0.0'});
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  try {
    await server.connect(serverTransport);
    await client.connect(clientTransport);
    const {tools} = await client.listTools();
    assert.deepEqual(tools.map((tool) => tool.name), ['studocu_get_capture_script', 'studocu_capture']);
    assert.equal(tools[1].inputSchema.properties.url.type, 'string');
    const script = await client.callTool({name: 'studocu_get_capture_script', arguments: {url: URL + '?sid=private'}});
    assert.equal(script.structuredContent.url, URL);
    assert.ok(!script.structuredContent.script.includes('private'));
    const result = await client.callTool({name: 'studocu_capture', arguments: {url: URL}});
    assert.equal(result.isError, true);
    assert.equal(result.structuredContent.status, 'partial');
    assert.equal(result.structuredContent.reveal, true);
    const invalid = await client.callTool({name: 'studocu_capture', arguments: {url: URL, timeoutMs: -1}});
    assert.equal(invalid.isError, true);
  } finally { await client.close(); await server.close(); }
});

test('stdio server launches from another directory and keeps stdout valid MCP', async () => {
  const transport = new StdioClientTransport({command: process.execPath, args: [cli, 'mcp'], cwd: os.tmpdir()});
  const client = new Client({name: 'stdio-test', version: '1.0.0'});
  try {
    await client.connect(transport);
    assert.ok((await client.listTools()).tools.some((tool) => tool.name === 'studocu_capture'));
    const result = await client.callTool({name: 'studocu_capture', arguments: {url: 'https://example.com/document/a'}});
    assert.equal(result.isError, true);
    assert.equal(result.structuredContent.error.code, 'INVALID_URL');
  } finally { await client.close(); }
});

test('existing-tab script returns a capture without sid or a browser download', async () => {
  const browser = await chromium.launch({executablePath: findChrome(), headless: true});
  try {
    const page = await browser.newPage();
    await page.route('**/*', (route) => route.fulfill({contentType: 'text/html', body: documentHtml}));
    await page.goto(URL + '?sid=private&keep=yes');
    let downloads = 0;
    page.on('download', () => downloads++);
    const data = await page.evaluate(captureScript({pageTimeoutMs: 1}));
    assert.equal(data.pageUrl, URL + '?keep=yes');
    assert.equal(data.pages[0].text, 'Known text');
    assert.equal(downloads, 0);
  } finally { await browser.close(); }
});
