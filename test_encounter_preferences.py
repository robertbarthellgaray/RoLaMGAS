import bootstrap  # noqa: F401
import math
import unittest
import numpy as np
from ephemeris import AU,MU_SUN,DAY
from dynamics import kepler
from encounter_preferences import first_outward_crossing_seconds,outer_approaches,preference_penalty,first_outer_years
from mission_search import normalize,objective_key


class ApproachTests(unittest.TestCase):
    def setUp(self):
        self.a=4*AU;self.e=.75;self.radius=5.5*AU
        self.r=np.array([AU,0.,0.]);self.v=np.array([0.,math.sqrt(MU_SUN*(2/AU-1/self.a)),0.])
        self.rate=math.sqrt(MU_SUN/self.a**3);self.period=2*math.pi/self.rate
        E=math.acos((1-self.radius/self.a)/self.e)
        self.outbound=(E-self.e*math.sin(E))/self.rate

    def approach(self,t,previous_radius=AU,frozen=1):
        r,v=kepler(self.r,self.v,t)
        states=[np.array([previous_radius,0.,0.,0.,0.,0.]),np.r_[r,np.zeros(3)]]
        return outer_approaches(['Earth','Jupiter'],[2450000.,2450000.+t/DAY],states,[v],
            [dict(start_jd=2450000.,end_jd=2450000.+t/DAY,r=self.r,v=self.v)],frozen)

    def test_analytic_crossing_matches_propagation(self):
        t=first_outward_crossing_seconds(self.r,self.v,self.radius,self.period)
        self.assertAlmostEqual(t/self.outbound,1.,places=12)
        r,v=kepler(self.r,self.v,t)
        self.assertLess(abs(np.linalg.norm(r)-self.radius),.01)
        self.assertGreater(r@v,0)

    def test_inbound_delay_and_extra_outward_revolution(self):
        out=self.approach(self.outbound)[0]
        self.assertEqual(out['direction'],'outward');self.assertEqual(out['normalized_detour_penalty'],0.)
        inward_time=self.period-self.outbound;back=self.approach(inward_time)[0]
        self.assertEqual(back['direction'],'inward')
        self.assertAlmostEqual(back['days_after_first_outward_radius_crossing'],(inward_time-self.outbound)/DAY,places=5)
        extra=self.approach(self.outbound+self.period)[0]
        self.assertEqual(extra['direction'],'outward');self.assertGreater(extra['normalized_detour_penalty'],1)

    def test_inward_transfers_and_frozen_prefix_are_excluded(self):
        self.assertEqual(self.approach(self.period-self.outbound,previous_radius=8*AU)[0]['normalized_detour_penalty'],0.)
        row=self.approach(self.period-self.outbound,frozen=2)[0]
        self.assertFalse(row['preference_eligible']);self.assertEqual(row['normalized_detour_penalty'],0.)
        self.assertEqual(outer_approaches(['Earth','Venus'],[0,1],[self.r,self.r],[self.v],[]),[])

    def test_circular_and_unbound_coasts_are_safe(self):
        self.assertIsNone(first_outward_crossing_seconds(self.r,np.array([0.,math.sqrt(MU_SUN/AU),0.]),self.radius,self.period))
        self.assertIsNone(first_outward_crossing_seconds(self.r,self.v*2,self.radius,self.period))

    def test_preference_changes_ranking_without_changing_physics(self):
        q=dict(launch_c3_km2_s2=12.,total_dsm_kms=0.,duration_years=8.,arrival_vinf_kms=7.,outer_approaches=self.approach(self.period-self.outbound))
        before=dict(q)
        self.assertGreater(objective_key(dict(search_objective='c3'))(q),12.)
        self.assertEqual(objective_key(dict(search_objective='c3',prefer_outbound_encounters=False))(q),12.)
        self.assertEqual(q,before);self.assertGreater(preference_penalty(q,{}),0)
        self.assertEqual(first_outer_years(dict(q,dates_jd_tdb=[2450000.])),(q['outer_approaches'][0]['julian_date_tdb']-2450000.)/365.25)
        self.assertEqual(normalize(dict(search_objective='outer_time',prefer_outbound_encounters=False))['search_objective'],'outer_time')
        with self.assertRaises(ValueError):normalize(dict(prefer_outbound_encounters='false'))


if __name__=='__main__':unittest.main()
