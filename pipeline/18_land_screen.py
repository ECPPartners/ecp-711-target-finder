"""Land screen (v1.1: Ross, Nov 17, 2026, from Luke's review of the v1.0 Top 50; v1.2: tests can be warnings, not removals).
Which tests remove a corner and which only warn is set by raw_land.hard_tests in the model file
(v1.1: upland, frontage, owner; v1.2: owner and min_zone_acres only). v1.2 adds rail and houses-on-farm-parcel warnings.
A raw-land corner (see 16_raw_corners.py) now passes only if at least one raw parcel:
  1. has enough UPLAND land near the corner: parcel area inside the corner zone (radius zone_m around the intersection),
     minus National Wetlands Inventory polygons, >= min_upland_acres
  2. fronts BOTH roads near the corner: parcel within frontage_m of 2+ distinct road directions (FDOT functional-class
     road lines clipped to the corner zone; segments within angle_deg of each other count as one road)
  3. is not owned by a fuel/c-store competitor, 7-Eleven itself, or a railroad/utility
Parcels owned by Walmart/Publix (likely fuel deed restrictions), churches, hospitals/health systems, schools and
government-affiliated entities still pass but are flagged. A corner where a competitor owns a raw parcel is flagged (often a station in the works).
All thresholds come from the model file (models/<version>.json, raw_land block).
Usage: python3 -I 18_land_screen.py <dor_extract_dir> <fdot_dir> <nwi.geojson> <candidates.json> <out.csv>
(v1.2+ also reads <fdot_dir>/fdot_rail.geojson from 21_rail_pull.py)
"""
import sys, os, re, math, importlib.util
import numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import load_model

spec = importlib.util.spec_from_file_location('raw16', os.path.join(os.path.dirname(os.path.abspath(__file__)), '16_raw_corners.py'))
raw16 = importlib.util.module_from_spec(spec); spec.loader.exec_module(raw16)

MODEL = load_model()
RL = MODEL['raw_land']
EXCLUDE = re.compile(RL['exclude_owner_regex'])
FLAGS = {k: re.compile(v) for k, v in RL['flag_owner_regex'].items()}
COMP = re.compile(RL['competitor_regex'])

def orientation(line, p):
    """Bearing (0-180) of the part of a road line nearest the corner."""
    seg = line.intersection(p.buffer(120))
    seg = max(getattr(seg, 'geoms', [seg]), key=lambda g: g.length) if not seg.is_empty else line
    c = list(seg.coords) if seg.geom_type == 'LineString' else list(seg.geoms[0].coords)
    (x0, y0), (x1, y1) = c[0], c[-1]
    return math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180

def road_groups(roads, p, zone):
    """Distinct road directions at the corner: list of clipped geometries, one per direction."""
    near = roads[roads.distance(p) <= 60]
    items = []
    for rid, g in near.groupby('ROADWAY'):
        geom = unary_union(list(g.geometry))
        items.append((orientation(geom, p), geom.intersection(zone)))
    groups = []
    for ang, geom in sorted(items, key=lambda t: t[0]):
        for gr in groups:
            d = abs(ang - gr[0]); d = min(d, 180 - d)
            if d < RL['same_road_angle_deg']:
                gr[1].append(geom); break
        else:
            groups.append([ang, [geom]])
    return [unary_union(g[1]) for g in groups]

def owner_flags(owner):
    o = str(owner or '').upper()
    return [k for k, rx in FLAGS.items() if rx.search(o)]

