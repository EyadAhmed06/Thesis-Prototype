"""Score the simple baselines (and the referee's own answer, as a sanity check) on a case set.
Usage: python run_baselines.py CASE_DIR SPLIT OUT_DIR"""
import sys, os, json; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from referee import Referee
import baselines as B, score as S

def main(case_dir, split, out_dir):
    cases = [json.loads(l) for l in open(os.path.join(case_dir, f'{split}_cases.jsonl'))]
    drives = json.load(open(os.path.join(case_dir, f'{split}_drives.json')))
    R = Referee.__new__(Referee); R.ch = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chargers.csv')).set_index('id')
    rng = np.random.default_rng(0)
    methods = {'referee answer (sanity check)': lambda c: dict(charge=c['must_charge'], charger=c['best_charger'], target=c['best_target']),
               'nearest compatible, to 80%': lambda c: B.nearest(c, drives, R),
               'random safe option': lambda c: B.random_safe(c, drives, R, rng),
               'goal-aware rule': lambda c: B.goal_rule(c, drives, R),
               'nearest, km only': lambda c: B.nearest(c, drives, R, est=True),
               'goal-aware rule, km only': lambda c: B.goal_rule(c, drives, R, est=True)}
    rows, summ = {}, []
    for name, f in methods.items():
        rows[name] = [S.grade(c, f(c), R, drives) for c in cases]
        summ.append(S.summary(rows[name], name))
    os.makedirs(out_dir, exist_ok=True)
    sm = pd.DataFrame(summ); sm.to_csv(os.path.join(out_dir, f'{split}_baselines_summary.csv'), index=False)
    allrows = pd.concat([pd.DataFrame(r).assign(method=n) for n, r in rows.items()])
    allrows.to_csv(os.path.join(out_dir, f'{split}_baselines_rows.csv'), index=False)
    # where the best simple method breaks: pass rate and top-1 by difficulty factor
    g = allrows[allrows.method == 'goal-aware rule']
    by = {f: g.groupby(f)[['valid', 'top1']].mean().round(3).to_dict() for f in ['n_rules', 'close', 'distractor', 'goal', 'truth_charge']}
    json.dump(by, open(os.path.join(out_dir, f'{split}_goal_rule_by_factor.json'), 'w'), indent=1, default=str)
    pd.set_option('display.width', 250); print(sm.round(3).to_string(index=False)); print(json.dumps(by, default=str))
    print(g[~g.valid].broken.value_counts().head(8).to_string())
if __name__ == '__main__':
    main(*sys.argv[1:4])
