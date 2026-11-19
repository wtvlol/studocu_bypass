# Studocu preview tools for agents

The CLI and MCP server share the same DOM capture implementation as
`capture_preview.js`. They reveal CSS-obscured content that the viewer supplies,
preserve selectable text and page HTML, and report frames that did not load.
They cannot recover server-withheld pages or reverse blur baked into an image.

## Install

Use Node.js 22+, run `npm ci` in this repository, and install Firefox. The tool
uses Mozilla geckodriver through Selenium; Selenium Manager finds or downloads
the driver on first use. To use an already installed driver, set
`GECKODRIVER_PATH` or pass `--geckodriver PATH`. Set `FIREFOX_PATH` if Firefox is
not in a standard location. Selenium's `SE_CACHE_PATH` and `SE_TIMEOUT`
environment variables can control the driver's cache directory and download
timeout.

Install Chrome/Chromium and Python for the existing PDF conversion pipeline.
Chrome is also an optional capture backend (`--browser chrome`, `CHROME_PATH`).

## CLI

```sh
node /absolute/path/studocu_bypass/studocu-agent.cjs capture \
  'https://www.studocu.com/sg/document/university/course/document/12345' \
  --output-dir ./output/agent
```

The command prints one JSON object to stdout. It starts isolated Firefox by
default, captures the document, saves artifacts and closes the browser. It does not use the
user's browser profile or existing cookies. `--headed` shows the isolated browser
during the operation; it closes when the capture finishes. Use `--browser firefox|chrome`,
`--firefox PATH`, `--geckodriver PATH`, `--chrome PATH`,
`--timeout-ms 120000`, `--page-timeout-ms 8000` or `--readable-only` as needed.
Run `node studocu-agent.cjs --help` for all CLI options.

Each call uses a separate `capture-*` folder, containing:

- `result.json`: the structured result, including failures.
- `preview-export.json`: format-2 capture compatible with `run.py`, when capture succeeds.
- `document.txt`: full extracted text, when capture succeeds.
- `preview.png`: viewport screenshot, when Chrome can produce one, including on failures.

Result fields include `status`, `browser`, `url`, `title`, `totalPages`, `capturedPages`,
`skippedPages`, `text`, `textTruncated`, `coverage` and absolute `artifacts` paths.
Unavailable results may instead contain an `error` with `code` and `message`.
Inline text defaults to 20,000 characters; `document.txt` contains the full text.
Text follows PDF text-layer order and may need interpretation for multi-column pages.

| Status | Exit code | Meaning |
|---|---|---|
| `captured` | 0 | Every observed preview frame was captured |
| `partial` | 2 | At least one observed frame was skipped |
| `unavailable` | 1 | No usable capture, or a navigation/browser failure |

`coverage: "loaded_preview_frames"` deliberately limits the claim: a successful
capture does not prove that the server supplied every page of the original
document. Image-only pages may have no extractable text. Review the capture and
compare the frame count with any known original page count.

To produce a PDF, run the existing pipeline on the returned capture path:

```sh
python3 run.py /absolute/path/to/capture-ABC123/preview-export.json
```

That build rejects skipped frames unless explicitly given `--allow-partial`.
The CLI does not fetch stylesheets/images into an offline cache; the Python PDF
step does that. A saved capture therefore still needs working asset URLs when
first converted to PDF.

## MCP

Launch the stdio server using the absolute script path; it works regardless of
the client's working directory. Clients that use an `mcpServers` JSON setting
can use:

```json
{
  "mcpServers": {
    "studocu-preview": {
      "command": "node",
      "args": ["/absolute/path/studocu_bypass/studocu-agent.cjs", "mcp"],
      "env": {
        "STUDOCU_OUTPUT_DIR": "/absolute/path/to/output/agent"
      }
    }
  }
}
```

Set `FIREFOX_PATH` and `GECKODRIVER_PATH` in `env` too if needed. Use the direct
`node` command for MCP so package-manager notices cannot pollute protocol stdout.

### `studocu_capture`