def main(dor_x, fdot, nwi, cand_json, out_csv):
    c = pd.read_json(cand_json)
    counties = sorted(c.county.unique())
    raw = pd.concat([raw16.raw_parcels(os.path.join(dor_x, k.lower().replace(' ', '_'))) for k in counties], ignore_index=True)
    raw = gpd.GeoDataFrame(raw, geometry='geometry', crs=3086)
    roads = gpd.read_file(os.path.join(fdot, 'fdot_funclass.geojson')).to_crs(3086)
    roads = roads[roads.FUNCLASS.isin(['04', '06', '07', '08', '14', '16', '17', '18'])]
    wet = gpd.read_file(nwi).to_crs(3086)
    wet = wet[wet.geometry.is_valid | True]; wet['geometry'] = wet.geometry.buffer(0)
    wsi = wet.sindex
    HARD = set(RL.get('hard_tests', ['upland', 'frontage', 'owner']))
    rail_path = os.path.join(fdot, 'fdot_rail.geojson')
    rail = gpd.read_file(rail_path).to_crs(3086) if RL.get('rail_warning') and os.path.exists(rail_path) else None
    g = gpd.GeoDataFrame(c, geometry=gpd.points_from_xy(c.lon, c.lat), crs=4326).to_crs(3086)
    rows = []
    for i, r in g.iterrows():
        p = r.geometry
        zone = p.buffer(RL['zone_m'])
        cand = raw[raw.intersects(p.buffer(RL['touch_m']))]
        groups = road_groups(roads, p, zone) if len(cand) else []
        wz = wet.iloc[list(wsi.query(zone, predicate='intersects'))]
        wet_zone = unary_union(list(wz.geometry)).intersection(zone) if len(wz) else None
        best = None
        comp_owned = sorted({str(o) for o in cand.OWN_NAME if COMP.search(str(o or '').upper())})
        rail_z = None
        if rail is not None:
            rz = rail[rail.intersects(zone)]
            rail_z = unary_union(list(rz.geometry)).intersection(zone) if len(rz) else None
        for _, q in cand.iterrows():
            inzone = q.geometry.intersection(zone)
            zone_ac = inzone.area / 4046.86
            wet_ac = inzone.intersection(wet_zone).area / 4046.86 if wet_zone is not None and not wet_zone.is_empty else 0.0
            upland = zone_ac - wet_ac
            fronts = sum(1 for rg in groups if not rg.is_empty and q.geometry.distance(rg) <= RL['frontage_m'])
            excluded = bool(EXCLUDE.search(str(q.OWN_NAME or '').upper()))
            fl = owner_flags(q.OWN_NAME)
            tests = {  # test name -> problem text, or None when it passes
                'upland': (f'only {upland:.2f} upland ac near corner (need {RL["min_upland_acres"]})' + (f'; {wet_ac:.1f} ac mapped wetland' if wet_ac >= 0.1 else '')) if upland < RL['min_upland_acres'] else None,
                'frontage': 'fronts one road only (not a corner)' if (fronts < 2 and len(groups) >= 2) else None,
                'owner': f'owned by {q.OWN_NAME}' if excluded else None,
            }
            if 'min_zone_acres' in RL:
                tests['min_zone_acres'] = f'only {zone_ac:.2f} ac of the parcel near the corner (need {RL["min_zone_acres"]})' if zone_ac < RL['min_zone_acres'] else None
            if rail_z is not None and not rail_z.is_empty:
                tests['rail'] = 'rail line at the parcel' if q.geometry.distance(rail_z) <= RL.get('rail_m', 30) else None
            if RL.get('houses_warning') and q.uc in raw16.AG and (q.NO_BULDNG or 0) > 0:
                tests['houses'] = f'farm parcel has {int(q.NO_BULDNG)} building(s) (houses to clear?)'
            ok = not any(v for k, v in tests.items() if k in HARD)
            fail = '; '.join(v for k, v in tests.items() if v and k in HARD)
            warn = '; '.join(v for k, v in tests.items() if v and k not in HARD)
            rec = dict(i=i, parcel=q.PARCEL_ID, owner=q.OWN_NAME, use=raw16.USE.get(q.uc, q.uc), acres=round(q.acres, 2),
                       zone_ac=round(zone_ac, 2), upland_ac_corner=round(upland, 2), wetland_ac_corner=round(wet_ac, 2), roads_fronted=fronts,
                       road_dirs=len(groups), ok=ok, flags='; '.join(fl), fail=fail, warnings=warn)
            # best = passing parcel, then fewest warnings and no owner flag, then most upland
            key = (ok, not fl, -warn.count(';') - bool(warn), upland)
            if best is None or key > best[0]: best = (key, rec)
        if best:
            best[1]['competitor_owns_corner_land'] = '; '.join(comp_owned)
            rows.append(best[1])
        if i % 100 == 0: print(i, len(g), flush=True)
    res = pd.DataFrame(rows).set_index('i')
    out = c.join(res.add_prefix('land_'))
    out['land_ok'] = out.land_ok.fillna(False).astype(bool) & out.raw_corner & (out.aerial_qa.fillna('') == '')
    out.drop(columns=[x for x in ['geometry'] if x in out]).to_csv(out_csv, index=False)
    print('raw corners', int(out.raw_corner.sum()), '| v1.0 raw_ok', int(out.raw_ok.sum()), '| v1.1 land_ok', int(out.land_ok.sum()))

if __name__ == '__main__':
    main(*sys.argv[1:6])
