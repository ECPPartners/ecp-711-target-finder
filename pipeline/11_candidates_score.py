"""Step 2: candidate intersections, factor scoring, hard filters, tiers, and backtest.
Usage: python3 -I 11_candidates_score.py <out_dir> <source_workbook.xlsx> <result.xlsx>
All distances computed in EPSG:3086 (Florida GDL Albers, meters).
Weights and rules: Tool Spec v1.0 (approved by Ross, Nov 3, 2026).
"""
import sys, os, glob, re, json
import numpy as np, pandas as pd, geopandas as gpd
from scipy.spatial import cKDTree
from shapely.geometry import Point

MI = 1609.344
PILOT = {'Duval': 'Bauer', 'St Johns': 'Bauer', 'Clay': 'Bauer', 'Volusia': 'Bauer', 'Brevard': 'Bauer',
         'Pasco': 'Golden', 'Hillsborough': 'Golden', 'St Lucie': 'Antonacci', 'Polk': 'Polk'}
WEIGHTS = {'new_rooftops': 30, 'rooftop_pipeline': 10, 'new_grocery': 15, 'traffic': 15, 'gap_to_7eleven': 10,
           'retail_node': 10, 'signal': 10}
KEEP_FC = {'04', '06', '07', '08', '14', '16', '17', '18'}   # arterials + collectors; no interstates/expressways/locals
RESTRICTIVE_MEDIAN = {'02', '03', '06', '08', '13', '17', '22', '31', '32', '34'}
GROCERS = {'Publix', 'Aldi', 'Winn-Dixie', 'Whole Foods', "Trader Joe's", 'Sprouts'}
ANCHORS = {'Walmart', 'Publix', 'Target', 'Home Depot', "Lowe's", 'Costco', "Sam's Club", 'Aldi', 'Winn-Dixie', 'Tractor Supply'}
NATIONALS = {"McDonald's", 'Starbucks', 'Dollar General'}
OPTS = json.loads(os.environ.get('SCORE_OPTS', '{}'))   # e.g. {"weights": {...}, "mf_weight": 0.5}
WEIGHTS = OPTS.get('weights', WEIGHTS)
MF_WEIGHT = OPTS.get('mf_weight', 1.0)   # weight per multifamily/condo unit in the rooftop count
TODAY = pd.Timestamp.today().strftime('%Y-%m-%d')

def xy(g): return np.c_[g.geometry.x.values, g.geometry.y.values]

def load(out, wb):
    counties = gpd.read_file(os.path.join(out, 'fl_counties.geojson'))[['NAME', 'geometry']].rename(columns={'NAME': 'county'}).to_crs(3086)
    fc = gpd.read_file(os.path.join(out, 'fdot', 'fdot_funclass.geojson')).to_crs(3086)
    limited = set(fc[fc.FUNCLASS.isin({'01', '02', '11', '12'})].ROADWAY)   # interstates / expressways
    fc = fc[fc.FUNCLASS.isin(KEEP_FC)].reset_index(drop=True)
    names = gpd.read_file(os.path.join(out, 'fdot', 'fdot_localnames.geojson')).to_crs(3086)
    aadt = gpd.read_file(os.path.join(out, 'fdot', 'fdot_aadt.geojson')).to_crs(3086)
    aadt = aadt[~aadt.ROADWAY.isin(limited)]   # a corner can't take access from an interstate; don't count its traffic
    sig = gpd.read_file(os.path.join(out, 'fdot', 'fdot_signals.geojson')).to_crs(3086)
    med = gpd.read_file(os.path.join(out, 'fdot', 'fdot_median.geojson')).to_crs(3086)
    parcels = pd.concat([pd.read_csv(p, dtype={'pid': str, 'uc': str}) for p in glob.glob(os.path.join(out, 'parcels', 'parcels_*.csv'))])
    parcels = gpd.GeoDataFrame(parcels, geometry=gpd.points_from_xy(parcels.lon, parcels.lat), crs=4326).to_crs(3086)
    se = pd.read_csv(os.path.join(out, 'seven_eleven_fl.csv'))
    se = gpd.GeoDataFrame(se, geometry=gpd.points_from_xy(se.lon, se.lat), crs=4326).to_crs(3086)
    net = pd.read_excel(wb, sheet_name='7-Eleven Network', dtype={'store_ref': str})
    stores = gpd.read_file(os.path.join(out, 'stores_fl.geojson')).to_crs(3086)
    fd = pd.read_csv(os.path.join(out, 'fdep_stations_fl.csv'))
    comp = fd[fd.category == 'Competitor']
    comp = gpd.GeoDataFrame(comp, geometry=gpd.points_from_xy(comp.lon, comp.lat), crs=4326).to_crs(3086)
    return counties, fc, names, aadt, sig, med, parcels, se, net, stores, comp

