"""Florida rows of ECP's 7-Eleven sales tracker -> geocoded (Census geocoder, onelineaddress).
Usage: python3 -I 05_tracker_geocode.py <tracker.xlsx> <out.csv>
Rows with intersection-style addresses (e.g. 'SWC Hwy 44 & Abrams Rd') are geocoded as intersections
via the Census geocoder where possible; unresolved rows are left blank and flagged.
"""
import sys, os, re, time, requests, openpyxl, pandas as pd

GEO = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

def geocode(addr):
    for _ in range(3):
        try:
            r = requests.get(GEO, params={'address': addr, 'benchmark': 'Public_AR_Current', 'format': 'json'}, timeout=60)
            m = r.json()['result']['addressMatches']
            if m: return m[0]['coordinates']['y'], m[0]['coordinates']['x'], m[0]['matchedAddress']
            return None, None, None
        except Exception:
            time.sleep(2)
    return None, None, None

def main(xlsx, out):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from tracker_parse import read_tracker
    t = read_tracker(xlsx)
    t = t[t.state == 'FL']
    rows = [dict(tracker_tab=r.tracker_tab, address=r.address, city=r.city, date=r.date, year_built=r.year_built, building_sf=r.building_sf,
                 acres=r.acres, cap_rate=r.cap_rate, annual_rent=r.annual_rent) for r in t.itertuples()]
    df = pd.DataFrame(rows).drop_duplicates(subset=['address', 'city', 'tracker_tab'])
    lat, lon, matched = [], [], []
    for _, r in df.iterrows():
        a = re.sub(r'^(NWC|NEC|SWC|SEC|NEQ|NWQ|SEQ|SWQ)\s+(of\s+)?', '', r['address'], flags=re.I)
        y, x, m = geocode(f"{a}, {r['city']}, FL")
        lat.append(y); lon.append(x); matched.append(m)
    df['lat'], df['lon'], df['geocode_match'] = lat, lon, matched
    df['geocode_source'] = 'U.S. Census Geocoder (Public_AR_Current), ' + time.strftime('%Y-%m-%d')
    df.to_csv(out, index=False)
    print(len(df), 'FL rows;', df['lat'].notna().sum(), 'geocoded')
    print(df[df['lat'].isna()][['tracker_tab', 'address', 'city']].to_string())

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
