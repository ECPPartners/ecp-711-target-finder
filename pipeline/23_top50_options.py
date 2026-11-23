"""v1.3 Top 50 with corner options (Ross, Nov 23, 2026): "a Top 50, and when an area has strong new-home growth and
good spacing from an existing 7-Eleven and multiple viable options per our criteria, list each as 2a, 2b, 2c."
  1. Viable option = a corner that passes the 2-mile filter and either
       - has a raw parcel passing the land screen (18_land_screen.py; warnings shown, not removed), or
       - has a one-owner redevelopment block of redev_min_acres+ with at most redev_max_buildings buildings (22_corner_options.py),
     and is not marked taken/pass by the deal makers (reviews/corner_status.csv).
  2. Trade areas = complete-linkage clusters of viable options, max trade_area_max_diameter_mi across.
  3. Trade areas need strong new-home growth: at least one option with min_area_new_homes+ new homes (2023-25, 3 mi).
     Qualifying areas rank by their best option's score; the top top_n_trade_areas are the Top 50.
  4. Options in an area: raw-land corners picked first, then one-owner land; listed best score first; at least min_corner_spacing_mi apart, each scoring at least
     min_secondary_score_ratio x the area's best, up to max_options_per_area. Labelled 1 (one option) or 2a, 2b, 2c.
  5. Highway plays: viable corners with highway_min_aadt+ combined AADT in areas below the growth bar, best score first,
     top highway_top_n (Ross, Nov 23: a separate short list rather than an exception to the Top 50).
  6. (v1.5+) output.regions: trade areas whose best corner is in a region's counties (e.g. the Panhandle) are ranked on
     their own list (P1, P2a ...), top_n each, and kept out of the main Top N and the highway list.
Usage: python3 -I 23_top50_options.py <options.csv> <corner_status.csv> <out.csv>
"""
import sys, os, re, string
import numpy as np, pandas as pd, geopandas as gpd
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import load_model

MI = 1609.344
M = load_model(); O = M['output']; OP = M['options']
key = lambda a, b: re.sub(r'[^A-Z0-9]', '', str(a).upper()) + re.sub(r'[^A-Z0-9]', '', str(b).upper())