def intersections(fc, names):
    j = gpd.sjoin(fc[['ROADWAY', 'geometry']], fc[['ROADWAY', 'geometry']], predicate='intersects')
    j = j[j.index < j.index_right]
    j = j[j.ROADWAY_left != j.ROADWAY_right]
    pts = []
    for i, r in j.iterrows():
        a, b = fc.geometry[i], fc.geometry[r.index_right]
        inter = a.intersection(b)
        geoms = getattr(inter, 'geoms', [inter])
        for p in geoms:
            if p.geom_type != 'Point': p = p.representative_point()
            # skip pure continuations: point must be interior (>25 m from both ends) of at least one road
            interior = any(min(p.distance(Point(l.coords[0])), p.distance(Point(l.coords[-1]))) > 25 for l in (a, b))
            if interior: pts.append((p.x, p.y, r.ROADWAY_left, r.ROADWAY_right))
    df = pd.DataFrame(pts, columns=['x', 'y', 'r1', 'r2'])
    # cluster points within 150 m (divided roads, offset legs)
    tree = cKDTree(df[['x', 'y']].values); seen = np.zeros(len(df), bool); rows = []
    for i in range(len(df)):
        if seen[i]: continue
        idx = [k for k in tree.query_ball_point(df.loc[i, ['x', 'y']].values, 150) if not seen[k]]
        seen[idx] = True
        sub = df.loc[idx]
        rows.append(dict(x=sub.x.mean(), y=sub.y.mean(), roadways=sorted(set(sub.r1) | set(sub.r2))))
    cand = gpd.GeoDataFrame(rows, geometry=gpd.points_from_xy([r['x'] for r in rows], [r['y'] for r in rows]), crs=3086)
    # names: nearest local-name segment for each roadway
    def road_name(rid, p):
        n = names[names.ROADWAY == rid]
        if n.empty: return None
        d = n.distance(p)
        return n.loc[d.idxmin(), 'NAME'] if d.min() < 80 else n.NAME.mode().iloc[0]
    labels = []
    for _, c in cand.iterrows():
        nm = [road_name(r, c.geometry) or f'FDOT {r}' for r in c.roadways]
        uniq, keys = [], set()
        for n in nm:
            k = re.sub(r'[^A-Z0-9]', '', n.upper())
            if k not in keys: keys.add(k); uniq.append(n)
        labels.append(' & '.join(uniq[:3]))
    cand['intersection_name'] = labels
    cand = cand[cand['intersection_name'].str.contains('&')]   # same-name continuations dropped
    return cand.reset_index(drop=True)

