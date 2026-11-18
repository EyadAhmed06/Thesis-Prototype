"""Version 2 of the test (core redesign, see redesign/SPEC.md): add driver wishes and conflict situations to the
situations already driven in SUMO, label them with the referee, select a balanced set and write the model's text.
No new SUMO runs: every wish is a condition on options the referee has already computed.
Usage: python make_v2.py CASE_DIR SPLIT N_KEEP SEED OUT_DIR"""
import sys, os, json, itertools, math; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import config as C
from referee import Referee
from select_cases import fact_sheet, hhmm, LETTERS

SEEN = ['max_wait', 'avoid_network', 'min_arrival']           # may appear in training prompts
HELD_OUT = ['parked_at', 'free_only', 'stop_city', 'no_fast']            # test only: never shown during training or adaptation

def net_name(n): return str(n).replace(' Network', '')

WISH_TEXT = {
    'max_wait': ['I can\'t spend more than {v} minutes at a charger.', 'I don\'t want to stop for longer than {v} minutes.',
                 'Any charging stop has to be {v} minutes or less.'],
    'avoid_network': ['My card doesn\'t work with {v}, so avoid their chargers.', 'Please don\'t send me to a {v} charger.',
                      'I can\'t pay at {v} stations.'],
    'min_arrival': ['I need at least {v} battery when I arrive.', 'Make sure I get there with {v} or more.',
                    'I\'m driving on later, so leave me at least {v} at the destination.'],
    'parked_at': ['I have a call at {v} and want to be parked then.', 'I need to be stopped somewhere at {v}.',
                  'At {v} I want to be parked, not driving.'],
    'free_only': ['Only use free chargers.', 'I don\'t want to pay anything for charging.', 'If I charge, it has to be free.'],
    'no_fast': ['Please don\'t use fast chargers, they\'re hard on my battery.', 'Please only use Level 2 chargers, not fast ones.',
                'No DC fast charging today, please.'],
    'stop_city': ['I want to stop in {v} on the way.', 'I\'d like the stop to be in {v}, I want to grab lunch there.',
                  'Please make the stop in {v}.'],
}
def wish_words(w, k):
    v = w.get('value')
    if w['type'] == 'max_wait': v = f'{v:.0f}'
    if w['type'] == 'avoid_network': v = net_name(v)
    if w['type'] == 'min_arrival': v = f'{v:.0%}'
    if w['type'] == 'parked_at': v = hhmm(v)
    return WISH_TEXT[w['type']][k].format(v=v)

def request_v2(c, k):
    from select_cases import request
    return ' '.join([request(c, k)] + [wish_words(w, k) for w in c.get('wishes', [])])