```json
{
  "url": "https://www.studocu.com/sg/document/university/course/document/12345",
  "browser": "firefox",
  "headless": true,
  "reveal": true,
  "timeoutMs": 120000,
  "pageTimeoutMs": 8000,
  "maxTextChars": 20000
}
```

Only `url` is required. Returns both a JSON text block and `structuredContent`
using the same result shape as the CLI. `isError` is true for partial and
unavailable results, while any successfully saved artifacts remain accessible.
The capture timeout covers navigation and page capture. Browser launch, initial
driver discovery/download and diagnostic screenshot/cleanup add time.
Set the MCP client's request timeout accordingly.

### `studocu_get_capture_script`

```json
{
  "url": "https://www.studocu.com/sg/document/university/course/document/12345?sid=example",
  "reveal": true,
  "pageTimeoutMs": 8000
}
```

Returns `url` with `sid` removed, plus a self-contained JavaScript `script`.
This tool does not control a browser. An agent with an existing browser tool
should open the cleaned URL first, await the script expression in that document
tab, and save the returned capture object as `preview-export.json`. This uses
the caller's already-open browser, and does not copy cookies or attach to a
remote-debugging endpoint. The expression reveals the preview but does not
trigger a download. For a manual console download, use `capture_preview.js`.

For an agent already using Playwright in its own application, the shared
function can also be imported directly:

```js
const {capturePreview} = require('/absolute/path/studocu_bypass/capture_preview.js');
const capture = await page.evaluate(capturePreview, {download: false, quiet: true});
```

Select the viewer iframe first if the document uses one. The CLI's
`captureInPage(page, url, options)` helper performs navigation and iframe discovery.

## URL identifiers

The CLI and `studocu_capture` remove all `sid` query parameters, including
duplicate or differently capitalized keys, **before navigation**. The
existing-tab helper returns the cleaned URL for the caller to open. The shared
browser capture also removes `sid` from its saved `pageUrl`. Other query
parameters and asset signatures are preserved.

This removes one URL identifier. It does not hide the IP address or browser
fingerprint, prevent server logging, or guarantee anonymity. Opening an original
URL containing `sid` before using the helper has already sent that identifier
to the site; cleaning the later capture cannot undo the earlier request.

## Verification and live test

The tests use actual headless Chrome with routed local fixture responses. They
cover CSS blur, sibling covers, layout preservation, lazy-loaded and virtualized
pages, iframe discovery, URL scrubbing before navigation, artifact output,
failure reporting, the console snippet and MCP client/server communication
(including a real stdio subprocess).

On 19 November 2026, the supplied GEA1000 document (ID `70292212`) returned HTTP
403 and an **Access Blocked** page in isolated Chrome and direct HTTP requests.
This was a server response, rather than a local sandbox network-denial error.

Isolated Firefox subsequently reached the same live document. Before capture,
the second page was under a `display:none` wrapper. After capture, both pages
were recovered, with no skipped frames and roughly 15,000 characters of text.
The actual CLI also succeeded in **headless Firefox**, with a fresh profile and
without copying existing cookies or changing automation-detection settings.
The live run exposed and fixed stylesheet discovery: Studocu used
`rel="preload stylesheet"`, which requires token matching (`[rel~="stylesheet"]`).

The captured pages were rebuilt as a two-page PDF and checked for selectable
text and page images. The document's original font URLs returned 404, so the
local verification PDF used installed Times/Cambria replacement fonts. Those
fonts and the recovered document are local ignored artifacts, not repository
content. Capture itself does not require the PDF step or replacement fonts.

These results establish a successful run for that document and environment;
other documents or later server responses may differ. The tool reports access
blocks explicitly and does not solve human-verification challenges.

The Firefox regression test uses a local iframe fixture with a hidden page and
a multi-token stylesheet link. Enable it by setting `GECKODRIVER_PATH` when
running `npm test`; the rest of the browser/MCP tests still use routed Chrome
fixtures. Live checks are manual and are not repeatedly requested by the test suite.