def factors(pts, ctx, exclude_store=None, road_radius=60, signal_radius=60):
    """Compute raw factor values for points (GeoDataFrame in 3086)."""
    (res_tree, res_w), lot_tree, groc_tree, se_fuel, anchor_df, aadt, sig, sig_roads, med, comp, newbuild_xy = ctx
    P = xy(pts); out = pd.DataFrame(index=pts.index)
    out['new_rooftops_3mi'] = [res_w[ix].sum() for ix in res_tree.query_ball_point(P, 3 * MI)]
    out['pipeline_lots_3mi'] = [len(ix) for ix in lot_tree.query_ball_point(P, 3 * MI)]
    out['new_grocers_3mi'] = [len(ix) for ix in groc_tree.query_ball_point(P, 3 * MI)] if groc_tree else 0
    # nearest 7-Eleven family fuel store (optionally excluding the store being backtested)
    fx = xy(se_fuel); t = cKDTree(fx)
    d, i = t.query(P, k=2)
    if exclude_store is not None:
        own = exclude_store.values
        d1 = np.where(se_fuel.index.values[i[:, 0]] == own, d[:, 1], d[:, 0])
        i1 = np.where(se_fuel.index.values[i[:, 0]] == own, i[:, 1], i[:, 0])
    else:
        d1, i1 = d[:, 0], i[:, 0]
    out['dist_to_7eleven_mi'] = d1 / MI
    out['nearest_7eleven'] = (se_fuel.address.values[i1] + ', ' + se_fuel.city.values[i1])
    # traffic: max AADT per FDOT roadway within radius, sum of top two roadways
    a = gpd.sjoin(pts[['geometry']].assign(pid=pts.index).set_geometry(pts.buffer(road_radius)), aadt[['ROADWAY', 'AADT', 'TFCTR', 'geometry']], predicate='intersects')
    per = a.groupby(['pid', 'ROADWAY']).AADT.max().reset_index().sort_values('AADT', ascending=False)
    out['combined_aadt'] = per.groupby('pid').AADT.apply(lambda s: s.head(2).sum())
    a['trucks'] = a.AADT * a.TFCTR / 100
    out['max_trucks_per_day'] = a.groupby('pid').trucks.max().round()
    # signal
    s = gpd.sjoin(pts[['geometry']].assign(pid=pts.index).set_geometry(pts.buffer(signal_radius)), sig[['geometry']], predicate='intersects')
    out['fdot_signal'] = out.index.isin(s.pid)
    # median
    m = gpd.sjoin(pts[['geometry']].assign(pid=pts.index).set_geometry(pts.buffer(40)), med[['MEDIAN_TYP', 'geometry']], predicate='intersects')
    out['restrictive_median'] = out.index.isin(m[m.MEDIAN_TYP.isin(RESTRICTIVE_MEDIAN)].pid)
    # retail node within 1/2 mile
    at = cKDTree(xy(anchor_df))
    anc_b, nat_b = [], []
    for ix in at.query_ball_point(P, 0.5 * MI):
        b = set(anchor_df.brand.values[ix])
        anc_b.append(sorted(b & ANCHORS)); nat_b.append(sorted(b & NATIONALS))
    out['anchors_half_mi'] = [', '.join(x) for x in anc_b]; out['n_anchors'] = [len(x) for x in anc_b]
    out['nationals_half_mi'] = [', '.join(x) for x in nat_b]; out['n_nationals'] = [len(x) for x in nat_b]
    # competitors
    ct = cKDTree(xy(comp))
    dc, ic = ct.query(P)
    out['nearest_competitor'] = comp.brand.values[ic] + ' (' + (dc / MI).round(2).astype(str) + ' mi)'
    out['competitor_within_0.15mi'] = dc < 0.15 * MI
    # proven vs white space: a 2018+ 7-Eleven build within 5 miles
    nb = cKDTree(newbuild_xy)
    out['market_type'] = np.where(nb.query(P)[0] <= 5 * MI, 'Proven (7-Eleven built here since 2018)', 'White space')
    return out

def score(f, ref=None):
    """Turn raw factors into 0-1 scores and a 0-100 total. ref = reference population for percentiles."""
    ref = f if ref is None else ref
    def pct(col, val):
        r = ref[col].dropna().values
        return pd.Series(np.searchsorted(np.sort(r), val.fillna(-1).values, side='right') / max(len(r), 1), index=val.index)
    s = pd.DataFrame(index=f.index)
    s['new_rooftops'] = pct('new_rooftops_3mi', f.new_rooftops_3mi)
    s['rooftop_pipeline'] = pct('pipeline_lots_3mi', f.pipeline_lots_3mi)
    s['new_grocery'] = np.clip(f.new_grocers_3mi, 0, 2) / 2
    s['traffic'] = np.where(f.combined_aadt.isna(), 0.5, pct('combined_aadt', f.combined_aadt))
    s['gap_to_7eleven'] = np.clip((f.dist_to_7eleven_mi - 2) / 3, 0, 1)
    s['retail_node'] = 0.6 * np.clip(f.n_anchors, 0, 2) / 2 + 0.4 * np.clip(f.n_nationals, 0, 3) / 3
    s['signal'] = np.where(f.fdot_signal, 1.0, np.where(f.signal_unknown, 0.5, 0.0))
    total = sum(s[k] * w for k, w in WEIGHTS.items())
    return s, total.round(1)

