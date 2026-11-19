"""Repair this paper's dead font links using equivalent installed Office fonts.

GEA1000's preview was exported with Calibri and Cambria Math. A small legacy
numeric subset encodes 2, 3 and 5 as !, double quote and #. Preserve its visible
mathematics by mapping those three slots in a separate local font copy.
"""
from pathlib import Path
import json
from fontTools.ttLib import TTCollection

root=Path(__file__).resolve().parent
office=Path('/Applications/Microsoft Word.app/Contents/Resources/DFonts')
out=root/'work/gea-fonts';out.mkdir(parents=True,exist_ok=True)
collection=TTCollection(office/'Cambria.ttc')
math=next(f for f in collection.fonts if any(n.nameID==1 and 'Math' in n.toUnicode() for n in f['name'].names))
math.save(out/'CambriaMath.ttf')
mapping=math.getBestCmap()
for table in math['cmap'].tables:
    if table.isUnicode():
        for source,target in [('!','2'),('"','3'),('#','5')]:table.cmap[ord(source)]=mapping[ord(target)]
math.save(out/'CambriaMathLegacyNumbers.ttf')
fonts={
    'ff1':str(office/'Calibrib.ttf'), 'ff2':str(office/'Calibri.ttf'),
    'ff3':str(office/'Calibri.ttf'), 'ff4':str(out/'CambriaMath.ttf'),
    'ff5':str(office/'Calibri.ttf'), 'ff6':str(out/'CambriaMathLegacyNumbers.ttf'),
    'ff7':str(office/'Calibrii.ttf'), 'ff8':str(office/'Calibrib.ttf'),
}
(root/'gea-font-map.json').write_text(json.dumps(fonts,indent=2))
print('Saved local font map: gea-font-map.json')
