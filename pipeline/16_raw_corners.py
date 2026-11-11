"""Raw-land corner test (Ross, Nov 11, 2026): a candidate keeps its place by default only if a raw parcel of
1.3+ acres touches the intersection. Backed by the BTS land check: ~72% of Florida 7-Eleven build-to-suits
(rent >= $350K) were built on raw land.

Raw parcel (FL DOR 2026 tax roll + parcel map):
  - DOR use code vacant residential 000, vacant commercial 010, vacant industrial 040, vacant institutional 070,
    acreage not zoned ag 099 -> must have no buildings (NO_BULDNG 0/blank)
  - agricultural 050-069 (cropland, timber, grazing, orchards, etc.) -> farm buildings allowed
  - land area >= 1.3 ac (LND_SQFOOT, or polygon area when blank)
  - excluded: public land, conservation land, and owners that are governments, school boards, CDDs or HOAs
    (common areas / ponds), parcels with just value under $5,000, and non-ag parcels under $15,000/acre just value
    (ponds, buffers, common-area remnants). Value is used only to screen out those remnants, never to score.
"Touches the intersection" = parcel polygon within 50 m of the intersection point (corner lots sit behind
road right-of-way). Usage:
  python3 -I 16_raw_corners.py <dor_extract_dir> <out_dir> <candidates.csv> <result.csv> <county> [...]
"""
import sys, os, glob, re
import numpy as np, pandas as pd, geopandas as gpd, pyogrio

RAW_VACANT = {'000', '010', '040', '070', '099'}
AG = {f'{i:03d}' for i in range(50, 70)}
USE = {'000': 'Vacant residential', '010': 'Vacant commercial', '040': 'Vacant industrial', '070': 'Vacant institutional',
       '099': 'Acreage, not ag', '051': 'Cropland', '052': 'Cropland', '053': 'Cropland', '054': 'Timberland', '055': 'Timberland',
       '056': 'Timberland', '057': 'Timberland', '058': 'Timberland', '059': 'Timberland', '060': 'Grazing land', '061': 'Grazing land',
       '062': 'Grazing land', '063': 'Grazing land', '064': 'Grazing land', '065': 'Grazing land', '066': 'Orchard/groves',
       '067': 'Poultry/bees/fish', '068': 'Dairy/feed lot', '069': 'Ornamentals/misc ag', '050': 'Improved agricultural'}
BAD_OWNER = re.compile(r'\b(COUNTY|CITY OF|TOWN OF|STATE OF|BOARD|DISTRICT|CDD|HOMEOWNERS|HOME OWNERS|ASSOCIATION|ASSN|HOA|POA|'
                       r'DEPT|DEPARTMENT|UNITED STATES|AUTHORITY|TRUSTEES OF THE INTERNAL|COMMUNITY DEVELOPMENT|UTILITIES|WATER MANAGEMENT)\b')
MIN_SQFT = 1.3 * 43560
TOUCH_M = 50

def norm(s): return re.sub(r'[^0-9A-Z]', '', str(s).upper())

def raw_parcels(cdir):
    nal_csv = glob.glob(os.path.join(cdir, '**', 'NAL*.csv'), recursive=True)[0]
    shp = [p for p in glob.glob(os.path.join(cdir, '**', '*.shp'), recursive=True) if 'pin' in p.lower()][0]
    n = pd.read_csv(nal_csv, usecols=['PARCEL_ID', 'DOR_UC', 'JV', 'LND_SQFOOT', 'NO_BULDNG', 'PUBLIC_LND', 'JV_CONSRV_LND', 'OWN_NAME', 'PHY_ADDR1'],
                    dtype=str, encoding_errors='replace')
    n['uc'] = n.DOR_UC.str.zfill(3)
    for c in ['JV', 'LND_SQFOOT', 'NO_BULDNG', 'JV_CONSRV_LND']: n[c] = pd.to_numeric(n[c], errors='coerce')
    vac = n.uc.isin(RAW_VACANT) & (n.NO_BULDNG.fillna(0) == 0)
    ag = n.uc.isin(AG)
    keep = (vac | ag) & (n.JV.fillna(0) >= 5000) & n.PUBLIC_LND.isna() & (n.JV_CONSRV_LND.fillna(0) == 0) \
           & ~n.OWN_NAME.fillna('').str.upper().str.contains(BAD_OWNER)
    n = n[keep].copy(); n['key'] = n.PARCEL_ID.map(norm)
    pin = pyogrio.read_dataframe(shp)
    idcol = [c for c in pin.columns if c != 'geometry'][0]
    pin['key'] = pin[idcol].map(norm)
    pin = pin[pin.key.isin(set(n.key))].to_crs(3086)
    pin = pin.dissolve(by='key').reset_index()
    g = pin.merge(n, on='key')
    g['acres'] = np.where(g.LND_SQFOOT > 0, g.LND_SQFOOT, g.geometry.area * 10.7639) / 43560
    g = g[g.acres >= MIN_SQFT / 43560]
    # ponds, buffers and other common-area remnants carry very low values; real non-ag land doesn't
    g = g[g.uc.isin(AG) | (g.JV / g.acres >= 15000)]
    return g[['PARCEL_ID', 'uc', 'acres', 'OWN_NAME', 'PHY_ADDR1', 'geometry']]

def main(dor_x, out, cand_csv, result, counties):
    raw = pd.concat([raw_parcels(os.path.join(dor_x, c.lower().replace(' ', '_'))) for c in counties], ignore_index=True)
    raw = gpd.GeoDataFrame(raw, geometry='geometry', crs=3086)
    print('raw parcels >= 1.3 ac:', len(raw))
    c = pd.read_csv(cand_csv)
    g = gpd.GeoDataFrame(c, geometry=gpd.points_from_xy(c.lon, c.lat), crs=4326).to_crs(3086)
    j = gpd.sjoin(g[['geometry']].assign(i=g.index).set_geometry(g.buffer(TOUCH_M)), raw, predicate='intersects')
    j = j.sort_values('acres', ascending=False)
    agg = j.groupby('i').agg(raw_parcels=('PARCEL_ID', 'nunique'), raw_best_acres=('acres', 'first'), raw_best_use=('uc', 'first'),
                             raw_best_parcel=('PARCEL_ID', 'first'), raw_best_owner=('OWN_NAME', 'first'), raw_best_addr=('PHY_ADDR1', 'first'))
    c = c.join(agg)
    c['raw_corner'] = c.raw_parcels.fillna(0) > 0
    c['raw_parcels'] = c.raw_parcels.fillna(0).astype(int)
    c['raw_best_use'] = c.raw_best_use.map(USE).fillna(c.raw_best_use)
    c['raw_best_acres'] = c.raw_best_acres.round(2)
    c.to_csv(result, index=False)
    print('candidates', len(c), '| with a raw 1.3+ ac corner parcel', int(c.raw_corner.sum()))
    print(c.groupby('county').raw_corner.agg(['sum', 'count']).to_string())

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:])
