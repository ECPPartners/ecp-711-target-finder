"""v1.1 two-step output: trade areas first, then the best corners in each (Ross, Nov 17, 2026, from Luke's review:
"right trade area, wrong corner"). Scores are unchanged; this changes how the list is organized.
  1. Pool = corners passing the land screen (18_land_screen.py).
  2. Trade areas = complete-linkage clusters: every corner in a trade area is within trade_area_max_diameter_mi of every
     other one (new-home counts are 3-mile radius, so corners this close share most of the same rooftops).
  3. Trade areas rank by their best corner's score. Each shows up to corners_per_trade_area corners, best score first,
     at least min_corner_spacing_mi apart.
Usage: python3 -I 19_trade_areas.py <land.csv> <out_corners.csv> <out_areas.csv>
"""
import sys, os
import numpy as np, pandas as pd, geopandas as gpd
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import load_model

MI = 1609.344
O = load_model()['output']

def main(land_csv, out_corners, out_areas):
    c = pd.read_csv(land_csv)
    pool = c[c.land_ok].copy()
    g = gpd.GeoDataFrame(pool, geometry=gpd.points_from_xy(pool.lon, pool.lat), crs=4326).to_crs(3086)
    xy = np.c_[g.geometry.x, g.geometry.y]
    lab = fcluster(linkage(pdist(xy), method='complete'), O['trade_area_max_diameter_mi'] * MI, criterion='distance')
    pool['ta'] = lab
    best = pool.groupby('ta').score.max().sort_values(ascending=False)
    ta_rank = {t: i + 1 for i, t in enumerate(best.index)}
    pool['trade_area_rank'] = pool.ta.map(ta_rank)
    pool['x'], pool['y'] = xy[:, 0], xy[:, 1]
    pool = pool.sort_values(['trade_area_rank', 'score'], ascending=[True, False])
    pick = []
    for t, sub in pool.groupby('trade_area_rank', sort=True):
        chosen = []
        for i, r in sub.iterrows():
            if all(np.hypot(r.x - pool.at[j, 'x'], r.y - pool.at[j, 'y']) >= O['min_corner_spacing_mi'] * MI for j in chosen):
                chosen.append(i)
            if len(chosen) == O['corners_per_trade_area']: break
        pick += [(i, k + 1) for k, i in enumerate(chosen)]
    pool['corner_in_area'] = pd.Series(dict(pick))
    pool['shown'] = pool.corner_in_area.notna() & (pool.trade_area_rank <= O['top_n_trade_areas'])
    areas = []
    for t, sub in pool.groupby('trade_area_rank'):
        top = sub.iloc[0]
        span = pdist(sub[['x', 'y']].values).max() / MI if len(sub) > 1 else 0
        areas.append(dict(trade_area_rank=t, county=top.county, re_manager=top.re_manager, market_type=top.market_type,
                          best_corner=top.intersection_name, best_score=top.score, tier=top.tier,
                          corners_passing=len(sub), corners_shown=int(sub.corner_in_area.notna().sum()),
                          span_mi=round(span, 1), new_homes_3mi_max=sub.new_rooftops_3mi.max(), aadt_max=sub.combined_aadt.max(),
                          nearest_7eleven_mi=round(sub.dist_to_7eleven_mi.min(), 1),
                          center_lat=sub.lat.mean(), center_lon=sub.lon.mean()))
    areas = pd.DataFrame(areas)
    pool.drop(columns=['x', 'y']).to_csv(out_corners, index=False)
    areas.to_csv(out_areas, index=False)
    print('pool', len(pool), '| trade areas', len(areas), '| shown corners', int(pool.shown.sum()),
          '| top', O['top_n_trade_areas'], 'areas hold', int(areas.head(O['top_n_trade_areas']).corners_passing.sum()), 'passing corners')

if __name__ == '__main__':
    main(*sys.argv[1:4])
