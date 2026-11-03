"""Return branches from zero-GM point targets retain cruise and charge a real impulse."""
import bootstrap
import unittest
from unittest.mock import patch
import numpy as np
from ephemeris import AU,DAY,JD0,MU_SUN
from mission_search import normalize,routes_for,get_ephemerides
from dynamics import Model
from append_flyby import extension_request,return_root_seeds

TARGET=dict(name='Return target (2030 AA)',id='54321010',command='DES=2030 AA;',kind='small_body',designation='2030 AA')
class States:
    def state(self,body,date):
        radius=AU*(1 if body=='Earth' else 1.7)
        rate=np.sqrt(MU_SUN/radius**3);angle=.5+(date-JD0)*DAY*rate
        return np.array([radius*np.cos(angle),radius*np.sin(angle),0.,-radius*rate*np.sin(angle),radius*rate*np.cos(angle),0.])

class MinorBodyReturnTests(unittest.TestCase):
    def parent(self,dsm=False):
        c=normalize(dict(target_object=TARGET,sequences=['EdvX' if dsm else 'EX'],launch_start='2030-01-01',launch_end='2031-01-01',custom_leg_days=[100,300],max_c3=1e5,max_arrival_vinf_kms=300,max_dsm_kms=1000,max_single_dsm_kms=1000,max_years=30))
        route=routes_for(c)[0];x=[.4,.5]+([.5,.501,.499,.5] if dsm else [])
        q=Model(route,c,States()).evaluate(x,[[0,True]])
        q.update(id='0123456789ab',status='passes_configured_patched_conic_screen')
        return c,route,q

    def test_return_keeps_prefix_exactly_fixed_and_charges_full_turnaround(self):
        c,r,q=self.parent();request=extension_request(c,r,q,'source','Earth',1,120,900)
        c=normalize(request);model=Model(routes_for(c)[0],c,States());x=np.asarray(request['append_flyby']['seed_x']);x[:2]=[.99,.01]
        result=model.evaluate(x,[[0,True],[0,True]])
        self.assertEqual(result['dates_jd_tdb'][:2],q['dates_jd_tdb'])
        self.assertEqual(result['segments'][:len(q['segments'])],q['segments'])
        self.assertEqual(result['launch_c3_km2_s2'],q['launch_c3_km2_s2'])
        self.assertEqual(result['flybys'],[])
        self.assertEqual(result['dsms'],q['dsms'])
        self.assertEqual(len(result['event_burns']),1)
        burn=result['event_burns'][0];self.assertEqual(burn['kind'],'target_turnaround')
        vector=np.asarray(result['departure_velocities_kms'][1])-np.asarray(q['arrival_velocities_kms'][-1])
        np.testing.assert_allclose(burn['delta_v_ecliptic_j2000_kms'],vector,atol=1e-12)
        self.assertAlmostEqual(result['total_dsm_kms'],float(np.linalg.norm(vector)),places=10)
        self.assertAlmostEqual(result['max_single_dsm_kms'],float(np.linalg.norm(vector)),places=10)
        self.assertTrue(result['budget_complete'])
        self.assertTrue(model.accepted(result))
        model.config['max_single_dsm_kms']=burn['magnitude_kms']/2
        self.assertFalse(model.accepted(result))
        self.assertEqual(return_root_seeds(model,[[0,True],[0,True]]),[])

    def test_added_leg_dsm_keeps_original_burn_controls_and_budget(self):
        c,r,q=self.parent(True);request=extension_request(c,r,q,'source','Earth',1,120,900,True)
        c=normalize(request);model=Model(routes_for(c)[0],c,States());x=np.asarray(request['append_flyby']['seed_x']);x[-3:]=[.501,.499,.5]
        result=model.evaluate(x,[[0,True],[0,True]])
        self.assertEqual(result['dsms'][0],q['dsms'][0])
        self.assertEqual(len(result['dsms']),2)
        total=sum(b['magnitude_kms'] for b in result['dsms']+result['event_burns'])
        self.assertAlmostEqual(result['total_dsm_kms'],total,places=10)
        self.assertEqual(c['search_objective'],'dsm')
        self.assertEqual(c['append_flyby']['original_target_object']['id'],TARGET['id'])

    def test_a_later_extension_keeps_the_previously_charged_point_turnaround(self):
        c,r,q=self.parent();c=normalize(extension_request(c,r,q,'source','Earth',1,120,900))
        route=routes_for(c)[0]
        first=Model(route,c,States()).evaluate(c['append_flyby']['seed_x'],[[0,True],[0,True]])
        first.update(id='abcdef012345',status='near_miss_not_accepted')
        later=normalize(extension_request(c,route,first,'return','Earth',1,120,900))
        result=Model(routes_for(later)[0],later,States()).evaluate(later['append_flyby']['seed_x'],[[0,True],[0,True],[0,True]])
        self.assertEqual(result['event_burns'],first['event_burns'])
        self.assertEqual(result['turnaround_delta_v_kms'],first['turnaround_delta_v_kms'])
        self.assertEqual(result['segments'][:len(first['segments'])],first['segments'])
        self.assertEqual(later['append_flyby']['original_target_object']['id'],TARGET['id'])

    def test_workers_register_original_target_even_when_new_destination_is_earth(self):
        c,r,q=self.parent();c=normalize(extension_request(c,r,q,'source','Earth',1,120,900))
        from horizons_targets import TARGETS,identity
        TARGETS.pop(TARGET['name'],None)
        with patch('mission_search.Ephemerides',return_value='loaded') as loader:
            self.assertEqual(get_ephemerides(c,routes_for(c)),'loaded')
        self.assertEqual(identity(TARGET['name'])['id'],TARGET['id'])
        self.assertIn(TARGET['name'],loader.call_args.args[1])

    def test_missing_identity_is_rejected_without_inventing_a_target(self):
        c,r,q=self.parent();c['target_object']=None
        with self.assertRaisesRegex(ValueError,'confirmed original Horizons identity'):
            extension_request(c,r,q,'source','Earth',1,120,900)

if __name__=='__main__':unittest.main()
