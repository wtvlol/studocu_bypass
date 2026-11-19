"""Build a font map that replaces a preview's dead font links with installed fonts.

Written for the GEA1000 paper. Its preview uses Calibri and Cambria Math, and
one legacy numeric subset (ff6) encodes the digits 2, 3 and 5 as '!', '"' and
'#'. This script copies Cambria Math out of Microsoft Office's Cambria.ttc,
makes a second copy with those three slots remapped, and writes a JSON font map
for `extract_preview.py --font-map` (or the `font_map` key in a preset).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_OFFICE = Path("/Applications/Microsoft Word.app/Contents/Resources/DFonts")

# pdf2htmlEX font-family -> font file. "{office}" is the Office font folder and
# "{out}" is the folder this script writes generated fonts to.
GEA1000_FONTS = {
    "ff1": "{office}/Calibrib.ttf",  # bold headings
    "ff2": "{office}/Calibri.ttf",  # body text
    "ff3": "{office}/Calibri.ttf",
    "ff4": "{out}/CambriaMath.ttf",  # formulas
    "ff5": "{office}/Calibri.ttf",
    "ff6": "{out}/CambriaMathLegacyNumbers.ttf",  # formulas with the remapped 2/3/5
    "ff7": "{office}/Calibrii.ttf",  # italic
    "ff8": "{office}/Calibrib.ttf",
}
LEGACY_DIGITS = [("!", "2"), ('"', "3"), ("#", "5")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--office-fonts-dir", type=Path, default=DEFAULT_OFFICE)
    ap.add_argument("--fonts-out", type=Path, default=ROOT / "work/gea-fonts")
    ap.add_argument("--map-out", type=Path, default=ROOT / "gea-font-map.json")
    args = ap.parse_args(argv)

    office = args.office_fonts_dir
    cambria = office / "Cambria.ttc"
    if not cambria.exists():
        print(f"error: {cambria} not found. Install Microsoft Word, or pass --office-fonts-dir "
              "pointing at a folder with Cambria.ttc and the Calibri fonts.", file=sys.stderr)
        return 1

    from fontTools.ttLib import TTCollection

    out = args.fonts_out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    collection = TTCollection(cambria)
    math = next(f for f in collection.fonts
                if any(n.nameID == 1 and "Math" in n.toUnicode() for n in f["name"].names))
    math.save(out / "CambriaMath.ttf")
    best = math.getBestCmap()
    for table in math["cmap"].tables:
        if table.isUnicode():
            for source, target in LEGACY_DIGITS:
                table.cmap[ord(source)] = best[ord(target)]
    math.save(out / "CambriaMathLegacyNumbers.ttf")

    fonts = {k: v.format(office=office, out=out) for k, v in GEA1000_FONTS.items()}
    missing = [f for f in fonts.values() if not Path(f).exists()]
    if missing:
        print(f"error: fonts not found: {', '.join(missing)}", file=sys.stderr)
        return 1
    args.map_out.write_text(json.dumps(fonts, indent=2))
    print(f"Saved font map: {args.map_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
