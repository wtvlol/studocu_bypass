"""Rebuild a readable document preview as a PDF.

Input is the preview-export.json written by capture_preview.js. This script
downloads only the stylesheet, fonts and images that those readable pages
reference, rebuilds the pages as local HTML, and prints them to PDF with
headless Chrome. It does not read cookies, sign in, remove blur, or fetch pages
that were not readable in the browser.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import ssl
import subprocess
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
BLOCKED_MARKERS = (b"Access Blocked", b"<Code>AccessDenied")
SRC_RE = re.compile(r'src="([^"]+)"')
CSS_URL_RE = re.compile(r"""url\(\s*['"]?(https://[^'")\s]+)['"]?\s*\)""")


class ExtractError(RuntimeError):
    """A problem the user can act on; printed without a traceback."""


# --------------------------------------------------------------------------- input


@dataclass
class Page:
    number: int
    class_name: str
    html: str


@dataclass
class Capture:
    title: str
    page_url: str
    stylesheets: list[str]
    pages: list[Page]
    total_pages: int
    skipped: list[dict] = field(default_factory=list)


def load_capture(path: Path, allow_partial: bool = False) -> Capture:
    """Read a capture_preview.js export (format 1 or 2)."""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        raise ExtractError(f"Capture file not found: {path}") from None
    except json.JSONDecodeError as e:
        raise ExtractError(f"{path} is not valid JSON: {e}") from None

    if data.get("format", 1) >= 2:
        pages = [Page(p["number"], p["className"], p["html"]) for p in data["pages"]]
        skipped = data.get("skippedPages", [])
        total = data.get("totalPages", len(pages) + len(skipped))
    else:  # Original export: a list of HTML strings, all assumed to use w0/h0.
        pages = [Page(i + 1, "pf w0 h0", h) for i, h in enumerate(data["pages"])]
        skipped = [{"number": n, "reason": "not loaded"} for n in data.get("unloadedPages", [])]
        total = len(pages) + len(skipped)

    if not pages:
        raise ExtractError("The capture contains no readable pages.")
    if skipped and not allow_partial:
        listed = ", ".join(f"{p['number']} ({p['reason']})" for p in skipped)
        raise ExtractError(
            f"{len(skipped)} of {total} pages were not readable when captured: {listed}.\n"
            "Load them in the browser and capture again, or pass --allow-partial to build "
            "a PDF of the readable pages only."
        )
    return Capture(data["title"], data["pageUrl"], data["stylesheets"], pages, total, skipped)


def page_numbers(text: str) -> list[int]:
    """Parse '1-3,5' into [1, 2, 3, 5]."""
    result: list[int] = []
    for part in text.split(","):
        part = part.strip()
        try:
            if "-" in part:
                a, b = (int(x) for x in part.split("-", 1))
                if a > b:
                    raise ValueError
                result.extend(range(a, b + 1))
            else:
                result.append(int(part))
        except ValueError:
            raise argparse.ArgumentTypeError(f"Invalid page range: {text!r}") from None
    if not result or any(n < 1 for n in result):
        raise argparse.ArgumentTypeError(f"Invalid page range: {text!r}")
    return result


# --------------------------------------------------------------------------- fetch


class Fetcher:
    """Downloads public HTTPS assets into a cache directory, safely and with retries."""

    def __init__(self, work_dir: Path, retries: int = 3, timeout: float = 35):
        self.dir = work_dir
        self.retries = retries
        self.timeout = timeout
        cafile = "/etc/ssl/cert.pem" if Path("/etc/ssl/cert.pem").exists() else None
        self.context = ssl.create_default_context(cafile=cafile)

    def path_for(self, url: str) -> Path:
        # Signed query strings change between sessions; the path identifies the asset.
        key = hashlib.sha256(url.split("?")[0].encode()).hexdigest()[:14]
        return self.dir / f"{key}-{Path(urlsplit(url).path).name or 'asset'}"

    def __call__(self, url: str) -> Path:
        if not url.startswith("https://"):
            raise ExtractError(f"Only HTTPS assets are supported: {url[:80]}")
        dest = self.path_for(url)
        if dest.exists():
            return dest
        data = self._download(url)
        tmp = dest.with_name(dest.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(dest)  # Atomic: an interrupted run never leaves a truncated cache file.
        return dest

    def _download(self, url: str) -> bytes:
        short = url.split("?")[0]
        for attempt in range(1, self.retries + 1):
            try:
                with urlopen(Request(url), context=self.context, timeout=self.timeout) as r:
                    data = r.read()
                    ctype = r.headers.get("Content-Type", "")
                break
            except HTTPError as e:
                if e.code in (401, 403, 404):
                    raise ExtractError(
                        f"Asset is not publicly accessible (HTTP {e.code}): {short}\n"
                        "Signed links expire; capture the preview again."
                    ) from None
                err: Exception = e
            except (URLError, TimeoutError) as e:
                err = e
            if attempt == self.retries:
                raise ExtractError(f"Could not download {short}: {err}")
            time.sleep(2 ** attempt)
        if any(m in data for m in BLOCKED_MARKERS) and ("html" in ctype or "xml" in ctype):
            raise ExtractError(f"Asset is not publicly accessible: {short}")
        return data


# --------------------------------------------------------------------------- css / images


def apply_font_map(css: str, font_map: dict[str, str]) -> str:
    for family, file in font_map.items():
        font = Path(file).expanduser().resolve()
        if not font.exists():
            raise ExtractError(f"Font in font map not found: {font}")
        pattern = r"@font-face\{font-family:" + re.escape(family) + r";[^}]+\}"
        replacement = "@font-face{font-family:" + family + ';src:url("' + font.as_uri() + '");}'
        css, count = re.subn(pattern, lambda _m, r=replacement: r, css)
        if not count:
            warnings.warn(f"Font map family {family!r} did not match any @font-face rule", stacklevel=2)
    return css


def localise_css(urls: list[str], fetch: Fetcher, font_map: dict[str, str]) -> str:
    styles = []
    for url in urls:
        css = fetch(url).read_text(errors="replace")
        css = apply_font_map(css, font_map)
        refs = list(dict.fromkeys(CSS_URL_RE.findall(css)))
        with ThreadPoolExecutor(max_workers=6) as pool:
            for ref, path in zip(refs, pool.map(fetch, refs), strict=False):
                css = css.replace(ref, path.as_uri())
        styles.append(css)
    return "\n".join(styles)


@dataclass
class HighlightOptions:
    """Pixels with R and G above `min_rg` and B at least `blue_gap` below them are cleared."""

    enabled: bool = False
    min_rg: int = 200
    blue_gap: int = 8


def clear_highlights(path: Path, opts: HighlightOptions) -> Path:
    import numpy as np
    from PIL import Image

    cleaned = path.with_name(f"nohl-{opts.min_rg}-{opts.blue_gap}-{path.stem}.png")
    if cleaned.exists():
        return cleaned
    arr = np.array(Image.open(path).convert("RGBA"))
    r, g, b = (arr[..., i].astype(int) for i in range(3))
    mask = (r > opts.min_rg) & (g > opts.min_rg) & (b < np.minimum(r, g) - opts.blue_gap)
    arr[mask, :3] = 255
    Image.fromarray(arr).save(cleaned)
    return cleaned


def localise_images(pages: list[Page], base_url: str, fetch: Fetcher, hl: HighlightOptions) -> None:
    """Replace each remote <img src> with a local file URI, downloading in parallel."""

    def remote(src: str) -> str | None:
        if src.startswith("data:"):
            return None
        return urljoin(base_url, html.unescape(src))

    srcs = {s for p in pages for s in SRC_RE.findall(p.html) if remote(s)}

    def resolve(src: str) -> tuple[str, Path]:
        path = fetch(remote(src))
        return src, clear_highlights(path, hl) if hl.enabled else path

    with ThreadPoolExecutor(max_workers=6) as pool:
        local = dict(pool.map(resolve, srcs))
    for p in pages:
        p.html = SRC_RE.sub(lambda m: f'src="{local[m[1]].as_uri()}"' if m[1] in local else m[0], p.html)


# --------------------------------------------------------------------------- html / pdf


def page_size_rules(css: str, pages: list[Page]) -> str:
    """Give every distinct page size its own named @page so mixed sizes print correctly."""
    widths = dict(re.findall(r"\.(w[0-9a-f]+)\{width:([\d.]+)px", css))
    heights = dict(re.findall(r"\.(h[0-9a-f]+)\{height:([\d.]+)px", css))
    if not widths or not heights:
        raise ExtractError("Page size classes (.w0/.h0) not found in the document stylesheet.")
    rules = []
    for wc, hc in sorted({size_classes(p.class_name) for p in pages}):
        if wc not in widths or hc not in heights:
            raise ExtractError(f"Stylesheet has no size for page classes {wc}/{hc}.")
        name = f"sz-{wc}-{hc}"
        rules.append(f"@page {name}{{size:{widths[wc]}px {heights[hc]}px;margin:0;}}")
        rules.append(f".p2hv .pf.{wc}.{hc}{{page:{name};}}")
    return "\n".join(rules)


def size_classes(class_name: str) -> tuple[str, str]:
    classes = class_name.split()
    w = next((c for c in classes if re.fullmatch(r"w[0-9a-f]+", c)), "w0")
    h = next((c for c in classes if re.fullmatch(r"h[0-9a-f]+", c)), "h0")
    return w, h


def build_html(title: str, css: str, pages: list[Page]) -> str:
    extra = (
        page_size_rules(css, pages)
        + "\nhtml,body{margin:0;padding:0;}.p2hv #page-container{position:static;}"
        ".p2hv .pf{margin:0!important;border:0!important;box-shadow:none!important;break-after:page;}"
        ".p2hv .pf:last-child{break-after:auto;}"
    )
    body = "".join(
        f'<div class="pf {" ".join(size_classes(p.class_name))}">{p.html}</div>' for p in pages
    )
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
        f"<style>{css}\n{extra}</style></head><body><div class=\"p2hv\"><div id=\"page-container\">"
        f"{body}</div></div></body></html>"
    )


def render_pdf(html_file: Path, out: Path, node: str | None, chrome: str | None, timeout: float) -> None:
    if not node:
        raise ExtractError("Node.js is required for the PDF renderer (install it or pass --node).")
    cmd = [node, str(ROOT / "render_preview.cjs"), html_file.as_uri(), str(out)]
    if chrome:
        cmd.append(chrome)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ExtractError(f"PDF rendering took longer than {timeout:.0f}s (see --render-timeout).") from None
    if r.returncode:
        raise ExtractError("PDF rendering failed:\n" + r.stderr[-2500:])


# --------------------------------------------------------------------------- entry points


@dataclass
class ExtractOptions:
    work_dir: Path = Path("work")
    pages: list[int] | None = None
    allow_partial: bool = False
    font_map: dict[str, str] = field(default_factory=dict)
    highlights: HighlightOptions = field(default_factory=HighlightOptions)
    node: str | None = shutil.which("node")
    chrome: str | None = None
    render_timeout: float = 120


def extract(capture_path: Path, output: Path, opts: ExtractOptions) -> Capture:
    """Build `output` from a capture file. Returns the capture that was used."""
    capture = load_capture(capture_path, opts.allow_partial or bool(opts.pages))
    if opts.pages:
        wanted = set(opts.pages)
        missing = wanted - {p.number for p in capture.pages}
        if missing:
            raise ExtractError(f"Requested pages were not readable in the capture: {sorted(missing)}")
        capture.pages = [p for p in capture.pages if p.number in wanted]

    work = opts.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    fetch = Fetcher(work)
    css = localise_css(capture.stylesheets, fetch, opts.font_map)
    localise_images(capture.pages, capture.page_url, fetch, opts.highlights)

    html_file = work / "preview.html"
    html_file.write_text(build_html(capture.title, css, capture.pages))
    out = output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    render_pdf(html_file, out, opts.node, opts.chrome, opts.render_timeout)
    return capture


def add_extract_arguments(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--work-dir", type=Path, default=Path("work"), help="Asset cache and HTML (default: work)")
    ap.add_argument("--pages", type=page_numbers, help="Only these captured pages, e.g. 1-11")
    ap.add_argument("--allow-partial", action="store_true", help="Build even if some pages were not readable")
    ap.add_argument("--font-map", type=Path, help="JSON mapping font-family names to local font files")
    ap.add_argument("--clear-yellow-highlights", action="store_true",
                    help="Whiten yellow highlight pixels in page images; inspect charts first")
    ap.add_argument("--highlight-min-rg", type=int, default=200)
    ap.add_argument("--highlight-blue-gap", type=int, default=8)
    ap.add_argument("--node", default=shutil.which("node"))
    ap.add_argument("--chrome", help="Chrome/Chromium executable (default: auto-detect)")
    ap.add_argument("--render-timeout", type=float, default=120)


def options_from_args(args: argparse.Namespace) -> ExtractOptions:
    font_map = json.loads(args.font_map.read_text()) if args.font_map else {}
    return ExtractOptions(
        work_dir=args.work_dir,
        pages=args.pages,
        allow_partial=args.allow_partial,
        font_map=font_map,
        highlights=HighlightOptions(args.clear_yellow_highlights, args.highlight_min_rg, args.highlight_blue_gap),
        node=args.node,
        chrome=args.chrome,
        render_timeout=args.render_timeout,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capture", type=Path, required=True, help="preview-export.json from capture_preview.js")
    ap.add_argument("--output", type=Path, required=True, help="PDF to write")
    add_extract_arguments(ap)
    args = ap.parse_args(argv)
    try:
        capture = extract(args.capture, args.output, options_from_args(args))
    except ExtractError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"Extracted {len(capture.pages)} of {capture.total_pages} pages: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
