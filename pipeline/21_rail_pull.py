"""Pull FDOT rail lines (freight, Amtrak, Brightline, SunRail, Tri-Rail) for the land screen's rail warning.
Usage: python3 -I 21_rail_pull.py <out.geojson>
Source: FDOT Rail_System_Layers_2025 FeatureServer (services1.arcgis.com).
"""
import sys, json, requests
URL = 'https://services1.arcgis.com/O1JpcwDW8sjYuddV/arcgis/rest/services/Rail_System_Layers_2025/FeatureServer/{}/query'
LAYERS = {11: 'Freight Rail', 6: 'Amtrak', 9: 'Brightline', 2: 'SunRail', 13: 'TriRail'}

def main(out):
    feats = []
    for lid, name in LAYERS.items():
        off = 0
        while True:
            r = requests.get(URL.format(lid), params={'where': '1=1', 'outFields': '*', 'outSR': 4326, 'f': 'geojson',
                                                      'resultOffset': off, 'resultRecordCount': 1000}, timeout=180)
            r.raise_for_status(); fc = r.json()
            for f in fc.get('features', []):
                if f.get('geometry'): f['properties']['rail_layer'] = name; feats.append(f)
            if len(fc.get('features', [])) < 1000: break
            off += 1000
        print(name, sum(1 for f in feats if f['properties']['rail_layer'] == name))
    json.dump({'type': 'FeatureCollection', 'features': feats}, open(out, 'w'))

if __name__ == '__main__':
    main(sys.argv[1])
