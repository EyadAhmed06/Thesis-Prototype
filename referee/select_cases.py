"""Apply the testability checks, balance the groups, and write each situation as the text the model reads.
Usage: python select_cases.py CASE_DIR SPLIT N_KEEP SEED"""
import sys, os, json, itertools; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import config as C
from referee import Referee

def hhmm(m): m = int(round(m)); return f'{m // 60:02d}:{m % 60:02d}'
LETTERS = 'ABCDEFGHIJ'

def request(c, w):
    g, dl, b = c['goal'], c.get('deadline_min'), c.get('budget')
    head = {('fastest', 0): 'Get me there as fast as possible.', ('fastest', 1): 'What is the quickest way to get there?', ('fastest', 2): 'Time matters most to me today.',
            ('cheapest', 0): 'I want to spend as little as possible on charging.', ('cheapest', 1): 'Cheapest way to get there, please.', ('cheapest', 2): 'Money matters more than time to me today.'}[(g, w)]
    parts = [head]
    if dl is not None: parts.append([f'I have to arrive by {hhmm(dl)}.', f'I cannot arrive later than {hhmm(dl)}.', f'I must be there no later than {hhmm(dl)}.'][w])
    if b is not None: parts.append([f'I will not spend more than ${b:.2f} on charging.', f'My charging budget is ${b:.2f} at most.', f'Do not go over ${b:.2f} for charging.'][w])
    return ' '.join(parts)

def fact_sheet(c, drives, R, energy_facts=True, show_network=False):
    cap = C.CAR['usable_kwh']; T = c['temp_c']
    def leg(lid):
        d = drives[lid]; return d['minutes'], (d['wh'] + R.climate_wh(T, d['minutes'])) / 1000, d['km']
    m, kwh, km = leg(f"{c['id']}__direct")
    lines = [f"Car: {C.CAR['name']}, {cap:.0f} kWh usable, battery now {c['soc0']:.0%} ({c['soc0'] * cap:.1f} kWh).",
             f"Time now: {hhmm(c['depart_min'])}. Outside temperature: {T} °C.",
             f"Trip without stopping: {km:.0f} km, {m:.0f} min" + (f", uses {kwh:.1f} kWh including heating/cooling." if energy_facts else '.')]
    if not energy_facts:
        lines.append('Typical use of this car: about 16 kWh per 100 km in mild weather; heating in cold weather adds about 0.2 kW for every degree below 12 °C.')
    lines.append(f"Rules: never let the battery drop below {C.RESERVE:.0%}; each charging stop adds {C.STOP_OVERHEAD_MIN:.0f} min for parking and plugging in.")
    lines.append('Chargers near the route:')
    kdc = C.CAR['max_dc_kw'] * C.dc_cold_factor(T)
    for L, cid in zip(LETTERS, c['candidates']):
        ch = R.ch.loc[cid]
        a, b = leg(f"{c['id']}__to__{cid}"), leg(f"{c['id']}__from__{cid}")
        kind = (f'DC fast, about {kdc:.0f} kW for this car at {T} °C, slower above 80%' if ch.level == 'DC' else f"Level 2, {C.CAR['onboard_ac_kw']} kW for this car")
        price = ch.price_text if isinstance(ch.price_text, str) and ch.price_text != 'not listed' else f"price not listed (assume ${C.UNKNOWN_PRICE[ch.level]:.2f} per kWh)"
        status = 'working' if ch.working else 'temporarily out of service'
        if not ch.public: status += ', private access'
        drive = f"{a[0]:.0f} min to reach it, then {b[0]:.0f} min to the destination" + (f"; uses {a[1]:.1f} kWh to reach it and {b[1]:.1f} kWh from it to the destination" if energy_facts else f"; {a[2]:.0f} km to reach it, {b[2]:.0f} km from it to the destination")
        net = f"; network: {ch.network}" if show_network and isinstance(ch.network, str) else ''
        lines.append(f"  {L}. {ch['name']} ({ch.city}): {kind}; plugs: {ch.plugs}; {price}; {status}{net}; {drive}.")
    lines.append(f"This car charges with these plugs: {', '.join(sorted(C.CAR['plugs_ac']))} (Level 2) and {', '.join(sorted(C.CAR['plugs_dc']))} (DC fast).")
    return '\n'.join(lines)

def main(case_dir, split, n_keep, seed):
    rng = np.random.default_rng(seed)
    cases = json.load(open(os.path.join(case_dir, f'{split}_labelled.json')))
    drives = json.load(open(os.path.join(case_dir, f'{split}_drives.json')))
    # a charger whose legs SUMO could not drive (no route) is dropped from the list; the referee never counted it anyway
    dropped = 0
    R = Referee.__new__(Referee); R.ch = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chargers.csv')).set_index('id')
    for c in cases:
        keep = [x for x in c['candidates'] if f"{c['id']}__to__{x}" in drives and f"{c['id']}__from__{x}" in drives]
        if len(keep) < len(c['candidates']):
            dropped += len(c['candidates']) - len(keep); c['candidates'] = keep
            c['distractor'] = any(R.usable(x) for x in keep)
    df = pd.DataFrame([{k: v for k, v in c.items() if k != 'options'} for c in cases])
    log = {'generated': len(df), 'chargers dropped because no drivable route': dropped}
    df = df[df.robust]; log['answer survives the referee error band'] = len(df)
    df = df.drop_duplicates(['origin_edge', 'dest_edge']); log['no duplicate trips'] = len(df)
    df = df[df.candidates.map(len) <= len(LETTERS)]
    # balance: half must charge; spread over rules x closeness x distractor
    df['cell'] = list(zip(df.n_rules, df.close, df.distractor))
    pick = []
    for mc in (True, False):
        sub = df[df.must_charge == mc].sample(frac=1, random_state=seed)
        cells = sub.groupby('cell').groups; want = n_keep // 2 if n_keep else len(sub)
        order = list(itertools.chain.from_iterable(itertools.zip_longest(*[list(v) for v in cells.values()])))
        pick += [i for i in order if i is not None][:want]
    sel = df.loc[pick]; log['kept after balancing'] = len(sel)
    byid = {c['id']: c for c in cases}; out = []
    for cid in sel.id:
        c = byid[cid]
        letter = {ch: L for L, ch in zip(LETTERS, c['candidates'])}
        c2 = {k: v for k, v in c.items() if k != 'options'}
        c2['best_letter'] = letter.get(c['best_charger']) if c['must_charge'] else None
        c2['letters'] = letter
        c2['facts'] = {'with_energy': fact_sheet(c, drives, R, True), 'without_energy': fact_sheet(c, drives, R, False)}
        c2['requests'] = [request(c, w) for w in range(3)]
        out.append(c2)
    with open(os.path.join(case_dir, f'{split}_cases.jsonl'), 'w') as f:
        for c in out: f.write(json.dumps(c, default=str) + '\n')
    s = pd.DataFrame(out)
    log.update({'must charge': int(s.must_charge.sum()), 'rules 0/1/2': s.n_rules.value_counts().sort_index().tolist(),
                'close': int(s.close.sum()), 'with trap charger': int(s.distractor.sum()),
                'temp range': [int(s.temp_c.min()), int(s.temp_c.max())], 'route km median': float(s.route_km.median())})
    json.dump(log, open(os.path.join(case_dir, f'{split}_selection_log.json'), 'w'), indent=1, default=str)
    print(json.dumps(log, default=str))
if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
