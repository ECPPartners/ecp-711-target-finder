"""Deal-maker review workbook for a trade-area model (v1.1+).
Usage: python3 -I 20_review_workbook.py <land.csv> <corners.csv> <areas.csv> <prior_review.xlsx> <out.xlsx>
prior_review.xlsx = the last filled-in review (Top 50 tab); its verdicts are carried onto matching corners.
"""
import sys, os, re
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import load_model

M = load_model(); O = M['output']; RL = M['raw_land']
F = 'Arial'
HDR = PatternFill('solid', start_color='1F3864'); YEL = PatternFill('solid', start_color='FFF2CC'); GRY = PatternFill('solid', start_color='EDEDED')
key = lambda a, b: re.sub(r'[^A-Z0-9]', '', str(a).upper()) + re.sub(r'[^A-Z0-9]', '', str(b).upper())
gmap = lambda la, lo: f'https://www.google.com/maps/search/?api=1&query={la:.6f},{lo:.6f}'
def title(s):
    out = []
    for p in str(s).split('&'):
        w = p.strip().title()
        w = re.sub(r"\b(Sr|Us|Cr|Sw|Nw|Ne|Se|N|S|E|W)\b(?=[ -]|$)", lambda m: m.group(1).upper(), w)
        w = re.sub(r"(\d)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), w)
        out.append(w)
    return ' & '.join(out)

def sheet(wb, name, df, widths, yellow=(), links=()):
    ws = wb.create_sheet(name)
    ws.append(list(df.columns))
    for c in ws[1]:
        c.font = Font(name=F, bold=True, color='FFFFFF'); c.fill = HDR; c.alignment = Alignment(wrap_text=True, vertical='top')
    for row in df.itertuples(index=False):
        ws.append([None if (isinstance(v, float) and pd.isna(v)) else v for v in row])
    for r in ws.iter_rows(min_row=2):
        for c in r:
            c.font = Font(name=F, size=10); c.alignment = Alignment(wrap_text=True, vertical='top')
            h = df.columns[c.column - 1]
            if h in yellow: c.fill = YEL
            if h in links and c.value:
                c.hyperlink = c.value; c.value = 'Open map'; c.font = Font(name=F, size=10, color='0563C1', underline='single')
            if isinstance(c.value, float): c.number_format = '0' if 'rank' in h.lower() else '#,##0.0'
            elif isinstance(c.value, int) and h not in ('Trade area', 'Corner #', 'v1.0 rank', 'Rank'): c.number_format = '#,##0'
    for i, w in enumerate(widths, 1): ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'B2'; ws.auto_filter.ref = ws.dimensions
    return ws

def main(land_csv, corners_csv, areas_csv, prior_xlsx, out):
    land = pd.read_csv(land_csv); c = pd.read_csv(corners_csv); a = pd.read_csv(areas_csv)
    pr = pd.read_excel(prior_xlsx, sheet_name='Top 50')
    pr['k'] = [key(x, y) for x, y in zip(pr.Intersection, pr.County)]
    prior = pr.set_index('k')
    for d in (c, land): d['k'] = [key(x, y) for x, y in zip(d.intersection_name, d.county)]
    def pv(k, col):
        return prior.at[k, col] if k in prior.index and pd.notna(prior.at[k, col]) else None
    top = a[a.trade_area_rank <= O['top_n_trade_areas']]
    shown = c[c.shown].sort_values(['trade_area_rank', 'corner_in_area'])

    wb = Workbook(); ws = wb.active; ws.title = 'Read Me'
    lines = [
        (f"7-Eleven Target Area Finder — model {M['version']} DRAFT for Ross", True),
        ('ECP Partners · Confidential · Do not share outside ECP', False),
        (f"Built {pd.Timestamp.today():%Y-%m-%d}. Not yet published to the live tool; v1.0 stays live until Ross approves this.", False),
        ('', False), ('What changed from v1.0 (from Luke\'s Nov 17 review of the Top 50)', True),
        ('1. Two-step list. The list is now trade areas first, then up to 3 corners in each. Corners within '
         f"{O['trade_area_max_diameter_mi']:g} miles of each other share one trade area (they draw on most of the same new homes). "
         'Trade areas rank by their best corner. Search the whole trade area, not just the corners listed.', False),
        ('2. Tighter land screen. A corner now needs a raw parcel that (a) has at least '
         f"{RL['min_upland_acres']} acres of upland within {RL['zone_m']} m (~{RL['zone_m'] * 3.28:.0f} ft) of the intersection after "
         'removing mapped wetlands (US Fish & Wildlife National Wetlands Inventory), (b) fronts both roads, and (c) isn\'t owned by a '
         'fuel/c-store competitor, 7-Eleven, a railroad or a utility. Walmart/Publix, church, hospital, school and government-affiliated '
         'owners are flagged, not removed. Corners where a competitor owns land are flagged (often a station in the works).', False),
        ('3. Scoring weights are unchanged from v1.0.', False),
        ('4. Luke\'s v1.0 verdicts are carried onto the same corners (grey columns) so nobody re-reviews them.', False),
        ('', False), ('Tabs', True),
        (f"Trade Areas: top {O['top_n_trade_areas']} trade areas. Corners: the corners in those areas (yellow columns to fill in). "
         'Screened Out: raw-land corners the new land screen removed, with the reason; rescue any that are wrong. '
         'v1.0 Top 50 → v1.1: where each corner Luke saw ended up. Method: settings for this model.', False),
        ('', False), ('PROPOSED — needs ECP confirmation', True),
        (f"• Trade area size: corners within {O['trade_area_max_diameter_mi']:g} mi of each other. • {O['corners_per_trade_area']} corners per area, "
         f"{O['min_corner_spacing_mi']:g} mi apart. • Top {O['top_n_trade_areas']} areas. • Upland needed: {RL['min_upland_acres']} ac within "
         f"{RL['zone_m']} m of the corner. • Frontage: parcel within {RL['frontage_m']} m of each road's centerline.", False),
        ('', False), ('Known limits', True),
        ('• NWI wetlands are mapped from aerials, sometimes decades old, and can be wrong in both directions. It removed Luke\'s Yes at '
         'New Kings Rd & 45th St W (rank 15), which is in Screened Out for a second look. • The tax roll is as of Jan 1, 2026, so corners built '
         'since then still look vacant (Luke\'s "corners all taken" at Community & Discovery and Henley & Sandridge aren\'t caught). '
         '• Trade areas only contain corners that pass the land screen; a better corner without raw land won\'t appear.', False),
        ('', False), ('Sources', True),
        ('FL Dept. of Revenue 2026 final tax roll and parcel maps (downloaded 2026-11-17); FDOT functional classification roads '
         '(pulled 2026-11-17); USFWS National Wetlands Inventory map service (pulled 2026-11-17); scores from model v1.0 (built 2026-11-11).', False),
    ]
    for t, b in lines:
        ws.append([t]); ws.cell(ws.max_row, 1).font = Font(name=F, bold=b, size=12 if b else 10)
        ws.cell(ws.max_row, 1).alignment = Alignment(wrap_text=True, vertical='top')
    ws.column_dimensions['A'].width = 140

    # Trade areas
    rows = []
    for _, r in top.iterrows():
        sub = shown[shown.trade_area_rank == r.trade_area_rank]
        rows.append({'Trade area': int(r.trade_area_rank), 'County': r.county, '7-Eleven RE manager': r.re_manager,
                     'Market': 'Proven' if str(r.market_type).startswith('Proven') else 'White space',
                     'Best corner': title(r.best_corner), 'Best score': r.best_score, 'Tier': r.tier,
                     'Corners passing land screen': int(r.corners_passing), 'Corners listed': int(r.corners_shown),
                     'Other corners listed': '; '.join(title(x) for x in sub.intersection_name.iloc[1:]) or '—',
                     'New homes 2023-25 (3 mi, max)': int(r.new_homes_3mi_max), 'Max combined AADT': None if pd.isna(r.aadt_max) else int(r.aadt_max),
                     'Nearest 7-Eleven (mi)': r.nearest_7eleven_mi,
                     'Luke (v1.0) on these corners': '; '.join(f"{title(x)}: {pv(k, 'Would you chase it?')}" for x, k in zip(sub.intersection_name, sub.k) if pv(k, 'Would you chase it?')) or '—',
                     'Google Maps (area center)': gmap(r.center_lat, r.center_lon),
                     'Right trade area? (Yes / No)': None, 'Better corner in this area we missed': None})
    sheet(wb, 'Trade Areas', pd.DataFrame(rows), [8, 11, 13, 11, 34, 8, 6, 10, 9, 40, 11, 11, 10, 40, 11, 14, 34],
          yellow=('Right trade area? (Yes / No)', 'Better corner in this area we missed'), links=('Google Maps (area center)',))

    # Corners
    rows = []
    for _, r in shown.iterrows():
        rows.append({'Trade area': int(r.trade_area_rank), 'Corner #': int(r.corner_in_area), 'Intersection': title(r.intersection_name),
                     'County': r.county, 'Score': r.score, 'Tier': r.tier, 'Why here': r.why_here,
                     'Raw parcel owner': r.land_owner, 'Parcel ID': r.land_parcel, 'Land use': r.land_use, 'Parcel acres': r.land_acres,
                     'Upland ac near corner': r.land_upland_ac_corner, 'Wetland ac near corner': r.land_wetland_ac_corner,
                     'Owner flag': r.land_flags if isinstance(r.land_flags, str) else None,
                     'Competitor owns land here': r.land_competitor_owns_corner_land if isinstance(r.land_competitor_owns_corner_land, str) else None,
                     'Combined AADT (FDOT 2025)': None if pd.isna(r.combined_aadt) else int(r.combined_aadt), 'Signal': r.signal,
                     'Nearest 7-Eleven (mi)': round(r.dist_to_7eleven_mi, 1), 'Nearest competitor': r.nearest_competitor, 'Access flag': r.access_flag,
                     'Google Maps': gmap(r.lat, r.lon),
                     'v1.0 rank': int(prior.at[r.k, 'Rank']) if r.k in prior.index else None,
                     'Luke v1.0: chase?': pv(r.k, 'Would you chase it?'), 'Luke v1.0: why': pv(r.k, 'Why / why not'),
                     'Would you chase it?': None, 'Why / why not': None, 'Raw parcel right?': None, 'Access OK?': None, 'What you already know': None, 'Reviewer': None})
    df = pd.DataFrame(rows)
    ws = sheet(wb, 'Corners', df, [8, 7, 34, 11, 7, 5, 40, 26, 20, 15, 8, 9, 9, 22, 18, 11, 8, 9, 20, 22, 10, 7, 8, 36, 10, 30, 9, 9, 24, 10],
               yellow=('Would you chase it?', 'Why / why not', 'Raw parcel right?', 'Access OK?', 'What you already know', 'Reviewer'), links=('Google Maps',))
    for r in ws.iter_rows(min_row=2):
        for c_ in r:
            if df.columns[c_.column - 1] in ('v1.0 rank', 'Luke v1.0: chase?', 'Luke v1.0: why'): c_.fill = GRY

    # Screened out
    so = land[land.raw_corner & (land.aerial_qa.fillna('') == '') & ~land.land_ok].sort_values('score', ascending=False)
    rows = [{'Intersection': title(r.intersection_name), 'County': r.county, 'Score': r.score, 'v1.0 Top 50 rank': int(prior.at[r.k, 'Rank']) if r.k in prior.index else None,
             'Luke v1.0: chase?': pv(r.k, 'Would you chase it?'), 'Why screened out': r.land_fail, 'Best raw parcel owner': r.land_owner,
             'Upland ac near corner': r.land_upland_ac_corner, 'Wetland ac near corner': r.land_wetland_ac_corner, 'Google Maps': gmap(r.lat, r.lon),
             'Wrong? Put it back (Yes + why)': None} for _, r in so.iterrows()]
    sheet(wb, 'Screened Out', pd.DataFrame(rows), [36, 11, 7, 9, 9, 48, 28, 9, 9, 10, 30], yellow=('Wrong? Put it back (Yes + why)',), links=('Google Maps',))

    # v1.0 top 50 -> v1.1
    cmap = c.set_index('k'); lmap = land.set_index('k')
    rows = []
    for _, r in pr.iterrows():
        k = r.k
        if k in cmap.index and cmap.at[k, 'shown']:
            where = f"Trade area {int(cmap.at[k, 'trade_area_rank'])}, corner {int(cmap.at[k, 'corner_in_area'])}"
        elif k in cmap.index:
            t = int(cmap.at[k, 'trade_area_rank'])
            where = f"Trade area {t} (outside top {O['top_n_trade_areas']})" if t > O['top_n_trade_areas'] else f"In trade area {t} but not in its top {O['corners_per_trade_area']} corners"
        else:
            where = 'Screened out: ' + str(lmap.at[k, 'land_fail']) if k in lmap.index else 'not found'
        rows.append({'v1.0 rank': int(r.Rank), 'Intersection': r.Intersection, 'County': r.County, 'Luke: chase?': r['Would you chase it?'] if pd.notna(r['Would you chase it?']) else None,
                     'Luke: why': r['Why / why not'] if pd.notna(r['Why / why not']) else None, 'Where it is in v1.1': where})
    sheet(wb, 'v1.0 Top 50 → v1.1', pd.DataFrame(rows), [8, 40, 11, 9, 60, 60])

    # Method
    meth = [('Model', f"{M['version']} — {M['name']} (status: {M['status']})"), ('Scope approved', M.get('scope_approved')),
            ('Weights (unchanged from v1.0)', ', '.join(f'{k} {v}' for k, v in M['weights'].items()) + f"; apartment/condo units count {M['mf_weight']}"),
            ('Hard filter', f"{M['hard_filters']['min_miles_to_7eleven_fuel']}+ miles from any 7-Eleven/Speedway fuel store"),
            ('Raw parcel', f"Vacant or agricultural parcel of {RL['min_acres']}+ ac within {RL['touch_m']} m of the intersection (FL DOR 2026), as in v1.0"),
            ('Upland test', f"Parcel area within {RL['zone_m']} m of the intersection minus NWI wetland/water polygons >= {RL['min_upland_acres']} ac"),
            ('Frontage test', f"Parcel within {RL['frontage_m']} m of each road (FDOT functional-class centerlines clipped to the corner zone; segments within {RL['same_road_angle_deg']}° count as one road)"),
            ('Excluded owners', 'Fuel/c-store competitors, 7-Eleven, railroads, utilities (plus v1.0 government/HOA/CDD exclusions)'),
            ('Flagged owners', ', '.join(RL['flag_owner_regex'].keys())),
            ('Trade areas', f"Complete-linkage clusters of passing corners, max {O['trade_area_max_diameter_mi']} mi between any two; ranked by best corner score"),
            ('Corners per area', f"Up to {O['corners_per_trade_area']}, best score first, at least {O['min_corner_spacing_mi']} mi apart"),
            ('Tiers', f"A = top {M['tiers']['A_top_pct']}%, B = next {M['tiers']['B_next_pct']}% (tiers still from v1.0 scoring pool)"),
            ('Model history', 'Every model version is saved in the GitHub repo (models/) and can be restored; see the project doc "Scoring Model History".')]
    sheet(wb, 'Method', pd.DataFrame(meth, columns=['Item', 'Setting']), [26, 120])
    wb.save(out); print('saved', out)

if __name__ == '__main__':
    main(*sys.argv[1:6])
