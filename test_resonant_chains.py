"""Physical regressions for bounded UOP and Mercury resonant starters."""
import bootstrap
import json,math,unittest
from pathlib import Path
import numpy as np
from dynamics import Model,kepler,flyby
from ephemeris import AU,DAY,MU_SUN,BODIES,jd
from mission_search import normalize,routes_for,branch_families,planned_jobs
from mercury_returns import coherent_families,verified_resonant_seeds
from trajectory_transfer import materialize
from tools.study_resonant_transfers import two_year_earth_limit,outgoing_flyby,configuration

DATA=json.loads((Path(__file__).parent/'departure_seeds/resonant_chains.json').read_text(encoding='utf-8'))

class EventEphemerides:
    def state(self,body,date):
        for record in DATA['records']:
            for e in record['reference_events']:
                if e['body']==body and abs(e['julian_date_tdb']-date)<1e-7:return np.array(e['planet_state_km_kms'])
        raise AssertionError(f'Unexpected event: {body}, {date}')


def config(target='Uranus',**extra):
    sequences=list(dict.fromkeys(r['sequence'] for r in DATA['records'] if r['body_ids'][-1]==str(BODIES[target][0])))
    c=configuration(target,sequences);c.update(extra);return normalize(c)


def accepted(c):return verified_resonant_seeds(c,routes_for(c),EventEphemerides())['accepted']

