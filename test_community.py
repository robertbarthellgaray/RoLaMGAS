"""Public science allowlists, opt-out and independently checked shared seeds."""
import bootstrap
import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import community as lib
from dynamics import Model
from mission_search import normalize,routes_for
from test_hard_c3_generation import CircularStates

class CommunityTests(unittest.TestCase):
    def parent(self,sequence='EJ'):
        c=normalize(dict(target='Jupiter' if sequence=='EJ' else 'Mars',sequences=[sequence],launch_start='2030-01-01',launch_end='2031-01-01',max_c3=1e9,max_arrival_vinf_kms=1000,max_dsm_kms=1000,max_single_dsm_kms=1000,max_years=100))
        route=routes_for(c)[0];ep=CircularStates();model=Model(route,c,ep);x=[.4,.5] if sequence=='EJ' else [.5,.4,.5,.51,.49,.5]
        q=model.evaluate(x,[v[0] for v in route['branch_options']]);q.update(status='passes_configured_patched_conic_screen',discovered_unix=time.time(),id='abcdef123456',username='PRIVATE',local_path='C:/Users/PRIVATE/secret',query='PRIVATE')
        return c,route,ep,q
    def test_public_allowlist_omits_identity_and_local_state(self):
        c,r,ep,q=self.parent();record=lib.public_record(q,c,r);raw=json.dumps(record)
        self.assertNotIn('PRIVATE',raw);self.assertNotIn('username',raw);self.assertNotIn('local_path',raw);self.assertNotIn('query',raw)
        self.assertEqual(record['body_ids'],['399','599']);self.assertIn('solved_at',record)
        q['id']='different device irrelevant';self.assertEqual(record['id'],lib.public_record(q,c,r)['id'])
    def test_public_c3_ceiling_does_not_change_local_search_metrics(self):
        c,r,ep,q=self.parent();q['launch_c3_km2_s2']=250.000001
        with patch.object(lib,'settings',return_value=dict(share_candidates=True,use_candidates=True,endpoint='https://example.test')),patch.object(lib,'exchange') as network:
            sync=lib.CommunitySync(c,[r]);sync.offer(q);sync.close();network.assert_not_called()
        self.assertEqual(q['launch_c3_km2_s2'],250.000001)
    def test_red_candidates_are_not_shared(self):
        c,r,ep,q=self.parent();q['periapsis_violation']=True;self.assertIsNone(lib.public_record(q,c,r))
    def test_low_c3_is_not_shared_even_if_legacy_record_says_pass(self):
        c,r,ep,q=self.parent()
        for energy in (0.,4.999999,float('nan')):
            q['launch_c3_km2_s2']=energy;self.assertIsNone(lib.public_record(q,c,r))
        q['launch_c3_km2_s2']=5.;self.assertIsNotNone(lib.public_record(q,c,r))
    def test_physical_dates_and_dsm_controls_remap_without_changing_arc(self):
        c,r,ep,q=self.parent('EdvM');record=lib.public_record(q,c,r)
        changed=dict(c,launch_jd=[c['launch_jd'][0]-10,c['launch_jd'][1]+10],dsm_velocity_box_kms=12.)
        model=Model(r,changed,ep);x,b=lib.record_variables(record,model);new=model.evaluate(x,b)
        np.testing.assert_allclose(new['dates_jd_tdb'],q['dates_jd_tdb'],atol=1e-9)
        self.assertAlmostEqual(new['launch_c3_km2_s2'],q['launch_c3_km2_s2'],places=6)
        np.testing.assert_allclose(new['dsms'][0]['delta_v_ecliptic_j2000_kms'],q['dsms'][0]['delta_v_ecliptic_j2000_kms'],atol=1e-9)
    def test_offline_starter_catalog_and_tampered_reported_c3(self):
        c,r,ep,q=self.parent();record=lib.public_record(q,c,r);record['metrics']['launch_c3_km2_s2']=0
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'community_seed_catalog.json').write_text(json.dumps(dict(candidates=[record])))
            pref=dict(share_candidates=False,use_candidates=True,endpoint='')
            with patch.object(lib,'RESOURCE_ROOT',Path(folder)),patch.object(lib,'settings',return_value=pref),patch.object(lib,'exchange') as network:
                result=lib.download_candidates(c,[r],ep);self.assertEqual(len(result['accepted']),1)
                self.assertGreater(result['accepted'][0]['launch_c3_km2_s2'],0)
                result=lib.download_candidates(dict(c,max_c3=q['launch_c3_km2_s2']-1),[r],ep)
                self.assertEqual(result['accepted'],[]);network.assert_not_called()
    def test_opt_out_prevents_even_queued_uploads(self):
        c,r,ep,q=self.parent()
        with patch.object(lib,'settings',return_value=dict(share_candidates=False,use_candidates=True,endpoint='https://example.test')),patch.object(lib,'exchange') as network:
            sync=lib.CommunitySync(c,[r]);sync.offer(q);sync.close();network.assert_not_called()
    def test_settings_are_enabled_by_default_but_no_endpoint_is_assumed(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(lib,'SETTINGS',Path(folder)/'settings.json'),patch.object(lib,'RESOURCE_ROOT',Path(folder)),patch.dict('os.environ',{},clear=True):
            self.assertTrue(lib.settings()['share_candidates']);self.assertFalse(lib.settings()['configured'])
            self.assertFalse(lib.save_settings(dict(share_candidates=False))['share_candidates'])
            self.assertFalse(lib.settings()['share_candidates'])
    def test_same_day_key_uses_tdb_calendar_midnight_and_preserves_body_order(self):
        c,r,ep,q=self.parent();a=lib.public_record(q,c,r)
        a['dates_jd_tdb']=[2460000.1,2461000.49]
        b=dict(a,dates_jd_tdb=[2460000.2,2461000.4],branches=[[0,False]])
        self.assertEqual(lib.encounter_key(a),lib.encounter_key(b))
        self.assertNotEqual(lib.encounter_key(a),lib.encounter_key(dict(b,dates_jd_tdb=[2460000.2,2461000.51])))
        self.assertNotEqual(lib.encounter_key(a),lib.encounter_key(dict(b,body_ids=['599','399'])))
    def test_same_day_duplicate_selection_retains_better_record_and_link_alias(self):
        c,r,ep,q=self.parent();a=lib.public_record(q,c,r)
        a.update(id='a',dates_jd_tdb=[2460000.1,2461000.1]);b=dict(a,id='b',dates_jd_tdb=[2460000.2,2461000.2],metrics=dict(a['metrics'],launch_c3_km2_s2=1.))
        winners,aliases=lib.unique_encounters([a,b]);self.assertEqual([v['id'] for v in winners],['b']);self.assertEqual(aliases,{'a':'b'})
        yellow=dict(b,id='c',classification='yellow');self.assertEqual(lib.unique_encounters([yellow,a])[0][0]['id'],'a')
    def test_repeat_sharing_is_bounded_by_encounter_days(self):
        c,r,ep,q=self.parent();q['launch_c3_km2_s2']=10.
        with patch.object(lib,'settings',return_value=dict(share_candidates=True,use_candidates=True,endpoint='https://example.test')),patch.object(lib,'exchange') as network:
            sync=lib.CommunitySync(c,[r]);sync.offer(q);sync.offer(dict(q,branches=[[0,False]]));sync.close()
            sent=[record for call in network.call_args_list for record in call.args[1]['candidates']]
            self.assertEqual(len(sent),1)
    def test_endpoint_validation(self):
        for url in ('http://external.example','https://name:secret@example.test','https://example.test?key=secret'):
            with self.assertRaises(ValueError):lib.endpoint_url(url)
        self.assertEqual(lib.endpoint_url('http://127.0.0.1:31311'),'http://127.0.0.1:31311')

if __name__=='__main__':unittest.main()
