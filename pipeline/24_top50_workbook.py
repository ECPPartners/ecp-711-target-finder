"""Top N trade areas with corner options workbook (v1.3+; N = output.top_n_trade_areas).
Usage: python3 -I 24_top50_workbook.py <top50.csv> <corner_status.csv> <prior_review.xlsx> <out.xlsx>
prior_review.xlsx = last filled-in Top 50 review; its verdicts and Ross's comments carry onto matching corners.
"""
import sys, os, re
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import load_model
import importlib.util
_s = importlib.util.spec_from_file_location('wb20', os.path.join(os.path.dirname(os.path.abspath(__file__)), '20_review_workbook.py'))
wb20 = importlib.util.module_from_spec(_s); _s.loader.exec_module(wb20)
title, gmap, key, sheet, F = wb20.title, wb20.gmap, wb20.key, wb20.sheet, wb20.F
M = load_model(); O = M['output']; OP = M['options']; RL = M['raw_land']
wb20.WIDTH.update({'Option': 7, 'Option type': 16, 'Station at the corner': 24, 'Road side / positioning': 48, 'Land owner': 28,
                   'Prior verdict (Luke)': 10, 'Luke: why': 34, 'Ross comment': 48, 'Status': 9, 'Reason': 50, 'Decided by': 12})

