"""Assemble the '7-Eleven Source Data' Excel workbook for the pilot counties.
Usage: python3 -I 08_source_workbook.py <out_dir> <xlsx_path>
Joins stores to the nearest DOR commercial parcel (<= 60 m) to read the parcel's actual year built
(an INFERENCE of the store's build year, labeled as such).
"""
import sys, os, glob, json
import pandas as pd, geopandas as gpd, numpy as np

PILOT = {'Duval': 'Bauer', 'St Johns': 'Bauer', 'Clay': 'Bauer', 'Volusia': 'Bauer', 'Brevard': 'Bauer',
         'Pasco': 'Golden', 'Hillsborough': 'Golden', 'St Lucie': 'Antonacci'}
TODAY = pd.Timestamp.today().strftime('%Y-%m-%d')

def load_parcels(out):
    frames = [pd.read_csv(p, dtype={'pid': str, 'uc': str}) for p in glob.glob(os.path.join(out, 'parcels', 'parcels_*.csv'))]
    p = pd.concat(frames, ignore_index=True)
    return gpd.GeoDataFrame(p, geometry=gpd.points_from_xy(p.lon, p.lat), crs=4326).to_crs(3086)

def nearest_parcel_year(pts, com):
    j = gpd.sjoin_nearest(pts.to_crs(3086), com[['pid', 'uc', 'yr', 'addr', 'geometry']], how='left', max_distance=60, distance_col='parcel_dist_m')
    j = j[~j.index.duplicated()]
    return j[['pid', 'uc', 'yr', 'parcel_dist_m']]

