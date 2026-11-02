"""Regression checks for launch-energy windows, fixed encounter dates and directions."""
import bootstrap  # noqa: F401
import copy
import unittest
import numpy as np
from dynamics import Model, kepler, lambert
from ephemeris import AU, DAY, JD0, MU_SUN, jd
from mission_search import normalize, routes_for, coverage, branch_families, objective_key
from candidate_refinement import neighborhood_request
from cost_refinement import refine


class CircularEphemerides:
    def state(self, body, date):
        radius = AU * dict(Earth=1., Venus=.723, Mars=1.524, Jupiter=5.2)[body]
        rate = np.sqrt(MU_SUN / radius**3)
        angle = .4 + (date-JD0)*DAY*rate
        return np.array([radius*np.cos(angle),radius*np.sin(angle),0.,
                         -radius*rate*np.sin(angle),radius*rate*np.cos(angle),0.])


class SearchConstraintTests(unittest.TestCase):
    def test_minimum_c3_is_validated_and_enforced_independently_of_dsm(self):
        c=normalize(dict(target='Mars',sequences=['EM'],min_c3=160,max_c3=170))
        model=Model(routes_for(c)[0],c,CircularEphemerides())
        q=dict(launch_c3_km2_s2=165.,arrival_vinf_kms=3.,duration_years=2.,
               total_dsm_kms=0.,dsms=[],flybys=[])
        self.assertTrue(model.accepted(q))
        for energy in (0.,120.,170.001):
            trial=dict(q,launch_c3_km2_s2=energy)
            self.assertFalse(model.accepted(trial))
        for request in (dict(min_c3=-1),dict(min_c3=float('nan')),
                        dict(min_c3=101,max_c3=100)):
            with self.assertRaises(ValueError):normalize(request)
        self.assertEqual(normalize({})['min_c3'],0.)

    def test_launch_c3_is_relative_velocity_squared_and_can_differ_for_same_endpoints(self):
        c=normalize(dict(target='Mars',sequences=['EM'],max_c3=1e5))
        model=Model(routes_for(c)[0],c,CircularEphemerides())
        x=np.array([.4,.6])
        energies=[]
        for direction in (True,False):
            q=model.evaluate(x,[[0,True,direction]])
            departure=np.array(q['departure_velocities_kms'][0])
            planet=np.array(q['events'][0]['planet_state_km_kms'][3:])
            self.assertAlmostEqual(q['launch_c3_km2_s2'],float(np.dot(departure-planet,departure-planet)),places=10)
            segment=q['segments'][0]
            r,v=kepler(np.array(segment['r']),np.array(segment['v']),
                       (segment['end_jd']-segment['start_jd'])*DAY)
            self.assertLess(np.linalg.norm(r-np.array(q['events'][-1]['planet_state_km_kms'][:3])),.02)
            self.assertEqual(np.cross(segment['r'],segment['v'])[2]>0,direction)
            energies.append(q['launch_c3_km2_s2'])
        self.assertGreater(abs(energies[1]-energies[0]),100.)

    def test_requested_arrival_replaces_final_duration_and_cannot_drift(self):
        c=normalize(dict(target='Jupiter',sequences=['EEJ'],launch_start='2004-12-01',
                         launch_end='2004-12-31',arrival_date='2012-12-01'))
        route=routes_for(c)[0];model=Model(route,c,None)
        for end_control in (0.,.25,1.):
            dates=model.dates([.5,.1,end_control])
            self.assertEqual(dates[-1],jd('2012-12-01'))
        self.assertEqual(coverage(c,[route])[1],jd('2012-12-01')+2)
        c=normalize(dict(target='Mars',sequences=['EM'],arrival_date='2035-01-01',arrival_tolerance_days=5))
        model=Model(routes_for(c)[0],c,None)
        self.assertEqual(model.dates([0.,0.])[-1],jd('2035-01-01')-5)
        self.assertEqual(model.dates([0.,1.])[-1],jd('2035-01-01')+5)

    def test_historical_exact_encounters_and_arrival_window_intersection(self):
        c=normalize(dict(target='Jupiter',sequences=['EEJ'],launch_start='2004-12-01',
                         launch_end='2004-12-31',arrival_date='2012-12-01',
                         event_windows=[['2004-12-15','2004-12-15'],
                                        ['2006-03-01','2006-03-31'],
                                        ['2012-01-01','2013-01-01']]))
        model=Model(routes_for(c)[0],c,None)
        dates=model.dates([.8,.5,.1])
        self.assertEqual(dates[0],jd('2004-12-15'))
        self.assertEqual(dates[-1],jd('2012-12-01'))
        with self.assertRaisesRegex(ValueError,'does not overlap'):
            normalize(dict(target='Mars',sequences=['EM'],arrival_date='2035-01-01',
                           event_windows=[['2030-01-01','2031-01-01'],['2032-01-01','2033-01-01']]))
        with self.assertRaisesRegex(ValueError,'follow'):
            normalize(dict(arrival_date='2000-01-01'))

    def test_neighborhood_keeps_fixed_arrival_and_time_objective(self):
        c=normalize(dict(target='Mars',sequences=['EM'],launch_start='2030-01-01',
                         launch_end='2030-02-01',arrival_date='2030-12-01',search_objective='time',
                         min_c3=20.,max_c3=200.))
        route=routes_for(c)[0];model=Model(route,c,None);x=[.5,.8]
        q=dict(id='0123456789ab',dates_jd_tdb=model.dates(x),x=x,
               branches=[[0,True]],launch_c3_km2_s2=60.)
        request=neighborhood_request(c,route,q,'parent',10.)
        normalized=normalize(request)
        self.assertEqual(request['search_objective'],'time')
        self.assertEqual(request['max_c3'],200.)
        self.assertEqual(request['min_c3'],20.)
        dates=Model(routes_for(normalized)[0],normalized,None).dates(request['local_refinement']['seed_x'])
        np.testing.assert_allclose(dates,q['dates_jd_tdb'],rtol=0,atol=1e-8)
        self.assertEqual(normalized['event_windows_jd'][-1][0],normalized['event_windows_jd'][-1][1])

    def test_time_refinement_shortens_a_physical_transfer_with_limits_intact(self):
        c=normalize(dict(target='Mars',sequences=['EM'],launch_start='2030-01-01',
                         launch_end='2030-02-01',max_c3=1e5,max_arrival_vinf_kms=200.,
                         search_objective='time'))
        model=Model(routes_for(c)[0],c,CircularEphemerides());x=np.array([.5,.8])
        before=model.evaluate(x,[[0,True]])
        after=refine(model,x,[[0,True]],objective='time',maxiter=50)
        self.assertIsNotNone(after)
        self.assertTrue(model.accepted(after))
        self.assertLess(after['duration_years'],before['duration_years']-.1)
        self.assertLessEqual(after['cost_refinement']['objective_after'],after['cost_refinement']['objective_before'])
        self.assertEqual(sorted([before,after],key=objective_key(c))[0],after)

    def test_new_direction_families_preserve_legacy_options(self):
        old=normalize(dict(target='Mars',sequences=['EM']))
        self.assertEqual(routes_for(old)[0]['branch_options'],[[[0,True]]])
        both=normalize(dict(target='Mars',sequences=['EM'],transfer_direction='both'))
        families=branch_families(routes_for(both)[0],10,502)
        self.assertEqual(families,[[[0,True,True]],[[0,True,False]]])
        retro=normalize(dict(target='Mars',sequences=['EM'],transfer_direction='retrograde'))
        self.assertEqual(routes_for(retro)[0]['branch_options'],[[[0,True,False]]])


if __name__=='__main__':unittest.main()
