import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
"""The referee: for a charging situation, drive every option in SUMO and find the best one.

A situation ("case") is a dict:
  origin_edge, dest_edge, depart_min (minutes after midnight), soc0 (0-1), temp_c,
  goal ('fastest' or 'cheapest'), deadline_min (minutes after midnight or None),
  candidates: list of charger ids (from chargers.csv) shown to the driver.
Every option = no charge, or charge at one candidate up to a target SoC.
"""
import sys, os, subprocess, tempfile, math, json
import xml.etree.ElementTree as ET
import pandas as pd
import config as C

SUMO_HOME = os.environ.get('SUMO_PKG', '/tmp/claude-0/-home-user/d281676a-9e0b-58dd-a185-3f1dadb4791e/scratchpad/sumo/lib/python3.13/site-packages/sumo')
sys.path.insert(0, SUMO_HOME + '/tools')
import sumolib

HERE = os.path.dirname(os.path.abspath(__file__))
VTYPE = '''<vType id="leafplus" vClass="passenger" emissionClass="Energy/unknown" mass="1830" speedFactor="1" speedDev="0" sigma="0">
 <param key="frontSurfaceArea" value="2.29"/><param key="airDragCoefficient" value="0.28"/><param key="rollDragCoefficient" value="0.012"/>
 <param key="constantPowerIntake" value="300"/><param key="propulsionEfficiency" value="0.88"/><param key="recuperationEfficiency" value="0.6"/>
 <param key="radialDragCoefficient" value="0.5"/></vType>'''   # same physics as the DEVRT check (sim-validation/devrt)

