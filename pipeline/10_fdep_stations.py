"""Pull every OPEN retail fuel station in Florida from FDEP's registered storage tank layer (STCM),
and tag brand from the facility name.
Usage: python3 -I 10_fdep_stations.py <out_dir>
Output: <out_dir>/fdep_stations_fl.csv
Source: FDEP Division of Waste Management, 'Registered Tanks from STCM' (ca.dep.state.fl.us OpenData/DWM_STCM layer 1).
Note: only fuel stations have registered tanks, so non-fuel 7-Elevens are not in this source.
"""
import sys, os, re, requests, pandas as pd

URL = "https://ca.dep.state.fl.us/arcgis/rest/services/OpenData/DWM_STCM/MapServer/1/query"
BRANDS = [
    ('7-Eleven family', '7-Eleven', r'7[\s-]?ELEVEN|SEVEN[\s-]?ELEVEN|\b7[\s-]11\b'),
    ('7-Eleven family', 'Speedway', r'SPEEDWAY'),
    ('7-Eleven family', 'Stripes', r'\bSTRIPES\b'),
    ('Competitor', 'Wawa', r'\bWAWA\b'),
    ('Competitor', 'RaceTrac', r'RACE[\s-]?TRAC|RACEWAY'),
    ('Competitor', 'Circle K', r'CIRCLE[\s-]?K\b'),
    ('Competitor', 'Murphy USA', r'MURPHY\s*(USA|EXPRESS)'),
    ('Competitor', "Buc-ee's", r'BUC[\s-]?EE'),
    ('Competitor', 'Sunoco', r'SUNOCO'),
    ('Competitor', "Love's", r"\bLOVE'?S\b"),
    ('Competitor', 'Pilot/Flying J', r'\bPILOT\b|FLYING\s*J'),
    ('Competitor', 'Sheetz', r'\bSHEETZ\b'),
    ('Competitor', 'Thorntons', r'THORNTON'),
    ('Competitor', 'QuikTrip', r'QUIK\s*TRIP|\bQT\b'),
    ('Competitor', 'Costco/Sam\'s/BJ\'s/Walmart fuel', r'COSTCO|SAM.?S CLUB|\bBJ.?S\b|WAL[\s-]?MART|MURPHY'),
    ('Competitor', 'Publix/Kroger fuel', r'PUBLIX'),
]

def brand_of(name):
    n = (name or '').upper()
    for cat, b, pat in BRANDS:
        if re.search(pat, n): return cat, b
    return 'Other station', ''

def main(out):
    import time
    rows = []
    import geopandas as gpd
    names = gpd.read_file(os.path.join(out, 'fl_counties.geojson')).NAME.tolist()
    counties = sorted(n.upper().replace('ST ', 'ST. ').replace('DESOTO', 'DESOTO') for n in names)
    for county in counties:
      offset = 0
      while True:
        for attempt in range(4):
            r = requests.get(URL, params={'where': f"FACILITY_STATUS='OPEN' AND FACILITY_TYPE='Retail Station' AND COUNTY='{county}'",
                                      'orderByFields': 'OBJECTID',
                                      'outFields': 'FACILITY_ID,FACILITY_NAME,ADDRESS1,CITY,ZIP5,COUNTY,FACILITY_STATUS,REGULATED,COL_DATE',
                                      'outSR': 4326, 'f': 'json', 'resultOffset': offset, 'resultRecordCount': 1000}, timeout=180)
            if r.ok: break
            time.sleep(5)
        r.raise_for_status(); d = r.json()
        feats = d.get('features', [])
        for f in feats:
            a = f['attributes']; g = f.get('geometry') or {}
            cat, b = brand_of(a['FACILITY_NAME'])
            num = re.search(r'#\s*(\d{4,6})', a['FACILITY_NAME'] or '')
            rows.append(dict(fdep_facility_id=a['FACILITY_ID'], name=a['FACILITY_NAME'], category=cat, brand=b,
                             store_no=num.group(1) if num and cat == '7-Eleven family' else None,
                             address=a['ADDRESS1'], city=a['CITY'], zip=a['ZIP5'], fdep_county=a['COUNTY'],
                             lat=g.get('y'), lon=g.get('x'), coord_collected=a.get('COL_DATE')))
        if len(feats) < 1000: break
        offset += 1000
    df = pd.DataFrame(rows)
    rest = requests.get(URL, params={'where': "FACILITY_STATUS='OPEN' AND FACILITY_TYPE='Retail Station' AND COUNTY NOT IN (" +
                                     ','.join("'" + c + "'" for c in counties) + ")", 'returnCountOnly': 'true', 'f': 'json'}, timeout=180).json()
    print('open retail stations outside the county list (not pulled):', rest.get('count'))
    df['source'] = 'FDEP Registered Tanks (STCM), open retail stations, pulled ' + pd.Timestamp.today().strftime('%Y-%m-%d')
    df.to_csv(os.path.join(out, 'fdep_stations_fl.csv'), index=False)
    print(len(df), 'open retail stations'); print(df.groupby(['category', 'brand']).size().to_string())
    print('missing coords', df.lat.isna().sum())

if __name__ == '__main__':
    main(sys.argv[1])