def main(out, wb, result):
    counties, fc, names, aadt, sig, med, parcels, se, net, stores, comp = load(out, wb)
    print('roads', len(fc))
    cand = intersections(fc, names)
    cand = gpd.sjoin(cand, counties, how='inner', predicate='within').drop(columns='index_right')
    cand = cand[cand.county.isin(PILOT)].reset_index(drop=True)
    print('candidate intersections in pilot', len(cand))

    res = parcels[(parcels.kind == 'res') & (parcels.yr >= 2023)].copy()
    res['units'] = np.where(res.uc.isin(['003', '004', '005', '008']), res.units * MF_WEIGHT, res.units)
    lots = parcels[parcels.kind == 'vacant_lot']
    com = parcels[parcels.kind == 'commercial']
    groc = stores[stores.brand.isin(GROCERS)]
    gy = gpd.sjoin_nearest(groc, com[['yr', 'geometry']], max_distance=60, how='left')
    gy = gy[~gy.index.duplicated()]
    new_groc = gy[gy.yr >= 2023]
    se_fuel = se[se.has_fuel == 'Y'].copy()
    netg = gpd.GeoDataFrame(net, geometry=gpd.points_from_xy(net.lon, net.lat), crs=4326).to_crs(3086)
    newbuilds = netg[netg['vintage (inferred)'] == 'New build (2018+)']
    sig_roads = set(sig.RDWYID.astype(str))
    ctx = ((cKDTree(xy(res)), res.units.values), cKDTree(xy(lots)), cKDTree(xy(new_groc)) if len(new_groc) else None,
           se_fuel, stores[stores.brand.isin(ANCHORS | NATIONALS)], aadt, sig, sig_roads, med, comp, xy(newbuilds))

    f = factors(cand, ctx)
    f['signal_unknown'] = [(not s) and not any(str(r) in sig_roads for r in rw) for s, rw in zip(f.fdot_signal, cand.roadways)]
    s, total = score(f)
    cand = pd.concat([cand, f, s.add_prefix('pts_'), total.rename('score')], axis=1)
    for k, w in WEIGHTS.items(): cand['pts_' + k] = (cand['pts_' + k] * w).round(1)

    # backtest: score 2018+ pilot builds as if they were candidates, against ALL intersections (before the 2-mile filter)
    bt = newbuilds.copy()
    match = gpd.sjoin_nearest(bt[['geometry']], se_fuel[['geometry']], max_distance=200, how='left')
    match = match[~match.index.duplicated()]
    bf = factors(bt, ctx, exclude_store=match.index_right.fillna(-1).astype(int), road_radius=150, signal_radius=150)
    bf['signal_unknown'] = ~bf.fdot_signal
    bs, btotal = score(bf, ref=f)
    bt = pd.concat([bt.drop(columns='geometry'), bf, btotal.rename('score')], axis=1)
    allscores = np.sort(total.values)
    bt['pct_rank_vs_all_intersections'] = np.searchsorted(allscores, bt.score.values, side='right') / len(allscores)
    legacy = netg[netg['vintage (inferred)'] == 'Legacy (pre-2018)']
    lf = factors(legacy, ctx, exclude_store=gpd.sjoin_nearest(legacy[['geometry']], se_fuel[['geometry']], max_distance=200, how='left').pipe(lambda m: m[~m.index.duplicated()]).index_right.fillna(-1).astype(int), road_radius=150, signal_radius=150)
    lf['signal_unknown'] = ~lf.fdot_signal
    _, ltotal = score(lf, ref=f)
    lrank = np.searchsorted(allscores, ltotal.values, side='right') / len(allscores)

    # hard filter + tiers
    cand['passes_2mi_filter'] = cand.dist_to_7eleven_mi >= 2
    fl = cand[cand.passes_2mi_filter].copy()
    q = fl.score.rank(pct=True)
    fl['tier'] = np.where(q >= 0.9, 'A', np.where(q >= 0.7, 'B', 'C'))
    fl['re_manager'] = fl.county.map(PILOT)
    # Polk: the Feb 2026 team map gives McDonald 'Polk (east of SR-27)'; west of US-27 is not assigned on the map.
    us27 = names[names.COUNTY.str.contains('Polk') & names.NAME.isin(['US-27', 'US 27'])].geometry.union_all()
    def polk_mgr(g):
        np_ = us27.interpolate(us27.project(g))
        return 'McDonald' if g.x > np_.x else 'Polk west (TBD)'
    m = fl.county == 'Polk'
    fl.loc[m, 're_manager'] = [polk_mgr(g) for g in fl.loc[m].geometry]
    ll = gpd.GeoSeries(fl.geometry, crs=3086).to_crs(4326)
    fl['lat'], fl['lon'] = ll.y.round(6), ll.x.round(6)
    fl['google_maps'] = 'https://www.google.com/maps/search/?api=1&query=' + fl.lat.astype(str) + ',' + fl.lon.astype(str)
    fl['access_flag'] = np.where(fl.restrictive_median & (fl.combined_aadt.fillna(0) < 25000), 'Verify median opening / full access (divided road, lower traffic)',
                        np.where(fl['competitor_within_0.15mi'], 'Competitor at corner: verify full access', ''))
    def why(r):
        bits = [f"{int(r.new_rooftops_3mi):,} homes built 2023-25 within 3 mi"]
        if r.pipeline_lots_3mi > 500: bits.append(f"{int(r.pipeline_lots_3mi):,} vacant platted lots")
        if r.new_grocers_3mi: bits.append(f"{int(r.new_grocers_3mi)} grocer(s) on 2023+ parcels")
        if pd.notna(r.combined_aadt): bits.append(f"{int(r.combined_aadt):,} combined AADT")
        bits.append(f"nearest 7-Eleven {r.dist_to_7eleven_mi:.1f} mi")
        if r.anchors_half_mi: bits.append('near ' + r.anchors_half_mi)
        return '; '.join(bits)
    fl['why_here'] = fl.apply(why, axis=1)
    fl = fl.sort_values('score', ascending=False)
    # Top 50 with 1-mile spacing so the list isn't 10 corners of the same growth area
    picked, P = [], []
    for i, r in fl.iterrows():
        p = (r.geometry.x, r.geometry.y)
        if all(np.hypot(p[0] - a, p[1] - b) > MI for a, b in P):
            picked.append(i); P.append(p)
        if len(picked) == 50: break
    top = fl.loc[picked].copy(); top.insert(0, 'rank', range(1, len(top) + 1))

    cols = ['rank', 'score', 'tier', 'intersection_name', 'county', 're_manager', 'market_type', 'why_here', 'new_rooftops_3mi', 'pipeline_lots_3mi',
            'new_grocers_3mi', 'combined_aadt', 'fdot_signal', 'signal_unknown', 'dist_to_7eleven_mi', 'nearest_7eleven', 'anchors_half_mi',
            'nationals_half_mi', 'nearest_competitor', 'access_flag', 'restrictive_median', 'max_trucks_per_day'] + ['pts_' + k for k in WEIGHTS] + ['lat', 'lon', 'google_maps']
    allc = fl.copy(); allc.insert(0, 'rank', range(1, len(allc) + 1))
    btsum = pd.DataFrame({
        'Group': ['Pilot 7-Elevens built 2018+ (backtest)', 'Pilot 7-Elevens built before 2018 (contrast)'],
        'Stores': [len(bt), len(lrank)],
        'Median percentile vs all pilot intersections': [np.median(bt.pct_rank_vs_all_intersections), np.median(lrank)],
        'Share in top 10%': [(bt.pct_rank_vs_all_intersections >= .9).mean(), (lrank >= .9).mean()],
        'Share in top 25%': [(bt.pct_rank_vs_all_intersections >= .75).mean(), (lrank >= .75).mean()],
        'Share in top 50%': [(bt.pct_rank_vs_all_intersections >= .5).mean(), (lrank >= .5).mean()],
    })
    lift = pd.DataFrame({'Factor (raw)': ['new_rooftops_3mi', 'pipeline_lots_3mi', 'new_grocers_3mi', 'combined_aadt', 'n_anchors', 'n_nationals'],
                         'Median at 2018+ builds': [bf[c].median() for c in ['new_rooftops_3mi', 'pipeline_lots_3mi', 'new_grocers_3mi', 'combined_aadt', 'n_anchors', 'n_nationals']],
                         'Median at legacy stores': [lf[c].median() for c in ['new_rooftops_3mi', 'pipeline_lots_3mi', 'new_grocers_3mi', 'combined_aadt', 'n_anchors', 'n_nationals']],
                         'Median at all intersections': [f[c].median() for c in ['new_rooftops_3mi', 'pipeline_lots_3mi', 'new_grocers_3mi', 'combined_aadt', 'n_anchors', 'n_nationals']]})
    btcols = ['address', 'city', 'county', 'parcel_year_built (inferred store age)', 'tracker_year_built', 'score', 'pct_rank_vs_all_intersections',
              'new_rooftops_3mi', 'pipeline_lots_3mi', 'new_grocers_3mi', 'combined_aadt', 'dist_to_7eleven_mi', 'anchors_half_mi', 'market_type']
    method = pd.DataFrame([
        ['Candidates', f'Intersections of FDOT arterial/collector roads (functional class {sorted(KEEP_FC)}), clustered within 150 m; interstates, expressways and local streets excluded. {len(cand):,} in pilot counties.'],
        ['Hard filters', f'2+ miles from any 7-Eleven/Speedway fuel store (FDEP + 7-Eleven API; non-fuel stores do not trigger it). {int(cand.passes_2mi_filter.sum()):,} pass. Curb cut on each road is implied by intersection; Luke verifies.'],
        ['Weights', ', '.join(f'{k} {w}' for k, w in WEIGHTS.items()) + ' (Tool Spec, approved Nov 3).'],
        ['New rooftops', 'Residential units with DOR actual year built 2023-2025 within 3 miles; scored as percentile among pilot intersections.'],
        ['Rooftop pipeline', 'Vacant residential parcels under 0.5 ac (platted lots) within 3 miles; percentile. INFERENCE: proxy for approved subdivisions.'],
        ['New grocery', 'Grocers (Publix, Aldi, Winn-Dixie, Whole Foods, Trader Joe\'s, Sprouts) on parcels built 2023+ within 3 miles; 0, 1, 2+. INFERENCE from parcel year built; "coming soon" stores not yet included.'],
        ['Traffic', 'Sum of the highest FDOT 2025 AADT on the two busiest roadways within 60 m (interstates/expressways excluded); percentile. No count = neutral (0.5), not zero.'],
        ['Gap', 'Distance to nearest 7-Eleven fuel store: 0 at 2 mi, full points at 5+ mi.'],
        ['Retail node', 'Within 1/2 mile: anchors (Walmart, Publix, Target, Home Depot, Lowe\'s, Costco, Sam\'s, Aldi, Winn-Dixie, Tractor Supply) 60%, nationals (McDonald\'s, Starbucks, Dollar General) 40%. Walmart/Lowe\'s data incomplete.'],
        ['Signal', 'FDOT signal within 60 m = full; no FDOT signal on roads FDOT tracks = 0; roads FDOT doesn\'t track = unknown (half).'],
        ['Tiers', 'Among candidates passing filters: A = top 10% of score, B = next 20%, C = rest.'],
        ['Top 50', 'Highest scores, no two within 1 mile of each other.'],
        ['Backtest', 'Each pilot 7-Eleven built 2018+ scored at its own location (its own store excluded from the gap) and ranked against all pilot intersections. CAVEAT: uses today\'s rooftop counts, not those at the time 7-Eleven chose the site.'],
        ['Data as of', f'Built {TODAY}. See 7-Eleven Source Data - Pilot.xlsx, Sources & Dates.'],
    ], columns=['Item', 'Method'])
    with pd.ExcelWriter(result, engine='openpyxl') as w:
        method.to_excel(w, 'Method & Weights', index=False)
        btsum.to_excel(w, 'Backtest Summary', index=False)
        lift.to_excel(w, 'Backtest Factors', index=False)
        bt[btcols].sort_values('pct_rank_vs_all_intersections', ascending=False).to_excel(w, 'Backtest Stores', index=False)
        top[cols].to_excel(w, 'Top 50', index=False)
        allc[cols].to_excel(w, 'All Candidates', index=False)
    allc[cols].to_csv(os.path.join(out, 'candidates_scored.csv'), index=False)
    print(btsum.to_string()); print(lift.to_string())
    print('tiers', fl.tier.value_counts().to_dict(), '| top50 by county', top.county.value_counts().to_dict())
    print(top[['rank', 'score', 'intersection_name', 'county', 'new_rooftops_3mi', 'combined_aadt', 'dist_to_7eleven_mi', 'market_type']].head(20).to_string())

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
