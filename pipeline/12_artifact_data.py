"""Export compact JSON data files for the 7-Eleven Target Area Finder artifact.
Usage: python3 -I 12_artifact_data.py <out_dir> <source.xlsx> <step2.xlsx> <artifact_data_dir>
"""
import sys, os, glob, json, hashlib
import numpy as np, pandas as pd, geopandas as gpd

PILOT = {'Duval': 'Bauer', 'St Johns': 'Bauer', 'Clay': 'Bauer', 'Volusia': 'Bauer', 'Brevard': 'Bauer',
         'Pasco': 'Golden', 'Hillsborough': 'Golden', 'St Lucie': 'Antonacci'}
WEIGHTS = {'new_rooftops': 30, 'rooftop_pipeline': 5, 'new_grocery': 10, 'traffic': 25, 'gap_to_7eleven': 10, 'retail_node': 10, 'signal': 10}
FC_NAME = {'04': 'Rural principal arterial', '06': 'Rural minor arterial', '07': 'Rural major collector', '08': 'Rural minor collector',
           '14': 'Urban principal arterial', '16': 'Urban minor arterial', '17': 'Urban major collector', '18': 'Urban minor collector',
           '01': 'Interstate', '11': 'Interstate', '02': 'Expressway', '12': 'Expressway'}

def clean(v):
    if isinstance(v, (float, np.floating)):
        return None if np.isnan(v) else round(float(v), 5)
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.bool_,)): return bool(v)
    return v

def recs(df, cols):
    return [{c: clean(r[c]) for c in cols} for _, r in df.iterrows()]

def dump(obj, path):
    json.dump(obj, open(path, 'w'), separators=(',', ':'))
    print(os.path.basename(path), round(os.path.getsize(path) / 1e3), 'KB')

