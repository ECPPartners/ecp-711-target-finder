# ECP 7-Eleven Target Area Finder — pipeline

Confidential to ECP Partners. Spec and build plan live in the claude.ai project "711 target area finder".

Run order (pilot counties), from a work dir with `dl/` and `out/`:
1. `01_atp_pull.py <run_id> dl/atp` — brand locations from AllThePlaces
2. `02_counties_stores.py dl/atp out` — FDOT county polygons + Florida store inventory
3. `03_fdot_pull.py out/fdot` — FDOT AADT/trucks, functional class, local names, signals, medians
4. `04_dor_download.py 2026 dl/dor <counties...>` — DOR NAL + parcel map zips
5. `05_tracker_geocode.py <tracker.xlsx> out/tracker_fl.csv` — ECP sales tracker FL rows
6. `06_parcels.py dl/dor dl/dor_x out/parcels <counties...>` — parcel points (res / vacant lots / commercial)
7. `07_network.py dl/atp out` — 7-Eleven network + tracker match
8. `10_fdep_stations.py out` — FDEP open retail fuel stations (run before 07)
9. `08_source_workbook.py out "<xlsx>"` then `09_format_xlsx.py "<xlsx>"`

Python deps: geopandas pyogrio pyarrow remotezip requests openpyxl
