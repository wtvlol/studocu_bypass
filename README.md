# preview-pdf

Turn a document preview you can already read in your browser into a clean,
printable PDF. Optionally, also make a **questions-only practice copy** with the
worked solutions removed, for revision.

```
browser (readable preview) ──capture_preview.js──▶ preview-export.json
        ──run.py──▶ output/<name>/<name>.pdf
                    output/<name>/<name>_Questions_Only.pdf   (optional)
```

## What it does and doesn't do

It rebuilds the pages your browser has **already loaded and can show you**. It
uses the document's own stylesheet, fonts and images, so text stays selectable
and formulas stay sharp.

It does **not** sign in, read cookies, download the site's original file, guess
hidden endpoints, or remove blur and paywalls. A page that is blurred, hidden or
not loaded is left out of the export and reported. By default the build stops,
so you never mistake a partial paper for a complete one.

## Setup

Requires Python 3.10+, Node.js 18+, and Google Chrome (or Chromium).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm install
```

## Usage

1. Open the document in your browser and make sure you can read it.
2. Open DevTools → Console, then paste in the contents of [`capture_preview.js`](capture_preview.js).
   It scrolls through every page so each one loads, then downloads
   `preview-export.json`. It prints a line for each page and warns about any page
   it skipped.
3. Move the JSON into this folder and run:

```bash
python3 run.py preview-export.json
```

The result is written to `output/<Document_Title>/<Document_Title>.pdf`.

### Practice copy (answers removed)

Pick a preset, or give the markers directly:

```bash
python3 run.py preview-export.json --preset generic-qa --name MyPaper
```

```bash
python3 run.py preview-export.json --marker-regex "^(?:Answer|Solution)\b" --question-pattern "^Q\s*(\d+)\b"
```

This writes `MyPaper_With_Solutions.pdf`, `MyPaper_Questions_Only.pdf` and
`MyPaper_redaction_log.json`. Redaction **deletes** the text, image pixels and
vector graphics underneath; it doesn't just cover them with a box. The run fails
if any question heading disappears, if an answer marker survives, or if text in a
`--forbid-color` colour survives.

To check the detected regions before anything is removed, add `--dry-run`. It
writes PNG previews with the regions outlined in red.

### Presets

Presets live in [`presets/`](presets). Their keys are the CLI options, written
with underscores, and any flag you pass overrides the preset.

| Preset | For |
|---|---|
| `default` | Any document: PDF only |
| `generic-qa` | `1.` / `Q1` headings, answers starting with Solution / Answer / Explanation |
| `st2334` | ST2334 papers (`1. MULTIPLE…` headings, `SOLUTION` markers) |
| `gea1000` | GEA1000 sample: yellow answer highlights, red explanations, font repair. Run `python3 make_gea_fonts.py` first (needs Microsoft Word's fonts) |

To add your own, copy one, adjust the regexes, and pass `--preset path/to/mine.json`.

```json
{
  "description": "My course: answers start with 'Worked solution'",
  "extract":  { "clear_yellow_highlights": false },
  "practice": { "marker_regex": "^Worked solution\\b", "expected_questions": 20, "forbid_colors": ["c00000"] }
}
```

### Useful options

| Option | Purpose |
|---|---|
| `--allow-partial` | Build from the readable pages even if some were skipped |
| `--pages 1-5,8` | Only these captured pages |
| `--clear-yellow-highlights` | Whiten highlighter-yellow pixels in page images (`--highlight-min-rg`, `--highlight-blue-gap` tune it) |
| `--font-map map.json` | Replace dead font links with local font files |
| `--top-content 60` | Keep a running header above this y position (PDF points) on continuation pages |
| `--page-size a4\|letter\|source` | Page size of the final PDFs (default `a4`) |
| `--chrome PATH` / `CHROME_PATH` | Use a specific Chrome; otherwise it is auto-detected |

You can also run each step on its own:

```bash
python3 extract_preview.py --capture preview-export.json --output out.pdf
```

```bash
python3 remove_solutions.py out.pdf --marker Solution --output-dir output
```

## Repeatability

- Downloads are cached in `work/`, keyed by asset path, so a re-run is quick and
  works offline. Files are written atomically and retried on network errors.
- The signed asset links in a capture expire after a while. If you get an
  "HTTP 403" error, capture again.
- Every redaction is listed in the log JSON, so you can review it or compare two runs.

## Development

```bash
pip install -r requirements-dev.txt
```

```bash
ruff check . && pytest
```

The tests cover page ranges, capture loading (including refusing skipped pages),
page-size rules, font maps, highlight clearing, answer-region detection, and a
full redaction run on a generated PDF. When Node and Chrome are present, they
also do a real Chrome render with mixed page sizes.

## Layout

| Path | |
|---|---|
| `capture_preview.js` | Browser console snippet that exports the readable pages |
| `extract_preview.py` | Downloads the assets and rebuilds the pages as HTML, then PDF |
| `render_preview.cjs` | Prints local HTML to PDF with headless Chrome (fails if any image is missing) |
| `remove_solutions.py` | Detects and redacts answer regions, then verifies the result |
| `run.py` | Whole pipeline from one command, driven by presets |
| `make_gea_fonts.py` | Font map for the GEA1000 paper |
| `presets/` | Per-paper settings |
| `archive/` | The original one-off scripts, kept for reference (not maintained) |
