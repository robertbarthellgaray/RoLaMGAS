"""Finite endpoint changes must not add an orbit or conceal correction costs."""
import bootstrap
import unittest
import numpy as np
from dynamics import kepler,lambert
from ephemeris import AU,DAY,JD0,MU_SUN,BODIES
from integrate_export import solar_piece,revolutions,planet_pieces,node_coast_boundary,validate_patch_epoch_shift
from finite_targeting import match_finite_patches,retarget_node


class CircularPlanets:
    def state(self,body,date):
        radius=AU*(1 if body=='Earth' else .723)
        n=np.sqrt(MU_SUN/radius**3);a=(date-JD0)*DAY*n+(0 if body=='Earth' else 1.2)
        return np.array([radius*np.cos(a),radius*np.sin(a),0.,-radius*n*np.sin(a),radius*n*np.cos(a),0.])


class FiniteTargetingTests(unittest.TestCase):
    def test_finite_endpoints_crossing_full_turn_do_not_add_an_orbit(self):
        r=np.array([AU,0.,0.]);v=np.array([0.,np.sqrt(MU_SUN/AU),0.])
        period=2*np.pi*np.sqrt(AU**3/MU_SUN)/DAY
        reference=dict(r=r.tolist(),v=v.tolist(),start_jd=JD0,end_jd=JD0+2*period+.01)
        self.assertEqual(revolutions(reference),2)
        start=JD0+2;end=reference['end_jd']-2
        r0,v0=kepler(r,v,(start-JD0)*DAY);r1,v1=kepler(r,v,(end-JD0)*DAY)
        piece=solar_piece(start,end,r0,r1,reference,boundary_velocities=(v0,v1))
        self.assertEqual(piece['revolutions'],1)  # Same physical orbit, different Lambert index.
        np.testing.assert_allclose(piece['state'](start)[3:],v0,atol=1e-8)
        np.testing.assert_allclose(piece['state'](end)[3:],v1,atol=1e-8)
        self.assertLess(piece['numerical_error_km'],.1)

    def test_local_match_improves_real_budget_and_keeps_fixed_epochs_and_altitudes(self):
        ep=CircularPlanets();dates=[JD0,JD0+160];a=ep.state('Earth',dates[0]);b=ep.state('Venus',dates[1])
        va,vb=lambert(a[:3],b[:3],160,(0,True));u=va-a[3:];incoming=vb-b[3:]
        nodes=[planet_pieces('Earth',dates[0],ep,uout=u,departure=True),
               planet_pieces('Venus',dates[1],ep,uin=incoming,altitude=300,terminal=True)]
        candidate=dict(dsms=[],segments=[dict(r=a[:3].tolist(),v=va.tolist(),start_jd=dates[0],end_jd=dates[1])],branches=[[0,True]])
        config=dict(min_c3=5.,max_c3=float(u@u)*1.2,minimum_altitude_km={'Earth':200,'Venus':300})
        new,points,report=match_finite_patches(nodes,candidate,config,ep,max_epoch_shift_days=0.)
        self.assertTrue(report['applied']);self.assertEqual(points,{})
        self.assertLess(report['matched_cruise_delta_v_kms'],report['baseline_cruise_delta_v_kms'])
        self.assertEqual([n['date'] for n in new],dates)
        self.assertAlmostEqual(new[0]['altitude'],200.,places=6)
        self.assertAlmostEqual(new[1]['altitude'],300.,places=6)
        self.assertEqual(nodes[0]['date'],dates[0]);self.assertEqual(nodes[1]['date'],dates[1])
        mu=BODIES['Earth'][1];energy=new[0]['peri_out_velocity']@new[0]['peri_out_velocity']-2*mu/new[0]['rp']
        self.assertGreaterEqual(energy,5.);self.assertLessEqual(energy,config['max_c3'])
        self.assertTrue(all(p['force_center']=='Earth' for p in new[0]['pieces']))
        t,state=node_coast_boundary(new[0],True)
        self.assertAlmostEqual(np.linalg.norm(state[:3]-ep.state('Earth',t)[:3]),new[0]['soi'],delta=.01)

    def test_large_date_adjustments_preserve_all_completed_reference_orbits(self):
        r=np.array([AU,0.,0.]);v=np.array([0.,np.sqrt(MU_SUN/AU),0.])
        period=2*np.pi*np.sqrt(AU**3/MU_SUN)/DAY
        reference=dict(r=r.tolist(),v=v.tolist(),start_jd=JD0,end_jd=JD0+period)
        end=JD0+4*period-1.;r1,v1=kepler(r,v,(end-JD0)*DAY)
        piece=solar_piece(JD0,end,r,r1,reference,boundary_velocities=(v,v1))
        self.assertEqual(piece['revolutions'],3)
        np.testing.assert_allclose(piece['state'](JD0)[3:],v,atol=1e-8)
        np.testing.assert_allclose(piece['state'](end)[3:],v1,atol=1e-8)

    def test_analytic_fit_and_numerically_integrated_hyperbola_match(self):
        ep=CircularPlanets();node=planet_pieces('Earth',JD0,ep,uout=np.array([8.,1.,.3]),departure=True)
        analytic=retarget_node(node,ep,node['peri_position'],node['peri_in_velocity'],node['peri_out_velocity'],JD0)
        for t in np.linspace(node['pieces'][0]['start'],node['pieces'][0]['end'],5):
            np.testing.assert_allclose(analytic['pieces'][0]['state'](t),node['pieces'][0]['state'](t),atol=1e-4)
        for invalid in [-1,366,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):validate_patch_epoch_shift(invalid)
        self.assertEqual(validate_patch_epoch_shift(0),0)
        self.assertEqual(validate_patch_epoch_shift(30),30)
        self.assertEqual(validate_patch_epoch_shift(365.25),365.25)


if __name__=='__main__':unittest.main()
