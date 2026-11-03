"""One gravity source per patched-conic arc, with explicit residual/burn budgets."""
import bootstrap
import unittest
from unittest.mock import patch
import numpy as np
import integrate_export as ex
from dynamics import lambert
from ephemeris import AU,BODIES,DAY,JD0,MU_SUN

class LinearPlanet:
    def state(self,body,date):return np.array([AU,30*(date-JD0)*DAY,0.,0.,30.,0.])

class ExportForceModelTests(unittest.TestCase):
    def test_soi_hyperbola_uses_only_encounter_planet_mu(self):
        original=ex.two_body_rhs;used=[]
        def tracked(t,y,mu):used.append(mu);return original(t,y,mu)
        ep=LinearPlanet();u=np.array([8.,0.,0.]);mu=BODIES['Earth'][1]
        with patch('integrate_export.two_body_rhs',side_effect=tracked):
            node=ex.planet_pieces('Earth',JD0,ep,uin=u,uout=None,altitude=200,terminal=True)
        self.assertEqual(set(used),{mu})
        piece=node['pieces'][0];self.assertEqual(piece['force_center'],'Earth')
        for date in np.linspace(piece['start'],piece['end'],11):
            relative=piece['state'](date)-ep.state('Earth',date)
            distance=np.linalg.norm(relative[:3])
            self.assertLessEqual(distance,node['soi']+.01)
            self.assertGreaterEqual(distance,node['rp']-.01)
            self.assertAlmostEqual(relative[3:]@relative[3:]/2-mu/distance,32.,places=7)
        self.assertAlmostEqual(np.linalg.norm(piece['state'](piece['start'])[:3]-ep.state('Earth',piece['start'])[:3]),node['soi'],delta=.01)

    def test_heliocentric_continuation_uses_only_sun_mu(self):
        original=ex.two_body_rhs;used=[]
        def tracked(t,y,mu):used.append(mu);return original(t,y,mu)
        initial=np.array([AU,0.,0.,0.,np.sqrt(MU_SUN/AU),0.])
        with patch('integrate_export.two_body_rhs',side_effect=tracked):
            piece=ex.solar_continuation(JD0,JD0+10,initial)
        self.assertEqual(set(used),{MU_SUN});self.assertEqual(piece['force_center'],'Sun')
        self.assertLess(piece['numerical_error_km'],.01)

    def test_speed_residual_is_not_a_fabricated_burn(self):
        q=dict(total_dsm_kms=0.,dsms=[],flybys=[dict(speed_mismatch_mps=2500.,passes_turn_screen=True)])
        burns=[dict(kind='launch_injection_from_200_km',magnitude_kms=4.),
               dict(kind='flyby_speed_match_burn',magnitude_kms=.2),
               dict(kind='finite_patch_junction',magnitude_kms=1.5),
               dict(kind='retargeted_DSM',magnitude_kms=.1)]
        b=ex.export_budget_breakdown(q,burns)
        self.assertFalse(b['candidate_maneuver_budget_complete']);self.assertEqual(b['unresolved_flyby_count'],1)
        self.assertEqual(b['unresolved_speed_mismatch_total_mps'],2500.)
        self.assertFalse(b['unresolved_speed_mismatch_is_delta_v'])
        self.assertAlmostEqual(b['exported_total_onboard_kms'],1.8)
        self.assertEqual(b['exported_additional_periapsis_speed_match_kms'],.2)
        self.assertEqual(b['exported_finite_soi_boundary_junction_kms'],1.5)

    def test_only_terminal_planet_requires_extended_position_download(self):
        class Curve:
            x=np.array([0.,10*DAY])
        class Ep:
            splines={'Earth':Curve(),'Jupiter':Curve()};manifest={'Earth':[],'Jupiter':[]}
        class Extended:
            splines={'Jupiter':Curve()};manifest={'Jupiter':['cached']}
        with patch('integrate_export.Ephemerides',side_effect=[ValueError('missing'),Extended()]),patch('integrate_export.fetch') as fetch:
            ex.extend_planet_ephemerides(Ep(),dict(cache='unused',max_ephemeris_step_days=1.),JD0,JD0+20,lambda text:None,bodies=['Jupiter'])
        self.assertTrue(fetch.called)
        self.assertEqual({call.args[1] for call in fetch.call_args_list},{'Jupiter'})

    def test_multirevolution_branch_minimizes_actual_boundary_jumps(self):
        r0=np.array([AU,0.,0.]);r1=AU*np.array([.5,np.sqrt(.75),0.]);days=600.
        va,vb=lambert(r0,r1,days,(1,True))
        other_a,other_b=lambert(r0,r1,days,(1,False))
        self.assertGreater(np.linalg.norm(va-other_a),.1)
        reference=dict(start_jd=JD0,end_jd=JD0+days,r=r0.tolist(),v=va.tolist())
        piece=ex.solar_piece(JD0,JD0+days,r0,r1,reference,True,boundary_velocities=(other_a,other_b))
        np.testing.assert_allclose(piece['state'](JD0)[3:],other_a,atol=1e-8)
        self.assertLess(piece['boundary_selection_delta_v_kms'],1e-7)

if __name__=='__main__':unittest.main()
