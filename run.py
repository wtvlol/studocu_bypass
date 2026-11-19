"""One command from a preview capture to finished PDFs.

    python3 run.py preview-export.json                          # any document -> PDF
    python3 run.py preview-export.json --preset generic-qa      # + questions-only copy
    python3 run.py preview-export.json --preset gea1000 --name GEA1000_Sample

A preset is a JSON file in presets/ (or any path) with optional "extract" and
"practice" sections. Their keys match the command-line options, written with
underscores: e.g. {"practice": {"marker_regex": "^Answer\\b"}}. Options given
on the command line override the preset. Without a "practice" section (and no
--marker / --marker-regex), only the rebuilt PDF is made.

Output goes to output/<name>/:
    <name>.pdf                        the rebuilt preview
    <name>_With_Solutions.pdf         (practice mode) normalised page size
    <name>_Questions_Only.pdf         (practice mode) answer regions removed
    <name>_redaction_log.json         (practice mode) what was removed, for review
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import extract_preview as ex
import remove_solutions as rs

ROOT = Path(__file__).resolve().parent


def load_preset(name: str | None) -> dict:
    if not name:
        return {}
    path = Path(name)
    if not path.exists():
        path = ROOT / "presets" / f"{name.removesuffix('.json')}.json"
    if not path.exists():
        available = ", ".join(sorted(p.stem for p in (ROOT / "presets").glob("*.json")))
        raise SystemExit(f"error: preset {name!r} not found. Available: {available}")
    return json.loads(path.read_text())


def resolve_path(value: str) -> Path:
    """Relative preset paths are tried from the current folder, then the project folder."""
    p = Path(value).expanduser()
    return p if p.is_absolute() or p.exists() else ROOT / p


def slug(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")[:60] or "Document"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture", type=Path, help="preview-export.json from capture_preview.js")
    ap.add_argument("--preset", help="Preset name in presets/ or path to a preset JSON")
    ap.add_argument("--name", help="Output name (default: from the document title)")
    ap.add_argument("--output-dir", type=Path, default=Path("output"))
    ex.add_extract_arguments(ap)
    rs.add_practice_arguments(ap)
    # Distinguish "flag not given" from "flag given with the default value", so presets can fill gaps.
    ap.set_defaults(**{a.dest: None for a in ap._actions if a.dest not in ("help", "capture", "output_dir")})
    return ap.parse_args(argv)


def merged(args: argparse.Namespace, section: dict, defaults: dict) -> dict:
    """CLI value if given, else preset value, else default."""
    return {k: (getattr(args, k) if getattr(args, k, None) not in (None, []) else section.get(k, d))
            for k, d in defaults.items()}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    preset = load_preset(args.preset)

    e = merged(args, preset.get("extract", {}), {
        "work_dir": "work", "pages": None, "allow_partial": False, "font_map": None,
        "clear_yellow_highlights": False, "highlight_min_rg": 200, "highlight_blue_gap": 8,
        "node": ex.shutil.which("node"), "chrome": None, "render_timeout": 120,
    })
    practice_section = preset.get("practice")
    want_practice = practice_section is not None or args.marker or args.marker_regex
    p = merged(args, practice_section or {}, {
        "marker": "SOLUTION", "marker_regex": None, "question_pattern": rs.DEFAULT_QUESTION_PATTERN,
        "expected_questions": None, "top_content": 0, "page_size": "a4", "forbid_colors": [],
        "dry_run": False,
    })
    if args.forbid_color:
        p["forbid_colors"] = args.forbid_color
    p["forbid_colors"] = [c if isinstance(c, tuple) else rs.parse_color(c) for c in p["forbid_colors"]]

    pages = e["pages"]
    if isinstance(pages, str):
        pages = ex.page_numbers(pages)
    font_map = {}
    if e["font_map"]:
        fm = resolve_path(str(e["font_map"]))
        if not fm.exists():
            raise SystemExit(f"error: font map {fm} not found (for gea1000, run make_gea_fonts.py first)")
        font_map = json.loads(fm.read_text())

    def options(clear: bool) -> ex.ExtractOptions:
        return ex.ExtractOptions(
            work_dir=Path(e["work_dir"]), pages=pages, allow_partial=e["allow_partial"], font_map=font_map,
            highlights=ex.HighlightOptions(clear, e["highlight_min_rg"], e["highlight_blue_gap"]),
            node=e["node"], chrome=e["chrome"], render_timeout=e["render_timeout"],
        )

    try:
        title = ex.load_capture(args.capture, allow_partial=True).title
        name = args.name or slug(title)
        out_dir = args.output_dir / name
        source_pdf = out_dir / f"{name}.pdf"
        capture = ex.extract(args.capture, source_pdf, options(False))
        print(f"Rebuilt {len(capture.pages)} of {capture.total_pages} pages: {source_pdf.resolve()}")

        if not want_practice:
            return 0
        practice_input = source_pdf
        if e["clear_yellow_highlights"]:
            # Answers are highlighted in the page images: build a second copy with them cleared.
            practice_input = Path(e["work_dir"]) / f"{name}_no_highlights.pdf"
            ex.extract(args.capture, practice_input, options(True))
        opts = rs.PracticeOptions(**p, solutions_source=source_pdf if practice_input != source_pdf else None)
        for path in rs.make_practice(practice_input, out_dir, name, opts):
            print(path.resolve())
    except (ex.ExtractError, rs.RedactionError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
