"""Hand-checked tests for the referee's rules. Run: python test_referee.py  (no SUMO needed: drives are given by hand)."""
import sys, os, unittest; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import config as C
from referee import Referee

def stub():
    R = Referee.__new__(Referee)
    R.ch = pd.DataFrame([
        dict(id='FREE_L2', level='L2', plugs='J1772', working=True, public=True, price_kind='kwh', price_value=0.0, price_fee=0.0),
        dict(id='PAID_DC', level='DC', plugs='CHADEMO J1772COMBO', working=True, public=True, price_kind='kwh', price_value=0.50, price_fee=0.0),
        dict(id='CCS_DC', level='DC', plugs='J1772COMBO', working=True, public=True, price_kind='kwh', price_value=0.40, price_fee=0.0),
        dict(id='BROKEN_DC', level='DC', plugs='CHADEMO', working=False, public=True, price_kind='kwh', price_value=0.30, price_fee=0.0),
        dict(id='HOURLY_L2', level='L2', plugs='J1772', working=True, public=True, price_kind='hour', price_value=1.0, price_fee=0.5),
    ]).set_index('id')
    R.ch['network'] = ['NetA', 'NetB', 'NetB', 'NetC', 'NetA']; R.ch['city'] = ['Ann Arbor', 'Livonia', 'Livonia', 'Detroit', 'Ann Arbor']
    return R

def drives(case_id, direct_wh, legs):
    """legs: {charger: (to_wh, to_min, from_wh, from_min)}; direct drive takes 50 min."""
    d = {f'{case_id}__direct': dict(wh=direct_wh, minutes=50, km=56)}
    for cid, (a, am, b, bm) in legs.items():
        d[f'{case_id}__to__{cid}'] = dict(wh=a, minutes=am, km=20); d[f'{case_id}__from__{cid}'] = dict(wh=b, minutes=bm, km=38)
    return d

LEGS = {'FREE_L2': (3000, 18, 6000, 34), 'PAID_DC': (3000, 18, 6000, 34), 'CCS_DC': (2500, 15, 6000, 34), 'BROKEN_DC': (2000, 12, 6000, 34)}
def case(**kw):
    c = dict(id='t', origin_edge='o', dest_edge='d', depart_min=13 * 60, soc0=0.25, temp_c=15, goal='cheapest', deadline_min=None, candidates=list(LEGS))
    c.update(kw); return c

class Rules(unittest.TestCase):
    def test_level2_time(self):  # 20% of 59 kWh at 6.6 kW = 107.3 min
        self.assertAlmostEqual(stub().charge_minutes('L2', 0.2, 0.4, 15), 0.2 * 59 / 6.6 * 60, places=3)
    def test_dc_cold_and_taper(self):
        R = stub()
        self.assertAlmostEqual(R.charge_minutes('DC', 0.2, 0.3, 20), 0.1 * 59 / 50 * 60, places=3)
        self.assertAlmostEqual(R.charge_minutes('DC', 0.2, 0.3, -3), 0.1 * 59 / 30 * 60, places=3)   # 50 kW x 0.6
        self.assertGreater(R.charge_minutes('DC', 0.85, 0.95, 20), R.charge_minutes('DC', 0.6, 0.7, 20))
    def test_price(self):
        R = stub()
        self.assertEqual(R.price('FREE_L2', 10, 60), 0.0)
        self.assertAlmostEqual(R.price('PAID_DC', 10, 20), 5.0)
        self.assertAlmostEqual(R.price('HOURLY_L2', 10, 120), 2.5)
    def test_plug_and_status(self):
        R = stub()
        self.assertIn('plug does not fit', R.usable('CCS_DC'))
        self.assertIn('not working', R.usable('BROKEN_DC'))
        self.assertEqual(R.usable('PAID_DC'), [])
    def test_climate(self):
        self.assertEqual(Referee.climate_wh(12, 60), 0)
        self.assertAlmostEqual(Referee.climate_wh(2, 60), 2260)
        self.assertAlmostEqual(Referee.climate_wh(2, 60, heat_scale=0.5), 1130)
    def test_no_charge_when_enough(self):
        best = stub().decide(case(soc0=0.9), drives('t', 8000, LEGS))['best']
        self.assertFalse(best['charge'])
    def test_must_charge_when_short(self):  # 25% = 14.75 kWh; drive 13 kWh would leave 3% < reserve
        best = stub().decide(case(), drives('t', 13000, LEGS))['best']
        self.assertTrue(best['charge'])
    def test_cheapest_without_deadline_picks_free(self):
        best = stub().decide(case(), drives('t', 13000, LEGS))['best']
        self.assertEqual(best['charger'], 'FREE_L2')
    def test_deadline_forces_fast(self):
        # reaches charger at 19.9%, needs 25%: 3 kWh. L2: 27 min -> arrives 14:24. DC: 3.6 min -> 14:01. Deadline 14:15.
        best = stub().decide(case(deadline_min=14 * 60 + 15), drives('t', 13000, LEGS))['best']
        self.assertEqual(best['charger'], 'PAID_DC')
    def test_never_wrong_plug_or_broken(self):
        res = stub().decide(case(goal='fastest'), drives('t', 13000, LEGS))
        valid = res['options'][res['options'].valid]
        self.assertNotIn('CCS_DC', set(valid.charger)); self.assertNotIn('BROKEN_DC', set(valid.charger))
    def test_smallest_sufficient_target(self):
        best = stub().decide(case(deadline_min=14 * 60 + 15), drives('t', 13000, LEGS))['best']
        # needs soc_end >= 10%: 6 kWh after the stop = 10.2%, so target >= 20.2% -> 25% in 5% steps
        self.assertAlmostEqual(best['target'], 0.25)
    def test_loose_deadline_keeps_free(self):  # same case, deadline 14:30: free L2 (14:24) still on time and cheapest
        best = stub().decide(case(deadline_min=14 * 60 + 30), drives('t', 13000, LEGS))['best']
        self.assertEqual(best['charger'], 'FREE_L2')
    def test_budget(self):  # fastest goal, budget $1: paid DC (~$1.50) not allowed -> free L2
        best = stub().decide(case(goal='fastest', budget=1.0), drives('t', 13000, LEGS))['best']
        self.assertEqual(best['charger'], 'FREE_L2')
    def test_judge_specific_decision(self):
        R = stub(); dr = drives('t', 13000, LEGS)
        self.assertFalse(R.judge(case(), dr, False, None, None)['valid'])           # not charging strands her
        self.assertIn('plug', R.judge(case(), dr, True, 'CCS_DC', 0.5)['broken'])
        self.assertTrue(R.judge(case(), dr, True, 'FREE_L2', 0.37)['valid'])          # off-grid targets are judged exactly
    def test_unsolvable(self):
        self.assertFalse(stub().decide(case(soc0=0.02), drives('t', 13000, LEGS))['solvable'])

