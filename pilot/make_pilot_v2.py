"""Pick pilot situations from the version-2 test set and add what the on-device check (R2) may know: only numbers that
are printed in the fact sheet. Also writes the sheet for human-written requests.
Usage: python make_pilot_v2.py ../referee/cases_v2/test_cases.jsonl ../referee/cases_v2/base/test_drives.json N_PILOT N_HUMAN"""
import sys, os, json, csv; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'referee'))
import numpy as np, pandas as pd
import config as C
from referee import Referee
from select_cases import hhmm

def main(cases_path, drives_path, n_pilot, n_human):
    here = os.path.dirname(os.path.abspath(__file__))
    R = Referee.__new__(Referee); R.ch = pd.read_csv(os.path.join(here, '..', 'referee', 'chargers.csv')).set_index('id')
    D = json.load(open(drives_path)); cases = [json.loads(l) for l in open(cases_path)]
    rng = np.random.default_rng(5)
    def device(c):
        T = c['temp_c']; kwh = lambda lid: (D[lid]['wh'] + R.climate_wh(T, D[lid]['minutes'])) / 1000
        ch = {}
        for cid, L in c['letters'].items():
            x = R.ch.loc[cid]; need = C.CAR['plugs_dc'] if x.level == 'DC' else C.CAR['plugs_ac']
            ch[L] = dict(plug_fits=bool(set(str(x.plugs).split()) & need), working=bool(x.working), public=bool(x.public),
                         kwh_to=round(kwh(f"{c['id']}__to__{cid}"), 2), kwh_from=round(kwh(f"{c['id']}__from__{cid}"), 2))
        return dict(usable_kwh=C.CAR['usable_kwh'], reserve=C.RESERVE, direct_kwh=round(kwh(f"{c['id']}__direct"), 2), chargers=ch)
    # pilot: spread over conflict x held-out x number of wishes
    df = pd.DataFrame(cases); df['cell'] = list(zip(df.conflict, df.held_out, df.n_wishes))
    groups = [list(rng.permutation(v)) for _, v in sorted(df.groupby('cell').groups.items(), key=lambda kv: str(kv[0]))]
    order = [i for row in __import__('itertools').zip_longest(*groups) for i in row if i is not None]
    pilot = [dict(cases[i], device=device(cases[i])) for i in order[:n_pilot]]
    with open(os.path.join(here, 'pilot_v2_cases.jsonl'), 'w') as f:
        for c in pilot: f.write(json.dumps(c, default=str) + '\n')
    # human sheet: the next situations in the same spread, with the meaning in plain fields and an empty column to write in
    human = [cases[i] for i in order[n_pilot:n_pilot + n_human]]
    with open(os.path.join(here, 'human_requests_sheet.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['id', 'goal', 'must arrive by', 'max spend on charging ($)', 'other wishes (all must be in your sentence)', 'YOUR REQUEST (write how you would say it to the car)'])
        for c in human:
            def say(x):
                t, v = x['type'], x.get('value')
                if t == 'max_wait': return f'stop no longer than {v:.0f} min'
                if t == 'avoid_network': return f"avoid the {str(v).replace(' Network', '')} network"
                if t == 'min_arrival': return f'arrive with at least {v:.0%} battery'
                if t == 'parked_at': return f'be parked (not driving) at {hhmm(v)}'
                if t == 'free_only': return 'only free chargers'
                if t == 'stop_city': return f'stop in {v}'
                return 'no DC fast chargers'
            wishes = [say(x) for x in c['wishes']]
            w.writerow([c['id'], c['goal'], hhmm(c['deadline_min']) if c.get('deadline_min') is not None else '',
                        f"{c['budget']:.2f}" if c.get('budget') is not None else '', '; '.join(wishes), ''])
    print(len(pilot), 'pilot situations;', len(human), 'rows in human_requests_sheet.csv')
if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
