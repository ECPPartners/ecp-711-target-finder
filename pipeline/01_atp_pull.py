"""Pull brand store locations from an AllThePlaces run (remote zip, range reads).
Usage: python3 -I 01_atp_pull.py <run_id> <out_dir>
Writes <out_dir>/<spider>.geojson for each spider that is non-empty in that run.
"""
import sys, os, json, time
from remotezip import RemoteZip

SPIDERS = ['seven_eleven_ca_us', 'speedway_us', 'wawa', 'race_trac_us', 'circle_k', 'sunoco_us',
           'murphy_usa_us', 'bucees_us', 'publix_us', 'walmart_us', 'winn_dixie_us', 'aldi_sud_us',
           'target_us', 'costco_ca_gb_us', 'sams_club', 'home_depot', 'lowes_us', 'tractor_supply',
           'mcdonalds', 'dollar_general', 'whole_foods', 'trader_joes_us', 'sprouts_farmers_market',
           'starbucks_us']

def main(run_id, out):
    os.makedirs(out, exist_ok=True)
    url = f"https://alltheplaces-data.openaddresses.io/runs/{run_id}/output.zip"
    status = {}
    for sp in SPIDERS:
        dest = os.path.join(out, f"{sp}.geojson")
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            status[sp] = 'have'; continue
        for attempt in range(3):
            try:
                with RemoteZip(url) as z:
                    name = f"output/{sp}.geojson"
                    if name not in z.namelist():
                        status[sp] = 'missing'; break
                    if z.getinfo(name).file_size == 0:
                        status[sp] = 'empty'; break
                    open(dest, 'wb').write(z.read(name))
                    status[sp] = 'ok'; break
            except Exception as e:
                status[sp] = f'error: {e}'; time.sleep(3)
    print(json.dumps(status, indent=1))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
