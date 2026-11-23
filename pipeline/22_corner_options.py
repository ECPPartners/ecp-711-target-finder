"""v1.3 corner options (Ross, Nov 23, 2026): every corner that could be a 7-Eleven option in a trade area.
import warnings; warnings.filterwarnings("ignore")
For each candidate corner it works out:
  - One-owner land option (corners without a usable raw parcel): one owner holds >= redev_min_acres touching the corner
    (within touch_m) made of vacant lots, farm land, or a house/mobile home on acreage (DOR 000-099 vacant/ag, 001, 002),
    not public/HOA/CDD land and not owned by a competitor. Built commercial corners and corners split among several owners
    with buildings (Ross on US-41 & Symmes) are not options.
  - Station at the corner: a parcel coded service station (DOR use 026) or owned by a fuel competitor touching the corner,
    or a competitor store (FDEP tanks) within station_m of the intersection.
  - Road side and direction served (US right-hand traffic): on an east-west main road the north side serves westbound
    traffic and the south side eastbound; on a north-south road the east side serves northbound and the west side
    southbound. When a station sits at the corner, the option's side is compared with the station's
    (Ross on Silver Palm & SR-52: 7-Eleven went across SR-52 from RaceTrac to outposition it for westbound traffic).
Information only: nothing here changes the score.
Usage: python3 -I 22_corner_options.py <dor_extract_dir> <fdot_dir> <fdep_stations.csv> <land.csv> <out.csv>
"""
import sys, os, re, glob, math, importlib.util
import numpy as np, pandas as pd, geopandas as gpd, pyogrio
from shapely.ops import unary_union
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import load_model

HERE = os.path.dirname(os.path.abspath(__file__))
def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file)); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
raw16 = _load('raw16', '16_raw_corners.py')
ls18 = _load('ls18', '18_land_screen.py')

M = load_model(); RL = M['raw_land']; OP = M['options']
COMP = re.compile(RL['competitor_regex'])
EXCL = re.compile(RL['exclude_owner_regex'] + r'|\bCOMMUNITY\b|\bHOLDINGS? OF THE\b')   # + HOA/CDD-style 'X COMMUNITY' owners
RESID = {f'{i:03d}' for i in range(0, 10)} - {'000'}          # 001-009 houses, condos, mobile homes, multifamily
SOFT = raw16.RAW_VACANT | raw16.AG | {'001', '002'}            # land a developer can buy and clear: vacant, farm, house/mobile home on acreage
STATION = {'026'}
def nm(s): return re.sub(r'[^A-Z0-9]', '', str(s or '').upper())

def all_parcels_near(cdir, zones):
    nal_csv = glob.glob(os.path.join(cdir, '**', 'NAL*.csv'), recursive=True)[0]
    shp = [p for p in glob.glob(os.path.join(cdir, '**', '*.shp'), recursive=True) if 'pin' in p.lower()][0]
    pin = pyogrio.read_dataframe(shp).to_crs(3086)
    idcol = [c for c in pin.columns if c != 'geometry'][0]
    pin = gpd.sjoin(pin, zones, predicate='intersects')
    pin['key'] = pin[idcol].map(raw16.norm)
    n = pd.read_csv(nal_csv, usecols=['PARCEL_ID', 'DOR_UC', 'JV', 'LND_SQFOOT', 'NO_BULDNG', 'PUBLIC_LND', 'OWN_NAME'], dtype=str, encoding_errors='replace')
    n['key'] = n.PARCEL_ID.map(raw16.norm); n = n[n.key.isin(set(pin.key))]
    n['uc'] = n.DOR_UC.str.zfill(3)
    for c in ['JV', 'LND_SQFOOT', 'NO_BULDNG']: n[c] = pd.to_numeric(n[c], errors='coerce')
    g = pin.merge(n, on='key')
    g['acres'] = np.where(g.LND_SQFOOT > 0, g.LND_SQFOOT, g.geometry.area * 10.7639) / 43560
    return g

def side(p, ang, q):
    """Which side of the main road q is on, and the travel direction that side serves."""
    a = math.radians(ang)
    dx, dy = math.cos(a), math.sin(a)
    ew = abs(dx) >= abs(dy)
    if ew and dx < 0: dx, dy = -dx, -dy
    if not ew and dy < 0: dx, dy = -dx, -dy
    cr = dx * (q.y - p.y) - dy * (q.x - p.x)
    if ew: return ('N', 'westbound') if cr > 0 else ('S', 'eastbound')
    return ('W', 'southbound') if cr > 0 else ('E', 'northbound')

