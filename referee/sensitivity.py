"""Sensitivity of the answer key to the two assumptions the robustness check does not vary: charging power and the
prices of chargers that list none (plus the fixed stop overhead). For each variant, the referee recomputes every option of
every test situation from the stored SUMO drives (no new simulation) and we count how often the best answer stays the
same: same charge/no-charge choice, same charger, and same set of things given up. The target percentage is reported
separately, since it moves with any change in charging speed.
Usage: python sensitivity.py [OUT.csv]"""
import os, sys, json, importlib
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import config as C
from referee import Referee

VARIANTS = [   # (name, what changes)
    ('DC fast power 25 kW (half)', dict(max_dc_kw=25.0)),
    ('DC fast power 75 kW (1.5x)', dict(max_dc_kw=75.0)),
    ('Level 2 power 3.3 kW (half)', dict(onboard_ac_kw=3.3)),
    ('unlisted prices x0.5', dict(price=0.5)),
    ('unlisted prices x1.5', dict(price=1.5)),
    ('stop overhead 10 min (double)', dict(overhead=10.0)),
]

def best(R, c, drives):
    o = R.options(c, drives)
    if not len(o) or not o.iloc[0].safe: return None
    b = o.iloc[0]
    return (bool(b.charge), b.charger if b.charge else None, R.level(b)), (b.target if b.charge else None)

def main(out=None):
    v2 = os.path.join(HERE, 'cases_v2')
    cases = [json.loads(l) for l in open(os.path.join(v2, 'test_cases.jsonl'))]
    drives = json.load(open(os.path.join(v2, 'base', 'test_drives.json')))
    R = Referee.__new__(Referee); R.ch = pd.read_csv(os.path.join(HERE, 'chargers.csv')).set_index('id')
    base = {c['id']: best(R, c, drives) for c in cases}
    keep = dict(car=dict(C.CAR), price=dict(C.UNKNOWN_PRICE), overhead=C.STOP_OVERHEAD_MIN)
    rows = []; stable = {c['id'] for c in cases}
    for name, ch in VARIANTS:
        C.CAR.update({k: v for k, v in ch.items() if k in C.CAR})
        if 'price' in ch: C.UNKNOWN_PRICE.update({k: v * ch['price'] for k, v in keep['price'].items()})
        if 'overhead' in ch: C.STOP_OVERHEAD_MIN = ch['overhead']
        same = same_t = n = conflict_same = conflict_n = 0
        for c in cases:
            a, b = base[c['id']], best(R, c, drives); n += 1
            ok = b is not None and a[0] == b[0]; same += ok; same_t += ok and a[1] == b[1]
            if not ok: stable.discard(c['id'])
            if c['conflict']: conflict_n += 1; conflict_same += ok
        rows.append(dict(variant=name, situations=n, same_answer=same, same_answer_share=same / n, same_including_target=same_t,
                         conflicts=conflict_n, conflicts_same=conflict_same))
        C.CAR.clear(); C.CAR.update(keep['car']); C.UNKNOWN_PRICE.update(keep['price']); C.STOP_OVERHEAD_MIN = keep['overhead']
        print(f'{name}: answer unchanged in {same}/{n} ({100 * same / n:.1f}%), including the target in {same_t}', flush=True)
    print(f'answer unchanged under every variant: {len(stable)}/{len(cases)}')
    rows.append(dict(variant='all variants at once (each one separately)', situations=len(cases), same_answer=len(stable), same_answer_share=len(stable) / len(cases)))
    json.dump(sorted(stable), open(os.path.join(os.path.dirname(os.path.abspath(out)) if out else os.path.join(HERE, 'results'), 'test_v2_stable_ids.json'), 'w'))
    d = pd.DataFrame(rows)
    d.to_csv(out or os.path.join(HERE, 'results', 'test_v2_sensitivity.csv'), index=False)
    return d

if __name__ == '__main__':
    main(*sys.argv[1:2])
