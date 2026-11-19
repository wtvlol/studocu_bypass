"""Extract the public Sample B preview using its observed page resources."""
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor
import json, re, ssl, subprocess

ROOT=Path(__file__).resolve().parent
ASSETS=ROOT/'sample-b-assets'
HASH='3d19d9bfbe9f76abca83d61f523b7b49'
BASE=f'https://doc-assets.studocu.com/{HASH}/html/'
manifest=json.loads((ASSETS/'manifest.json').read_text())
query=urlsplit(manifest['assets'][0]['url']).query
context=ssl.create_default_context(cafile='/etc/ssl/cert.pem')

def download(item):
    name,url=item
    path=ASSETS/name
    if not path.exists():
        with urlopen(Request(url),context=context,timeout=30) as r:
            data=r.read()
        if b'Access Blocked' in data or b'<Code>AccessDenied' in data:
            raise RuntimeError(f'Access denied: {name}')
        path.write_bytes(data)
    return path

css=(ASSETS/f'{HASH}.css').read_text()
font_urls=re.findall(r'''url\(['"](https://[^'"\)]+\.woff)['"]''',css)
# Page 2 through 12 were observed in the public viewer.
page_names=[f'{HASH}{i}.page' for i in range(2,13)]
resources=[(n,BASE+n+'?'+query) for n in page_names]
resources.extend((u.rsplit('/',1)[-1],u) for u in font_urls)
with ThreadPoolExecutor(max_workers=4) as pool:
    for p in pool.map(download,resources):print('Saved',p.name,flush=True)
for u in font_urls:css=css.replace(u,u.rsplit('/',1)[-1])
width=re.search(r'\.w0\{width:([\d.]+)px',css).group(1)
height=re.search(r'\.h0\{height:([\d.]+)px',css).group(1)

cover='''<div class="pf w0 h0"><div style="position:absolute;top:60px;left:65px;right:65px;font-family:'Times New Roman',serif;font-size:13px;line-height:1.5">
<div style="text-align:center;font-weight:bold;font-size:16px">NATIONAL UNIVERSITY OF SINGAPORE</div>
<div style="text-align:center;font-size:14px">DEPARTMENT OF STATISTICS AND DATA SCIENCE</div>
<div style="text-align:center;font-weight:bold;font-size:17px;margin-top:22px">ST2334 PROBABILITY AND STATISTICS</div>
<div style="text-align:center;font-size:14px">SEMESTER I, AY 2024/2025</div>
<div style="text-align:center;font-weight:bold;font-size:17px;margin-top:20px">Final Examination (Sample Paper B)</div>
<div style="text-align:center;font-size:15px">Suggested Solutions</div>
<div style="font-weight:bold;margin-top:42px">INSTRUCTIONS</div>
<ul style="padding-left:18px;line-height:1.7">
<li>This assessment contains 30 questions.</li>
<li>The total marks is 60; each question is worth 2 marks.</li>
<li>Please answer ALL questions.</li>
<li>Calculators of any kind are allowed.</li>
<li>Coverage: Chapters 1 to 6.</li>
<li>For multiple response questions, 2 marks are awarded only if all correct options are selected.</li>
</ul></div></div>'''
pages=[cover];images={}
for n in page_names:
    raw=(ASSETS/n).read_text()
    if 'class="pc ' not in raw:raise RuntimeError(f'Unexpected page: {n}')
    raw=re.sub(r'src="(?:https://[^\"]*/)?(bg[0-9a-z]+\.png)(?:\?[^\"]*)?"',r'src="\1"',raw)
    for name in re.findall(r'src="(bg[0-9a-z]+\.png)"',raw):images[name]=BASE+name+'?'+query
    pages.append('<div class="pf w0 h0">'+raw+'</div>')
with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(download,images.items()))
extra=f'''@page{{size:{width}px {height}px;margin:0;}}
html,body{{margin:0;padding:0;}}.p2hv #page-container{{position:static;}}
.p2hv .pf{{margin:0!important;border:0!important;box-shadow:none!important;break-after:page;}}
.p2hv .pf:last-child{{break-after:auto;}}'''
html='<!doctype html><html><head><meta charset="utf-8"><title>ST2334 Sample B AY2024-25 - Suggested Solutions</title><style>'+css+extra+'</style></head><body><div class="p2hv"><div id="page-container">'+''.join(pages)+'</div></div></body></html>'
html_path=ASSETS/'sample-b.html';html_path.write_text(html)
out=ROOT/'sample-b-extracted.pdf'
cmd=['/Users/keith/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node',str(ROOT/'render_local.mjs'),html_path.as_uri(),str(out)]
r=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
if r.returncode:raise RuntimeError(r.stderr[-1500:])
print('Extracted',out)