class Wishes(unittest.TestCase):
    """Driver wishes and the priority order (hard > deadline > budget > wishes). Base: must charge, cheapest = FREE_L2."""
    def best(self, **kw):
        return stub().decide(case(**kw), drives('t', 13000, LEGS))
    def test_base_is_free_l2(self):
        b = self.best()['best']; self.assertEqual(b['charger'], 'FREE_L2')
    def test_max_wait_moves_to_dc(self):
        r = self.best(wishes=[dict(type='max_wait', value=25)])
        self.assertEqual(r['best']['charger'], 'PAID_DC'); self.assertFalse(r['conflict'])
        self.assertLessEqual(C.STOP_OVERHEAD_MIN + r['best']['charge_min'], 25)
    def test_avoid_network(self):
        self.assertEqual(self.best(wishes=[dict(type='avoid_network', value='NetA')])['best']['charger'], 'PAID_DC')
    def test_min_arrival_raises_target(self):  # needs target >= 0.5 + 6000/59000 = 0.602 -> 0.65
        b = self.best(wishes=[dict(type='min_arrival', value=0.5)])['best']
        self.assertEqual(b['charger'], 'FREE_L2'); self.assertAlmostEqual(b['target'], 0.65)
    def test_parked_at_forces_a_stop(self):  # enough battery to skip charging, but the driver wants to be parked at 13:30
        r = self.best(soc0=0.6, wishes=[dict(type='parked_at', value=13 * 60 + 30)])
        self.assertTrue(r['best']['charge']); self.assertTrue(r['best']['stop_start'] <= 13 * 60 + 30 <= r['best']['stop_end'])
    def test_parked_after_arrival_needs_no_stop(self):  # arrives 13:50, so at 14:30 the car is parked anyway
        r = self.best(soc0=0.6, wishes=[dict(type='parked_at', value=14 * 60 + 30)])
        self.assertFalse(r['best']['charge']); self.assertFalse(r['conflict'])
    def test_stop_city(self):
        self.assertEqual(self.best(wishes=[dict(type='stop_city', value='Livonia')])['best']['charger'], 'PAID_DC')
    def test_deadline_beats_wish(self):  # only DC is fast enough; the wish for free charging is given up
        r = self.best(deadline_min=13 * 60 + 70, wishes=[dict(type='free_only')])
        self.assertEqual(r['best']['charger'], 'PAID_DC'); self.assertTrue(r['conflict'])
        self.assertEqual(Referee.level(r['best']), (False, False, 1))
    def test_deadline_beats_budget(self):  # no option meets both: keep the deadline, break the budget
        r = self.best(deadline_min=13 * 60 + 70, budget=0.5)
        self.assertEqual(r['best']['charger'], 'PAID_DC'); self.assertEqual(Referee.level(r['best']), (False, True, 0))
    def test_no_fast(self):  # fastest driver would take DC; the wish keeps them on Level 2
        self.assertEqual(self.best(goal='fastest', wishes=[dict(type='no_fast')])['best']['charger'], 'FREE_L2')
        self.assertEqual(self.best(goal='fastest')['best']['charger'], 'PAID_DC')
    def test_judge_reports_wish(self):
        R = stub(); c = case(wishes=[dict(type='free_only')])
        j = R.judge(c, drives('t', 13000, LEGS), True, 'PAID_DC', 0.6)
        self.assertTrue(j['safe']); self.assertFalse(j['valid']); self.assertIn('not free', j['broken'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
