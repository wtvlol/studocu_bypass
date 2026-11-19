STUDOCU PREVIEW EXTRACTION

Approach
1. Open the supplied document normally and load each readable preview page.
2. Record the preview HTML and its linked stylesheet, fonts and images.
3. Download those public assets with Python and keep their original positioning.
4. Print the saved local HTML to PDF using a separate headless Chrome process.
5. Identify each solution/explanation section and permanently redact it to create
   a practice copy. Check that every question survives and no answer text remains.
6. Render both PDFs and visually inspect formulas, diagrams and page boundaries.

This is reconstruction of the readable preview, rather than access to the site's
original downloadable PDF. It does not use account cookies, remove blurring,
guess restricted download endpoints, or bypass login/payment requirements.
Public asset links can expire. A fresh export may be needed later.

Files
- capture_preview.js: exports the already-loaded document DOM as JSON.
- extract_preview.py: fetches linked assets and reconstructs the PDF.
- render_preview.cjs: prints the local reconstruction with installed Chrome.
- remove_solutions.py: permanently removes marked solution sections and creates
  A4 practice/solutions copies. Each different paper still needs visual review.
- original scripts/: copies of the actual earlier ST2334 scripts, as used.
  These historical scripts contain task-specific paths and expect their original
  temporary asset directories; they are reference snapshots, not standalone tools.
- make_gea_fonts.py: creates gea-font-map.json to repair the GEA1000 paper's dead
  font links with the equivalent installed Microsoft Office fonts. The local
  paths in this map are specific to this Mac. The font map is optional.

Requirements
- Python 3, the packages in requirements.txt, Node.js, and installed Google Chrome.
- For a standalone installation: python3 -m pip install -r requirements.txt
  and npm install in this folder. The Codex bundled renderer also works directly.

Typical use
1. Open a document you can read and scroll through every page.
2. Run capture_preview.js in its browser developer console. Save the resulting
   preview-export.json beside these scripts.
3. Run:
   python3 extract_preview.py --capture preview-export.json --work-dir work --output extracted.pdf
4. For a paper whose question headings are Q1, Q2, ... and solutions start with
   Explanation, run:
   python3 remove_solutions.py extracted.pdf --marker Explanation --question-pattern "^Q\\s*(\\d+)\\b" --output-dir output --name GEA1000_Sample

The code also accepts the asset manifest used by the browser tool:
python3 extract_preview.py --manifest /absolute/path/manifest.json --hash DOCUMENT_ASSET_HASH --pages 1-11 --work-dir work --output extracted.pdf

Highlighted answers
For GEA1000, correct answers are highlighted in yellow in the page backgrounds.
Render a second intermediate copy with --clear-yellow-highlights, then pass that
copy to remove_solutions.py and pass the original to --solutions-source.
The highlight option clears yellow pixels from background images, so inspect
any charts using yellow before enabling it for a different paper.
GEA1000 also uses an Answer heading for Q15, so use:
--marker-regex "^(?:Explanation|Answer)\\b" --question-pattern "^Q\\s*(\\d+)\\b"
The source explanations use red text; check that none survives in the final
questions-only copy. This is an additional check, not the redaction mechanism.

Do not treat an incomplete/blocked preview as a complete document. Check the page
count and all question numbers before using an extracted paper for revision.

Location
This folder contains code only. Downloaded preview assets, temporary renders and
font copies were left in the ST2334 working folder. Run make_gea_fonts.py here
to regenerate the local font map before processing the GEA1000 paper.
