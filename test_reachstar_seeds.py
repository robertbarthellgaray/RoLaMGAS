"""Offline physical checks for credited resonance starters and bound enforcement."""
import bootstrap
import json,math,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from dynamics import Model,kepler
from ephemeris import AU,MU_SUN,DAY,calendar
from mission_search import normalize,routes_for,planned_jobs
from community import record_variables
from resonant_shooting_seeds import reference,resonant_velocity,verified_seeds,seed_venus_returns

DATA=reference()
class Events:
    def state(self,body,date):
        for record in [DATA['records'][-1],*DATA.get('future_records',[])]:
            for e in record['reference_events']:
                if e['body']==body and abs(e['julian_date_tdb']-date)<1e-7:return np.array(e['planet_state_km_kms'])
        raise AssertionError(f'Unexpected ephemeris lookup {body}, {date}')

def setup(record,**overrides):
    names={'199':'Mercury','299':'Venus','399':'Earth','499':'Mars','599':'Jupiter','699':'Saturn','799':'Uranus','899':'Neptune'}
    dates=record['dates_jd_tdb'];seq=record['sequence']
    c=normalize(dict(target=names[record['body_ids'][-1]],sequences=[seq],launch_start='1970-01-01',launch_end='1971-01-01',
        event_windows=[[calendar(d-.001).removesuffix(' TDB'),calendar(d+.001).removesuffix(' TDB')] for d in dates],
        min_c3=5,max_c3=20,max_dsm_kms=.005,max_single_dsm_kms=.005,max_years=19,max_arrival_vinf_kms=30,
        vinf_tolerance_mps=.1,dsm_velocity_box_kms=6.,
        route_overrides={seq:dict(leg_days=[[max(1,d*.8),d*1.2+1] for d in np.diff(dates)],branch_options=[[b] for b in record['branches']])}))
    c=normalize(dict(c,**overrides));route=routes_for(c)[0]
    return c,route,Model(route,c,Events())

class ReachStarSeedTests(unittest.TestCase):
    def test_cone_preserves_relative_speed_and_closes_one_solar_period(self):
        r=.723*AU;v=math.sqrt(MU_SUN/r);period=2*math.pi*math.sqrt(r**3/MU_SUN)/DAY
        state=np.array([r,0,0,0,v,0]);va=resonant_velocity(state,period,11.,np.array([2.,-1.,4.]))
        self.assertAlmostEqual(np.linalg.norm(va-state[3:]),11.,places=11)
        self.assertAlmostEqual(np.linalg.norm(va),v,places=11)
        final,velocity=kepler(state[:3],va,period*DAY)
        self.assertLess(np.linalg.norm(final-state[:3]),.1);np.testing.assert_allclose(velocity,va,atol=1e-8)
        with self.assertRaises(ValueError):resonant_velocity(state,period,1000.,[1,0,0])
        with self.assertRaises(ValueError):resonant_velocity(state,-1,11.,[1,0,0])
    def test_twelve_prefixes_revalidate_and_low_altitude_research_is_not_silently_accepted(self):
        self.assertEqual(len(DATA['records']),12);ordinary=0
        for record in DATA['records']:
            self.assertIn('ReachStar on Bilibili',record['credit'])
            c,r,m=setup(record);result=verified_seeds(c,[r],Events())
            self.assertEqual(bool(result['accepted']),record['standard_altitude_screen_passed'])
            ordinary+=len(result['accepted'])
            c,r,m=setup(record,minimum_altitude_km={'Earth':130.,'Venus':250.})
            self.assertEqual(len(verified_seeds(c,[r],Events())['accepted']),1)
        self.assertEqual(ordinary,7)
    def test_hard_c3_floor_is_checked_before_full_revalidation(self):
        c,r,m=setup(DATA['records'][-1],min_c3=15.)
        with patch.object(Model,'evaluate',side_effect=AssertionError('Forbidden energy must not evaluate a full chain')):
            self.assertEqual(verified_seeds(c,[r],Events())['accepted'],[])
        c,r,m=setup(DATA['records'][-1],historical_mission_seeds=False)
        self.assertEqual(verified_seeds(c,[r],Events())['accepted'],[])
    def test_venus_shooting_starts_keep_fixed_epochs_and_input_samples(self):
        record=DATA['records'][-1];c,r,m=setup(record,minimum_altitude_km={'Earth':130.,'Venus':250.})
        x,bb=record_variables(record,m);samples=np.tile(x,(4,1));original=samples.copy()
        points,stats=seed_venus_returns(samples,m,bb)
        self.assertGreater(stats['retained'],0)
        for p in points:
            self.assertTrue(m.c3_in_bounds(m.launch_c3(p,bb)))
            np.testing.assert_allclose(m.dates(p),record['dates_jd_tdb'],rtol=0,atol=.000001)
            self.assertTrue(np.all((p>=0)&(p<=1)))
        np.testing.assert_array_equal(samples,original)
        c,r,m=setup(record,min_c3=15.)
        points,stats=seed_venus_returns(samples,m,bb);self.assertEqual(points,[]);self.assertEqual(stats['c3_rejected'],4)
    def test_reference_branches_are_kept_even_with_one_worker_family(self):
        record=DATA['records'][-1];c,r,m=setup(record,branch_families=1)
        self.assertEqual(list(planned_jobs(c,[r]))[0][2],record['branches'])
    def test_custom_routes_admit_the_discovered_inner_planet_leg_times(self):
        route=routes_for(normalize(dict(target='Mercury',sequences=['EVMEVdvVMe'])))[0]
        self.assertIn([2,False],route['branch_options'][-1])
        route=routes_for(normalize(dict(target='Venus',sequences=['EVMeV'])))[0]
        self.assertLessEqual(route['leg_days'][-1][0],41.)
    def test_future_year_starters_are_recomputed_and_respect_ordinary_floors(self):
        self.assertEqual(len(DATA['future_records']),4)
        for record in DATA['future_records']:
            c,r,m=setup(record,max_dsm_kms=.01,max_single_dsm_kms=.01)
            result=verified_seeds(c,[r],Events())
            self.assertEqual(len(result['accepted']),1)
            q=result['accepted'][0];self.assertLess(q['total_dsm_kms'],.01)
            self.assertLess(q['launch_c3_km2_s2'],20)

if __name__=='__main__':unittest.main()
