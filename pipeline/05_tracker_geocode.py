"""Florida rows of ECP's 7-Eleven sales tracker -> geocoded (Census geocoder, onelineaddress).
Usage: python3 -I 05_tracker_geocode.py <tracker.xlsx> <out.csv>
Rows with intersection-style addresses (e.g. 'SWC Hwy 44 & Abrams Rd') are geocoded as intersections
via the Census geocoder where possible; unresolved rows are left blank and flagged.
"""
import sys, re, time, requests, openpyxl, pandas as pd

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
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    rows = []
    for sheet, datecol in [('On Market', 'Listed Date'), ('Sold', 'Sold Date'), ('Pulled from Market', 'Listed Date')]:
        data = [r for r in wb[sheet].iter_rows(values_only=True)]
        hdr_i = next(i for i, r in enumerate(data) if r and r[0] == 'Tenant') if any(r and r[0] == 'Tenant' for r in data) else 0
        hdr = [str(h).strip() if h else f'col{i}' for i, h in enumerate(data[hdr_i])] if data[hdr_i][0] == 'Tenant' else \
              ['Tenant', 'Property Address', 'City', 'State', datecol, 'Days on Market', 'Price', 'Cap Rate', 'Annual Rent',
               'Lease Term Remaining', 'Lease Type', 'LL Responsibilities', 'Year Built', 'Building SF', 'Land (Acres)',
               'Rent/SF', 'Price/SF', 'Increases']
        for r in data[hdr_i + 1:]:
            if not r or not r[3] or str(r[3]).strip() != 'FL': continue
            d = dict(zip(hdr, r))
            rows.append({'tracker_tab': sheet, 'address': str(d.get('Property Address') or '').strip(),
                         'city': str(d.get('City') or '').strip(), 'date': d.get(datecol) or d.get('Sold Date') or d.get('Listed Date'),
                         'year_built': d.get('Year Built') or d.get('Year Built/Renovated'), 'building_sf': d.get('Building SF'),
                         'acres': d.get('Land (Acres)'), 'cap_rate': d.get('Cap Rate'), 'annual_rent': d.get('Annual Rent')})
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
