"""Before/after aerials for build-to-suit sites from Esri World Imagery Wayback.
Usage: python3 -I 14_wayback_pairs.py <bts_sites.csv> <img_dir> [years_before=2]
For each located site: 'before' = newest Wayback release dated on or before Dec 31 of (year built - years_before);
'after' = newest release. Each image is a 3x3 block of zoom-18 tiles (~450 m across) centred on the site, with a
crosshair at the site pin. Writes <img_dir>/<idx>_before.jpg, <idx>_after.jpg and <img_dir>/releases_used.csv.
"""
import sys, os, re, io, math, requests, pandas as pd
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw

WMTS = "https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/WMTSCapabilities.xml"
TILE = "https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/{rel}/{z}/{y}/{x}"
Z = 18
UA = {'User-Agent': 'ECP-site-research/1.0'}

def releases():
    x = requests.get(WMTS, headers=UA, timeout=60).text
    rels = []
    for m in re.finditer(r'<ows:Title>World Imagery \(Wayback (\d{4}-\d{2}-\d{2})\)</ows:Title>.*?tile/(\d+)/', x, re.S):
        rels.append((m.group(1), int(m.group(2))))
    return sorted(set(rels))

def tile_xy(lat, lon, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y

def mosaic(lat, lon, rel):
    fx, fy = tile_xy(lat, lon, Z); cx, cy = int(fx), int(fy)
    img = Image.new('RGB', (768, 768))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            r = requests.get(TILE.format(rel=rel, z=Z, y=cy + dy, x=cx + dx), headers=UA, timeout=60)
            if r.ok and r.content[:2] in (b'\xff\xd8', b'\x89P'):
                img.paste(Image.open(io.BytesIO(r.content)).convert('RGB'), ((dx + 1) * 256, (dy + 1) * 256))
    px, py = (fx - cx + 1) * 256, (fy - cy + 1) * 256
    d = ImageDraw.Draw(img)
    for r_ in (14, 15):
        d.ellipse([px - r_, py - r_, px + r_, py + r_], outline=(255, 40, 40))
    d.line([px - 30, py, px - 18, py], fill=(255, 40, 40), width=2); d.line([px + 18, py, px + 30, py], fill=(255, 40, 40), width=2)
    d.line([px, py - 30, px, py - 18], fill=(255, 40, 40), width=2); d.line([px, py + 18, px, py + 30], fill=(255, 40, 40), width=2)
    return img

def main(csv, out, years_before=2):
    os.makedirs(out, exist_ok=True)
    rels = releases(); print(len(rels), 'releases', rels[0], rels[-1])
    sites = pd.read_csv(csv)
    used = []
    for i, s in sites.iterrows():
        if pd.isna(s.lat): continue
        try: yb = int(str(s.year_built)[:4])
        except ValueError: yb = int(str(s.date)[:4])
        cutoff = f'{yb - years_before}-12-31'
        before = [r for r in rels if r[0] <= cutoff]
        if not before: before = rels[:1]
        b, a = before[-1], rels[-1]
        for tag, rel in (('before', b), ('after', a)):
            p = os.path.join(out, f'{i:03d}_{tag}.jpg')
            if not os.path.exists(p): mosaic(s.lat, s.lon, rel[1]).save(p, quality=82)
        used.append(dict(idx=i, year_built=yb, before_release=b[0], after_release=a[0]))
        if i % 20 == 0: print('done', i)
    pd.DataFrame(used).to_csv(os.path.join(out, 'releases_used.csv'), index=False)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 2)
