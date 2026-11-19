"""Make a with-solutions copy and a questions-only practice copy of a PDF.

Every region from an answer marker (e.g. "Explanation") to the next question
heading is redacted. Redaction deletes the text, image pixels and vector
graphics underneath; it does not just paint a box over them. After redacting,
the result is checked: every question heading must survive, no marker may
remain, and (with --forbid-color) no text may remain in the answer colour.
A JSON log of the redacted rectangles is written so the result can be reviewed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

PAGE_SIZES = {"a4": (595.2756, 841.8898), "letter": (612.0, 792.0)}
DEFAULT_QUESTION_PATTERN = r"^Q?\s*(\d+)\s*[.):]?(?:\s|$)"


class RedactionError(RuntimeError):
    pass


@dataclass
class Line:
    text: str
    rect: tuple[float, float, float, float]  # x0, y0, x1, y1


@dataclass
class PageLines:
    width: float
    height: float
    lines: list[Line]


@dataclass
class Detection:
    regions: list[tuple[int, tuple[float, float, float, float]]] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    markers: int = 0


def find_answer_regions(
    pages: list[PageLines], question_re: re.Pattern, marker_re: re.Pattern, top_content: float = 0
) -> Detection:
    """Find the answer regions to redact. Pure: no PDF access, so it is easy to test.

    An answer region starts just above a marker line and ends just above the next
    question heading, carrying over page breaks. On a continuation page it starts
    at `top_content`, so a running header above that line is kept.
    """
    det = Detection()
    in_answer = False
    for index, page in enumerate(pages):
        events = []
        for line in page.lines:
            y0 = line.rect[1]
            if q := question_re.match(line.text):
                events.append((y0, 0, q.group(1)))
            if marker_re.match(line.text):
                events.append((y0, 1, None))
        start = top_content if in_answer else None
        for y, kind, number in sorted(events, key=lambda e: (e[0], e[1])):
            if kind == 0:  # question heading
                det.questions.append(number)
                if in_answer and start is not None and y - 2 > start:
                    det.regions.append((index, (0, start, page.width, y - 2)))
                in_answer, start = False, None
            else:  # answer marker
                det.markers += 1
                if not in_answer:
                    start = max(top_content, y - 1)
                in_answer = True
        if in_answer and start is not None:
            det.regions.append((index, (0, start, page.width, page.height)))
    return det


def read_lines(page: pymupdf.Page) -> PageLines:
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(s["text"] for s in line["spans"]).strip()
            lines.append(Line(text, tuple(line["bbox"])))
    return PageLines(page.rect.width, page.rect.height, lines)


def colored_spans(doc: pymupdf.Document, rgb: tuple[float, float, float], tolerance: float = 0.15):
    """Yield (page number, text) of non-blank spans whose colour is close to `rgb`."""
    for i, page in enumerate(doc):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    c = span["color"]
                    color = ((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255
                    if span["text"].strip() and all(abs(a - b) <= tolerance for a, b in zip(color, rgb, strict=False)):
                        yield i + 1, span["text"]


def parse_color(text: str) -> tuple[float, float, float]:
    text = text.strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{6}", text):
        return tuple(int(text[i : i + 2], 16) / 255 for i in (0, 2, 4))
    parts = [float(x) for x in text.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("Colour must be RRGGBB or r,g,b in 0..1")
    return tuple(parts)


@dataclass
class PracticeOptions:
    marker: str = "SOLUTION"
    marker_regex: str | None = None
    question_pattern: str = DEFAULT_QUESTION_PATTERN
    expected_questions: int | None = None
    solutions_source: Path | None = None
    top_content: float = 0
    page_size: str = "a4"
    forbid_colors: list[tuple[float, float, float]] = field(default_factory=list)
    dry_run: bool = False


def resize(doc: pymupdf.Document, page_size: str) -> pymupdf.Document:
    if page_size == "source":
        return doc
    width, height = PAGE_SIZES[page_size]
    out = pymupdf.open()
    for i in range(len(doc)):
        out.new_page(width=width, height=height).show_pdf_page(pymupdf.Rect(0, 0, width, height), doc, i)
    return out


def make_practice(input_pdf: Path, output_dir: Path, name: str, opts: PracticeOptions) -> list[Path]:
    source = pymupdf.open(opts.solutions_source or input_pdf)
    practice = pymupdf.open(input_pdf)
    if len(source) != len(practice):
        raise RedactionError("Solutions and practice sources must have the same page count")

    question_re = re.compile(opts.question_pattern, re.I)
    marker_re = re.compile(opts.marker_regex or (r"^" + re.escape(opts.marker) + r"\b"), re.I)
    det = find_answer_regions([read_lines(p) for p in practice], question_re, marker_re, opts.top_content)

    if not det.markers:
        raise RedactionError("No answer markers found; refusing to write an unchanged practice copy")
    if opts.expected_questions and len(det.questions) != opts.expected_questions:
        raise RedactionError(f"Expected {opts.expected_questions} questions, found {det.questions}")

    output_dir.mkdir(parents=True, exist_ok=True)
    log = [{"page": i + 1, "rect": list(r)} for i, r in det.regions]
    log_path = output_dir / f"{name}_redaction_log.json"
    log_path.write_text(json.dumps(log, indent=2))

    if opts.dry_run:
        written = [log_path]
        for i, page in enumerate(practice):
            for _, r in (x for x in det.regions if x[0] == i):
                page.draw_rect(pymupdf.Rect(r), color=(1, 0, 0), width=2)
            png = output_dir / f"{name}_preview_p{i + 1:02d}.png"
            page.get_pixmap(dpi=72).save(png)
            written.append(png)
        return written

    for i, rect in det.regions:
        practice[i].add_redact_annot(pymupdf.Rect(rect), fill=(1, 1, 1))
    for page in practice:
        # Removes the text, overlapping image pixels and vector graphics, not just a cover-up box.
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                              text=pymupdf.PDF_REDACT_TEXT_REMOVE)

    surviving = [q.group(1) for p in practice for ln in read_lines(p).lines if (q := question_re.match(ln.text))]
    if surviving != det.questions:
        raise RedactionError(f"Question headings changed: before {det.questions}, after {surviving}")
    if any(marker_re.match(ln.text) for p in practice for ln in read_lines(p).lines):
        raise RedactionError("An answer marker survived redaction")
    for rgb in opts.forbid_colors:
        leftover = list(colored_spans(practice, rgb))
        if leftover:
            page, text = leftover[0]
            raise RedactionError(f"{len(leftover)} span(s) in the answer colour survived, e.g. page {page}: {text!r}")

    written = []
    for doc, suffix in [(source, "With_Solutions"), (practice, "Questions_Only")]:
        out = resize(doc, opts.page_size)
        out.set_metadata({
            "title": f"{name.replace('_', ' ')} - {suffix.replace('_', ' ')}",
            "subject": "Rebuilt from a readable preview; the practice copy has solution regions removed.",
        })
        path = output_dir / f"{name}_{suffix}.pdf"
        out.save(path, garbage=4, deflate=True)
        written.append(path)
    written.append(log_path)
    print(f"Kept {len(det.questions)} question headings and removed {det.markers} answer sections "
          f"across {len(source)} pages.")
    return written


def add_practice_arguments(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--marker", default="SOLUTION", help="Literal text that starts an answer (default: SOLUTION)")
    ap.add_argument("--marker-regex", help=r"Regex instead of --marker, e.g. ^(?:Explanation|Answer)\b")
    ap.add_argument("--question-pattern", default=DEFAULT_QUESTION_PATTERN,
                    help="Regex for question headings; group 1 is the number")
    ap.add_argument("--expected-questions", type=int)
    ap.add_argument("--solutions-source", type=Path,
                    help="Unaltered PDF for the with-solutions copy (when input had highlights cleared)")
    ap.add_argument("--top-content", type=float, default=0,
                    help="Top of content in PDF points; keeps a running header above it")
    ap.add_argument("--page-size", choices=["a4", "letter", "source"], default="a4")
    ap.add_argument("--forbid-color", type=parse_color, action="append", default=[],
                    help="Fail if text in this colour survives (RRGGBB or r,g,b); repeatable")
    ap.add_argument("--dry-run", action="store_true", help="Only write the log and PNG previews with regions outlined")


def practice_options_from_args(args: argparse.Namespace) -> PracticeOptions:
    return PracticeOptions(
        marker=args.marker, marker_regex=args.marker_regex, question_pattern=args.question_pattern,
        expected_questions=args.expected_questions, solutions_source=args.solutions_source,
        top_content=args.top_content, page_size=args.page_size, forbid_colors=args.forbid_color,
        dry_run=args.dry_run,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path)
    ap.add_argument("--output-dir", type=Path, default=Path("output"))
    ap.add_argument("--name", default="Study_Paper")
    add_practice_arguments(ap)
    args = ap.parse_args(argv)
    try:
        paths = make_practice(args.input, args.output_dir, args.name, practice_options_from_args(args))
    except RedactionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    for p in paths:
        print(p.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