def main(out, xlsx):
    counties = gpd.read_file(os.path.join(out, 'fl_counties.geojson'))[['NAME', 'geometry']].rename(columns={'NAME': 'county'})
    print('county names:', sorted(counties.county)[:70])
    parcels = load_parcels(out)
    com = parcels[parcels.kind == 'commercial']

    # 1. 7-Eleven network (pilot)
    se = pd.read_csv(os.path.join(out, 'seven_eleven_fl.csv'))
    se = se[se.county.isin(PILOT)].copy()
    g = gpd.GeoDataFrame(se, geometry=gpd.points_from_xy(se.lon, se.lat), crs=4326)
    py = nearest_parcel_year(g, com)
    se['parcel_id'] = py.pid.values; se['parcel_use_code'] = py.uc.values
    se['parcel_year_built (inferred store age)'] = py.yr.values
    se['re_manager'] = se.county.map(PILOT)
    yb = pd.to_numeric(se['parcel_year_built (inferred store age)'], errors='coerce').fillna(pd.to_numeric(se.tracker_year_built, errors='coerce'))
    se['vintage (inferred)'] = np.where(yb >= 2018, 'New build (2018+)', np.where(yb.notna(), 'Legacy (pre-2018)', 'Unknown'))
    se['format'] = np.where(se.has_fuel == 'Y', 'Fuel', 'Non-fuel')
    net = se[['brand', 'store_ref', 'in_7eleven_api', 'in_fdep', 'fdep_facility_id', 'address', 'city', 'zip', 'county', 're_manager', 'format', 'diesel', 'vintage (inferred)',
              'parcel_year_built (inferred store age)', 'parcel_id', 'parcel_use_code', 'tracker_tab', 'tracker_date',
              'tracker_year_built', 'tracker_acres', 'tracker_sf', 'tracker_match_method', 'lat', 'lon', 'source']]

    # 2/3. Competitors, anchors & grocers (pilot)
    st = gpd.read_file(os.path.join(out, 'stores_fl.geojson'))
    st = st.rename(columns={'NAME': 'county'})
    st = st[st.county.isin(PILOT)]
    fd = pd.read_csv(os.path.join(out, 'fdep_stations_fl.csv'))
    fd = fd[fd.category == 'Competitor']
    fdg = gpd.sjoin(gpd.GeoDataFrame(fd, geometry=gpd.points_from_xy(fd.lon, fd.lat), crs=4326), counties, how='inner', predicate='within')
    fdg = fdg[fdg.county.isin(PILOT)]
    comp = pd.DataFrame({'category': 'Competitor', 'brand': fdg.brand, 'name': fdg['name'], 'street': fdg.address, 'city': fdg.city,
                         'zip': fdg.zip, 'county': fdg.county, 'lat': fdg.lat, 'lon': fdg.lon, 'source': fdg.source,
                         'fuel_diesel': None, 'fuel_hgv': None})
    anc = st[st.category.isin(['Grocer', 'Anchor', 'National QSR/retail'])].copy()
    py = nearest_parcel_year(anc, com)
    anc['parcel_year_built (inferred)'] = py.yr.values
    anc['new_since_2023 (inferred)'] = np.where(pd.to_numeric(anc['parcel_year_built (inferred)'], errors='coerce') >= 2023, 'Y', '')
    keep = ['category', 'brand', 'name', 'street', 'city', 'zip', 'county', 'lat', 'lon', 'source']
    comp = comp[keep + ['fuel_diesel', 'fuel_hgv']]
    anc = anc[keep + ['parcel_year_built (inferred)', 'new_since_2023 (inferred)']]

    # 4. Traffic (AADT segments)
    aadt = gpd.read_file(os.path.join(out, 'fdot', 'fdot_aadt.geojson'))
    aadt['trucks_per_day'] = (aadt.AADT * aadt.TFCTR / 100).round()
    mid = aadt.geometry.interpolate(0.5, normalized=True)
    aadt['mid_lat'], aadt['mid_lon'] = mid.y, mid.x
    traffic = aadt[['COUNTY', 'ROADWAY', 'DESC_FRM', 'DESC_TO', 'YEAR_', 'AADT', 'TFCTR', 'trucks_per_day', 'COSITE', 'mid_lat', 'mid_lon']]
    traffic = traffic.rename(columns={'COUNTY': 'county', 'ROADWAY': 'fdot_roadway_id', 'DESC_FRM': 'from', 'DESC_TO': 'to',
                                      'YEAR_': 'count_year', 'TFCTR': 'truck_pct', 'COSITE': 'count_site'})
    traffic['source'] = 'FDOT Annual Average Daily Traffic (TDA), pulled ' + TODAY
    sig = gpd.read_file(os.path.join(out, 'fdot', 'fdot_signals.geojson'))
    sig_summary = sig.groupby('COUNTY').size().rename('fdot_signals').reset_index()

    # 5. Rooftops by ZIP-less summary: by county and city
    parcels['city'] = parcels.city.fillna('').astype(str).str.upper().str.strip()
    res = parcels[parcels.kind == 'res'].copy()
    res['period'] = pd.cut(res.yr, [2009, 2019, 2022, 2026], labels=['2010-2019', '2020-2022', '2023-2025'])
    roof = res.groupby(['city', 'period'], observed=False).units.sum().unstack(fill_value=0).reset_index()
    vac = parcels[parcels.kind == 'vacant_lot'].groupby('city').size().rename('vacant_platted_lots').reset_index()
    roof = roof.merge(vac, on='city', how='outer').fillna(0)
    roof = roof[roof.city.astype(str).str.strip() != ''].sort_values('2023-2025', ascending=False)
    roof['source'] = 'FL DOR 2026 Final NAL + 2026 parcel map; units = DOR NO_RES_UNTS (min 1) by actual year built'

    # 6. Sources & dates
    sources = pd.DataFrame([
        ['7-Eleven / Speedway stores', 'FDEP registered storage tanks (open retail stations named 7-Eleven/Speedway/Stripes) merged with 7-Eleven store API via AllThePlaces', 'FDEP pulled ' + TODAY + '; API run 2026-10-31', 'Hard data. FDEP covers fuel stores; non-fuel stores come from the API only. An OPEN FDEP record can include a store under construction.'],
        ['Fuel vs non-fuel', "7-Eleven's own store API (fuel record present)", 'Run 2026-10-31', 'Hard data'],
        ['Store vintage', 'Year built of nearest DOR commercial parcel (<=60 m), else tracker year built', 'DOR 2026 Final', 'INFERENCE'],
        ['Competitors', 'FDEP registered storage tanks: open retail stations, brand from facility name (Wawa, RaceTrac, Circle K, Sunoco, Murphy USA, Buc-ee\'s, Love\'s, Pilot, etc.)', 'Pulled ' + TODAY, 'Hard data; brand tag is a name match (stations renamed after a sale may be mis-tagged)'],
        ['Anchors & grocers', 'AllThePlaces: Publix, Aldi, Winn-Dixie, Walmart, Target, Costco, Sam\'s, Home Depot, Lowe\'s, Tractor Supply, McDonald\'s, etc.', 'Runs 2026-10-10 to 10-31', "Hard data; Walmart and Lowe's INCOMPLETE; Dollar General partial"],
        ['New grocery flag', 'Grocer on a parcel with year built 2023+', 'DOR 2026 Final', 'INFERENCE'],
        ['Traffic & trucks', 'FDOT AADT TDA layer (AADT, truck factor)', 'Count year 2025, pulled ' + TODAY, 'Hard data'],
        ['Signals', 'FDOT Traffic Signal Locations TDA', 'Pulled ' + TODAY, 'Hard data; appears to cover state road system only'],
        ['Rooftops', 'FL DOR NAL tax roll + parcel map', '2026 Final roll (year built through 2025)', 'Hard data; 0.2-6.6% of parcels per county not on the parcel map (newest splits undercounted)'],
        ['ECP sales tracker', '7-Eleven 2026 Sales Tracker (11/11/26)', '2026-11-11', 'ECP data'],
        ['RE manager territories', '7-Eleven FL-Southeast Development Team Map', 'Feb 2026', 'ECP data'],
    ], columns=['Dataset', 'Source', 'As of', 'Data class'])
    gaps = pd.DataFrame([
        ['7-Eleven network (fixed Nov 10)', f"Now FDEP + 7-Eleven API. {int(net.tracker_tab.notna().sum())} of the pilot stores carry a tracker match; statewide 54 of 64 tracker rows match (the rest are duplicate listings or address-format mismatches: Apollo Beach, St. Augustine, CR-210 St. Johns, Homosassa, San Antonio, Homestead, Eustis, Winter Haven).",
         'Luke spot-checks Hillsborough and Pasco; confirm the unmatched tracker sites.'],
        ['Walmart / Lowe\'s incomplete', 'AllThePlaces spiders returned partial data in all recent runs.', 'Retry each monthly refresh; Publix/Aldi/Target/Home Depot complete.'],
        ['County-road signals', 'FDOT signals layer appears to cover state roads only.', 'Mark unknown; Luke verifies on site.'],
        ['7-eleven.com', 'Still blocked from scripts after allowlisting (may be bot-blocking or not yet applied).', 'Not needed now that FDEP works; recheck later.'],
    ], columns=['Gap', 'Detail', 'Fix'])

    with pd.ExcelWriter(xlsx, engine='openpyxl') as w:
        pd.DataFrame({'7-Eleven Source Data — ECP Partners — CONFIDENTIAL': [
            f'Pilot counties: {", ".join(PILOT)}', f'Built {TODAY}', 'Data class key: Hard data = from the source as published; ECP data = from ECP; INFERENCE = derived by Claude, verify before relying on it.',
            'See Data Gaps for known limits.']}).to_excel(w, 'Read Me', index=False)
        net.to_excel(w, '7-Eleven Network', index=False)
        comp.to_excel(w, 'Competitors', index=False)
        anc.to_excel(w, 'Anchors & Grocers', index=False)
        traffic.to_excel(w, 'Traffic', index=False)
        sig_summary.to_excel(w, 'Signals by County', index=False)
        roof.to_excel(w, 'Rooftops by City', index=False)
        sources.to_excel(w, 'Sources & Dates', index=False)
        gaps.to_excel(w, 'Data Gaps', index=False)
    print('network', len(net), net['vintage (inferred)'].value_counts().to_dict(), net.format.value_counts().to_dict())
    print('competitors', comp.brand.value_counts().to_dict())
    print('anchors', anc.brand.value_counts().to_dict(), '| new grocers', (anc['new_since_2023 (inferred)'] == 'Y').sum())
    print('traffic segs', len(traffic), '| rooftop cities', len(roof))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
