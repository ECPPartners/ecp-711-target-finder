"""Read ECP's 7-Eleven sales tracker (any version) into one table.
Handles both layouts: the 2025 file (no 'Lease Expiration' column) and the 2026 file (adds 'Lease Expiration'
after 'Lease Term Remaining'). Tabs with a header row are read by column name; tabs without one (Pulled from
Market) are read by position, detecting the layout per row (a date in column 11 = 2026 layout).
"""
import datetime as dt
import openpyxl, pandas as pd

OLD = ['Tenant', 'Address', 'City', 'State', 'Date', 'Days on Market', 'Price', 'Cap Rate', 'Annual Rent', 'Lease Term Remaining',
       'Lease Type', 'LL Responsibilities', 'Year Built', 'Building SF', 'Land (Acres)', 'Rent/SF', 'Price/SF', 'Increases']
NEW = OLD[:10] + ['Lease Expiration'] + OLD[10:]
ALIASES = {'property address': 'Address', 'address': 'Address', 'listed date': 'Date', 'sold date': 'Date', 'asking price': 'Price',
           'sales price': 'Price', 'year built/renovated': 'Year Built', 'year built': 'Year Built'}

def _canon(h):
    h = str(h or '').strip()
    return ALIASES.get(h.lower(), h)

def read_tracker(xlsx):
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    out = []
    for tab in ['On Market', 'Sold', 'Pulled from Market']:
        if tab not in wb.sheetnames: continue
        rows = [r for r in wb[tab].iter_rows(values_only=True)]
        hdr = None
        if rows and rows[0] and str(rows[0][0]).strip() == 'Tenant':
            hdr = [_canon(h) for h in rows[0]]; rows = rows[1:]
        for r in rows:
            if not r or not r[1] or r[0] in (None, 'Tenant'): continue
            if hdr: d = dict(zip(hdr, r))
            else: d = dict(zip(NEW if isinstance(r[10], (dt.date, dt.datetime)) else OLD, r))
            try: rent = float(d.get('Annual Rent'))
            except (TypeError, ValueError): rent = None
            out.append(dict(tracker_tab=tab, tenant=d.get('Tenant'), address=str(d.get('Address') or '').strip(),
                            city=str(d.get('City') or '').strip(), state=str(d.get('State') or '').strip().upper(),
                            date=str(d.get('Date'))[:10], annual_rent=rent, year_built=d.get('Year Built'),
                            building_sf=d.get('Building SF'), acres=d.get('Land (Acres)'), cap_rate=d.get('Cap Rate'),
                            lease_type=d.get('Lease Type')))
    return pd.DataFrame(out)