def make_wish(kind, c, base, R, rng):
    """Set the wish's value from the options so that the current best breaks it (it changes the answer), or None."""
    safe = base[base.safe]; b = base.iloc[0]; chg = safe[safe.charge]
    if kind == 'max_wait':
        if not b.charge: return None
        stop = C.STOP_OVERHEAD_MIN + b.charge_min
        alt = C.STOP_OVERHEAD_MIN + chg[chg.charger != b.charger].groupby('charger').charge_min.min()
        alt = alt[alt < stop - 10]
        if not len(alt): return None
        v = 5 * round((stop + alt.min()) / 2 / 5)          # halfway between the best's stop and the shortest other stop
        return dict(type=kind, value=float(v)) if alt.min() + 3 <= v <= stop - 3 else None
    if kind == 'avoid_network':
        if not b.charge: return None
        n = R.ch.loc[b.charger, 'network']
        if not isinstance(n, str) or n == 'Non-Networked': return None
        return dict(type=kind, value=n)
    if kind == 'min_arrival':
        v = min(0.8, math.ceil((b.soc_end + 0.10) * 20) / 20)
        return dict(type=kind, value=float(v)) if v > b.soc_end + 0.02 else None
    if kind == 'parked_at':
        # a time when the best option is on the road but another safe option is parked at a charger
        cand = chg[chg.charger != b.charger] if b.charge else chg
        if not len(cand): return None
        o = cand.iloc[int(rng.integers(len(cand)))]
        t = 5 * round((o.stop_start + o.stop_end) / 2 / 5)
        if not (o.stop_start <= t <= o.stop_end) or not (c['depart_min'] < t < b.arrive_min): return None
        if b.charge and b.stop_start <= t <= b.stop_end: return None
        return dict(type=kind, value=int(t))
    if kind == 'free_only':
        free = [x for x in c['candidates'] if not R.usable(x) and R.ch.loc[x, 'price_kind'] == 'kwh'
                and R.ch.loc[x, 'price_value'] == 0 and R.ch.loc[x, 'price_fee'] == 0]
        if not free or not b.charge or b.cost <= 0: return None
        return dict(type=kind)
    if kind == 'no_fast':
        l2 = [x for x in c['candidates'] if not R.usable(x) and R.ch.loc[x, 'level'] == 'L2']
        return dict(type=kind) if b.charge and R.ch.loc[b.charger, 'level'] == 'DC' and l2 else None
    if kind == 'stop_city':
        cities = sorted({R.ch.loc[x, 'city'] for x in c['candidates'] if not R.usable(x)} - ({R.ch.loc[b.charger, 'city']} if b.charge else set()))
        if not cities: return None
        return dict(type=kind, value=cities[int(rng.integers(len(cities)))])
    raise ValueError(kind)

