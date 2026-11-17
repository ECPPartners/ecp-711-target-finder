"""Pull U.S. Fish & Wildlife National Wetlands Inventory (NWI) polygons around candidate corners.
Usage: python3 -I 17_wetlands_pull.py <candidates.csv|json> <out.geojson> [radius_m=400]
Only corners with a raw parcel (raw_corner true) are queried. Source: fwspublicservices.wim.usgs.gov Wetlands MapServer.
"""
import sys, json, math, time, requests
import pandas as pd

URL = 'https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/0/query'

def query(lat, lon, r):
    dlat = r / 111320; dlon = r / (111320 * math.cos(math.radians(lat)))
    feats, offset = [], 0
    while True:
        p = {'geometry': f'{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat}', 'geometryType': 'esriGeometryEnvelope',
             'inSR': 4326, 'spatialRel': 'esriSpatialRelIntersects', 'outFields': 'OBJECTID,ATTRIBUTE,WETLAND_TYPE,ACRES',
             'outSR': 4326, 'maxAllowableOffset': 0.00001, 'f': 'json', 'resultOffset': offset, 'resultRecordCount': 200}
        for attempt in range(6):
            try:
                r_ = requests.get(URL, params=p, timeout=120); r_.raise_for_status(); fc = r_.json()
                if 'error' in fc: raise RuntimeError(fc['error'])
                break
            except Exception as e:
                if attempt == 5: raise
                time.sleep(10 * (attempt + 1))
        # esri JSON -> GeoJSON (NWI geometry fails without maxAllowableOffset; ~1 m generalization is fine at site scale)
        feats += [{'type': 'Feature', 'properties': f['attributes'], 'geometry': {'type': 'Polygon', 'coordinates': f['geometry']['rings']}}
                  for f in fc.get('features', [])]
        if not fc.get('exceededTransferLimit') and len(fc.get('features', [])) < 200: break
        offset += 200
    return feats

def main(cand, out, radius=400):
    c = pd.read_json(cand) if cand.endswith('.json') else pd.read_csv(cand)
    c = c[c.raw_corner.astype(bool)]
    seen, feats = set(), []
    for i, (lat, lon) in enumerate(zip(c.lat, c.lon)):
        for f in query(lat, lon, radius):
            k = f['properties']['OBJECTID']
            if k in seen: continue
            seen.add(k); feats.append(f)
        if i % 25 == 0: print(i, len(c), len(feats), flush=True)
    json.dump({'type': 'FeatureCollection', 'features': feats}, open(out, 'w'))
    print('corners', len(c), '| wetland polygons', len(feats))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 400)
