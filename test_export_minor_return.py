"""A geometric asteroid visit followed by a physical, explicitly budgeted return burn."""
import bootstrap
import csv,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from dynamics import lambert
from ephemeris import AU,DAY,JD0,MU_SUN,BODIES
import integrate_export as ex

class CircularTargets:
    class Coverage:
        x=np.array([-10*DAY,1000*DAY])
    def __init__(self):
        self.splines={'Earth':self.Coverage(),'Test asteroid':self.Coverage()}
        self.manifest={'Earth':[],'Test asteroid':[]}
    def state(self,body,date):
        radius=AU*(1 if body=='Earth' else 1.3)
        n=np.sqrt(MU_SUN/radius**3);a=(date-JD0)*DAY*n+(0 if body=='Earth' else .9)
        return np.array([radius*np.cos(a),radius*np.sin(a),0.,-radius*n*np.sin(a),radius*n*np.cos(a),0.])

def return_candidate(ep):
    bodies=['Earth','Test asteroid','Earth'];dates=[JD0,JD0+200,JD0+500]
    states=[ep.state(body,date) for body,date in zip(bodies,dates)]
    va,at=lambert(states[0][:3],states[1][:3],200,(0,True))
    after,vb=lambert(states[1][:3],states[2][:3],300,(0,True));turn=after-at
    launch=va-states[0][3:];arrival=vb-states[2][3:]
    return dict(id='123456abcdef',status='passes_configured_patched_conic_screen',sequence='EXE',bodies=bodies,
        dates_jd_tdb=dates,launch_c3_km2_s2=float(launch@launch),launch_vinf_vector_kms=launch.tolist(),
        arrival_vinf_vector_kms=arrival.tolist(),arrival_vinf_kms=float(np.linalg.norm(arrival)),duration_years=500/365.25,
        departure_velocities_kms=[va.tolist(),after.tolist()],arrival_velocities_kms=[at.tolist(),vb.tolist()],
        flybys=[],dsms=[],total_dsm_kms=float(np.linalg.norm(turn)),cruise_dsm_kms=0.,turnaround_delta_v_kms=float(np.linalg.norm(turn)),
        event_burns=[dict(kind='target_turnaround',event_index=1,body=bodies[1],julian_date_tdb=dates[1],magnitude_kms=float(np.linalg.norm(turn)),delta_v_ecliptic_j2000_kms=turn.tolist())],
        branches=[[0,True],[0,True]],
        events=[dict(body=b,julian_date_tdb=t,planet_state_km_kms=s.tolist()) for b,t,s in zip(bodies,dates,states)],
        segments=[dict(start_jd=dates[0],end_jd=dates[1],r=states[0][:3].tolist(),v=va.tolist()),
                  dict(start_jd=dates[1],end_jd=dates[2],r=states[1][:3].tolist(),v=after.tolist())])

class MinorReturnExportTests(unittest.TestCase):
    def test_intermediate_offset_uses_that_events_incoming_velocity(self):
        ep=CircularTargets();q=return_candidate(ep);node=ex.minor_body_event_node(q,1,ep,10000.)
        original=ep.state('Test asteroid',q['dates_jd_tdb'][1]);offset=node['target_state'][:3]-original[:3]
        incoming=np.array(q['arrival_velocities_kms'][0])-original[3:]
        self.assertAlmostEqual(float(offset@incoming),0.,delta=1e-5)
        self.assertAlmostEqual(float(np.linalg.norm(offset)),10000.,delta=1e-6)
        _,before=ex.node_coast_boundary(node,False);_,after=ex.node_coast_boundary(node,True)
        np.testing.assert_allclose(before[:3],after[:3])
        np.testing.assert_allclose(before[3:],q['arrival_velocities_kms'][0])
        np.testing.assert_allclose(after[3:],q['departure_velocities_kms'][1])

    def test_solar_return_is_continuous_and_has_no_asteroid_gravity(self):
        ep=CircularTargets();q=return_candidate(ep)
        c=dict(powered_flybys=False,target_object=None,cache='unused',max_ephemeris_step_days=1.,minimum_altitude_km={'Earth':200},
            min_c3=6.25,effective_min_c3=6.25,max_c3=10000.,max_dsm_kms=100.,max_arrival_vinf_kms=100.,max_years=20.,
            max_single_dsm_kms=100.,max_powered_flyby_kms=100.,vinf_tolerance_mps=20.)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'candidate.json';path.write_text(json.dumps(q));output=Path(temp)/'export'
            with patch('integrate_export.normalize',return_value=c),patch('integrate_export.routes_for',return_value=[]),patch('integrate_export.get_ephemerides',return_value=ep),patch('integrate_export.Ephemerides',side_effect=ValueError('No other cached bodies')):
                report=ex.export(path,{},output)
            self.assertTrue(report['numerical_validation_passed'])
            self.assertLess(report['maximum_position_join_residual_km'],.01)
            self.assertFalse(report['nbody_propagation'])
            self.assertEqual({s['center'] for s in report['force_segments']},{'Sun','Earth'})
            turns=report['exported_target_turnaround_burns'];self.assertEqual(len(turns),1)
            self.assertEqual(turns[0]['body'],'Test asteroid')
            self.assertAlmostEqual(turns[0]['magnitude_kms'],np.linalg.norm([turns[0][k] for k in ('dx_kms','dy_kms','dz_kms')]),places=12)
            budget=report['maneuver_budget_breakdown']
            self.assertEqual(budget['exported_cruise_dsm_kms'],0.)
            self.assertGreater(budget['exported_target_turnaround_kms'],0.)
            self.assertAlmostEqual(budget['exported_total_onboard_kms'],budget['exported_target_turnaround_kms']+budget['exported_finite_soi_boundary_junction_kms'],places=10)
            with (output/'burns.csv').open(encoding='utf-8') as stream:rows=list(csv.DictReader(stream))
            self.assertEqual(sum(row['kind']=='target_turnaround' for row in rows),1)
            with (output/'encounters.csv').open(encoding='utf-8') as stream:encounter=list(csv.DictReader(stream))[1]
            self.assertEqual(float(encounter['target_center_distance_km']),10000.)

if __name__=='__main__':unittest.main()