def main(out, src_xlsx, step2_xlsx, dest):
    os.makedirs(dest, exist_ok=True)
    counties = gpd.read_file(os.path.join(out, 'fl_counties.geojson'))[['NAME', 'geometry']].rename(columns={'NAME': 'county'})
    pilot = counties[counties.county.isin(PILOT)]
    minx, miny, maxx, maxy = pilot.total_bounds
    pad = 0.12
    inbox = lambda df: df[(df.lon > minx - pad) & (df.lon < maxx + pad) & (df.lat > miny - pad) & (df.lat < maxy + pad)]

    # candidates
    c = pd.read_csv(os.path.join(out, 'candidates_scored_optionB.csv'))
    c['id'] = [hashlib.md5(f'{a:.4f},{b:.4f}'.encode()).hexdigest()[:10] for a, b in zip(c.lat, c.lon)]
    top_ids = set(pd.read_excel(step2_xlsx, sheet_name='Top 50 (Option B)').pipe(lambda t: [hashlib.md5(f'{a:.4f},{b:.4f}'.encode()).hexdigest()[:10] for a, b in zip(t.lat, t.lon)]))
    c['top50'] = c.id.isin(top_ids)
    c['signal'] = np.where(c.fdot_signal, 'Yes', np.where(c.signal_unknown, 'Unknown', 'No'))
    cols = ['id', 'rank', 'score', 'tier', 'top50', 'intersection_name', 'county', 're_manager', 'market_type', 'why_here', 'new_rooftops_3mi',
            'pipeline_lots_3mi', 'new_grocers_3mi', 'combined_aadt', 'signal', 'dist_to_7eleven_mi', 'nearest_7eleven', 'anchors_half_mi',
            'nationals_half_mi', 'nearest_competitor', 'access_flag', 'max_trucks_per_day'] + ['pts_' + k for k in WEIGHTS] + ['lat', 'lon']
    c['access_flag'] = c.access_flag.fillna('')
    dump(recs(c, cols), os.path.join(dest, 'candidates.json'))

    # 7-Eleven stores (pilot rows carry vintage; context stores just outside the pilot are included without it)
    net = pd.read_excel(src_xlsx, sheet_name='7-Eleven Network', dtype={'store_ref': str})
    se = pd.read_csv(os.path.join(out, 'seven_eleven_fl.csv'), dtype={'store_ref': str})
    se = inbox(se)
    for d in (se, net): d['lat'], d['lon'] = d.lat.round(5), d.lon.round(5)
    net = net.drop_duplicates(['store_ref', 'lat', 'lon'])
    se = se.merge(net[['store_ref', 'lat', 'lon', 'vintage (inferred)', 'parcel_year_built (inferred store age)']], on=['store_ref', 'lat', 'lon'], how='left')
    se = se.rename(columns={'vintage (inferred)': 'vintage', 'parcel_year_built (inferred store age)': 'year_built'})
    se['vintage'] = se.vintage.fillna('Outside pilot')
    se['source_short'] = np.where(se.in_7eleven_api == 'Y', np.where(se.in_fdep == 'Y', 'FDEP + 7-Eleven API', '7-Eleven API'), 'FDEP')
    dump(recs(se, ['brand', 'address', 'city', 'county', 'has_fuel', 'vintage', 'year_built', 'tracker_tab', 'source_short', 'lat', 'lon']), os.path.join(dest, 'stores.json'))

    # competitors (FDEP)
    fd = pd.read_csv(os.path.join(out, 'fdep_stations_fl.csv'))
    comp = inbox(fd[fd.category == 'Competitor'])
    dump(recs(comp, ['brand', 'name', 'address', 'city', 'lat', 'lon']), os.path.join(dest, 'competitors.json'))

    # anchors & grocers
    st = gpd.read_file(os.path.join(out, 'stores_fl.geojson'))
    st = st[st.category.isin(['Grocer', 'Anchor', 'National QSR/retail'])]
    st = inbox(pd.DataFrame(st.drop(columns='geometry')))
    dump(recs(st, ['category', 'brand', 'street', 'city', 'lat', 'lon']), os.path.join(dest, 'anchors.json'))

    # counties: all FL (light outline) with pilot flag + manager
    counties['manager'] = counties.county.map(PILOT)
    counties['pilot'] = counties.county.isin(PILOT)
    cs = counties.copy(); cs['geometry'] = cs.geometry.simplify(0.003, preserve_topology=True)
    dump(json.loads(cs.to_json()), os.path.join(dest, 'counties.json'))

    # roads (pilot arterials/collectors + interstates for orientation)
    fc = gpd.read_file(os.path.join(out, 'fdot', 'fdot_funclass.geojson'))
    fc = fc[fc.FUNCLASS.isin(FC_NAME)]
    names = gpd.read_file(os.path.join(out, 'fdot', 'fdot_localnames.geojson'))
    nm = names.groupby('ROADWAY').NAME.agg(lambda s: s.mode().iloc[0] if len(s) else '').to_dict()
    fc['cls'] = fc.FUNCLASS.map(lambda x: 'interstate' if x in ('01', '11', '02', '12') else ('arterial' if x in ('04', '06', '14', '16') else 'collector'))
    fc['name'] = fc.ROADWAY.map(nm).fillna('')
    fc['geometry'] = fc.geometry.simplify(0.0003, preserve_topology=False)
    fc = fc[~fc.geometry.is_empty]
    dump(json.loads(fc[['cls', 'name', 'geometry']].to_json()), os.path.join(dest, 'roads.json'))

    # rooftop growth grid (1 km cells, units built 2023-2025, apartments/condos at half)
    parcels = pd.concat([pd.read_csv(p, dtype={'uc': str}, usecols=['uc', 'yr', 'units', 'lat', 'lon', 'kind']) for p in glob.glob(os.path.join(out, 'parcels', 'parcels_*.csv'))])
    r = parcels[(parcels.kind == 'res') & (parcels.yr >= 2023)].copy()
    r['w'] = np.where(r.uc.isin(['003', '004', '005', '008']), r.units * 0.5, r.units)
    g = gpd.GeoDataFrame(r, geometry=gpd.points_from_xy(r.lon, r.lat), crs=4326).to_crs(3086)
    g['cx'] = (g.geometry.x // 1000) * 1000 + 500; g['cy'] = (g.geometry.y // 1000) * 1000 + 500
    cells = g.groupby(['cx', 'cy']).w.sum().reset_index()
    cells = cells[cells.w >= 5]
    cg = gpd.GeoDataFrame(cells, geometry=gpd.points_from_xy(cells.cx, cells.cy), crs=3086).to_crs(4326)
    dump([[round(p.y, 4), round(p.x, 4), int(w)] for p, w in zip(cg.geometry, cg.w)], os.path.join(dest, 'rooftops.json'))

    # backtest stores + meta
    x = pd.read_excel(step2_xlsx, sheet_name=None)
    bt = x['Backtest Stores']
    dump(recs(bt, ['address', 'city', 'county', 'score', 'pct_rank_vs_all_intersections', 'new_rooftops_3mi', 'combined_aadt', 'market_type']), os.path.join(dest, 'backtest.json'))
    meta = {
        'built': pd.Timestamp.today().strftime('%Y-%m-%d'),
        'weights': WEIGHTS,
        'pilot': PILOT,
        'counts': {'intersections': 2459, 'candidates': int(len(c)), 'tierA': int((c.tier == 'A').sum()), 'tierB': int((c.tier == 'B').sum()),
                   'stores_pilot': int(len(net)), 'competitors': int(len(comp))},
        'weight_options': recs(x['Weight Options'].dropna(subset=['Weights']).iloc[:2], list(x['Weight Options'].columns[:7])),
        'method': recs(x['Method & Weights'], ['Item', 'Method']),
        'sources': recs(pd.read_excel(src_xlsx, sheet_name='Sources & Dates'), ['Dataset', 'Source', 'As of', 'Data class']),
        'gaps': recs(pd.read_excel(src_xlsx, sheet_name='Data Gaps'), ['Gap', 'Detail', 'Fix']),
    }
    dump(meta, os.path.join(dest, 'meta.json'))

if __name__ == '__main__':
    main(*sys.argv[1:5])