def main(dor_x, fdot, fdep_csv, land_csv, out_csv):
    c = pd.read_csv(land_csv)
    c = c.copy()   # candidates.json holds only corners that pass the 2-mile filter
    g = gpd.GeoDataFrame(c, geometry=gpd.points_from_xy(c.lon, c.lat), crs=4326).to_crs(3086)
    roads = gpd.read_file(os.path.join(fdot, 'fdot_funclass.geojson')).to_crs(3086)
    roads = roads[roads.FUNCLASS.isin(['04', '06', '07', '08', '14', '16', '17', '18'])]
    fd = pd.read_csv(fdep_csv); fd = fd[fd.category == 'Competitor']
    comp = gpd.GeoDataFrame(fd, geometry=gpd.points_from_xy(fd.lon, fd.lat), crs=4326).to_crs(3086)
    parts = []
    for county, sub in g.groupby('county'):
        z = gpd.GeoDataFrame({'i': sub.index}, geometry=sub.buffer(RL['touch_m']).values, crs=3086)
        parts.append(all_parcels_near(os.path.join(dor_x, county.lower().replace(' ', '_')), z))
    P = pd.concat(parts, ignore_index=True)
    rows = []
    for i, r in g.iterrows():
        p = r.geometry
        near = P[P.i == i]
        # main road: highest functional class at the corner (lowest last digit), then the longest
        nr = roads[roads.distance(p) <= 60].copy()
        ang = None
        if len(nr):
            nr['cls'] = nr.FUNCLASS.astype(int) % 10
            top = nr[nr.cls == nr.cls.min()]
            ang = ls18.orientation(unary_union(list(top.geometry)), p)
        # station at the corner
        st_parcels = near[near.uc.isin(STATION) | near.OWN_NAME.fillna('').str.upper().str.contains(COMP)]
        st_pts = comp[comp.distance(p) <= OP['station_m']]
        stations = []
        for _, s in st_parcels.iterrows():
            lbl = str(s.OWN_NAME).title() if COMP.search(str(s.OWN_NAME).upper()) else f'station parcel ({str(s.OWN_NAME).title()})'
            stations.append((lbl, s.geometry.representative_point()))
        for _, s in st_pts.iterrows():
            if not any(q.distance(s.geometry) < 60 for _, q in stations):
                stations.append((f"{s.brand}", s.geometry))
        # redevelopment holding: largest single-owner block touching the corner
        ok = near[near.uc.isin(SOFT) & near.PUBLIC_LND.isna()
                  & ~near.OWN_NAME.fillna('').str.upper().str.contains(raw16.BAD_OWNER)
                  & ~near.OWN_NAME.fillna('').str.upper().str.contains(COMP)
                  & ~near.OWN_NAME.fillna('').str.upper().str.contains(EXCL)]
        redev_owner, redev_ac, redev_built, redev_geom = None, 0.0, None, None
        if len(ok):
            by = ok.groupby(ok.OWN_NAME.map(nm)).agg(acres=('acres', 'sum'), owner=('OWN_NAME', 'first'), built=('NO_BULDNG', lambda s: int(s.fillna(0).sum())))
            b = by.sort_values('acres', ascending=False).iloc[0]
            redev_owner, redev_ac, redev_built = b.owner, round(float(b.acres), 2), b.built
            redev_geom = unary_union(list(ok[ok.OWN_NAME.map(nm) == by.acres.idxmax()].geometry))
        owners_at_corner = near.OWN_NAME.map(nm).nunique()
        # option parcel location: raw parcel (from the land screen) or the redevelopment block
        if r.land_ok and isinstance(r.land_parcel, str):
            q = near[near.PARCEL_ID == r.land_parcel]
            opt_geom = unary_union(list(q.geometry)) if len(q) else None
            opt_type = 'Raw land'
        else:
            opt_geom = redev_geom; opt_type = 'One-owner land (houses/lots)'
        redev_ok = (not r.land_ok) and redev_ac >= OP['redev_min_acres']
        pos = None
        if ang is not None and opt_geom is not None:
            s_opt, dir_opt = side(p, ang, opt_geom.representative_point())
            road = 'E-W' if dir_opt in ('eastbound', 'westbound') else 'N-S'
            if stations:
                st_sides = [(nmn, side(p, ang, sp)) for nmn, sp in stations]
                same = [nmn for nmn, (s, _) in st_sides if s == s_opt]
                opp = [nmn for nmn, (s, _) in st_sides if s != s_opt]
                pos = f"Option on {s_opt} side of the {road} main road (serves {dir_opt})."
                if opp and not same:
                    pos += f" Station(s) across the road ({', '.join(opp)}): can outposition them for {dir_opt} traffic."
                elif same and not opp:
                    pos += f" Same side as {', '.join(same)}: competes head-on for {dir_opt} traffic."
                else:
                    pos += f" Stations on both sides ({', '.join(same + opp)})."
            else:
                pos = f"No station at the corner. Option on {s_opt} side of the {road} main road (serves {dir_opt})."
        rows.append(dict(i=i, option_type=opt_type if (r.land_ok or redev_ok) else None, redev_ok=redev_ok, redev_owner=redev_owner,
                         redev_acres=redev_ac, redev_buildings=redev_built, owners_at_corner=owners_at_corner,
                         stations_at_corner='; '.join(sorted({s for s, _ in stations})) or None, positioning=pos))
    res = pd.DataFrame(rows).set_index('i')
    c.join(res).to_csv(out_csv, index=False)
    print('corners', len(c), '| raw-land options', int(c.land_ok.sum()), '| redevelopment options', int(res.redev_ok.sum()),
          '| with a station at the corner', int(res.stations_at_corner.notna().sum()))

if __name__ == '__main__':
    main(*sys.argv[1:6])
