"""Generate, label and filter charging situations on the real Michigan network.
Usage: python gen_cases.py NET SPLIT N_RAW SEED OUT_DIR      (SPLIT = test (Ann Arbor starts) or train (Detroit starts))"""
import sys, os, json, time; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from scipy.spatial import cKDTree
import config as C
from referee import Referee

AREAS = {'test': (-84.20, -83.55), 'train': (-83.30, -82.90)}   # longitude band of the start point
def main(net_path, split, n_raw, seed, out_dir, id_start=0):
    rng = np.random.default_rng(seed); os.makedirs(out_dir, exist_ok=True)
    R = Referee(net_path); net = R.net
    edges = [e for e in R.router.edges if e.getLength() > 50 and e.getSpeed() < 25]
    lon = np.array([net.convertXY2LonLat(*e.getShape()[0])[0] for e in edges])
    lo, hi = AREAS[split]; starts = [e for e, x in zip(edges, lon) if lo <= x <= hi]
    ch = R.ch.copy(); cxy = np.array([net.convertLonLat2XY(a, b) for a, b in zip(ch.lon, ch.lat)])
    compat = np.array([not R.usable(c) for c in ch.index])
    cases = []
    while len(cases) < n_raw:
        o = starts[rng.integers(len(starts))].getID(); d = edges[rng.integers(len(edges))].getID()
        if o == d: continue
        F = R.router.tree_from(o); p = R.router.path_from(o, F, d)
        if not p: continue
        km = sum(net.getEdge(e).getLength() for e in p) / 1000
        if not 30 <= km <= 110: continue
        pts = np.array([pt for e in p for pt in net.getEdge(e).getShape()])
        dist, _ = cKDTree(pts).query(cxy)
        near = ch.assign(d=dist, ok=compat)[dist < 3000]
        good_dc = near[near.ok & (near.level == 'DC')].sort_values('d')
        good_l2 = near[near.ok & (near.level == 'L2')].sort_values('d')
        bad = near[~near.ok].sort_values('d')
        distractor = bool(rng.random() < 0.5) and len(bad) > 0
        k_dc = min(len(good_dc), int(rng.integers(1, 4))); k_l2 = min(len(good_l2), int(rng.integers(2, 5)))
        pick_dc = list(good_dc.index[rng.permutation(len(good_dc))[:k_dc]]) if k_dc else []
        pick_l2 = list(good_l2.index[rng.permutation(len(good_l2))[:k_l2]]) if k_l2 else []
        pick_bad = [bad.index[0]] if distractor else []          # the closest charger that can't be used: a tempting trap
        cand = pick_dc + pick_l2 + pick_bad
        if len(pick_dc) + len(pick_l2) < 2: continue
        cand = [cand[i] for i in rng.permutation(len(cand))]
        cases.append(dict(id=f'{split}{id_start + len(cases):04d}', split=split, origin_edge=o, dest_edge=d, route_km=round(km, 1),
                          depart_min=int(rng.choice(np.arange(7 * 60, 19 * 60, 15))), soc0=round(float(rng.uniform(0.08, 0.45)), 2),
                          temp_c=int(rng.integers(-15, 33)), goal=str(rng.choice(['fastest', 'cheapest'])),
                          n_rules=int(rng.choice([0, 1, 2])), distractor=distractor, candidates=cand))
    print(len(cases), 'raw cases; driving legs in SUMO...', flush=True); t = time.time()
    legs = [l for c in cases for l in R.legs_for(c)]
    drives = R.drive(legs); print(len(drives), 'legs driven in', round(time.time() - t), 's', flush=True)
    kept = []
    for c in cases:
        free = R.decide(dict(c, deadline_min=None, budget=None), drives)
        if not free['solvable']: continue
        ops = free['options']; v = ops[ops.valid]
        # set the driver's extra rules so that they actually matter where possible
        c['deadline_min'] = None; c['budget'] = None
        if c['n_rules'] >= 1:
            if c['goal'] == 'cheapest' or c['n_rules'] == 2:
                fast, cheap = v.arrive_min.min(), v.sort_values(['cost', 'arrive_min']).iloc[0].arrive_min
                dl = (fast + cheap) / 2 if cheap - fast > 10 else fast + 20
                c['deadline_min'] = int(np.ceil(dl / 5) * 5)
            if c['goal'] == 'fastest' or c['n_rules'] == 2:
                cheap, fastc = v.cost.min(), v.sort_values(['arrive_min', 'cost']).iloc[0].cost
                b = (cheap + fastc) / 2 if fastc - cheap > 1 else cheap + 2
                c['budget'] = float(np.ceil(b * 2) / 2)
        res = R.decide(c, drives)
        if not res['solvable']: continue
        b, s = res['best'], res['second']
        key = 'arrive_min' if c['goal'] == 'fastest' else 'cost'
        gap = None if s is None else float(s[key] - b[key])
        c.update(robust=bool(res['robust']), must_charge=bool(b['charge']), best_charger=b['charger'], best_target=b['target'],
                 best_arrive_min=float(b['arrive_min']), best_cost=round(float(b['cost']), 2), best_soc_end=round(float(b['soc_end']), 3),
                 second_charger=None if s is None else s['charger'], gap=gap,
                 close=bool(gap is not None and gap < (C.CLOSE_MIN if key == 'arrive_min' else C.CLOSE_USD)), n_valid=int(res['n_valid']))
        c['options'] = res['options'].round(4).to_dict('records')
        kept.append(c)
    json.dump(kept, open(os.path.join(out_dir, f'{split}_labelled.json'), 'w'), default=str)
    json.dump(drives, open(os.path.join(out_dir, f'{split}_drives.json'), 'w'))
    df = pd.DataFrame([{k: v for k, v in c.items() if k != 'options'} for c in kept])
    print(len(df), 'solvable;', int(df.robust.sum()), 'robust;', 'must charge', int(df.must_charge.sum()))
if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5], int(sys.argv[6]) if len(sys.argv) > 6 else 0)
