"""Paired statistics for the model results (Section "Metrics and Statistics" of the Design chapter).

Every comparison is made on the same situations: McNemar's test on the pass/fail pairs (exact binomial version when
there are fewer than 25 discordant pairs), the paired difference in pass rate with a 95% Wald interval, and Holm's
correction within each family. The families follow the proposal in the thesis (one per research question):
  RQ1  each model in each role  vs  the exact planner that ignores wishes (strongest baseline without wishes)
  RQ2  each pair of roles, within each model
  RQ3  each adaptation  vs  no adaptation, within each model and role
All three use the main profile and template wording, so that only one thing differs in each comparison.
To change a family, edit families() below; nothing else depends on it.

Usage: python stats_v2.py MODEL_SCORES.csv BASELINE_ROWS.csv OUT.csv"""
import sys, itertools, math
import numpy as np, pandas as pd
from score import mcnemar, holm

BASELINE_RQ1 = 'exact planner, ignores wishes'

def paired(a, b):
    """a, b: pass/fail of two methods on the same situations, aligned. Returns counts, difference and test."""
    a, b = np.asarray(a, bool), np.asarray(b, bool); n = len(a); t = mcnemar(a, b)
    d = (t['b'] - t['c']) / n
    se = math.sqrt(max(t['b'] + t['c'] - (t['b'] - t['c']) ** 2 / n, 0.0)) / n
    return dict(n=n, pass_a=a.mean(), pass_b=b.mean(), only_a=t['b'], only_b=t['c'], diff=d, diff_lo=d - 1.96 * se, diff_hi=d + 1.96 * se, p=t['p'])

def _align(x, y):
    m = x.merge(y, on='id', suffixes=('_a', '_b'))
    return m.valid_a.astype(bool).values, m.valid_b.astype(bool).values

def families(d, base):
    """Yields (family, label_a, label_b, rows_a, rows_b); rows are DataFrames with columns id, valid."""
    main = d[(d.wording == 'template') & (d.adapt == 'none') & (d.profile == d.profile_main)]
    for (m, r), g in main.groupby(['model', 'role']):
        yield 'RQ1', f'{m} {r}', BASELINE_RQ1, g[['id', 'valid']], base
    for m, g in main.groupby('model'):
        for r1, r2 in itertools.combinations(sorted(g.role.unique()), 2):
            yield 'RQ2', f'{m} {r1}', f'{m} {r2}', g[g.role == r1][['id', 'valid']], g[g.role == r2][['id', 'valid']]
    ad = d[(d.wording == 'template') & (d.profile == d.profile_main)]
    for (m, r), g in ad.groupby(['model', 'role']):
        none = g[g.adapt == 'none']
        if none.empty: continue
        for a in sorted(set(g.adapt) - {'none'}):
            yield 'RQ3', f'{m} {r} {a}', f'{m} {r} none', g[g.adapt == a][['id', 'valid']], none[['id', 'valid']]

def main(scores_path, base_path, out):
    d = pd.read_csv(scores_path)
    for col, default in (('adapt', 'none'), ('profile', 'laptop')):
        if col not in d: d[col] = default
    d['profile_main'] = 'laptop' if 'laptop' in set(d.profile) else d.profile.iloc[0]
    b = pd.read_csv(base_path); base = b[b.method == BASELINE_RQ1][['id', 'valid']]
    rows = []
    for fam, la, lb, xa, xb in families(d, base):
        a, bb = _align(xa, xb)
        if len(a): rows.append(dict(family=fam, a=la, b=lb, **paired(a, bb)))
    s = pd.DataFrame(rows, columns=['family', 'a', 'b', 'n', 'pass_a', 'pass_b', 'only_a', 'only_b', 'diff', 'diff_lo', 'diff_hi', 'p'])
    s['holm_significant'] = False
    for fam, g in s.groupby('family'):
        s.loc[g.index, 'holm_significant'] = holm(list(g.p))
        s.loc[g.index, 'family_size'] = len(g)
    s.to_csv(out, index=False)
    print(f'{len(s)} paired comparisons written to {out}')
    return s

if __name__ == '__main__':
    main(*sys.argv[1:4])
