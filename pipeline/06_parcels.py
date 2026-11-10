"""Join DOR NAL (tax roll) to DOR parcel polygons; write compact parcel points for the scoring model.
Usage: python3 -I 06_parcels.py <dor_zip_dir> <work_dir> <out_dir> <county> [...]
Output per county: <out_dir>/parcels_<county>.csv with
  pid, uc (DOR use code), yr (actual year built), units (res units, >=1 for residential),
  lot_sqft, addr, lat, lon, kind
kind: 'res' (residential, built 2010+), 'vacant_lot' (vacant residential < 0.5 ac),
      'commercial' (DOR use codes 011-039, any year; used to date store parcels)
Source: Florida Dept. of Revenue, 2026 Final NAL tax roll + 2026 parcel map (PIN) files.
"""
import sys, os, glob, re, zipfile
import pandas as pd, geopandas as gpd, pyogrio

RES_UC = {'001', '002', '003', '004', '005', '006', '007', '008'}  # SFR, mobile, MF10+, condo, coop, retirement, misc res, MF<10
VACANT_RES = '000'

def norm(s):
    return re.sub(r'[^0-9A-Z]', '', str(s).upper())

def find(zdir, county, kind):
    key = county.lower().replace(' ', '')
    for p in glob.glob(os.path.join(zdir, '*.zip')):
        n = os.path.basename(p).lower().replace(' ', '').replace('_', '')
        if kind == 'nal' and n.startswith(key) and 'nal' in n: return p
        if kind == 'pin' and n.startswith(key.replace('saint', 'st')) and 'pin' in n: return p
    raise FileNotFoundError(f'{county} {kind}')

def main(zdir, work, out, counties):
    os.makedirs(out, exist_ok=True)
    for county in counties:
        cdir = os.path.join(work, county.lower().replace(' ', '_')); os.makedirs(cdir, exist_ok=True)
        for kind in ('nal', 'pin'):
            with zipfile.ZipFile(find(zdir, county, kind)) as z: z.extractall(cdir)
        nal_csv = glob.glob(os.path.join(cdir, '**', 'NAL*.csv'), recursive=True)[0]
        shp = [p for p in glob.glob(os.path.join(cdir, '**', '*.shp'), recursive=True) if 'pin' in p.lower()][0]
        nal = pd.read_csv(nal_csv, usecols=['PARCEL_ID', 'DOR_UC', 'ACT_YR_BLT', 'NO_RES_UNTS', 'LND_SQFOOT', 'PHY_ADDR1', 'PHY_CITY'],
                          dtype=str, encoding_errors='replace')
        nal['uc'] = nal.DOR_UC.str.zfill(3)
        nal['yr'] = pd.to_numeric(nal.ACT_YR_BLT, errors='coerce')
        nal['units'] = pd.to_numeric(nal.NO_RES_UNTS, errors='coerce')
        nal['lot_sqft'] = pd.to_numeric(nal.LND_SQFOOT, errors='coerce')
        ucn = pd.to_numeric(nal.uc, errors='coerce')
        res = nal.uc.isin(RES_UC) & (nal.yr >= 2010)
        vac = (nal.uc == VACANT_RES) & (nal.lot_sqft > 0) & (nal.lot_sqft < 21780)
        com = ucn.between(11, 39)
        nal['kind'] = None
        nal.loc[res, 'kind'] = 'res'; nal.loc[vac, 'kind'] = 'vacant_lot'; nal.loc[com, 'kind'] = 'commercial'
        nal = nal[nal.kind.notna()].copy()
        nal.loc[nal.kind == 'res', 'units'] = nal.loc[nal.kind == 'res', 'units'].fillna(1).clip(lower=1)
        nal['key'] = nal.PARCEL_ID.map(norm)
        pin = pyogrio.read_dataframe(shp)
        idcol = [c for c in pin.columns if c != 'geometry'][0]
        pin['key'] = pin[idcol].map(norm)
        pin = pin[pin.key.isin(set(nal.key))]
        pts = pin.copy(); pts['geometry'] = pin.geometry.representative_point()
        pts = pts.to_crs(4326)
        pts['lat'] = pts.geometry.y; pts['lon'] = pts.geometry.x
        pts = pts.drop_duplicates('key')[['key', 'lat', 'lon']]
        m = nal.merge(pts, on='key', how='left')
        unmatched = m.lat.isna().mean()
        m = m[m.lat.notna()]
        m = m.rename(columns={'PARCEL_ID': 'pid', 'PHY_ADDR1': 'addr', 'PHY_CITY': 'city'})
        m[['pid', 'uc', 'yr', 'units', 'lot_sqft', 'addr', 'city', 'lat', 'lon', 'kind']].to_csv(
            os.path.join(out, f"parcels_{county.lower().replace(' ', '_')}.csv"), index=False)
        print(county, m.groupby('kind').size().to_dict(), f'unmatched to map: {unmatched:.1%}',
              'res units built 2023-2025:', int(m[(m.kind == 'res') & (m.yr >= 2023)].units.sum()))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:])
