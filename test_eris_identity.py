"""Regression cases captured from JPL and the user's Eris import failure."""
import bootstrap
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs,urlparse
import numpy as np
from horizons_targets import resolve,register_target,identity,satellite_parent,moon_model_notice,canonical_target,resolution_query
from ephemeris import parse_horizons

FIXTURES=Path(__file__).parent/'test_fixtures'

class ErisIdentityTests(unittest.TestCase):
    def setUp(self):
        self.lookup=json.loads((FIXTURES/'eris_lookup.json').read_text())
        self.bary=(FIXTURES/'eris_barycenter_vectors.txt').read_text()
        self.primary=(FIXTURES/'eris_primary_vectors.txt').read_text()

    def test_same_spk_solutions_have_distinct_selectable_queries(self):
        with patch('horizons_targets.request_json',return_value=self.lookup):result=resolve('Eris')
        self.assertTrue(result['ambiguous'])
        choices=[c['designation'] for c in result['choices']]
        self.assertEqual(len(choices),len(set(choices)))
        self.assertIn('SPK=20136199',choices);self.assertIn('SB=20136199',choices)
        self.assertIn('SPK=920136199',choices);self.assertIn('SPK=120136199',choices)

    def test_explicit_spk_uses_precomputed_barycenter_not_integrated_solution(self):
        with patch('horizons_targets.request_json',side_effect=[self.lookup,{'result':self.bary}]) as request:
            result=resolve('SPK=20136199','2015-11-18')
        self.assertEqual((result['id'],result['command'],result['kind']),('20136199','20136199','horizons_object'))
        self.assertEqual(parse_qs(urlparse(request.call_args_list[1].args[0]).query)['COMMAND'],["'20136199'"])
        times,states=parse_horizons(self.bary,result['name'])
        self.assertEqual(len(times),4);self.assertTrue(np.isfinite(states).all())

    def test_explicit_sb_preserves_current_integrated_solution_with_same_id(self):
        sbdb={'object':{'fullname':'136199 Eris (2003 UB313)','spkid':'20136199','des':'136199'},'orbit':{},'phys_par':[]}
        with patch('horizons_targets.request_json',side_effect=[self.lookup,sbdb]) as request:
            result=resolve('SB=20136199')
        self.assertEqual(parse_qs(urlparse(request.call_args_list[0].args[0]).query)['group'],['sb'])
        self.assertEqual((result['id'],result['command'],result['kind']),('20136199','136199;','small_body'))
        self.assertEqual(resolution_query(result),'SB=20136199')

    def test_primary_is_not_a_moon_but_dysnomia_still_is(self):
        with patch('horizons_targets.request_json',side_effect=[self.lookup,{'result':self.primary}]):result=resolve('SPK=920136199')
        self.assertEqual(result['kind'],'horizons_object');self.assertIsNone(moon_model_notice(result))
        self.assertNotIn('parent_body',result)
        times,states=parse_horizons(self.primary,result['name']);self.assertEqual(len(times),4)
        self.assertIsNone(satellite_parent(result))
        self.assertEqual(satellite_parent(dict(id='120136199',kind='horizons_object')),'Eris')
        self.assertEqual(satellite_parent(dict(id='220136108',kind='horizons_object')),'Haumea')
        self.assertIsNone(satellite_parent(dict(id='920136108',kind='horizons_object')))

    def test_legacy_primary_cache_is_repaired_and_can_be_used_as_target(self):
        old=dict(name='Eris (primary body)',id='920136199',command='920136199',kind='natural_satellite',parent_body='Eris',model_limitation='wrongly called a moon')
        from gui import App
        from mission_search import normalize
        with tempfile.TemporaryDirectory() as folder,patch('gui.HERE',Path(folder)),patch('gui.resolve',side_effect=AssertionError('Cached identity should work offline')):
            app=App();app.targets['spk=920136199']=old
            target=app.lookup('SPK=920136199','2030-01-01')
            self.assertNotIn('model_limitation',target);self.assertEqual(target['kind'],'horizons_object')
            saved=json.loads(app.targets_path.read_text());self.assertEqual(saved['spk=920136199']['kind'],'horizons_object')
            config=normalize(dict(target_object=target,sequences=['EJX']))
            self.assertEqual(config['target_object']['id'],'920136199')
        self.assertIsNone(moon_model_notice(old))
        self.assertEqual(old['kind'],'natural_satellite','Normalization must not mutate caller data')

    def test_portable_options_retain_integrated_solution_selection(self):
        from search_options import export_options,import_options
        target=dict(name='136199 Eris (2003 UB313)',id='20136199',command='136199;',kind='small_body',designation='136199')
        doc=export_options(dict(target_object=target,sequences=['EJX']))['document']
        imported=import_options(doc)['config']['target_object']
        self.assertEqual(imported['query'],'SB=20136199');self.assertEqual(imported['command'],'136199;')
        self.assertEqual(resolution_query(dict(target,kind='horizons_object',command='20136199')),'SPK=20136199')

    def test_vector_identity_is_still_strict(self):
        with patch('horizons_targets.request_json',side_effect=[self.lookup,{'result':self.primary}]):
            with self.assertRaisesRegex(ValueError,'identity differs'):resolve('SPK=20136199')
        register_target(dict(name='Eris (system barycenter)',id='20136199',command='20136199',kind='horizons_object'))
        with self.assertRaisesRegex(ValueError,'resolved target ID'):parse_horizons(self.primary,'Eris (system barycenter)')

    def test_legacy_import_can_try_integrated_solution_after_arrival_coverage_failure(self):
        from trajectory_transfer import confirm_record_target
        from ephemeris import jd
        from unittest.mock import Mock
        descriptor=dict(name='Eris',id='20136199',command='20136199',kind='horizons_object')
        record=dict(body_ids=['399','20136199'],dates_jd_tdb=[jd('2015-11-18'),jd('2051-04-01')])
        current=dict(name='136199 Eris (2003 UB313)',id='20136199',command='136199;',kind='small_body')
        lookup=Mock(side_effect=[ValueError('No ephemeris for target after 2030'),current])
        confirmed,recovery=confirm_record_target(descriptor,record,lookup,'2015-11-18')
        self.assertEqual(confirmed,current);self.assertIn('unchanged numerical',recovery['acceptance'])
        self.assertEqual(lookup.call_args_list[0].args,('SPK=20136199','2051-04-01T00:00:00'))
        self.assertEqual(lookup.call_args_list[1].args,('SB=20136199','2015-11-18'))
        for error in (ValueError('Identity mismatch'),RuntimeError('Certificate verification failed')):
            lookup=Mock(side_effect=error)
            with self.assertRaises(type(error)):confirm_record_target(descriptor,record,lookup,'2015-11-18')
            self.assertEqual(lookup.call_count,1,'Unrelated failures must not change selected solution')

    def test_same_id_different_ephemeris_solutions_do_not_share_cache_tables(self):
        from ephemeris import save_table,Ephemerides,DAY,JD0
        integrated=(FIXTURES/'eris_integrated_vectors.txt').read_text()
        bary=dict(name='Eris (system barycenter)',id='20136199',command='20136199',kind='horizons_object')
        current=dict(name='136199 Eris (2003 UB313)',id='20136199',command='136199;',kind='small_body',designation='136199')
        register_target(bary);t,_=parse_horizons(self.bary,bary['name']);start=JD0+t[0]/DAY;end=JD0+t[-1]/DAY
        with tempfile.TemporaryDirectory() as folder:
            save_table(folder,bary['name'],self.bary,'precomputed fixture')
            register_target(current);save_table(folder,current['name'],integrated,'integrated fixture')
            sb=Ephemerides(folder,[current['name']],start,end,1)
            self.assertTrue(all(m['target_identity']['kind']=='small_body' for m in sb.manifest[current['name']]))
            register_target(bary);mb=Ephemerides(folder,[bary['name']],start,end,1)
            self.assertTrue(all(m['target_identity']['kind']=='horizons_object' for m in mb.manifest[bary['name']]))
            self.assertGreater(np.linalg.norm(sb.state(current['name'],start)[:3]-mb.state(bary['name'],start)[:3]),1.)

if __name__=='__main__':unittest.main()