class Referee:
    def __init__(self, net_path, chargers_csv=os.path.join(HERE, 'chargers.csv')):
        self.net_path = net_path
        self.net = sumolib.net.readNet(net_path)
        self.ch = pd.read_csv(chargers_csv).set_index('id')
        from router import Router
        self.router = Router(self.net)

    # ---------- routing ----------
    def route(self, a, b):
        return self.router.path_from(a, self.router.tree_from(a), b)

    # ---------- SUMO energy for many legs in one run ----------
    def drive(self, legs, workers=4):
        """legs: list of dict(id, edges, departPos, arrivalPos). Returns {id: dict(wh, minutes, km)} from SUMO.
        Legs are split over several SUMO processes; inside one process, legs run one after another so cars never meet."""
        legs = [l for l in legs if l['edges']]
        if not legs: return {}
        chunks = [legs[i::workers] for i in range(workers)]
        procs = [self._start(c) for c in chunks if c]
        out = {}
        for p, ti in procs:
            p.wait()
            if p.returncode != 0: raise RuntimeError(p.stderr.read().decode()[-2000:])
            for tr in ET.parse(ti).getroot().iter('tripinfo'):
                em = tr.find('emissions')
                out[tr.get('id')] = dict(wh=float(em.get('electricity_abs')), minutes=float(tr.get('duration')) / 60, km=float(tr.get('routeLength')) / 1000)
        return out

    def _start(self, legs):
        tmp = tempfile.mkdtemp(prefix='ref_')
        rou, ti = os.path.join(tmp, 'legs.rou.xml'), os.path.join(tmp, 'ti.xml')
        t = 0.0; lines = ['<routes>', VTYPE]
        for l in legs:
            ff = sum(self.net.getEdge(e).getLength() / self.net.getEdge(e).getSpeed() for e in l['edges'])
            lines.append(f'<vehicle id="{l["id"]}" type="leafplus" depart="{t:.0f}" departPos="{l.get("departPos", "base")}" arrivalPos="{l.get("arrivalPos", "max")}" departLane="best" departSpeed="0"><route edges="{" ".join(l["edges"])}"/></vehicle>')
            t += 2 * ff + 120          # next leg starts long after this one ends, so vehicles never meet
        lines.append('</routes>')
        open(rou, 'w').write('\n'.join(lines))
        p = subprocess.Popen([SUMO_HOME + '/bin/sumo', '-n', self.net_path, '-r', rou, '--tripinfo-output', ti,
                        '--device.emissions.probability', '1', '--no-step-log', '--no-warnings', '--time-to-teleport', '-1',
                        '--ignore-route-errors', '--end', str(int(t + 7200))], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return p, ti

    # ---------- physics added on top of SUMO ----------
    @staticmethod
    def climate_wh(temp_c, minutes, heat_scale=1.0):
        h = C.HEAT
        w = heat_scale * h['k_heat_W_per_C'] * max(0, h['T_heat'] - temp_c) + h['k_cool_W_per_C'] * max(0, temp_c - h['T_cool'])
        return w * minutes / 60

    def charge_minutes(self, level, soc_from, soc_to, temp_c):
        """Minutes to charge from soc_from to soc_to (fractions), in 1% steps with taper for DC."""
        if soc_to <= soc_from: return 0.0
        cap = C.CAR['usable_kwh']; mins = 0.0; s = soc_from
        while s < soc_to - 1e-9:
            step = min(0.01, soc_to - s)
            if level == 'L2':
                kw = C.CAR['onboard_ac_kw']
            else:
                kw = C.CAR['max_dc_kw'] * C.dc_cold_factor(temp_c)
                if s > C.TAPER_START:
                    kw *= 1 - (1 - C.TAPER_END_FRACTION) * (s - C.TAPER_START) / (1 - C.TAPER_START)
            mins += step * cap / kw * 60; s += step
        return mins

    def price(self, cid, kwh, minutes):
        c = self.ch.loc[cid]
        v = c.price_value if pd.notna(c.price_value) else C.UNKNOWN_PRICE[c.level]
        if c.price_kind == 'hour': return c.price_fee + v * minutes / 60
        if c.price_kind == 'min': return c.price_fee + v * minutes
        return c.price_fee + v * kwh

    def usable(self, cid):
        c = self.ch.loc[cid]
        plugs = set(str(c.plugs).split())
        need = C.CAR['plugs_dc'] if c.level == 'DC' else C.CAR['plugs_ac']
        reasons = []
        if not plugs & need: reasons.append('plug does not fit')
        if not c.working: reasons.append('not working')
        if not c.public: reasons.append('not public')
        return reasons

    # ---------- the legs a case needs ----------
    def legs_for(self, case):
        o, d = case['origin_edge'], case['dest_edge']
        F, B = self.router.tree_from(o), self.router.tree_to(d)
        legs = [dict(id=f"{case['id']}__direct", edges=self.router.path_from(o, F, d))]
        for cid in case['candidates']:
            c = self.ch.loc[cid]
            legs.append(dict(id=f"{case['id']}__to__{cid}", edges=self.router.path_from(o, F, c.edge), arrivalPos=c.pos))
            legs.append(dict(id=f"{case['id']}__from__{cid}", edges=self.router.path_to(d, B, c.edge), departPos=c.pos))
        return legs

    # ---------- score every option ----------
    def options(self, case, drives, energy_scale=1.0, heat_scale=1.0, only=None):
        """All options (or only=(charger, target) for one specific decision) with their outcome and broken rules."""
        cap = C.CAR['usable_kwh'] * 1000; T = case['temp_c']; out = []
        def leg(lid):
            d = drives.get(lid)
            if d is None: return None
            return d['minutes'], (d['wh'] + self.climate_wh(T, d['minutes'], heat_scale)) * energy_scale, d['km']
        def add(**o):
            o['broken'] = '; '.join(o.pop('reasons')); o['valid'] = o['broken'] == ''; out.append(o)
        L = leg(f"{case['id']}__direct")
        if L and (only is None or only[0] is None):
            m, wh, km = L; soc_end = case['soc0'] - wh / cap; arr = case['depart_min'] + m
            r = []
            if soc_end < C.RESERVE: r.append(f'arrives at {soc_end:.0%}, below the {C.RESERVE:.0%} reserve')
            if case.get('deadline_min') is not None and arr > case['deadline_min']: r.append('arrives after the deadline')
            add(charge=False, charger=None, target=None, arrive_min=arr, cost=0.0, soc_end=soc_end, km=km, reasons=r)
        for cid in case['candidates']:
            if only is not None and only[0] != cid: continue
            A, B = leg(f"{case['id']}__to__{cid}"), leg(f"{case['id']}__from__{cid}")
            if not A or not B: continue
            lvl = self.ch.loc[cid, 'level']; soc_at = case['soc0'] - A[1] / cap
            for tgt in ([x / 100 for x in range(20, 101, 5)] if only is None else [only[1]]):
                r = list(self.usable(cid))
                if soc_at < C.RESERVE: r.append(f'reaches the charger at {soc_at:.0%}, below the reserve')
                if tgt <= soc_at:
                    if only is None: continue
                    r.append('target is below the battery level on arrival')
                cm = self.charge_minutes(lvl, max(soc_at, 0), tgt, T)
                kwh = (tgt - max(soc_at, 0)) * C.CAR['usable_kwh']
                soc_end = tgt - B[1] / cap
                arr = case['depart_min'] + A[0] + C.STOP_OVERHEAD_MIN + cm + B[0]
                if soc_end < C.RESERVE: r.append(f'arrives at {soc_end:.0%}, below the reserve')
                if case.get('deadline_min') is not None and arr > case['deadline_min']: r.append('arrives after the deadline')
                cost = self.price(cid, kwh, cm)
                if case.get('budget') is not None and cost > case['budget'] + 1e-9: r.append('costs more than the budget')
                add(charge=True, charger=cid, target=tgt, arrive_min=arr, cost=cost, soc_end=soc_end, km=A[2] + B[2], charge_min=cm, kwh=kwh, reasons=r)
        df = pd.DataFrame(out)
        if df.empty or only is not None: return df
        key = ['arrive_min', 'cost'] if case['goal'] == 'fastest' else ['cost', 'arrive_min']
        return df.sort_values(['valid'] + key, ascending=[False, True, True]).reset_index(drop=True)

    def decide(self, case, drives):
        """Best option + robustness: does the best charger/no-charge choice survive the referee's error band?"""
        base = self.options(case, drives)
        best = base.iloc[0] if len(base) and base.iloc[0].valid else None
        if best is None: return dict(solvable=False)
        def choice(df):
            b = df.iloc[0]
            return (bool(b.charge), b.charger) if b.valid else (None, None)
        alts = [choice(self.options(case, drives, energy_scale=s, heat_scale=h))
                for s in (1 - C.ENERGY_ERROR, 1 + C.ENERGY_ERROR) for h in (1.0, C.HEAT_SCALE_ALT)]
        robust = all(a == (bool(best.charge), best.charger) for a in alts)
        valid = base[base.valid]
        # second best = best valid option with a different charger / charge decision
        other = valid[(valid.charge != best.charge) | (valid.charger.fillna('') != ('' if pd.isna(best.charger) else best.charger))]
        return dict(solvable=True, robust=robust, best=best.to_dict(), second=(other.iloc[0].to_dict() if len(other) else None),
                    n_valid=len(valid), options=base)

    def judge(self, case, drives, charge, charger, target):
        """Outcome of one specific decision (a model's or a baseline's). target as a fraction 0-1."""
        if not charge: df = self.options(case, drives, only=(None, None))
        elif charger not in case['candidates']: return dict(valid=False, broken='charger not in the list', arrive_min=None, cost=None)
        else: df = self.options(case, drives, only=(charger, min(max(target, 0.0), 1.0)))
        if df.empty: return dict(valid=False, broken='could not be evaluated', arrive_min=None, cost=None)
        return df.iloc[0].to_dict()
