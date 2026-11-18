"""Score the simple methods on the version-2 test (wishes + priority order).
Usage: python run_baselines_v2.py CASE_DIR SPLIT OUT_DIR"""
import sys, os, json; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from referee import Referee
import baselines as B, score as S
from make_v2 import SEEN

def main(case_dir, split, out_dir, drives_path):
    cases = [json.loads(l) for l in open(os.path.join(case_dir, f'{split}_cases.jsonl'))]
    drives = json.load(open(drives_path))
    R = Referee.__new__(Referee); R.ch = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chargers.csv')).set_index('id')
    rng = np.random.default_rng(0)
    methods = {'referee answer (sanity check)': lambda c: dict(charge=c['must_charge'], charger=c['best_charger'], target=c['best_target'], gives_up=c['gives_up']),
               'random safe option': lambda c: B.random_safe(c, drives, R, rng),
               'nearest compatible, to 80%': lambda c: B.nearest(c, drives, R),
               'goal-aware rule (no wishes)': lambda c: B.goal_rule(c, drives, R),
               'exact planner, ignores wishes': lambda c: B.planner(c, drives, R, wishes=[]),
               'exact planner, reads only training wish types': lambda c: B.planner(c, drives, R, wishes=[w for w in c['wishes'] if w['type'] in SEEN])}
    rows, summ = {}, []
    for name, f in methods.items():
        rows[name] = [S.grade_v2(c, f(c), R, drives) for c in cases]
        summ.append(S.summary_v2(rows[name], name))
    os.makedirs(out_dir, exist_ok=True)
    sm = pd.DataFrame(summ); sm.to_csv(os.path.join(out_dir, f'{split}_v2_baselines_summary.csv'), index=False)
    allrows = pd.concat([pd.DataFrame(r).assign(method=n) for n, r in rows.items()]); allrows.to_csv(os.path.join(out_dir, f'{split}_v2_baselines_rows.csv'), index=False)
    by = {m: {f: allrows[allrows.method == m].groupby(f).valid.mean().round(3).to_dict() for f in ['conflict', 'held_out', 'n_wishes', 'n_rules']}
          for m in ['goal-aware rule (no wishes)', 'exact planner, reads only training wish types']}
    json.dump(by, open(os.path.join(out_dir, f'{split}_v2_by_factor.json'), 'w'), indent=1, default=str)
    pd.set_option('display.width', 250)
    print(sm[['method', 'top1', 'pass_rate', 'pass_lo', 'pass_hi', 'safe_rate', 'target_mae', 'honest_rate']].round(3).to_string(index=False)); print(json.dumps(by, indent=1, default=str))
if __name__ == '__main__':
    main(*sys.argv[1:5])
