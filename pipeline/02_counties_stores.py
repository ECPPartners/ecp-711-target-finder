"""Florida county polygons (FDOT) + store inventory filtered to Florida, tagged with county.
Usage: python3 -I 02_counties_stores.py <atp_dir> <out_dir>
"""
import sys, os, json, requests
import geopandas as gpd
import pandas as pd

FDOT = "https://services1.arcgis.com/O1JpcwDW8sjYuddV/arcgis/rest/services"
PILOT = ['DUVAL', 'ST. JOHNS', 'CLAY', 'VOLUSIA', 'BREVARD', 'PASCO', 'HILLSBOROUGH', 'ST. LUCIE']

# spider -> (category, display brand, source run)
SPIDERS = {
    'seven_eleven_ca_us': ('7-Eleven family', None, '2026-10-31'),
    'speedway_us': ('7-Eleven family', 'Speedway', '2026-10-31'),
    'wawa': ('Competitor', 'Wawa', '2026-10-31'),
    'race_trac_us': ('Competitor', 'RaceTrac', '2026-10-31'),
    'circle_k': ('Competitor', 'Circle K', '2026-10-31'),
    'sunoco_us': ('Competitor', 'Sunoco', '2026-10-31'),
    'murphy_usa_us': ('Competitor', 'Murphy USA', '2026-10-17'),
    'bucees_us': ('Competitor', "Buc-ee's", '2026-10-31'),
    'publix_us': ('Grocer', 'Publix', '2026-10-31'),
    'winn_dixie_us': ('Grocer', 'Winn-Dixie', '2026-10-10'),
    'aldi_sud_us': ('Grocer', 'Aldi', '2026-10-31'),
    'whole_foods': ('Grocer', 'Whole Foods', '2026-10-31'),
    'trader_joes_us': ('Grocer', "Trader Joe's", '2026-10-31'),
    'sprouts_farmers_market': ('Grocer', 'Sprouts', '2026-10-31'),
    'walmart_us': ('Anchor', 'Walmart', '2026-10-10 (incomplete: spider partial in all recent runs)'),
    'target_us': ('Anchor', 'Target', '2026-10-31'),
    'costco_ca_gb_us': ('Anchor', 'Costco', '2026-10-31'),
    'sams_club': ('Anchor', "Sam's Club", '2026-10-17'),
    'home_depot': ('Anchor', 'Home Depot', '2026-10-31'),
    'lowes_us': ('Anchor', "Lowe's", '2026-10-17 (incomplete: spider broken in recent runs)'),
    'tractor_supply': ('Anchor', 'Tractor Supply', '2026-10-17'),
    'mcdonalds': ('National QSR/retail', "McDonald's", '2026-10-10'),
    'dollar_general': ('National QSR/retail', 'Dollar General', '2026-10-31 (file truncated; partial)'),
    'starbucks_us': ('National QSR/retail', 'Starbucks', '2026-10-31'),
}

def fdot_layer(service, where="1=1", fields="*", layer=0):
    url = f"{FDOT}/{service}/FeatureServer/{layer}/query"
    feats, offset = [], 0
    while True:
        r = requests.get(url, params={'where': where, 'outFields': fields, 'outSR': 4326, 'f': 'geojson',
                                       'resultOffset': offset, 'resultRecordCount': 2000}, timeout=120)
        r.raise_for_status(); fc = r.json()
        feats += fc['features']
        if len(fc['features']) < 2000: break
        offset += 2000
    return gpd.GeoDataFrame.from_features(feats, crs=4326)

def read_features(path):
    try:
        return json.load(open(path))['features'], False
    except Exception:
        feats = []
        for line in open(path):
            line = line.strip().rstrip(',')
            if line.startswith('{"type": "Feature"'):
                try: feats.append(json.loads(line))
                except Exception: pass
        return feats, True

def main(atp, out):
    os.makedirs(out, exist_ok=True)
    counties = fdot_layer('Florida_County_Boundaries_with_FDOT_Districts', layer=7)
    print(counties.columns.tolist()); print(counties.head(2).drop(columns='geometry'))
    counties.to_file(os.path.join(out, 'fl_counties.geojson'), driver='GeoJSON')
    rows = []
    for sp, (cat, brand, run) in SPIDERS.items():
        p = os.path.join(atp, f'{sp}.geojson')
        if not os.path.exists(p): print('MISSING', sp); continue
        feats, partial = read_features(p)
        if partial: print('PARTIAL FILE (truncated, parsed line by line):', sp, len(feats))
        for f in feats:
            pr = f['properties']; g = f.get('geometry')
            if not g or g.get('type') != 'Point': continue
            lon, lat = g['coordinates'][:2]
            if not (24 < lat < 31.1 and -87.7 < lon < -79.9): continue
            b = brand or pr.get('brand') or '7-Eleven'
            rows.append(dict(category=cat, brand=b, name=pr.get('name'), ref=pr.get('ref'),
                             street=pr.get('addr:street_address') or pr.get('addr:full'),
                             city=pr.get('addr:city'), state=pr.get('addr:state'), zip=pr.get('addr:postcode'),
                             fuel_diesel=pr.get('fuel:diesel'), fuel_hgv=pr.get('fuel:HGV_diesel'),
                             opening_date=pr.get('opening_date'), lat=lat, lon=lon,
                             source=f'AllThePlaces {sp} run {run}'))
    df = pd.DataFrame(rows)
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326)
    namecol = [c for c in counties.columns if 'NAME' in c.upper() or 'COUNTY' in c.upper()]
    print('county name col candidates', namecol)
    g = gpd.sjoin(g, counties, how='inner', predicate='within').drop(columns='index_right')
    g.to_file(os.path.join(out, 'stores_fl.geojson'), driver='GeoJSON')
    print(g.groupby(['category', 'brand']).size().to_string())

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
