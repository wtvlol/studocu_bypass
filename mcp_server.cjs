const {McpServer} = require('@modelcontextprotocol/sdk/server/mcp.js');
const {StdioServerTransport} = require('@modelcontextprotocol/sdk/server/stdio.js');
const {z} = require('zod');
const {captureDocument, validateUrl} = require('./agent_tool.cjs');
const {capturePreview} = require('./capture_preview.js');

function captureScript(options = {}) {
  return `(async () => {
    if (!/(^|\\.)studocu\\.com$/.test(location.hostname)) throw new Error('Open a Studocu document first.');
    return await (${capturePreview.toString()})(${JSON.stringify({download: false, quiet: true, ...options})});
  })()`;
}

function createServer(capture = captureDocument) {
  const server = new McpServer({name: 'studocu-preview', version: '1.0.0'});
  server.registerTool('studocu_get_capture_script', {
    title: 'Get a capture script for an existing Studocu tab',
    description: 'Return JavaScript to reveal and capture loaded preview content in a Studocu tab already '
      + 'open in the caller\'s browser. Useful when isolated Chrome is blocked. This tool does not execute '
      + 'the script: await it using your browser tool and save the returned format-2 capture JSON.',
    inputSchema: {
      url: z.string().url().describe('Studocu document URL; sid is removed from the returned URL'),
      reveal: z.boolean().default(true),
      pageTimeoutMs: z.number().int().min(1).max(60000).default(8000),
    },
    annotations: {readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false},
  }, async ({url, ...options}) => {
    const result = {
      url: validateUrl(url),
      script: captureScript(options),
      usage: 'Open the returned cleaned URL first, then await this JavaScript expression in that tab. '
        + 'It returns the capture object; '
        + 'save it as preview-export.json. It changes preview presentation but does not download a file.',
      coverage: 'loaded_preview_frames',
    };
    return {content: [{type: 'text', text: JSON.stringify(result)}], structuredContent: result};
  });
  server.registerTool('studocu_capture', {
    title: 'Reveal and capture a Studocu preview',
    description: 'Open a Studocu document in isolated Chrome, remove client-side CSS blur and sibling covers, '
      + 'and return extracted text, page coverage and saved capture/text/screenshot paths. '
      + 'Only browser-supplied preview content can be recovered. Captured means all observed preview frames, '
      + 'not proof of the full original document. Missing pages produce a partial or unavailable result.',
    inputSchema: {
      url: z.string().url().describe('HTTPS Studocu document URL'),
      reveal: z.boolean().default(true).describe('Reveal client-side blurred content'),
      timeoutMs: z.number().int().min(1).max(600000).default(120000),
      pageTimeoutMs: z.number().int().min(1).max(60000).default(8000),
      maxTextChars: z.number().int().min(0).max(100000).default(20000),
    },
    annotations: {readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true},
  }, async ({url, ...options}) => {
    try {
      const result = await capture(url, options);
      return {
        content: [{type: 'text', text: JSON.stringify(result)}],
        structuredContent: result, isError: result.status !== 'captured',
      };
    } catch (err) {
      const result = {status: 'unavailable', error: {code: err.code ?? 'CAPTURE_FAILED', message: err.message}};
      return {content: [{type: 'text', text: JSON.stringify(result)}], structuredContent: result, isError: true};
    }
  });
  return server;
}

async function startServer() {
  const server = createServer();
  await server.connect(new StdioServerTransport());
}

module.exports = {createServer, startServer, captureScript};
