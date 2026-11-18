"""Recompute runner-up, gap and close from the stored option tables (no SUMO needed).
Used once on 2026-11-16 after fixing a bug where the runner-up of a no-charge best answer was the best answer itself.
Usage: python relabel_close.py CASE_DIR SPLIT"""
import sys, os, json; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import config as C
def main(d, split):
    p = os.path.join(d, f'{split}_labelled.json'); cs = json.load(open(p)); n = 0
    for c in cs:
        o = pd.DataFrame(c['options']); v = o[o.valid]
        if not len(v): continue
        b = v.iloc[0]; bch = '' if pd.isna(b.charger) else b.charger
        oth = v[(v.charge != b.charge) | (v.charger.fillna('') != bch)]
        key = 'arrive_min' if c['goal'] == 'fastest' else 'cost'
        s = oth.iloc[0] if len(oth) else None
        c['second_charger'] = None if s is None or pd.isna(s.charger) else s.charger
        c['gap'] = None if s is None else float(s[key] - b[key])
        c['close'] = bool(c['gap'] is not None and c['gap'] < (C.CLOSE_MIN if key == 'arrive_min' else C.CLOSE_USD)); n += c['close']
    json.dump(cs, open(p, 'w'), default=str)
    print(split, len(cs), 'close:', n)
if __name__ == '__main__':
    main(*sys.argv[1:3])
