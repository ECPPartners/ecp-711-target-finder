"""Contact sheets of before/after aerial pairs for review.
Usage: python3 -I 15_contact_sheets.py <bts_sites.csv> <img_dir> <sheet_dir> [per_sheet=6] [px=300]
"""
import sys, os, pandas as pd
from PIL import Image, ImageDraw, ImageFont

def main(csv, img, out, per=6, px=300):
    os.makedirs(out, exist_ok=True)
    s = pd.read_csv(csv)
    rel = pd.read_csv(os.path.join(img, 'releases_used.csv')).set_index('idx')
    idx = [i for i in rel.index if os.path.exists(os.path.join(img, f'{i:03d}_before.jpg'))]
    try: font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 13)
    except OSError: font = ImageFont.load_default()
    lab = 230
    for k in range(0, len(idx), per):
        chunk = idx[k:k + per]
        sheet = Image.new('RGB', (lab + 2 * px + 20, len(chunk) * (px + 8)), 'white')
        d = ImageDraw.Draw(sheet)
        for j, i in enumerate(chunk):
            y = j * (px + 8); r = s.loc[i]; u = rel.loc[i]
            txt = f"#{i}\n{str(r.address)[:30]}\n{str(r.city)[:22]}, {r.state}\nBuilt {u.year_built}\nBefore: {u.before_release}\nAfter: {u.after_release}"
            d.multiline_text((6, y + 6), txt, fill='black', font=font, spacing=4)
            for c, tag in enumerate(('before', 'after')):
                im = Image.open(os.path.join(img, f'{i:03d}_{tag}.jpg')).resize((px, px))
                sheet.paste(im, (lab + c * (px + 10), y))
        sheet.save(os.path.join(out, f'sheet_{k // per + 1:02d}.jpg'), quality=80)
    print(len(idx), 'sites on', (len(idx) + per - 1) // per, 'sheets')

if __name__ == '__main__':
    a = sys.argv
    main(a[1], a[2], a[3], int(a[4]) if len(a) > 4 else 6, int(a[5]) if len(a) > 5 else 300)
