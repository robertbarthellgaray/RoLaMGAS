"""Regression checks for fractional target-center distances and retrograde exports."""
import bootstrap
import unittest
import numpy as np
from ephemeris import AU,DAY,MU_SUN,jd
from integrate_export import small_body_node,solar_piece,requirement_violations
from dynamics import kepler
from mission_search import normalize

class FixedTarget:
    def state(self,body,date):
        return np.array([AU,2*AU,0.,0.,12.,-1.])

class ExportTargetingTests(unittest.TestCase):
    def test_fractional_minor_body_distance_and_legacy_default(self):
        ep=FixedTarget();incoming=np.array([5.,-3.,1.])
        for distance in (0.1,0.001,10000.):
            node=small_body_node('test',2451545.,ep,incoming,distance)
            offset=node['target_state'][:3]-ep.state('test',2451545.)[:3]
            self.assertAlmostEqual(np.linalg.norm(offset),distance,delta=1e-7)
            self.assertAlmostEqual(float(offset@incoming),0.,delta=5e-7)
        self.assertEqual(small_body_node('test',2451545.,ep,incoming)['center_distance_km'],10000.)
        for distance in (-1,0,float('nan'),float('inf')):
            with self.assertRaises(ValueError):small_body_node('test',2451545.,ep,incoming,distance)

    def test_finite_boundary_export_retains_retrograde_coast(self):
        start=jd('2030-01-01');end=start+40
        r=np.array([AU,0.,0.]);v=np.array([0.,-np.sqrt(MU_SUN/AU),0.])
        endpoint,expected=kepler(r,v,(end-start)*DAY)
        piece=solar_piece(start,end,r,endpoint,dict(r=r,v=v,start_jd=start,end_jd=end))
        np.testing.assert_allclose(piece['state'](start)[3:],v,atol=1e-8)
        np.testing.assert_allclose(piece['state'](end)[3:],expected,atol=1e-8)
        self.assertLess(piece['numerical_error_km'],.01)

    def test_export_retains_c3_floor_and_arrival_requirement(self):
        c=normalize(dict(min_c3=160,max_c3=170,arrival_date='2012-12-15',launch_start='2004-12-01',launch_end='2005-01-01'))
        q=dict(launch_c3_km2_s2=120,total_dsm_kms=0,arrival_vinf_kms=10,duration_years=8,flybys=[],dsms=[],dates_jd_tdb=[jd('2004-12-15'),jd('2014-01-01')])
        failures=requirement_violations(q,c)
        self.assertTrue(any('minimum' in s for s in failures))
        self.assertTrue(any('arrival-date' in s for s in failures))

if __name__=='__main__':unittest.main()
