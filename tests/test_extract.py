import argparse
import json
import shutil
from pathlib import Path

import pytest

import extract_preview as ex


@pytest.mark.parametrize("text,expected", [
    ("1", [1]), ("1-3", [1, 2, 3]), ("1, 3-4", [1, 3, 4]), ("2,2", [2, 2]),
])
def test_page_numbers(text, expected):
    assert ex.page_numbers(text) == expected


@pytest.mark.parametrize("text", ["", "0", "3-1", "1-", "a", "-2"])
def test_page_numbers_rejects(text):
    with pytest.raises(argparse.ArgumentTypeError):
        ex.page_numbers(text)


def write_capture(tmp_path, **overrides):
    data = {
        "format": 2, "title": "T", "pageUrl": "https://example.com/doc", "totalPages": 2,
        "stylesheets": ["https://doc-assets.example.com/html/a.css"], "skippedPages": [],
        "pages": [{"number": 1, "className": "pf w0 h0", "html": "<div class=\"pc\">one</div>"},
                  {"number": 2, "className": "pf w1 h1", "html": "<div class=\"pc\">two</div>"}],
    }
    data.update(overrides)
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(data))
    return path


def test_load_capture_v2(tmp_path):
    cap = ex.load_capture(write_capture(tmp_path))
    assert [p.number for p in cap.pages] == [1, 2]
    assert cap.pages[1].class_name == "pf w1 h1"


def test_load_capture_v1(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"title": "T", "pageUrl": "u", "stylesheets": [], "unloadedPages": [],
                                "pages": ["<div>a</div>"]}))
    cap = ex.load_capture(path)
    assert cap.pages[0].class_name == "pf w0 h0"


def test_unreadable_pages_refused_unless_partial(tmp_path):
    path = write_capture(tmp_path, totalPages=3, skippedPages=[{"number": 3, "reason": "blurred"}])
    with pytest.raises(ex.ExtractError, match="3 \\(blurred\\)"):
        ex.load_capture(path)
    assert len(ex.load_capture(path, allow_partial=True).pages) == 2


def test_requested_pages_must_be_readable(tmp_path):
    path = write_capture(tmp_path, totalPages=3, skippedPages=[{"number": 3, "reason": "blurred"}])
    opts = ex.ExtractOptions(work_dir=tmp_path / "w", pages=[3])
    with pytest.raises(ex.ExtractError, match="not readable"):
        ex.extract(path, tmp_path / "o.pdf", opts)


CSS = ".w0{width:300.000000px;}.h0{height:400.000000px;}.w1{width:400.000000px;}.h1{height:300.000000px;}"


def test_page_size_rules_mixed_sizes():
    pages = [ex.Page(1, "pf w0 h0", ""), ex.Page(2, "pf w1 h1", "")]
    rules = ex.page_size_rules(CSS, pages)
    assert "@page sz-w0-h0{size:300.000000px 400.000000px" in rules
    assert "@page sz-w1-h1{size:400.000000px 300.000000px" in rules


def test_page_size_rules_missing_class():
    with pytest.raises(ex.ExtractError, match="size classes"):
        ex.page_size_rules("", [ex.Page(1, "pf w0 h0", "")])


def test_font_map_warns_when_unmatched(tmp_path):
    font = tmp_path / "f.ttf"
    font.write_bytes(b"x")
    css = "@font-face{font-family:ff1;src:url(https://x/a.woff)format('woff');}"
    out = ex.apply_font_map(css, {"ff1": str(font)})
    assert font.as_uri() in out and "https://x/a.woff" not in out
    with pytest.warns(UserWarning, match="ff9"):
        ex.apply_font_map(css, {"ff9": str(font)})


def test_clear_highlights(tmp_path):
    np = pytest.importorskip("numpy")
    from PIL import Image

    arr = np.zeros((1, 3, 4), dtype=np.uint8)
    arr[0, 0] = (255, 240, 60, 255)  # yellow -> cleared
    arr[0, 1] = (250, 250, 250, 255)  # near white -> kept
    arr[0, 2] = (20, 20, 200, 255)  # blue -> kept
    src = tmp_path / "img.png"
    Image.fromarray(arr).save(src)
    out = np.array(Image.open(ex.clear_highlights(src, ex.HighlightOptions(True))))
    assert tuple(out[0, 0]) == (255, 255, 255, 255)
    assert tuple(out[0, 1]) == (250, 250, 250, 255)
    assert tuple(out[0, 2]) == (20, 20, 200, 255)


def test_fetcher_cache_key_ignores_signature(tmp_path):
    f = ex.Fetcher(tmp_path)
    assert f.path_for("https://a/b/c.png?sig=1") == f.path_for("https://a/b/c.png?sig=2")


def test_fetcher_rejects_http(tmp_path):
    with pytest.raises(ex.ExtractError, match="HTTPS"):
        ex.Fetcher(tmp_path)("http://a/b.css")


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_render_mixed_page_sizes(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    if not (Path(ex.ROOT) / "node_modules/playwright-core").exists():
        pytest.skip("needs npm install")
    pages = [ex.Page(1, "pf w0 h0", '<div class="pc">portrait</div>'),
             ex.Page(2, "pf w1 h1", '<div class="pc">landscape</div>')]
    html_file = tmp_path / "p.html"
    html_file.write_text(ex.build_html("T", CSS, pages))
    out = tmp_path / "p.pdf"
    try:
        ex.render_pdf(html_file, out, shutil.which("node"), None, 60)
    except ex.ExtractError as e:
        if "Could not start Chrome" in str(e):
            pytest.skip("no Chrome")
        raise
    doc = pymupdf.open(out)
    sizes = [(round(p.rect.width), round(p.rect.height)) for p in doc]
    assert sizes == [(225, 300), (300, 225)]  # px * 0.75 = pt
