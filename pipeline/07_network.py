"""Build the 7-Eleven family network for Florida (one row per store) and match the ECP sales tracker.
Usage: python3 -I 07_network.py <atp_dir> <out_dir>
Inputs: <atp_dir>/seven_eleven_ca_us.geojson, speedway_us.geojson; <out_dir>/fl_counties.geojson,
        <out_dir>/tracker_fl.csv (from 05)
Output: <out_dir>/seven_eleven_fl.csv
Fields: store_ref, brand, address, city, zip, lat, lon, county, has_fuel (from 7-Eleven's own store API:
a store has fuel if the API lists a fuel record for it), diesel, tracker_match (tab/date/year built/acres),
source.
"""
import sys, os, json, re
import pandas as pd, geopandas as gpd, numpy as np

def base(r): return str(r).split('_')[0]

def main(atp, out):
    se = [f for f in json.load(open(os.path.join(atp, 'seven_eleven_ca_us.geojson')))['features']
          if (f['properties'].get('addr:state') or '') == 'FL']
    shops, fuel = {}, {}
    for f in se:
        p = f['properties']; b = base(p['ref'])
        if p.get('shop'): shops[b] = f
        if p.get('amenity') == 'fuel': fuel[b] = p
    rows = []
    for b, f in shops.items():
        p = f['properties']; lon, lat = f['geometry']['coordinates'][:2]
        fp = fuel.get(b, {})
        rows.append(dict(store_ref=b, brand=p.get('brand') or '7-Eleven', address=p.get('addr:street_address'),
                         city=p.get('addr:city'), zip=p.get('addr:postcode'), lat=lat, lon=lon,
                         has_fuel='Y' if b in fuel else 'N', diesel=fp.get('fuel:diesel'),
                         source='7-Eleven store API via AllThePlaces (seven_eleven_ca_us, run 2026-10-31)'))
    sp = [f for f in json.load(open(os.path.join(atp, 'speedway_us.geojson')))['features']
          if (f['properties'].get('addr:state') or '') == 'FL']
    for f in sp:
        p = f['properties']; b = str(p['ref'])
        if b in shops: continue
        lon, lat = f['geometry']['coordinates'][:2]
        rows.append(dict(store_ref=b, brand='Speedway', address=p.get('addr:street_address'), city=p.get('addr:city'),
                         zip=p.get('addr:postcode'), lat=lat, lon=lon, has_fuel='Y' if p.get('amenity') == 'fuel' else 'N',
                         diesel=p.get('fuel:diesel'), source='Speedway store API via AllThePlaces (speedway_us, run 2026-10-31)'))
    df = pd.DataFrame(rows)
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326)
    counties = gpd.read_file(os.path.join(out, 'fl_counties.geojson'))[['NAME', 'geometry']].rename(columns={'NAME': 'county'})
    g = gpd.sjoin(g, counties, how='left', predicate='within').drop(columns='index_right')
    # match tracker rows: geocoded within 250 m, else same city + same house number + street token
    tr = pd.read_csv(os.path.join(out, 'tracker_fl.csv'))
    gm = g.to_crs(3086)
    for col in ['tracker_tab', 'tracker_date', 'tracker_year_built', 'tracker_acres', 'tracker_sf', 'tracker_match_method']:
        g[col] = None
    for _, t in tr.iterrows():
        idx, method = None, None
        if pd.notna(t.lat):
            pt = gpd.GeoSeries(gpd.points_from_xy([t.lon], [t.lat]), crs=4326).to_crs(3086).iloc[0]
            d = gm.distance(pt)
            if d.min() < 250: idx, method = d.idxmin(), f'geocode within {int(d.min())} m'
        if idx is None:
            num = re.match(r'^\s*(\d+)', str(t.address))
            toks = set(re.findall(r'[a-z]{3,}|\d{2,}', str(t.address).lower())) - {'road', 'street', 'avenue', 'highway', 'hwy', 'blvd', 'drive', 'the'}
            cand = g[g.city.fillna('').str.lower().str.strip() == str(t.city).lower().strip().replace('saint', 'st.')]
            if cand.empty: cand = g[g.city.fillna('').str.lower().str.contains(str(t.city).lower().split()[0][:5])]
            best = None
            for i, s in cand.iterrows():
                a = str(s.address).lower()
                score = len(toks & set(re.findall(r'[a-z]{3,}|\d{2,}', a))) + (2 if num and a.startswith(num.group(1)) else 0)
                if score >= 2 and (best is None or score > best[0]): best = (score, i)
            if best: idx, method = best[1], 'city + address token match'
        if idx is not None:
            g.loc[idx, ['tracker_tab', 'tracker_date', 'tracker_year_built', 'tracker_acres', 'tracker_sf', 'tracker_match_method']] = \
                [t.tracker_tab, str(t.date)[:10], t.year_built, t.acres, t.building_sf, method]
    g.drop(columns='geometry').to_csv(os.path.join(out, 'seven_eleven_fl.csv'), index=False)
    print('stores', len(g), '| fuel', (g.has_fuel == 'Y').sum(), '| non-fuel', (g.has_fuel == 'N').sum())
    print('tracker rows', len(tr), '| matched to a store', g.tracker_tab.notna().sum())
    print(g.groupby('county').size().sort_values(ascending=False).head(15).to_string())

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
