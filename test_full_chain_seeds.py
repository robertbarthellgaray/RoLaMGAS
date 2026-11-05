"""Physical complete-chain regressions using six preserved JPL event states."""
import bootstrap
import json,unittest
from unittest.mock import patch
import numpy as np
from dynamics import Model,kepler
from earth_return_seeds import chain_reference,verified_chain_seeds,preferred_chain_branch,fit_initial_dsm
from ephemeris import DAY
from mission_search import normalize,routes_for,planned_jobs


class EventEphemerides:
    def state(self,body,date):
        for event in chain_reference()['reference_events']:
            if event['body']==body and abs(event['julian_date_tdb']-date)<1e-7:
                return np.array(event['planet_state_km_kms'])
        raise AssertionError(f'Unexpected body/date: {body} {date}')


def config(**extra):
    c=dict(target='Jupiter',sequences=['EdvEVEEJ'],launch_start='2029-01-01',launch_end='2043-01-01',
           min_c3=6.25,max_c3=10.,max_arrival_vinf_kms=15.,max_dsm_kms=1.5,max_single_dsm_kms=.7,
           minimum_altitude_km={'Earth':200.,'Venus':300.})
    c.update(extra);return normalize(c)


def seeds(c):return verified_chain_seeds(c,routes_for(c),EventEphemerides())


class FullChainSeedTests(unittest.TestCase):
    def test_all_tradeoffs_are_recomputed_with_small_burns_and_safe_turns(self):
        c=config();r=seeds(c);self.assertEqual(r['stats']['accepted'],5)
        model=Model(routes_for(c)[0],c,EventEphemerides())
        for q in r['accepted']:
            self.assertTrue(model.accepted(q));self.assertLess(q['total_dsm_kms'],.5)
            self.assertLess(q['max_vinf_mismatch_mps'],.03)
            self.assertEqual(len(q['dsms']),1);self.assertGreaterEqual(q['min_turn_margin_deg'],0.)
            self.assertEqual(q['powered_flyby_delta_v_kms'],0.)
        low=min(r['accepted'],key=lambda q:q['launch_c3_km2_s2'])
        self.assertAlmostEqual(low['launch_c3_km2_s2'],6.25,places=8)
        self.assertAlmostEqual(low['total_dsm_kms'],.49392463,places=6)

    def test_launch_window_and_velocity_box_remapping_preserve_physical_seed(self):
        a=seeds(config())['accepted'][0]
        b=seeds(config(launch_start='2030-01-01',launch_end='2038-01-01',dsm_velocity_box_kms=12.))['accepted'][0]
        np.testing.assert_allclose(a['dates_jd_tdb'],b['dates_jd_tdb'],atol=1e-8)
        np.testing.assert_allclose(a['dsms'][0]['delta_v_ecliptic_j2000_kms'],b['dsms'][0]['delta_v_ecliptic_j2000_kms'],atol=1e-9)
        self.assertNotEqual(a['x'][0],b['x'][0]);self.assertNotEqual(a['x'][7:],b['x'][7:])

    def test_declared_sun_only_arcs_reach_their_next_positions(self):
        q=seeds(config())['accepted'][0]
        for i,s in enumerate(q['segments']):
            r,_=kepler(np.array(s['r']),np.array(s['v']),(s['end_jd']-s['start_jd'])*DAY)
            target=q['segments'][i+1]['r'] if i+1<len(q['segments']) else q['events'][-1]['planet_state_km_kms'][:3]
            self.assertLess(np.linalg.norm(r-target),.1)

    def test_current_limits_and_explicit_windows_are_never_bypassed(self):
        for extra in [dict(launch_start='2034-01-01'),dict(max_arrival_vinf_kms=8.),dict(max_single_dsm_kms=.18),
                      dict(minimum_altitude_km={'Earth':300.,'Venus':300.}),dict(earth_return_seeds=False)]:
            with self.subTest(extra=extra):self.assertEqual(seeds(config(**extra))['accepted'],[])
        c=config();dates=chain_reference()['donor']['dates_jd_tdb']
        c['event_windows_jd']=[[v+1.,v+2.] for v in dates]
        self.assertEqual(seeds(c)['accepted'],[])

    def test_narrow_energy_interval_builds_a_real_bounded_dsm(self):
        c=config(min_c3=7.5,max_c3=7.6);r=seeds(c)
        self.assertEqual(r['stats']['continuations'],1);self.assertEqual(len(r['accepted']),1)
        q=r['accepted'][0];self.assertAlmostEqual(q['launch_c3_km2_s2'],7.5,places=8)
        self.assertGreater(q['total_dsm_kms'],.346);self.assertLess(q['total_dsm_kms'],.429)
        self.assertLess(q['max_vinf_mismatch_mps'],.03)

    def test_known_family_is_scheduled_even_with_one_branch_and_grouped_routes(self):
        c=config(branch_families=1);one=list(planned_jobs(c,routes_for(c)))
        self.assertEqual(one[0][2],chain_reference()['donor']['branches'])
        grouped=config(branch_families=1,sequences=['EVEEJ','EdvEVEEJ'])
        jobs=[j for j in planned_jobs(grouped,routes_for(grouped)) if j[0]['id']=='EdvEVEEJ']
        self.assertEqual(jobs[0][2],one[0][2]);self.assertEqual(jobs[0][3:6],one[0][3:6])
        fixed=config(branch_families=1,route_overrides={'EdvEVEEJ':{'branch_options':[[[0,True]]]*5}})
        self.assertIsNone(preferred_chain_branch(fixed,routes_for(fixed)[0]))

    def test_continuation_never_evaluates_a_full_chain_outside_user_c3(self):
        c=config(min_c3=7.5,max_c3=7.6);model=Model(routes_for(c)[0],c,EventEphemerides());evaluate=model.evaluate
        def guarded(x,branches,*args,**kwargs):
            self.assertTrue(model.c3_in_bounds(model.launch_c3(x,branches)))
            return evaluate(x,branches,*args,**kwargs)
        with patch.object(model,'evaluate',side_effect=guarded):
            q=fit_initial_dsm(model,chain_reference()['donor']['dates_jd_tdb'],chain_reference()['donor']['branches'],7.5,fractions=(.82,))
        self.assertIsNotNone(q)
        with self.assertRaisesRegex(ValueError,'outside'):fit_initial_dsm(model,q['dates_jd_tdb'],q['branches'],6.25)

if __name__=='__main__':unittest.main()
