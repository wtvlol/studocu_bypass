"""Save a readable Studocu preview as PDF using its public page assets.

Accept either a JSON export made by capture_preview.js, or the asset manifest
exported by the browser's pageAssets capability. Does not read cookies, sign in,
remove blurs, or discover restricted download endpoints.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlsplit
import argparse, hashlib, json, os, re, shutil, ssl, subprocess

def page_numbers(text):
    result=[]
    for part in text.split(','):
        if '-' in part:
            a,b=map(int,part.split('-'));result.extend(range(a,b+1))
        else:result.append(int(part))
    if not result or any(n<1 for n in result):raise ValueError('Invalid page range')
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    mode=ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--capture',type=Path,help='JSON saved by capture_preview.js')
    mode.add_argument('--manifest',type=Path,help='Browser pageAssets manifest')
    ap.add_argument('--hash',help='Document asset hash, for manifest mode')
    ap.add_argument('--pages',type=page_numbers,help='Visible page numbers, e.g. 1-11')
    ap.add_argument('--work-dir',type=Path,default=Path('work'))
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--node',default=shutil.which('node'))
    ap.add_argument('--chrome',help='Optional installed Chrome executable')
    ap.add_argument('--font-map',type=Path,help='Optional JSON mapping font-family names to local font files')
    ap.add_argument('--clear-yellow-highlights',action='store_true',help='Remove yellow answer highlights from preview background images; inspect charts before using')
    args=ap.parse_args()
    work=args.work_dir.resolve();work.mkdir(parents=True,exist_ok=True)
    context=ssl.create_default_context()
    if Path('/etc/ssl/cert.pem').exists():context=ssl.create_default_context(cafile='/etc/ssl/cert.pem')
    cache={}
    def fetch(url):
        if not url.startswith('https://'):raise ValueError('Only HTTPS assets are supported')
        key=hashlib.sha256(url.split('?')[0].encode()).hexdigest()[:14]
        name=key+'-'+Path(urlsplit(url).path).name
        dest=work/name
        if not dest.exists():
            with urlopen(Request(url),context=context,timeout=35) as r:data=r.read()
            if b'Access Blocked' in data or b'<Code>AccessDenied' in data:
                raise RuntimeError('Asset is not publicly accessible: '+url.split('?')[0])
            dest.write_bytes(data)
        cache[url]=dest
        return dest
    if args.capture:
        captured=json.loads(args.capture.read_text())
        if captured.get('unloadedPages'):raise ValueError('Some pages are not loaded; scroll through the preview and capture again')
        title=captured['title'];pages=captured['pages'];css_urls=captured['stylesheets']
        base_url=captured['pageUrl']
    else:
        if not args.hash or not args.pages:ap.error('--manifest requires --hash and --pages')
        manifest=json.loads(args.manifest.read_text())
        assets=manifest['assets']
        css_asset=next(a for a in assets if a['name']==args.hash+'.css')
        css_urls=[css_asset['url']]
        base_url=css_asset['url'].rsplit('/',1)[0]+'/'
        query=urlsplit(css_asset['url']).query
        # These page numbers come from the visible preview, not a guessed page count.
        urls=[base_url+args.hash+str(n)+'.page?'+query for n in args.pages]
        def get_page(url):
            raw=fetch(url).read_text()
            if 'class="pc ' not in raw:raise RuntimeError('Unexpected preview page content')
            # Image URLs in page fragments are relative to the same signed asset directory.
            def image_url(m):
                url=urljoin(base_url,m[1]);url+=('?' + query) if '?' not in url else ''
                return 'src="'+url+'"'
            return re.sub(r'src="([^"]+)"',image_url,raw)
        with ThreadPoolExecutor(max_workers=4) as pool:pages=list(pool.map(get_page,urls))
        title='Study paper extracted from readable preview'
    styles=[]
    overrides=json.loads(args.font_map.read_text()) if args.font_map else {}
    for url in css_urls:
        css=fetch(url).read_text()
        for family,file in overrides.items():
            font=Path(file).expanduser().resolve()
            if not font.exists():raise FileNotFoundError(font)
            css=re.sub(r'@font-face\{font-family:'+re.escape(family)+r';[^}]+}',
                '@font-face{font-family:'+family+';src:url("'+font.as_uri()+'");}',css)
        # Download only resources referenced by the document stylesheet.
        refs=re.findall(r'''url\(\s*['"]?(https://[^'"\)\s]+)['"]?\s*\)''',css)
        for ref in dict.fromkeys(refs):css=css.replace(ref,fetch(ref).as_uri())
        styles.append(css)
    for i,raw in enumerate(pages):
        def local_image(m):
            url=m[1].replace('&amp;','&')
            path=fetch(urljoin(base_url,url))
            if args.clear_yellow_highlights:
                from PIL import Image
                cleaned=path.with_name('no-highlight-v2-'+path.stem+'.png')
                if not cleaned.exists():
                    image=Image.open(path).convert('RGBA')
                    pixels=list(image.getdata())
                    pixels=[(255,255,255,a) if r>200 and g>200 and b<min(r,g)-8 else (r,g,b,a) for r,g,b,a in pixels]
                    image.putdata(pixels);image.save(cleaned)
                path=cleaned
            return 'src="'+path.as_uri()+'"'
        pages[i]=re.sub(r'src="([^"]+)"',local_image,raw)
    css='\n'.join(styles)
    width=re.search(r'\.w0\{width:([\d.]+)px',css).group(1)
    height=re.search(r'\.h0\{height:([\d.]+)px',css).group(1)
    extra=f'''@page{{size:{width}px {height}px;margin:0;}}
    html,body{{margin:0;padding:0;}}.p2hv #page-container{{position:static;}}
    .p2hv .pf{{margin:0!important;border:0!important;box-shadow:none!important;break-after:page;}}
    .p2hv .pf:last-child{{break-after:auto;}}'''
    import html
    document='<!doctype html><html><head><meta charset="utf-8"><title>'+html.escape(title)+'</title><style>'+css+extra+'</style></head><body><div class="p2hv"><div id="page-container">'
    document+=''.join('<div class="pf w0 h0">'+p+'</div>' for p in pages)
    document+='</div></div></body></html>'
    html_file=work/'preview.html';html_file.write_text(document)
    out=args.output.resolve();out.parent.mkdir(parents=True,exist_ok=True)
    if not args.node:raise RuntimeError('Node.js is required for the local PDF renderer')
    cmd=[args.node,str(Path(__file__).with_name('render_preview.cjs')),html_file.as_uri(),str(out)]
    if args.chrome:cmd.append(args.chrome)
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=75)
    if r.returncode:raise RuntimeError(r.stderr[-2500:])
    print(f'Extracted {len(pages)} pages: {out}')

if __name__=='__main__':main()
