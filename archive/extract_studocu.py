"""Save the already-public Studocu preview assets; render them locally as a PDF.

Uses the asset manifest exported from the visible browser page. No authentication,
unblurring, guessed PDF endpoints, or access-control changes are performed.
"""
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor
import json, re, subprocess, ssl, sys

ROOT = Path(__file__).resolve().parent
SOLUTIONS = '--solutions' in sys.argv
ASSETS = ROOT / ('solutions-assets' if SOLUTIONS else 'studocu-assets')
MANIFEST = json.loads((ASSETS / 'manifest.json').read_text())
HASH = '1ef27decd6be3914b36c50e25a25d6df' if SOLUTIONS else 'd370d206ae624784de92b73ca2d704f9'
BASE = f'https://doc-assets.studocu.com/{HASH}/html/'
QUERY = urlsplit(MANIFEST['assets'][0]['url']).query
# These exact page resources were observed loading in the public viewer.
PAGE_NAMES = [f'{HASH}{i}.page' for i in (range(2,13) if SOLUTIONS else (2, 3, 4, 5, 6, 8, 9, 10))]

def download(item):
    name, url = item
    dest = ASSETS / name
    if not dest.exists():
        with urlopen(Request(url), timeout=30, context=ssl.create_default_context(cafile='/etc/ssl/cert.pem')) as response:
            data = response.read()
        if b'Access Blocked' in data or b'<Code>AccessDenied' in data:
            raise RuntimeError(f'Access denied for {name}')
        dest.write_bytes(data)
    return dest

downloads = [(n, BASE+n+'?'+QUERY) for n in PAGE_NAMES]
source_css = (ASSETS / f'{HASH}.css').read_text()
font_urls = re.findall(r'''url\(['"](https://[^'"\)]+\.woff)['"]''',source_css)
downloads += [(u.rsplit('/',1)[-1], u) for u in font_urls]
with ThreadPoolExecutor(max_workers=4) as pool:
    for path in pool.map(download, downloads):
        print('Saved', path.name, flush=True)

css = source_css
for font_url in font_urls:
    css = css.replace(font_url, font_url.rsplit('/',1)[-1])
width = re.search(r'\.w0\{width:([\d.]+)px', css).group(1)
height = re.search(r'\.h0\{height:([\d.]+)px', css).group(1)
# Reproduce the cover text without changing the mathematical question pages.
cover = '''<div class="pf w0 h0"><div class="pc pc1 w0 h0">
<div class="c x0 y1 w2 h2">
<div class="t m0 x1 h3 y2 ff1 fs0 fc0 sc0 ls2">ST2334 PROBABILITY AND STATISTICS</div>
<div class="t m0 x2 h4 y3 ff1 fs2 fc0 sc0 ls1">SEMESTER I, AY 2022/2023</div>
<div class="t m0 x3 h3 y4 ff1 fs0 fc0 sc0 ls2">Example Questions for the Final Examination</div>
<div class="t m0 x4 h5 y5 ff2 fs2 fc0 sc0 ls2">• The format of the exam is open book (hard copies or/and soft copies physically stored on</div>
<div class="t m0 x5 h5 y6 ff2 fs2 fc0 sc0 ls2">the laptop for exam are allowed), onsite through exam software: Exemplify. A laptop</div>
<div class="t m0 x5 h5 y7 ff2 fs2 fc0 sc0 ls2">with the software installed and solid battery that can last for at least 2 hours is needed.</div>
<div class="t m0 x4 h5 y8 ff2 fs2 fc0 sc0 ls2">• Calculators of any kind are allowed.</div>
<div class="t m0 x4 h5 y9 ff2 fs2 fc0 sc0 ls2">• All chapters covered during the semester, i.e., Chapters 1 – 7.</div>
<div class="t m0 x6 h5 ya ff2 fs2 fc0 sc0 ls2">1</div>
</div></div></div>'''
if SOLUTIONS:
    cover = cover.replace('Example Questions for the Final Examination</div>', 'Example Questions for the Final Examination: Solution</div>')
else:
    cover = '''<div class="pf w0 h0"><div style="position:absolute;top:42px;left:42px;right:42px;font-family:'Times New Roman',serif;font-size:9px;line-height:1.5">
    <div style="text-align:center;font-weight:bold;font-size:12px">ST2334 PROBABILITY AND STATISTICS</div>
    <div style="text-align:center;font-weight:bold;font-size:10px">SEMESTER I, AY 2022/2023</div>
    <div style="text-align:center;font-weight:bold;font-size:12px;margin-top:16px">Example Questions for the Final Examination</div>
    <ul style="padding-left:12px;margin-top:32px">
    <li>The format of the exam is open book (hard copies or/and soft copies physically stored on the laptop for exam are allowed), onsite through exam software: Exemplify. A laptop with the software installed and solid battery that can last for at least 2 hours is needed.</li>
    <li style="margin-top:7px">Calculators of any kind are allowed.</li>
    <li style="margin-top:7px">All chapters covered during the semester, i.e., Chapters 1 – 7.</li>
    </ul></div><div style="position:absolute;bottom:24px;width:100%;text-align:center;font-family:'Times New Roman',serif;font-size:9px">1</div></div>'''
pages = [cover]
image_downloads = {}
for name in PAGE_NAMES:
    raw = (ASSETS / name).read_text()
    # Page resources are pdf2htmlEX HTML fragments, not the corrupt preview transcript.
    if not ('class="pf ' in raw or 'class="pc ' in raw):
        raise RuntimeError(f'Unexpected page format in {name}: {raw[:80]}')
    raw = re.sub(r'src="(?:https://[^\"]*/)?(bg[0-9a-z]+\.png)(?:\?[^\"]*)?"', r'src="\1"', raw)
    for image_name in re.findall(r'src="(bg[0-9a-z]+\.png)"', raw):
        image_downloads[image_name] = BASE+image_name+'?'+QUERY
    raw = raw.replace('Document continues below', '')
    pages.append('<div class="pf w0 h0">'+raw+'</div>')
with ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(download, image_downloads.items()))

extra = f'''@page {{size: {width}px {height}px; margin:0;}}
html,body{{margin:0;padding:0;}} .p2hv #page-container{{position:static;}}
.p2hv .pf{{margin:0!important;border:0!important;box-shadow:none!important;break-after:page;}}
.p2hv .pf:last-child{{break-after:auto;}}
.page-content{{display:block!important;}}
'''
html = '<!doctype html><html><head><meta charset="utf-8"><style>'+css+extra+'</style></head><body><div class="p2hv"><div id="page-container">'+''.join(pages)+'</div></div></body></html>'
html_file = ASSETS / 'questions.html'
html_file.write_text(html)
out = ROOT.parent.parent / ('output/pdf/ST2334_AY2022-23_Final_Example_With_Solutions.pdf' if SOLUTIONS else 'output/pdf/ST2334_AY2022-23_Final_Example_Questions_Only.pdf')
out.parent.mkdir(parents=True, exist_ok=True)
command = ['/Users/keith/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node',
    str(ROOT/'render_local.mjs'), html_file.as_uri(), str(out)]
result = subprocess.run(command, capture_output=True, text=True, timeout=60)
if result.returncode or not out.exists():
    raise RuntimeError(result.stderr[-1500:])
print('PDF:', out)
