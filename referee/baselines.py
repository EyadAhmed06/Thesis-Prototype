"""Simple methods the model must beat. Each returns a decision dict(charge, charger, target) using only what the fact sheet says."""
import numpy as np
import config as C

def _facts(c, drives, R, est=False):
    """est=False: the exact per-leg energy the 'with energy' fact sheet shows.
    est=True: only km and minutes, energy guessed with the fact sheet's rule of thumb (16 kWh/100 km + 0.2 kW per degree below 12 C)."""
    cap = C.CAR['usable_kwh'] * 1000; T = c['temp_c']
    def leg(lid):
        d = drives[lid]
        if est: return d['minutes'], 160.0 * d['km'] + 200.0 * max(0.0, 12.0 - T) * d['minutes'] / 60
        return d['minutes'], d['wh'] + R.climate_wh(T, d['minutes'])
    return cap, leg

def need_charge_estimate(c, drives, R, est=False):
    cap, leg = _facts(c, drives, R, est)
    m, wh = leg(f"{c['id']}__direct")
    return c['soc0'] - wh / cap < C.RESERVE

def _target(c, drives, R, cid, margin=0.05, est=False):
    cap, leg = _facts(c, drives, R, est)
    need = leg(f"{c['id']}__from__{cid}")[1] / cap + C.RESERVE + margin
    return float(min(1.0, np.ceil(need * 20) / 20))

def usable(c, R):
    return [cid for cid in c['candidates'] if not R.usable(cid)]

def nearest(c, drives, R, est=False):
    """Charge only if the trip can't be done; then the compatible working charger with the shortest detour, to 80%."""
    if not need_charge_estimate(c, drives, R, est): return dict(charge=False, charger=None, target=None)
    _, leg = _facts(c, drives, R, est)
    ok = usable(c, R)
    if not ok: return dict(charge=True, charger=c['candidates'][0], target=0.8)
    cid = min(ok, key=lambda x: leg(f"{c['id']}__to__{x}")[0] + leg(f"{c['id']}__from__{x}")[0])
    return dict(charge=True, charger=cid, target=0.8)

def random_safe(c, drives, R, rng):
    """Any option that does not strand the car, ignoring the driver's goal and rules."""
    res = R.options(dict(c, deadline_min=None, budget=None, wishes=[]), drives)
    safe = res[res.valid]
    if not len(safe): return dict(charge=False, charger=None, target=None)
    o = safe.iloc[rng.integers(len(safe))]
    return dict(charge=bool(o.charge), charger=o.charger if o.charge else None, target=None if not o.charge else float(o.target))

def goal_rule(c, drives, R, est=False):
    """What a careful programmer would write: no charge if the trip fits; else, among usable chargers that the car can
    reach, the goal's favourite (fastest: least total time with DC preferred; cheapest: lowest price per kWh), charged to
    what the remaining trip needs plus a 5% margin; skip options that clearly break the driver's deadline or budget."""
    cap, leg = _facts(c, drives, R, est)
    m, wh = leg(f"{c['id']}__direct")
    if c['soc0'] - wh / cap >= C.RESERVE + 0.02 and (c.get('deadline_min') is None or c['depart_min'] + m <= c['deadline_min']):
        return dict(charge=False, charger=None, target=None)
    best = None
    for cid in usable(c, R):
        a_m, a_wh = leg(f"{c['id']}__to__{cid}"); b_m, b_wh = leg(f"{c['id']}__from__{cid}")
        if c['soc0'] - a_wh / cap < C.RESERVE: continue
        tgt = _target(c, drives, R, cid, est=est)
        soc_at = c['soc0'] - a_wh / cap
        cm = R.charge_minutes(R.ch.loc[cid, 'level'], soc_at, tgt, c['temp_c'])
        arr = c['depart_min'] + a_m + C.STOP_OVERHEAD_MIN + cm + b_m
        cost = R.price(cid, (tgt - soc_at) * C.CAR['usable_kwh'], cm)
        if c.get('deadline_min') is not None and arr > c['deadline_min']: continue
        if c.get('budget') is not None and cost > c['budget']: continue
        key = (arr, cost) if c['goal'] == 'fastest' else (cost, arr)
        if best is None or key < best[0]: best = (key, cid, tgt)
    if best is None:
        ok = usable(c, R)
        if not ok: return dict(charge=True, charger=c['candidates'][0], target=0.8)
        return dict(charge=True, charger=ok[0], target=0.8)
    return dict(charge=True, charger=best[1], target=best[2])


def planner(c, drives, R, wishes=None):
    """Exact planner: searches every option with the referee's own rules and priority order, given the settings it is told
    (goal, deadline, budget, wishes). Used for role R3 (the model only fills in the settings) and as a ceiling baseline.
    It only uses numbers printed on the 'with energy' fact sheet, so with correct settings it matches the referee."""
    res = R.options(dict(c, wishes=c.get('wishes', []) if wishes is None else wishes), drives)
    if not len(res) or not res.iloc[0].safe: return dict(charge=False, charger=None, target=None, gives_up=[])
    b = res.iloc[0]
    gives = (['arrival time'] if b.deadline_broken else []) + (['budget'] if b.budget_broken else []) + (['wishes'] if b.wishes_broken else [])
    return dict(charge=bool(b.charge), charger=b.charger if b.charge else None, target=float(b.target) if b.charge else None, gives_up=gives)
