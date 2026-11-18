"""Our side only: package the pilot situations with everything the offline demo needs (no SUMO, no pandas on the laptop)."""
import sys, json, math; sys.path.insert(0, '/mnt/project-files/referee')
import pandas as pd
import config as C
from referee import Referee
CD = '/mnt/project-files/referee/cases'
R = Referee.__new__(Referee); R.ch = pd.read_csv('/mnt/project-files/referee/chargers.csv').set_index('id')
lab = {c['id']: c for c in json.load(open(f'{CD}/test_labelled.json'))}
sel = {json.loads(l)['id']: json.loads(l) for l in open(f'{CD}/test_cases.jsonl')}
drives = json.load(open(f'{CD}/test_drives.json'))
ids = [json.loads(l)['id'] for l in open('/mnt/project-files/pilot/pilot_cases.jsonl')]
def clean(v): return None if isinstance(v, float) and math.isnan(v) else v
out = []
for i in ids:
    c, s = lab[i], sel[i]; T = c['temp_c']
    def kwh(lid): d = drives[lid]; return round((d['wh'] + R.climate_wh(T, d['minutes'])) / 1000, 2)
    chargers = {}
    for cid, L in s['letters'].items():
        ch = R.ch.loc[cid]
        chargers[L] = dict(id=cid, name=ch['name'], level=ch.level, plugs=ch.plugs, working=bool(ch.working), public=bool(ch.public),
                           kwh_to=kwh(f'{i}__to__{cid}'), kwh_from=kwh(f'{i}__from__{cid}'))
    opts = [{k: clean(v) for k, v in o.items() if k in ('charge', 'charger', 'target', 'arrive_min', 'cost', 'soc_end', 'broken', 'valid')} for o in c['options']]
    out.append(dict(id=i, goal=c['goal'], deadline_min=clean(c.get('deadline_min')), budget=clean(c.get('budget')), soc0=c['soc0'], temp_c=T,
                    depart_min=c['depart_min'], direct_kwh=kwh(f'{i}__direct'), facts=s['facts'], requests=s['requests'], chargers=chargers,
                    must_charge=c['must_charge'], best_letter=s['best_letter'], best_target=clean(c['best_target']),
                    best_arrive_min=c['best_arrive_min'], best_cost=c['best_cost'], options=opts))
json.dump(dict(car=dict(C.CAR, plugs_ac=sorted(C.CAR['plugs_ac']), plugs_dc=sorted(C.CAR['plugs_dc'])), reserve=C.RESERVE, situations=out),
          open('demo_situations.json', 'w'))
print(len(out), sum(len(o['options']) for o in out))