def main(case_dir, split, n_keep, seed, out_dir):
    rng = np.random.default_rng(seed); os.makedirs(out_dir, exist_ok=True)
    cases = json.load(open(os.path.join(case_dir, f'{split}_labelled.json')))
    drives = json.load(open(os.path.join(case_dir, f'{split}_drives.json')))
    R = Referee.__new__(Referee); R.ch = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chargers.csv')).set_index('id')
    kinds = SEEN if split == 'train' else SEEN + HELD_OUT
    out, log = [], {'base situations': len(cases)}
    for c in cases:
        c = {k: v for k, v in c.items() if k != 'options'}
        c['candidates'] = [x for x in c['candidates'] if f"{c['id']}__to__{x}" in drives and f"{c['id']}__from__{x}" in drives]
        c['distractor'] = any(R.usable(x) for x in c['candidates'])
        n_w = int(rng.choice([0, 1, 2], p=[0.2, 0.45, 0.35])); c['wishes'] = []
        wt = np.array([{'max_wait': 3, 'free_only': 4}.get(k, 1) for k in kinds], float)   # rarer-to-bite types tried first more often
        for kind in rng.choice(kinds, size=len(kinds), replace=False, p=wt / wt.sum()):
            if len(c['wishes']) >= n_w: break
            if any(w['type'] == kind for w in c['wishes']): continue
            base = R.options(c, drives)
            if not len(base) or not base.iloc[0].safe: break
            w = make_wish(str(kind), c, base, R, rng)
            if w: c['wishes'].append(w)
        # some two-rule drivers get a budget no on-time option can meet: the deadline must win over the budget
        if c['n_rules'] == 2 and rng.random() < 0.4:
            base = R.options(c, drives)
            ok = base[base.safe & ~base.deadline_broken & base.charge]
            if len(ok) and not len(base[base.safe & ~base.deadline_broken & ~base.charge]):
                m = ok.cost.min(); v = math.floor(m * 0.6 * 2) / 2
                if v >= 0.5 and m - v >= 0.5: c['budget'] = float(v); c['budget_conflict'] = True
        res = R.decide(c, drives)
        if not res['solvable'] or not res['robust']: continue
        b, s = res['best'], res['second']; lv = Referee.level(b)
        key = 'arrive_min' if c['goal'] == 'fastest' else 'cost'
        gap = None if s is None else float(s[key] - b[key])
        c.update(n_wishes=len(c['wishes']), wish_types=[w['type'] for w in c['wishes']],
                 held_out=any(w['type'] in HELD_OUT for w in c['wishes']), conflict=bool(res['conflict']),
                 best_level=list(lv), gives_up=(['arrival time'] if lv[0] else []) + (['budget'] if lv[1] else []) + (['wishes'] if lv[2] else []),
                 must_charge=bool(b['charge']), best_charger=b['charger'] if b['charge'] else None,
                 best_target=b['target'] if b['charge'] else None, best_arrive_min=float(b['arrive_min']),
                 best_cost=round(float(b['cost']), 2), best_soc_end=round(float(b['soc_end']), 3), best_broken=b['soft_broken'],
                 second_charger=None if s is None else s['charger'], gap=gap,
                 close=bool(gap is not None and gap < (C.CLOSE_MIN if key == 'arrive_min' else C.CLOSE_USD)),
                 n_valid=res['n_valid'], n_best_level=res['n_best_level'])
        out.append(c)
    df = pd.DataFrame(out); log['robust with wishes'] = len(df)
    df = df.drop_duplicates(['origin_edge', 'dest_edge']); df = df[df.candidates.map(len) <= len(LETTERS)]
    # balance: conflict about a third, spread over number of wishes x held-out x must charge
    freq = pd.Series([t for x in df.wish_types for t in x]).value_counts()
    df['primary'] = [min(x, key=lambda t: freq[t]) if x else 'none' for x in df.wish_types]   # rarest wish type first
    df['cell'] = list(zip(df.primary, df.gives_up.map(tuple), df.must_charge))
    want = {True: n_keep // 3, False: n_keep - n_keep // 3} if n_keep else {True: None, False: None}
    pick = []
    for cf in (True, False):
        sub = df[df.conflict == cf].sample(frac=1, random_state=seed)
        groups = [list(v) for _, v in sorted(sub.groupby('cell').groups.items(), key=lambda kv: str(kv[0]))]
        order = [i for i in itertools.chain.from_iterable(itertools.zip_longest(*groups)) if i is not None]
        pick += order[:want[cf]] if want[cf] else order
    sel = df.loc[pick]; byid = {c['id']: c for c in out}; final = []
    for cid in sel.id:
        c = byid[cid]; letter = {ch: L for L, ch in zip(LETTERS, c['candidates'])}
        c['letters'] = letter; c['best_letter'] = letter.get(c['best_charger']) if c['must_charge'] else None
        c['facts'] = {'with_energy': fact_sheet(c, drives, R, True, show_network=True),
                      'without_energy': fact_sheet(c, drives, R, False, show_network=True)}
        c['requests'] = {'template': [request_v2(c, k) for k in range(3)]}
        final.append(c)
    with open(os.path.join(out_dir, f'{split}_cases.jsonl'), 'w') as f:
        for c in final: f.write(json.dumps(c, default=str) + '\n')
    s = pd.DataFrame(final)
    log.update({'kept': len(s), 'conflict': int(s.conflict.sum()), 'must charge': int(s.must_charge.sum()),
                'wishes 0/1/2': s.n_wishes.value_counts().sort_index().tolist(), 'with held-out wish type': int(s.held_out.sum()),
                'wish types': pd.Series([t for x in s.wish_types for t in x]).value_counts().to_dict(),
                'rules 0/1/2': s.n_rules.value_counts().sort_index().tolist(), 'with trap charger': int(s.distractor.sum()),
                'close': int(s.close.sum()), 'budget set below every on-time option': int(s.get('budget_conflict', pd.Series(dtype=bool)).fillna(False).sum()), 'gives up': pd.Series([','.join(x) or 'nothing' for x in s.gives_up]).value_counts().to_dict()})
    json.dump(log, open(os.path.join(out_dir, f'{split}_selection_log.json'), 'w'), indent=1, default=str)
    print(json.dumps(log, indent=1, default=str))
if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5])
