"""Score decisions against the referee: the metrics and statistics of the study."""
import math, numpy as np, pandas as pd
from scipy.stats import binomtest, chi2

def wilson(k, n, z=1.96):
    if n == 0: return (float('nan'),) * 3
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)

def grade(c, dec, R, drives):
    """One decision -> one row of scores."""
    j = R.judge(c, drives, dec['charge'], dec.get('charger'), dec.get('target'))
    best = dict(charge=c['must_charge'], charger=c['best_charger'], target=c['best_target'])
    row = dict(id=c['id'], n_rules=c['n_rules'], close=c['close'], distractor=c['distractor'], goal=c['goal'],
               truth_charge=best['charge'], pred_charge=bool(dec['charge']),
               top1=(not dec['charge'] and not best['charge']) or (bool(dec['charge']) and best['charge'] and dec.get('charger') == best['charger']),
               target_err=(abs(100 * (dec['target'] - best['target'])) if dec['charge'] and best['charge'] and dec.get('target') is not None else np.nan),
               valid=bool(j.get('valid', False)), broken=j.get('broken', ''))
    if row['valid']:
        if c['goal'] == 'fastest': row['gap'] = j['arrive_min'] - c['best_arrive_min']; row['gap_unit'] = 'min'
        else: row['gap'] = j['cost'] - c['best_cost']; row['gap_unit'] = '$'
    return row

def summary(rows, name):
    d = pd.DataFrame(rows); n = len(d)
    tp = int((d.pred_charge & d.truth_charge).sum()); fp = int((d.pred_charge & ~d.truth_charge).sum()); fn = int((~d.pred_charge & d.truth_charge).sum())
    prec = tp / (tp + fp) if tp + fp else float('nan'); rec = tp / (tp + fn) if tp + fn else float('nan')
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else float('nan')
    pr, plo, phi = wilson(int(d.valid.sum()), n); t1, tlo, thi = wilson(int(d.top1.sum()), n)
    g = d[d.valid]
    return dict(method=name, n=n, recall=rec, precision=prec, f1=f1, top1=t1, top1_lo=tlo, top1_hi=thi,
                target_mae=float(d.target_err.mean()), pass_rate=pr, pass_lo=plo, pass_hi=phi,
                gap_min_fastest=float(g[g.goal == 'fastest'].gap.mean()) if len(g[g.goal == 'fastest']) else float('nan'),
                gap_usd_cheapest=float(g[g.goal == 'cheapest'].gap.mean()) if len(g[g.goal == 'cheapest']) else float('nan'))

def mcnemar(a, b):
    """a, b: boolean arrays of success on the same cases. Exact test when discordant pairs are few."""
    a, b = np.asarray(a, bool), np.asarray(b, bool); n01 = int((a & ~b).sum()); n10 = int((~a & b).sum())
    if n01 + n10 == 0: return dict(b=n01, c=n10, p=1.0)
    if n01 + n10 < 25: p = binomtest(n01, n01 + n10, 0.5).pvalue
    else: p = float(chi2.sf((abs(n01 - n10) - 1) ** 2 / (n01 + n10), 1))
    return dict(b=n01, c=n10, p=p)

def holm(ps, alpha=0.05):
    order = np.argsort(ps); m = len(ps); rej = [False] * m
    for k, i in enumerate(order):
        if ps[i] <= alpha / (m - k): rej[i] = True
        else: break
    return rej

# ---------- version 2 (wishes + priority order, see redesign/SPEC.md) ----------
GIVE_UP = ('arrival time', 'budget', 'wishes')
def broken_categories(j):
    return sorted((['arrival time'] if j.get('deadline_broken') else []) + (['budget'] if j.get('budget_broken') else [])
                  + (['wishes'] if j.get('wishes_broken') else []))

def grade_v2(c, dec, R, drives):
    """One decision -> one row. pass = safe and keeps everything the best option keeps (same rule level).
    honest = the decision's own list of what it gives up matches what it actually breaks."""
    j = R.judge(c, drives, dec['charge'], dec.get('charger'), dec.get('target'))
    safe = bool(j.get('safe', False))
    lvl = (bool(j.get('deadline_broken')), bool(j.get('budget_broken')), int(j.get('wishes_broken') or 0)) if safe else None
    best_lvl = tuple(c['best_level']); best_lvl = (bool(best_lvl[0]), bool(best_lvl[1]), int(best_lvl[2]))
    said = dec.get('gives_up')
    row = dict(id=c['id'], n_rules=c['n_rules'], n_wishes=c['n_wishes'], held_out=c['held_out'], conflict=c['conflict'],
               wish_types=','.join(c['wish_types']), close=c['close'], distractor=c['distractor'], goal=c['goal'],
               truth_charge=c['must_charge'], pred_charge=bool(dec['charge']),
               top1=(not dec['charge'] and not c['must_charge']) or (bool(dec['charge']) and c['must_charge'] and dec.get('charger') == c['best_charger']),
               target_err=(abs(100 * (dec['target'] - c['best_target'])) if dec['charge'] and c['must_charge'] and dec.get('target') is not None else np.nan),
               safe=safe, valid=bool(safe and lvl == best_lvl), level=str(lvl), broken=j.get('broken', ''),
               honest=(None if said is None else bool(safe and sorted(set(said)) == broken_categories(j))))
    if row['valid']:
        if c['goal'] == 'fastest': row['gap'] = j['arrive_min'] - c['best_arrive_min']; row['gap_unit'] = 'min'
        else: row['gap'] = j['cost'] - c['best_cost']; row['gap_unit'] = '$'
    return row

def summary_v2(rows, name):
    s = summary(rows, name); d = pd.DataFrame(rows)
    sf, slo, shi = wilson(int(d.safe.sum()), len(d)); s.update(safe_rate=sf, safe_lo=slo, safe_hi=shi)
    h = d.honest.dropna()
    if len(h): s['honest_rate'] = float(h.astype(bool).mean())
    return s
