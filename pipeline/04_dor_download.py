"""Download FL Dept. of Revenue tax-roll (NAL) and parcel map (PIN) files for given counties.
Usage: python3 -I 04_dor_download.py <year e.g. 2026> <out_dir> <county> [<county> ...]
County names as DOR spells them in file names (e.g. Pasco, "Saint Johns", Duval).
Finds the latest Final release folder automatically if <year> is 'latest'.
"""
import sys, os, time, requests, urllib.parse

SITE = "https://floridarevenue.com"
API = SITE + "/property/dataportal/_api/web/GetFolderByServerRelativeUrl('{}')/{}?$select=Name,Length,ServerRelativeUrl"
ROOT = "/property/dataportal/Documents/PTO Data Portal"
H = {'Accept': 'application/json;odata=nometadata', 'User-Agent': 'Mozilla/5.0'}

def ls(folder, kind, tries=6):
    for a in range(tries):   # the DOR portal is slow and drops requests; retry with backoff
        try:
            r = requests.get(API.format(urllib.parse.quote(folder), kind), headers=H, timeout=240)
            r.raise_for_status(); return r.json()['value']
        except Exception:
            if a == tries - 1: raise
            time.sleep(30 * (a + 1))

def latest_final(sub):
    names = [f['Name'] for f in ls(f"{ROOT}/{sub}", 'Folders') if f['Name'].endswith('F')]
    return sorted(names)[-1]

def fetch(item, out):
    dest = os.path.join(out, item['Name'])
    if os.path.exists(dest) and os.path.getsize(dest) == int(item['Length']):
        return dest, 'have'
    url = SITE + urllib.parse.quote(item['ServerRelativeUrl'])
    for a in range(5):
        try:
            with requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(dest + '.part', 'wb') as f:
                    for chunk in r.iter_content(1 << 20): f.write(chunk)
            if os.path.getsize(dest + '.part') == int(item['Length']):
                os.replace(dest + '.part', dest); return dest, 'downloaded'
        except Exception as e:
            print('retry', item['Name'], e, flush=True)
        time.sleep(30 * (a + 1))
    return dest, 'FAILED'

def main(year, out, counties):
    os.makedirs(out, exist_ok=True)
    nal_rel = latest_final('Tax Roll Data Files/NAL') if year == 'latest' else f'{year}F'
    map_rel = latest_final('Map Data') if year == 'latest' else f'{year}F'
    nal = ls(f"{ROOT}/Tax Roll Data Files/NAL/{nal_rel}", 'Files')
    pin = ls(f"{ROOT}/Map Data/{map_rel}/{map_rel} PIN", 'Files')
    print('NAL release', nal_rel, '| map release', map_rel)
    for c in counties:
        key = c.lower().replace(' ', '')
        n = [f for f in nal if f['Name'].lower().replace(' ', '').startswith(key)]
        mk = key.replace('saint', 'st')
        p = [f for f in pin if f['Name'].lower().replace(' ', '').startswith((mk + '_', key + '_', 'miami' + mk + '_', 'miami-' + mk + '_')) and 'pin' in f['Name'].lower()]
        for item in n[:1] + p[:1]:
            print(c, *fetch(item, out), round(int(item['Length']) / 1e6, 1), 'MB', flush=True)
        if not n or not p: print('NOT FOUND', c, 'nal' if not n else '', 'pin' if not p else '')

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