class ResonanceTests(unittest.TestCase):
    def test_exact_perihelion_return_has_no_free_energy_gain(self):
        q=two_year_earth_limit();self.assertAlmostEqual(q['c3_km2_s2'],25.7850522,places=6)
        self.assertAlmostEqual(q['aphelion_au'],2.1748021,places=6)
        self.assertLess(q['maximum_post_flyby_speed_kms'],q['jupiter_hohmann_departure_speed_kms'])
        r=np.array([AU,0.,0.]);v=np.array([0.,q['departure_speed_kms'],0.]);a=q['semimajor_axis_au']*AU
        final,_=kepler(r,v,2*math.pi*math.sqrt(a**3/MU_SUN))
        self.assertLess(np.linalg.norm(final-r),.01)
        for beta in np.linspace(-math.pi,math.pi,13):
            outgoing=outgoing_flyby(np.array([0.,q['launch_vinf_kms'],0.]),BODIES['Earth'][1],BODIES['Earth'][2]+200,beta,np.array([1.,0.,0.]))
            self.assertLessEqual(np.linalg.norm(outgoing+[0.,q['earth_speed_kms'],0.]),q['departure_speed_kms']+1e-10)

    def test_forward_flyby_preserves_excess_speed_and_recovers_periapsis(self):
        incoming=np.array([3.,-5.,2.]);mu=BODIES['Mercury'][1];radius=BODIES['Mercury'][2]
        for altitude in (200.,1000.,20000.):
            for beta in (-2.,0.,1.5):
                outgoing=outgoing_flyby(incoming,mu,radius+altitude,beta,incoming)  # parallel hint uses safe basis
                self.assertAlmostEqual(np.linalg.norm(outgoing),np.linalg.norm(incoming),places=12)
                f=flyby('Mercury',incoming,outgoing,200.,.001)
                self.assertTrue(f['passes_turn_screen']);self.assertAlmostEqual(f['conservative_equal_speed_altitude_km'],altitude,places=6)

    def test_custom_mercury_ladder_contains_late_revolutions_and_inner_approach(self):
        c=normalize(dict(target='Mercury',sequences=['EVVMedvMedvMedvMe']));r=routes_for(c)[0]
        self.assertIn([1,True],r['branch_options'][2])
        for options in r['branch_options'][3:]:self.assertIn([5,True],options)
        r=routes_for(normalize(dict(target='Mercury',sequences=['EVMeMeMeMe'])))[0]
        first=branch_families(r,1,502)[0]
        self.assertEqual([b[0] for b in first[2:]],[2,3,5])
        self.assertEqual(coherent_families(r)[1][2:],[ [1,True],[2,True],[4,True]])

    def test_explicit_branch_restrictions_and_parent_priority_are_preserved(self):
        r=routes_for(normalize(dict(target='Mercury',sequences=['EVMeMeMeMe'])))[0]
        r['branch_options']=[[[0,True]] for _ in r['branch_options']]
        self.assertTrue(all(b==[0,True] for f in coherent_families(r) for b in f))
        c=config('Mercury');r=routes_for(c)[-1];parent=[o[-1] for o in r['branch_options']]
        self.assertEqual(branch_families(r,1,502,preferred=parent),[parent])

    def test_all_starters_rebuild_with_safe_turns_and_actual_burns(self):
        for target,count in [('Uranus',4),('Mercury',4)]:
            c=config(target);rows=accepted(c);self.assertEqual(len(rows),count)
            for q in rows:
                model=Model(next(r for r in routes_for(c) if r['id']==q['sequence']),c,EventEphemerides())
                self.assertTrue(model.accepted(q));self.assertLess(q['max_vinf_mismatch_mps'],.01)
                self.assertGreater(q['min_turn_margin_deg'],-1e-9)
                self.assertAlmostEqual(q['total_dsm_kms'],sum(b['magnitude_kms'] for b in q['dsms']),places=9)

    def test_user_limits_and_windows_cannot_be_bypassed_by_stored_seeds(self):
        for extra in [dict(min_c3=24.),dict(max_dsm_kms=.4),dict(max_arrival_vinf_kms=5.),
                      dict(minimum_altitude_km={'Earth':1000.}),dict(historical_mission_seeds=False),
                      dict(launch_start='2035-01-01',launch_end='2036-01-01')]:
            with self.subTest(extra=extra):self.assertEqual(accepted(config(**extra)),[])
        c=config();record=DATA['records'][0]
        c['event_windows_jd']=[[v+1,v+2] for v in record['dates_jd_tdb']]
        self.assertEqual(accepted(c),[])

    def test_energy_pruning_happens_before_any_full_chain_evaluation(self):
        from unittest.mock import patch
        c=config(min_c3=24.);original=Model.evaluate
        def guarded(model,x,branches,*args,**kwargs):
            self.assertTrue(model.c3_in_bounds(model.launch_c3(x,branches)))
            return original(model,x,branches,*args,**kwargs)
        with patch.object(Model,'evaluate',guarded):self.assertEqual(accepted(c),[])

    def test_portable_records_reproduce_all_coasts_without_search(self):
        for target in ['Uranus','Mercury']:
            c=config(target)
            for record in DATA['records']:
                if record['body_ids'][-1]!=str(BODIES[target][0]):continue
                route=next(r for r in routes_for(c) if r['id']==record['sequence'])
                q=materialize(record,c,route,EventEphemerides())
                self.assertAlmostEqual(q['arrival_vinf_kms'],record['metrics']['arrival_vinf_kms'],places=8)

    def test_verified_branch_is_scheduled_with_one_slot_alone_or_grouped(self):
        for target in ['Uranus','Mercury']:
            c=config(target,branch_families=1)
            jobs=list(planned_jobs(c,routes_for(c)))
            for job in jobs:
                known=next(r for r in DATA['records'] if r['sequence']==job[0]['id'])
                self.assertEqual(job[2],known['branches'])
                solo=dict(c,sequences=[job[0]['id']])
                self.assertEqual(list(planned_jobs(solo,routes_for(solo)))[0][2],job[2])

    def test_uop_2033_can_use_its_short_first_venus_leg(self):
        r=routes_for(normalize(dict(target='Uranus',sequences=['EVEEU'])))[0]
        self.assertLessEqual(r['leg_days'][0][0],81.)
        self.assertIn([1,True],r['branch_options'][1])

if __name__=='__main__':unittest.main()
