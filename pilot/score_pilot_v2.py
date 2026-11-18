"""Score pilot_v2_results.jsonl against the referee. Usage: python score_pilot_v2.py CASES_V2_JSONL DRIVES_JSON RESULTS_JSONL OUT_CSV"""
import sys, os, json, re; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'referee'))
import pandas as pd
from referee import Referee
import baselines as B, score as S

def hm(x):
    try: h, m = str(x).strip().split(':')[:2]; return int(h) * 60 + int(m[:2])
    except Exception: return None
def num(x):
    try: return float(str(x).replace('$', '').replace('%', '').strip()) if x not in (None, '', 'null') else None
    except Exception: return None

def form_to_settings(f, c, R):
    """The model's form -> goal, deadline, budget and wishes in the referee's terms."""
    goal = str(f.get('goal', '')).lower().strip(); goal = goal if goal in ('fastest', 'cheapest') else 'fastest'
    w = []
    if num(f.get('max_wait_minutes')) is not None: w.append(dict(type='max_wait', value=num(f['max_wait_minutes'])))
    if f.get('avoid_network'):
        nets = {R.ch.loc[x, 'network'] for x in c['candidates'] if isinstance(R.ch.loc[x, 'network'], str)}
        hit = [n for n in nets if str(f['avoid_network']).lower().replace(' network', '') in n.lower()]
        w.append(dict(type='avoid_network', value=hit[0] if hit else str(f['avoid_network'])))
    if num(f.get('min_arrival_percent')) is not None: w.append(dict(type='min_arrival', value=num(f['min_arrival_percent']) / 100))
    if f.get('parked_at') and hm(f['parked_at']) is not None: w.append(dict(type='parked_at', value=hm(f['parked_at'])))
    if f.get('free_only') is True: w.append(dict(type='free_only'))
    if f.get('stop_city'):
        cities = {R.ch.loc[x, 'city'] for x in c['candidates']}
        hit = [x for x in cities if str(f['stop_city']).lower().strip() == str(x).lower()]
        w.append(dict(type='stop_city', value=hit[0] if hit else str(f['stop_city'])))
    if f.get('no_fast') is True: w.append(dict(type='no_fast'))
    return goal, hm(f.get('deadline')) if f.get('deadline') else None, num(f.get('budget')), w

def same_wishes(a, b):
    k = lambda ws: sorted((x['type'], round(x['value'], 2) if isinstance(x.get('value'), float) else x.get('value')) for x in ws)
    return k(a) == k(b)

def grade_answer(r, c, drives, R):
    """One stored model answer -> one graded row (the decision it leads to, checked by the referee)."""
    inv = {v: k for k, v in c['letters'].items()}; extra = {}
    if r['role'].startswith('R3'):
        f = r['form']
        if f.get('ok'):
            goal, dl, bu, w = form_to_settings(f, c, R)
            dec = B.planner(dict(c, goal=goal, deadline_min=dl, budget=bu), drives, R, wishes=w)
            extra = dict(read_goal_ok=goal == c['goal'], read_deadline_ok=dl == c.get('deadline_min'),
                         read_budget_ok=(bu is None and c.get('budget') is None) or (bu is not None and c.get('budget') is not None and abs(bu - c['budget']) < 0.01),
                         read_wishes_ok=same_wishes(w, c['wishes']))
            extra['read_all_ok'] = all(extra.values())
        else:
            dec = dict(charge=False, charger=None, target=None, gives_up=None); extra = dict(read_all_ok=False)
        parsed = bool(f.get('ok'))
    else:
        d = r['decision']; parsed = d['ok']
        dec = dict(charge=d['charge'], charger=inv.get(d['charger']) if d['charge'] else None, target=d['target'], gives_up=d['gives_up'])
        if d['charge'] and dec['charger'] is None: dec['charger'] = 'not in list'
    g = S.grade_v2(c, dec, R, drives)
    g.update(model=r['model'], role=r['role'], facts=r['facts'], wording=r['wording'], variant=r['variant'], parsed=parsed,
             profile=r.get('profile', 'laptop'), threads=r.get('threads'), wall_s=r['wall_s'], retried=bool(r.get('problems')),
             memory_gb=r.get('memory_gb'), write_tok_s=r.get('write_tok_s'), read_tok_s=r.get('read_tok_s'),
             pred_letter=c['letters'].get(dec['charger']) if dec['charge'] else None, pred_target=dec.get('target'), **extra)
    return g

def main(cases_path, drives_path, res_path, out):
    cases = {json.loads(l)['id']: json.loads(l) for l in open(cases_path)}; drives = json.load(open(drives_path))
    R = Referee.__new__(Referee); R.ch = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'referee', 'chargers.csv')).set_index('id')
    rows = [grade_answer(json.loads(l), cases[json.loads(l)['id']], drives, R) for l in open(res_path)]
    d = pd.DataFrame(rows).drop_duplicates(['model', 'role', 'facts', 'wording', 'variant', 'profile', 'id'], keep='last'); d.to_csv(out, index=False)
    summ = []
    for key, g in d.groupby(['model', 'role', 'facts', 'wording', 'profile']):
        s = S.summary_v2(g.to_dict('records'), ' / '.join(map(str, key)))
        s.update(model=key[0], role=key[1], facts=key[2], wording=key[3], profile=key[4], threads=g.threads.dropna().max() if g.threads.notna().any() else None,
                 wall_s_p95=g.wall_s.quantile(0.95), retried=g.retried.mean(),
                 memory_gb_max=pd.to_numeric(g.memory_gb, errors='coerce').max(), write_tok_s_median=pd.to_numeric(g.write_tok_s, errors='coerce').median(),
                 read_tok_s_median=pd.to_numeric(g.read_tok_s, errors='coerce').median())
        s.update(parsed=g.parsed.mean(), wall_s_median=g.wall_s.median(), pass_held_out=g[g.held_out].valid.mean(), pass_seen=g[~g.held_out].valid.mean(),
                 pass_conflict=g[g.conflict].valid.mean())
        if 'read_all_ok' in g: s['read_all_ok'] = g.read_all_ok.mean()
        summ.append(s)
    sm = pd.DataFrame(summ); sm.to_csv(out.replace('.csv', '_summary.csv'), index=False)
    pd.set_option('display.width', 250); print(sm.round(3).to_string(index=False))
if __name__ == '__main__':
    main(*sys.argv[1:5])
