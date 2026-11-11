"""Build-to-suit 7-Eleven deals from ECP's sales tracker (annual rent >= $350,000, per Ross), with coordinates.
Usage: python3 -I 13_bts_sites.py <tracker.xlsx> <atp_dir> <out_dir>
Location order: (1) the 7-Eleven / Speedway store API record (AllThePlaces) in the same state and city whose
address shares the house number and street tokens; (2) FL only: the merged FL network (FDEP + API);
(3) U.S. Census geocoder. Unresolved rows are kept and flagged.
Output: <out_dir>/bts_sites.csv
"""
import sys, os, re, json, time, requests, openpyxl, pandas as pd

HDR = ['Tenant', 'Property Address', 'City', 'State', 'Date', 'Days on Market', 'Price', 'Cap Rate', 'Annual Rent', 'Lease Term Remaining',
       'Lease Type', 'LL Responsibilities', 'Year Built', 'Building SF', 'Land (Acres)', 'Rent/SF', 'Price/SF', 'Increases']
STOP = {'road', 'rd', 'street', 'st', 'avenue', 'ave', 'highway', 'hwy', 'blvd', 'boulevard', 'drive', 'dr', 'the', 'and', 'of', 'parkway', 'pkwy',
        'lane', 'ln', 'way', 'nec', 'nwc', 'sec', 'swc', 'n', 's', 'e', 'w', 'north', 'south', 'east', 'west', 'us', 'sr', 'fm', 'cr'}

def toks(s):
    return set(re.findall(r'[a-z]{3,}|\d+', str(s).lower())) - STOP

def tracker_rows(xlsx):
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    out = []
    for tab in ['On Market', 'Sold', 'Pulled from Market']:
        data = [r for r in wb[tab].iter_rows(values_only=True)]
        start = 1 if data and data[0] and data[0][0] == 'Tenant' else 0
        if start == 0: start = 1 if all(v is None for v in (data[0] or [])) else 0
        for r in data[start:]:
            if not r or not r[1] or r[0] in (None, 'Tenant'): continue
            d = dict(zip(HDR, r))
            try: rent = float(d['Annual Rent'])
            except (TypeError, ValueError): continue
            out.append(dict(tab=tab, tenant=d['Tenant'], address=str(d['Property Address']).strip(), city=str(d['City'] or '').strip(),
                            state=str(d['State'] or '').strip().upper(), date=str(d['Date'])[:10], annual_rent=rent,
                            year_built=d['Year Built'], building_sf=d['Building SF'], acres=d['Land (Acres)'], lease_type=d['Lease Type']))
    return pd.DataFrame(out)

def api_stores(atp):
    rows = []
    for sp in ['seven_eleven_ca_us', 'speedway_us']:
        for f in json.load(open(os.path.join(atp, f'{sp}.geojson')))['features']:
            p = f['properties']
            if sp == 'seven_eleven_ca_us' and not p.get('shop'): continue
            g = f.get('geometry') or {}
            if g.get('type') != 'Point': continue
            rows.append(dict(state=(p.get('addr:state') or '').upper(), city=(p.get('addr:city') or '').lower().strip(),
                             addr=p.get('addr:street_address') or '', lon=g['coordinates'][0], lat=g['coordinates'][1]))
    return pd.DataFrame(rows)

def match_api(r, api):
    cand = api[(api.state == r.state)]
    city = r.city.lower().replace('saint ', 'st. ').strip()
    c2 = cand[cand.city.str.startswith(city[:6])]
    num = re.match(r'^\s*(\d+)', r.address)
    best = None
    for _, s in (c2 if len(c2) else cand).iterrows():
        a = s.addr.lower()
        sc = len(toks(r.address) & toks(a)) + (3 if num and a.startswith(num.group(1) + ' ') else 0)
        if sc >= 3 and (best is None or sc > best[0]): best = (sc, s)
    return (best[1].lat, best[1].lon, f'7-Eleven store API address match ({best[1].addr}, {best[1].city.title()})') if best else None

def census(addr, city, state):
    a = re.sub(r'^(NWC|NEC|SWC|SEC|NEQ|NWQ|SEQ|SWQ)\s+(of\s+)?', '', addr, flags=re.I)
    for _ in range(3):
        try:
            m = requests.get("https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
                             params={'address': f'{a}, {city}, {state}', 'benchmark': 'Public_AR_Current', 'format': 'json'}, timeout=60).json()['result']['addressMatches']
            return (m[0]['coordinates']['y'], m[0]['coordinates']['x'], 'Census geocoder: ' + m[0]['matchedAddress']) if m else None
        except Exception: time.sleep(2)
    return None

def main(xlsx, atp, out):
    t = tracker_rows(xlsx)
    print('tracker rows with rent', len(t))
    b = t[t.annual_rent >= 350000].drop_duplicates(subset=['address', 'city', 'state']).reset_index(drop=True)
    print('BTS (rent >= $350K), unique sites', len(b))
    api = api_stores(atp)
    fl = pd.read_csv(os.path.join(out, 'seven_eleven_fl.csv'))
    lat, lon, how = [], [], []
    for _, r in b.iterrows():
        m = match_api(r, api)
        if not m and r.state == 'FL':
            fm = fl[fl.tracker_tab.notna() & (fl.city.fillna('').str.lower().str[:6] == r.city.lower()[:6])]
            for _, s in fm.iterrows():
                if len(toks(r.address) & toks(s.address)) >= 2: m = (s.lat, s.lon, f'FL network (FDEP/API) match ({s.address})'); break
        if not m: m = census(r.address, r.city, r.state)
        lat.append(m[0] if m else None); lon.append(m[1] if m else None); how.append(m[2] if m else 'UNRESOLVED')
    b['lat'], b['lon'], b['location_source'] = lat, lon, how
    b.to_csv(os.path.join(out, 'bts_sites.csv'), index=False)
    print(b.location_source.str.split(':| \\(').str[0].value_counts().to_string())
    print(b[b.lat.isna()][['state', 'city', 'address']].to_string())

if __name__ == '__main__':
    main(*sys.argv[1:4])