def main(top_csv, status_csv, prior_xlsx, out):
    t = pd.read_csv(top_csv)
    top = t[t.in_top.fillna(False).astype(bool)].copy()
    top['n'] = top.option.str.extract(r'^(\d+)')[0].astype(int)
    top = top.sort_values(['n', 'option'])
    pr = pd.read_excel(prior_xlsx, sheet_name='Top 50')
    pr['k'] = [key(a, b) for a, b in zip(pr.Intersection, pr.County)]
    prior = pr.set_index('k')
    def pv(k, col):
        return prior.at[k, col] if k in prior.index and col in prior.columns and pd.notna(prior.at[k, col]) else None

    wb = Workbook(); ws = wb.active; ws.title = 'Read Me'
    n_multi = int((top.groupby('n').size() > 1).sum())
    TN = f"Top {O['top_n_trade_areas']}"
    lines = [(f"7-Eleven Target Area Finder — {TN} with corner options (model {M['version']} DRAFT)", True),
             ('ECP Partners · Confidential · Do not share outside ECP', False),
             (f"Built {pd.Timestamp.today():%Y-%m-%d}. Not published to the live tool until Ross approves.", False), ('', False),
             ('How to read it', True),
             (f"Each number is a trade area: corners within {O['trade_area_max_diameter_mi']:g} miles of each other with strong new-home growth "
              f"(an option with {O['min_area_new_homes']:,}+ new homes 2023-25 within 3 mi) and 2+ miles from any 7-Eleven fuel store. "
              f"Where an area has more than one viable corner they are listed as 2a, 2b, 2c ({n_multi} of the {O["top_n_trade_areas"]} areas have 2+ options; "
              f"{len(top)} corners in all). Up to {O['max_options_per_area']} options per area, ordered by the best roads (traffic and signal) "
              f"so 'a' is the corner on the strongest roads; each scores at least {int(O['min_secondary_score_ratio'] * 100)}% of the area's best.", False),
             ('Viable corner = raw land that passes the land screen (problems shown as warnings, not removed), or one owner with '
              f"{OP['redev_min_acres']}+ acres of vacant lots, farm land or a house on acreage at the corner (\"One-owner land\"). Built commercial "
              'corners and corners split among several owners with buildings are not options.', False),
             ('"Road side / positioning" says which side of the main road the option is on and which direction of traffic that side serves '
              '(north side of an east-west road = westbound, east side of a north-south road = northbound). Where a station is at the corner, it '
              'says whether the option is across the road from it (can outposition it for that direction) or on the same side. '
              'This is information for the deal maker; it does not change the score.', False),
             *[(f"{rn} tab: trade areas whose best corner is in {', '.join(rc['counties'])}, ranked on their own (P1, P2a ...), up to {rc['top_n']} areas. "
                'Same rules as the main list; not part of it.', False) for rn, rc in O.get('regions', {}).items()],
             (f"Highway Plays tab: up to {O.get('highway_top_n', 0)} corners with {O.get('highway_min_aadt', 0):,}+ cars/day in areas below the growth bar "
              f'(e.g. US-301 & CR-218). A separate short list, not part of the {TN}.', False),
             ('Grey columns carry Luke\'s v1.0 verdicts and Ross\'s Nov 23 comments. Yellow columns are for this review.', False), ('', False),
             (M.get('changes_heading', 'What changed from v1.2'), True),
             (M.get('changes_line') or '1. Top 50 trade areas with a/b/c options, ordered by best roads, up to 5 per area; highway plays listed separately (Ross, Nov 23). 2. Deal-maker corner status: corners marked taken or pass are left out '
              '(see Passed & Taken tab; edit reviews/corner_status.csv to change). 3. 7-Elevens the team knows about that the sources miss are added '
              '(Silver Palm Blvd & SR-52 NEC), so corners within 2 mi drop. 4. One-owner land options. 5. Station-at-corner and road-side notes. '
              'Scoring weights unchanged from v1.2 (traffic 35, new homes 25).', False), ('', False),
             ('PROPOSED — needs ECP confirmation', True),
             (f"• Strong growth = {O['min_area_new_homes']:,}+ new homes (2023-25, 3 mi) at one corner in the area. • Up to {O['max_options_per_area']} options per area. "
              f"• One-owner land: {OP['redev_min_acres']}+ ac, at most {OP['redev_max_buildings']} building. • Station at the corner = within {OP['station_m']} m.", False), ('', False),
             ('Known limits', True),
             *([(M['extra_limits'], False)] if M.get('extra_limits') else []),
             ('• Stations under construction are only caught '
              'if the parcel is already owned by a competitor or coded as a station (Circle K at US-41 & Symmes was not). • Tax roll as of Jan 1, 2026. '
              '• Silver Palm & SR-52 7-Eleven location is approximate until we have the address.', False), ('', False),
             ('Sources', True),
             ('FL Dept. of Revenue 2026 tax roll and parcel maps; FDOT 2025 AADT, functional classification, signals and rail layers; USFWS National Wetlands '
              'Inventory; AllThePlaces store runs Oct 2026; FDEP registered storage tanks; ECP 7-Eleven sales tracker 11/11/26; deal-maker reviews '
              '11/17 (Luke) and 11/23 (Ross). Rebuilt 2026-11-23.', False)]
    for txt, b in lines:
        ws.append([txt]); c = ws.cell(ws.max_row, 1)
        c.font = Font(name=F, bold=b, size=12 if b else 10); c.alignment = Alignment(wrap_text=True, vertical='top')
    ws.column_dimensions['A'].width = 140

    def row(r, label_col, label):
        raw = r.option_type == 'Raw land'
        return {label_col: label, 'County': r.county, '7-Eleven RE manager': r.re_manager, 'Intersection': title(r.intersection_name),
                     'Option type': r.option_type, 'Score': r.score, 'Tier': r.tier,
                     'New homes 2023-25 (3 mi)': int(r.new_rooftops_3mi), 'Combined AADT (FDOT 2025)': None if pd.isna(r.combined_aadt) else int(r.combined_aadt),
                     'Signal': r.signal, 'Nearest 7-Eleven (mi)': round(r.dist_to_7eleven_mi, 1), 'Nearest 7-Eleven': r.nearest_7eleven,
                     **({'New market': ('Yes' if r.dist_to_7eleven_mi >= O['new_market_mi'] else None)} if 'new_market_mi' in O else {}),
                     'Station at the corner': r.stations_at_corner if isinstance(r.stations_at_corner, str) else None,
                     'Road side / positioning': r.positioning if isinstance(r.positioning, str) else None,
                     'Land owner': r.land_owner if raw else r.redev_owner,
                     'Land acres': r.land_acres if raw else r.redev_acres,
                     'Land warnings': (r.land_warnings if raw and isinstance(r.land_warnings, str) and r.land_warnings else
                                       (None if raw else (f"{int(r.redev_buildings)} building(s) on the land" if r.redev_buildings else None))),
                     'Owner flag': r.land_flags if raw and isinstance(r.land_flags, str) else None,
                     'Why here': r.why_here, 'Google Maps': gmap(r.lat, r.lon),
                     'Prior verdict (Luke)': pv(r.k, 'Would you chase it?'), 'Luke: why': pv(r.k, 'Why / why not'), 'Ross comment': pv(r.k, 'Ross comments'),
                     'Call 7-Eleven on it? (Yes / Maybe / No)': None, 'Why / why not': None, 'What you already know': None, 'Reviewer': None}
    df = pd.DataFrame([row(r, 'Option', r.option) for _, r in top.iterrows()])
    ws2 = sheet(wb, TN, df, yellow=('Call 7-Eleven on it? (Yes / Maybe / No)', 'Why / why not', 'What you already know', 'Reviewer'), links=('Google Maps',))
    GRY = PatternFill('solid', start_color='EDEDED'); BAND = PatternFill('solid', start_color='F3F7FC')
    thick = Side(style='medium', color='1F3864')
    prev = None
    for rr in ws2.iter_rows(min_row=2):
        n = re.match(r'\d+', str(rr[0].value)).group()
        band = int(n) % 2 == 0
        for c in rr:
            h = df.columns[c.column - 1]
            if h in ('Prior verdict (Luke)', 'Luke: why', 'Ross comment'): c.fill = GRY
            elif band and c.fill.start_color.rgb in (None, '00000000'): c.fill = BAND
            if prev is not None and n != prev: c.border = Border(top=thick)
        rr[0].font = Font(name=F, size=10, bold=True)
        prev = n
    ws2.freeze_panes = 'E2'

    for rname in O.get('regions', {}):
        rg = t[t.get('in_region_top', pd.Series(False, index=t.index)).fillna(False).astype(bool) & (t.region == rname)].copy()
        if len(rg):
            rg['n'] = rg.option.str.extract(r'(\d+)')[0].astype(int); rg = rg.sort_values(['n', 'option'])
            sheet(wb, rname, pd.DataFrame([row(r, 'Option', r.option) for _, r in rg.iterrows()]),
                  yellow=('Call 7-Eleven on it? (Yes / Maybe / No)', 'Why / why not', 'What you already know', 'Reviewer'), links=('Google Maps',))
    hw = t[t.highway_rank.notna()].sort_values('highway_rank') if 'highway_rank' in t else t.iloc[:0]
    if len(hw):
        hdf = pd.DataFrame([row(r, 'Highway #', int(r.highway_rank)) for _, r in hw.iterrows()])
        sheet(wb, 'Highway Plays', hdf, yellow=('Call 7-Eleven on it? (Yes / Maybe / No)', 'Why / why not', 'What you already know', 'Reviewer'), links=('Google Maps',))
    # summary by 7-Eleven real estate manager and county
    top['mgr'] = top.re_manager.fillna('Unassigned')
    by = top.groupby(['mgr', 'county']).agg(areas=('n', 'nunique'), corners=('option', 'count'), best=('n', 'min')).reset_index()
    by = by.sort_values(['mgr', 'best']).rename(columns={'mgr': '7-Eleven RE manager', 'county': 'County', 'areas': 'Trade areas in list',
                                                       'corners': 'Corner options', 'best': 'Best area #'})
    tot = top.groupby('mgr').agg(a=('n', 'nunique'), c=('option', 'count')).reset_index()
    by = pd.concat([by] + [pd.DataFrame([{'7-Eleven RE manager': r.mgr, 'County': 'ALL', 'Trade areas in list': r.a, 'Corner options': r.c}]) for _, r in tot.iterrows()],
                   ignore_index=True).sort_values(['7-Eleven RE manager', 'County'])
    sheet(wb, 'By Manager', by)
    st = pd.read_csv(status_csv)
    s_rows = [{'Intersection': title(r.intersection), 'County': r.county, 'Status': r.status, 'Reason': r.reason, 'Decided by': r.decided_by,
               'Decided on': r.decided_on} for _, r in st.iterrows()]
    sheet(wb, 'Passed & Taken', pd.DataFrame(s_rows))

    tk = t.copy(); tk['k'] = [key(a, b) for a, b in zip(tk.intersection_name, tk.county)]; tk = tk.drop_duplicates('k').set_index('k')
    m_rows = []
    for _, r in pr.iterrows():
        k = r.k
        if k in tk.index:
            x = tk.loc[k]
            if x.get('in_top') == True: where = f"Option {x.option}"
            elif x.get('in_region_top') == True: where = f"{x.region} tab, option {x.option}"
            elif isinstance(x.get('status'), str): where = f"Left out: {x.status} ({x.status_reason})"
            elif x.get('viable') != True: where = 'Not a viable corner: ' + (x.land_fail if isinstance(x.land_fail, str) and x.land_fail else 'no raw parcel and no one-owner land')
            elif pd.notna(x.get('highway_rank')): where = f"Highway play #{int(x.highway_rank)}"
            elif x.get('area_growth_ok') != True: where = f"Trade area under {O['min_area_new_homes']:,} new homes"
            elif pd.notna(x.get('area_rank')) and x.area_rank > O['top_n_trade_areas']: where = f"Trade area ranks {int(x.area_rank)} (outside Top {O['top_n_trade_areas']})"
            else: where = f"In trade area {int(x.area_rank)} but not one of its listed options"
        else:
            where = 'Under 2 mi from a 7-Eleven (incl. team-known stores)'
        m_rows.append({'v1.0 rank': int(r.Rank), 'Intersection': r.Intersection, 'County': r.County,
                       'Luke: chase?': r['Would you chase it?'] if pd.notna(r['Would you chase it?']) else None,
                       'Ross comment': r['Ross comments'] if 'Ross comments' in pr and pd.notna(r['Ross comments']) else None, f"Where it is in {M['version']}": where})
    sheet(wb, f"v1.0 Top 50 → {M['version']}", pd.DataFrame(m_rows), links=())
    meth = [('Model', f"{M['version']} — {M['name']} (status: {M['status']})"), ('Scope', M.get('scope_approved')),
            ('Weights', ', '.join(f'{k} {v}' for k, v in M['weights'].items()) + f"; apartments count {M['mf_weight']}; signal unknown {M.get('signal_unknown_credit', 0.5)}"),
            ('Hard filter', f"{M['hard_filters']['min_miles_to_7eleven_fuel']}+ mi from any 7-Eleven/Speedway fuel store, incl. team-known stores (pipeline/manual_7eleven.csv)"),
            ('Land screen', f"Removed only if owned by a competitor/7-Eleven/rail/utility or under {RL.get('min_zone_acres')} ac near the corner; other problems are warnings"),
            ('One-owner land', f"{OP['redev_min_acres']}+ ac of vacant/farm/house-on-acreage land from one owner touching the corner, <= {OP['redev_max_buildings']} building"),
            ('Trade areas', f"Complete-linkage clusters of viable corners, max {O['trade_area_max_diameter_mi']} mi across; must have {O['min_area_new_homes']}+ new homes at one corner; ranked by best corner score"),
            ('Options', f"Up to {O['max_options_per_area']} per area, raw land first, ordered by best roads (traffic + signal points), each >= {int(O['min_secondary_score_ratio']*100)}% of the area's best score; no spacing rule"),
            ('Highway plays', f"Viable corners with {O.get('highway_min_aadt', 0):,}+ combined AADT in areas below the growth bar; top {O.get('highway_top_n', 0)} by score"),
            ('Deal-maker status', 'reviews/corner_status.csv: taken or pass corners are left out of the options'),
            ('Model history', 'All versions saved in the GitHub repo (models/); see the project doc "Scoring Model History".')]
    sheet(wb, 'Method', pd.DataFrame(meth, columns=['Item', 'Setting']))
    wb.save(out); print('saved', out, '| rows', len(df))

if __name__ == '__main__':
    main(*sys.argv[1:5])
