#!/usr/bin/env node
const {parseArgs} = require('node:util');
const {captureDocument} = require('./agent_tool.cjs');

const HELP = `Usage:
  node studocu-agent.cjs capture <studocu-url> [options]
  node studocu-agent.cjs mcp

Options for capture:
  --output-dir PATH       Artifact directory (default: output/agent)
  --timeout-ms N          Overall capture timeout (default: 120000)
  --page-timeout-ms N     Wait per missing page (default: 8000)
  --chrome PATH          Chrome executable (or CHROME_PATH)
  --readable-only        Capture without changing blur or visibility
  --headed               Show the isolated browser window

stdout: one JSON result; exit codes: 0 captured, 2 partial, 1 unavailable/error.
MCP uses stdio. Set STUDOCU_OUTPUT_DIR to choose its artifact directory.
Only content supplied to the browser can be revealed; server-withheld pages
and pre-blurred image pixels cannot be recovered.
`;

async function main() {
  if (process.argv[2] === 'mcp') {
    const {startServer} = require('./mcp_server.cjs');
    await startServer();
    return;
  }
  const {values, positionals} = parseArgs({
    allowPositionals: true,
    options: {
      help: {type: 'boolean', short: 'h'},
      'output-dir': {type: 'string'}, 'timeout-ms': {type: 'string'},
      'page-timeout-ms': {type: 'string'}, chrome: {type: 'string'},
      'readable-only': {type: 'boolean'}, headed: {type: 'boolean'},
    },
  });
  if (values.help) { process.stdout.write(HELP); return; }
  if (positionals[0] !== 'capture' || positionals.length !== 2) throw new Error(HELP);
  const result = await captureDocument(positionals[1], {
    outputDir: values['output-dir'], chrome: values.chrome,
    timeoutMs: values['timeout-ms'] === undefined ? undefined : Number(values['timeout-ms']),
    pageTimeoutMs: values['page-timeout-ms'] === undefined ? undefined : Number(values['page-timeout-ms']),
    reveal: !values['readable-only'], headless: !values.headed,
  });
  process.stdout.write(JSON.stringify(result) + '\n');
  process.exitCode = result.status === 'captured' ? 0 : result.status === 'partial' ? 2 : 1;
}

main().catch((err) => {
  process.stdout.write(JSON.stringify({status: 'unavailable', error: {
    code: err.code ?? 'INVALID_ARGUMENTS', message: err.message,
  }}) + '\n');
  process.exitCode = 1;
});
