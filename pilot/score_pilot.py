"""Score pilot_results.jsonl against the referee. Runs on our side (needs the referee package).
Usage: python score_pilot.py pilot_results.jsonl"""
import sys, os, json; sys.path.insert(0, '/mnt/project-files/referee')
import pandas as pd
from referee import Referee
import score as S, baselines as B
CD = '/mnt/project-files/referee/cases'
cases = {json.loads(l)['id']: json.loads(l) for l in open(f'{CD}/test_cases.jsonl')}
drives = json.load(open(f'{CD}/test_drives.json'))
R = Referee.__new__(Referee); R.ch = pd.read_csv('/mnt/project-files/referee/chargers.csv').set_index('id')
res = list({(r['model'], r.get('role', 'R1'), r['facts'], r['wording'], r['id']): r for r in map(json.loads, open(sys.argv[1]))}.values())  # last answer wins on reruns
groups, rows = {}, []
for r in res:
    c = cases[r['id']]; role = r.get('role', 'R1'); extra = {}
    if role == 'R1':
        inv = {v: k for k, v in c['letters'].items()}
        dec = dict(charge=r['charge'], charger=inv.get(r['charger']) if r['charge'] else None, target=r['target'])
        if r['charge'] and dec['charger'] is None: dec['charger'] = '__unknown_letter__'
    else:   # R3: the model's reading of the request feeds the goal-aware planner
        goal = r['goal'] if r['goal'] in ('fastest', 'cheapest') else 'fastest'
        dec = B.goal_rule(dict(c, goal=goal, deadline_min=r['deadline_min'], budget=r['budget']), drives, R)
        extra = dict(read_goal_ok=r['goal'] == c['goal'], read_deadline_ok=r['deadline_min'] == c.get('deadline_min'),
                     read_budget_ok=(r['budget'] is None and c.get('budget') is None) or (r['budget'] is not None and c.get('budget') is not None and abs(r['budget'] - c['budget']) < 0.01))
    g = S.grade(c, dec, R, drives); g.update(model=r['model'], role=role, facts=r['facts'], wording=r['wording'], parsed=r['ok'], wall_s=r['wall_s'], **extra)
    rows.append(g); groups.setdefault((r['model'], role, r['facts'] if role == 'R1' else '-', r['wording']), []).append(g)
out = []
for k, v in groups.items():
    s = S.summary(v, ' / '.join(map(str, k))); d = pd.DataFrame(v)
    s.update(parsed=float(d.parsed.mean()), median_s=float(d.wall_s.median()))
    if 'read_goal_ok' in d: s.update(read_all_ok=float((d.read_goal_ok & d.read_deadline_ok & d.read_budget_ok).mean()))
    out.append(s)
pd.set_option('display.width', 250)
print(pd.DataFrame(out).round(3).to_string(index=False))
pd.DataFrame(rows).to_csv(os.path.splitext(sys.argv[1])[0] + '_scored.csv', index=False)
