"""Following one resolved minor body with another preserves the cruise and budgets."""
import bootstrap
import copy,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch,Mock
import numpy as np
import test_minor_body_return as minor
TARGET=minor.TARGET
from append_flyby import extension_request,original_target_descriptors
from mission_search import normalize,routes_for,get_ephemerides
from dynamics import Model
from gui import App

NEXT=dict(name='Follow-on target (2031 BB)',id='54321011',command='DES=2031 BB;',kind='small_body',designation='2031 BB')
class FollowOnStates(minor.States):
    def state(self,body,date):
        if body==NEXT['name']:
            from ephemeris import AU,DAY,JD0,MU_SUN
            radius=2.1*AU;n=np.sqrt(MU_SUN/radius**3);a=.8+(date-JD0)*DAY*n
            return np.array([radius*np.cos(a),radius*np.sin(a),0.,-radius*n*np.sin(a),radius*n*np.cos(a),0.])
        return super().state(body,date)

class FollowOnTargetTests(unittest.TestCase):
    def parent(self):return minor.MinorBodyReturnTests().parent()
    def follow_on(self):
        c,r,q=self.parent();request=extension_request(c,r,q,'source',minimum_days=120,maximum_days=1500,target_object=NEXT)
        c=normalize(request);route=routes_for(c)[0];result=Model(route,c,FollowOnStates()).evaluate(c['append_flyby']['seed_x'],route['branch_options'][0]+[[0,True]])
        return c,route,q,result
    def test_resolved_second_target_preserves_prefix_and_charges_turnaround(self):
        c,r,q,result=self.follow_on()
        self.assertEqual(c['target_object']['id'],NEXT['id']);self.assertEqual(r['bodies'],['Earth',TARGET['name'],NEXT['name']])
        self.assertEqual(result['segments'][:len(q['segments'])],q['segments']);self.assertEqual(result['dates_jd_tdb'][:2],q['dates_jd_tdb'])
        self.assertEqual(result['launch_c3_km2_s2'],q['launch_c3_km2_s2']);self.assertEqual(len(result['event_burns']),1)
        expected=np.asarray(result['departure_velocities_kms'][1])-np.asarray(q['arrival_velocities_kms'][-1])
        self.assertAlmostEqual(result['total_dsm_kms'],np.linalg.norm(expected),places=10)
        self.assertEqual(result['flybys'],[])
    def test_another_extension_retains_both_original_identities_and_burns(self):
        c,r,q,first=self.follow_on();first.update(id='abcdef123456',status='near_miss_not_accepted')
        c=normalize(extension_request(c,r,first,'follow','Earth',minimum_days=120,maximum_days=1500))
        route=routes_for(c)[0];result=Model(route,c,FollowOnStates()).evaluate(c['append_flyby']['seed_x'],[b[0] for b in route['branch_options']])
        self.assertEqual({d['id'] for d in original_target_descriptors(c)},{TARGET['id'],NEXT['id']})
        self.assertEqual(result['segments'][:len(first['segments'])],first['segments']);self.assertEqual(len(result['event_burns']),2)
        self.assertEqual(result['event_burns'][0],first['event_burns'][0])
    def test_worker_registers_all_custom_targets(self):
        c,r,_,_=self.follow_on()
        with patch('mission_search.Ephemerides',return_value='sentinel'):
            self.assertEqual(get_ephemerides(c,[r]),'sentinel')
        from horizons_targets import identity
        self.assertEqual(identity(TARGET['name'])['id'],TARGET['id']);self.assertEqual(identity(NEXT['name'])['id'],NEXT['id'])
    def test_missing_second_frozen_identity_is_rejected(self):
        c,r,_,first=self.follow_on();first.update(id='abcdef123456',status='near_miss_not_accepted')
        request=extension_request(c,r,first,'follow','Earth',minimum_days=120,maximum_days=1500)
        request['append_flyby']['original_target_objects']=[TARGET];request['append_flyby']['original_target_object']=TARGET
        with self.assertRaisesRegex(ValueError,'original resolved Horizons'):normalize(request)
    def test_follow_on_target_requires_local_confirmation(self):
        from test_return_earth_backend import ReturnEarthBackendTests
        with tempfile.TemporaryDirectory() as folder:
            app,_,saved_config=ReturnEarthBackendTests().saved(folder);app.targets={'old':saved_config['target_object']}
            with self.assertRaisesRegex(ValueError,'follow-on Horizons'):
                app.append_candidate('saved','abcdef123456',minimum_days=120,maximum_days=900,target_object=NEXT)
            app.start.assert_not_called()
            app.targets['next']=NEXT
            with patch('append_flyby.extension_request',return_value={'confirmed':'yes'}) as extend:
                app.append_candidate('saved','abcdef123456',minimum_days=120,maximum_days=900,target_object=dict(NEXT,command='untrusted'))
                self.assertEqual(extend.call_args.kwargs['target_object'],NEXT)
                app.start.assert_called_once_with({'confirmed':'yes'})
    def test_two_minor_body_export_is_continuous_and_has_no_fabricated_target_gravity(self):
        import integrate_export as ex
        c,r,_,q=self.follow_on();q.update(id='abcdef123456',status='near_miss_not_accepted')
        ep=FollowOnStates();ep.manifest={b:[] for b in r['bodies']};ep.splines={'Earth':type('Coverage',(),{'x':np.array([-1e12,1e12])})()}
        with tempfile.TemporaryDirectory() as temp:
            candidate=Path(temp)/'candidate.json';candidate.write_text(json.dumps(q))
            with patch('integrate_export.get_ephemerides',return_value=ep),patch('integrate_export.Ephemerides',side_effect=ValueError('No extra cached bodies')):
                report=ex.export(candidate,c,Path(temp)/'export',arrival_altitude_km=10000.)
            self.assertTrue(report['numerical_validation_passed'])
            self.assertGreater(report['turnaround_delta_v_kms'] if 'turnaround_delta_v_kms' in report else report['total_onboard_delta_v_kms'],0.)
            self.assertEqual({row['center'] for row in report['force_segments']},{'Sun','Earth'})
            self.assertEqual(report['arrival_state']['body'],NEXT['name'])

    def test_profile_boundary_defaults_respect_explicit_overrides(self):
        self.assertEqual(normalize(dict(mission_profile='flyby'))['c3_seed_boundary'],'maximum')
        self.assertEqual(normalize(dict(mission_profile='orbiter'))['c3_seed_boundary'],'minimum')
        self.assertEqual(normalize(dict(mission_profile='flyby',c3_seed_boundary='minimum'))['c3_seed_boundary'],'minimum')

if __name__=='__main__':unittest.main()
