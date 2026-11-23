"""Pull FDOT layers for the pilot counties (WGS84 GeoJSON).
Usage: python3 -I 03_fdot_pull.py <out_dir>
Layers: AADT (with truck factor), functional classification, local road names, traffic signals, median type.
"""
import sys, os, json, requests

FDOT = "https://services1.arcgis.com/O1JpcwDW8sjYuddV/arcgis/rest/services"
# counties come from the model (v1.0 pilot list kept as the default)
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from model import load_model
    _pc = load_model().get('pilot_counties', {})
except Exception:
    _pc = {}
_LIKE = {'St Johns': 'JOHNS', 'St Lucie': 'LUCIE', 'Miami-Dade': 'DADE', 'Indian River': 'INDIAN', 'Palm Beach': 'PALM', 'Santa Rosa': 'SANTA', 'DeSoto': 'SOTO'}
COUNTY_LIKE = [f"%{_LIKE.get(c, c.upper())}%" for c in _pc] or ['%DUVAL%', '%JOHNS%', '%CLAY%', '%VOLUSIA%', '%BREVARD%', '%PASCO%', '%HILLSBOROUGH%', '%LUCIE%', '%POLK%']
LAYERS = {
    'aadt': 'Annual_Average_Daily_Traffic_TDA',
    'funclass': 'Functional_Classification_TDA',
    'localnames': 'Roadways_With_Local_Name_TDA',
    'signals': 'Traffic_Signal_Locations_TDA',
    'median': 'Median_Type_TDA',
}

def pull(service, where):
    url = f"{FDOT}/{service}/FeatureServer/0/query"
    feats, offset = [], 0
    while True:
        r = requests.get(url, params={'where': where, 'outFields': '*', 'outSR': 4326, 'f': 'geojson',
                                       'resultOffset': offset, 'resultRecordCount': 1000}, timeout=180)
        r.raise_for_status(); fc = r.json()
        if 'features' not in fc: raise RuntimeError(str(fc)[:300])
        feats += fc['features']
        if len(fc['features']) < 1000: break
        offset += 1000
    return feats

def main(out):
    os.makedirs(out, exist_ok=True)
    where = ' OR '.join(f"COUNTY LIKE '{c}'" for c in COUNTY_LIKE)
    for key, svc in LAYERS.items():
        feats = pull(svc, where)
        json.dump({'type': 'FeatureCollection', 'features': feats}, open(os.path.join(out, f'fdot_{key}.geojson'), 'w'))
        counties = {}
        for f in feats:
            c = f['properties'].get('COUNTY'); counties[c] = counties.get(c, 0) + 1
        print(key, len(feats), counties)

if __name__ == '__main__':
    main(sys.argv[1])