def main(opt_csv, status_csv, out_csv):
    c = pd.read_csv(opt_csv)
    st = pd.read_csv(status_csv)
    st['k'] = [key(a, b) for a, b in zip(st.intersection, st.county)]
    c['k'] = [key(a, b) for a, b in zip(c.intersection_name, c.county)]
    c = c.merge(st[['k', 'status', 'reason', 'decided_by']].rename(columns={'reason': 'status_reason'}), on='k', how='left')
    redev_viable = c.redev_ok.fillna(False).astype(bool) & (c.redev_buildings.fillna(0) <= OP.get('redev_max_buildings', 1))
    c['option_type'] = np.where(c.land_ok, 'Raw land', np.where(redev_viable, 'One-owner land (houses/lots)', None))
    c['viable'] = c.option_type.notna() & c.status.isna()
    v = c[c.viable].copy()
    g = gpd.GeoDataFrame(v, geometry=gpd.points_from_xy(v.lon, v.lat), crs=4326).to_crs(3086)
    xy = np.c_[g.geometry.x, g.geometry.y]
    v['ta'] = fcluster(linkage(pdist(xy), method='complete'), O['trade_area_max_diameter_mi'] * MI, criterion='distance')
    v['x'], v['y'] = xy[:, 0], xy[:, 1]
    growth = v.groupby('ta').new_rooftops_3mi.max()
    v['area_growth_ok'] = v.ta.map(growth >= O['min_area_new_homes'])
    # region of each trade area = region of its best corner
    best_county = v.sort_values('score', ascending=False).groupby('ta').county.first()
    reg_of = {}
    for rname, rc in O.get('regions', {}).items():
        for t, cty in best_county.items():
            if cty in set(rc['counties']): reg_of[t] = rname
    v['region'] = v.ta.map(reg_of)
    prefix = {None: ''} | {k: rc.get('label_prefix', k[:1]) for k, rc in O.get('regions', {}).items()}
    def ranking(mask):
        g_ = v[mask]
        o_ = list(g_[g_.area_growth_ok].groupby('ta').score.max().sort_values(ascending=False).index)
        o_ += [t for t in g_.groupby('ta').score.max().sort_values(ascending=False).index if t not in set(o_)]
        return {t: i + 1 for i, t in enumerate(o_)}
    rank = ranking(v.region.isna())
    for rname in O.get('regions', {}): rank |= ranking(v.region == rname)
    v['area_rank'] = v.ta.map(rank)
    v['area_key'] = v.region.fillna('') + '|' + v.area_rank.astype(str)
    v['road_pts'] = v.pts_traffic.fillna(0) + v.pts_signal.fillna(0)
    v = v.sort_values(['area_rank', 'road_pts', 'score'], ascending=[True, False, False])
    lab = {}
    for ak, sub in v.groupby('area_key'):
        t = prefix[sub.region.iloc[0] if isinstance(sub.region.iloc[0], str) else None] + str(int(sub.area_rank.iloc[0]))
        floor = sub.score.max() * O['min_secondary_score_ratio']
        chosen = []
        # raw land first (ECP's default since Nov 11), then one-owner land fills open slots; both by score
        for kind in ('Raw land', None):
            for i, r in sub.iterrows():
                if (kind and r.option_type != kind) or (not kind and r.option_type == 'Raw land'): continue
                if chosen and r.score < floor: continue
                if len(chosen) == O['max_options_per_area']: break
                if O.get('min_corner_spacing_mi') is None or all(np.hypot(r.x - v.at[j, 'x'], r.y - v.at[j, 'y']) >= O['min_corner_spacing_mi'] * MI for j in chosen):
                    chosen.append(i)
        chosen = sorted(chosen, key=lambda j: (-v.at[j, 'road_pts'], -v.at[j, 'score']))
        for n, i in enumerate(chosen):
            lab[i] = f'{t}' if len(chosen) == 1 else f'{t}{string.ascii_lowercase[n]}'
    v['option'] = pd.Series(lab)
    v['in_top'] = v.option.notna() & (v.area_rank <= O['top_n_trade_areas']) & v.area_growth_ok & v.region.isna()
    v['in_region_top'] = False
    for rname, rc in O.get('regions', {}).items():
        v.loc[v.option.notna() & (v.region == rname) & (v.area_rank <= rc['top_n']) & v.area_growth_ok, 'in_region_top'] = True
    hw = v[v.area_growth_ok.eq(False) & v.region.isna() & (v.combined_aadt >= O.get('highway_min_aadt', 1e12))].sort_values('score', ascending=False)
    hw = hw.head(O.get('highway_top_n', 0))
    v['highway_rank'] = pd.Series({i: n + 1 for n, i in enumerate(hw.index)})
    v['area_options'] = v.groupby('area_key').option.transform('count')
    v['area_viable_corners'] = v.groupby('area_key').option.transform('size')
    out = pd.concat([v.drop(columns=['x', 'y']), c[~c.viable]], ignore_index=True)
    out.to_csv(out_csv, index=False)
    top = v[v.in_top]
    print('viable corners', len(v), '| trade areas', v.ta.nunique(), '| Top', O['top_n_trade_areas'], 'areas ->', len(top), 'options',
          '| areas with 2+ options', int((top.groupby('area_rank').size() > 1).sum()),
          '| raw/redev', dict(top.option_type.value_counts()), '| highway plays', int(v.highway_rank.notna().sum()),
          '| region lists', {r: int((v.in_region_top & (v.region == r)).sum()) for r in O.get('regions', {})})

if __name__ == '__main__':
    main(*sys.argv[1:4])
