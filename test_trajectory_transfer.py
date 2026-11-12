"""Selected website solutions are re-evaluated, never replaced by an optimization."""
import bootstrap
import json,shutil,subprocess,tempfile,threading,time,unittest
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from trajectory_transfer import checked_record,materialize,pin_record_epochs
from search_options import import_options
from mission_search import normalize,routes_for
from test_full_chain_seeds import EventEphemerides

ROOT=Path(__file__).resolve().parent

def documents():
    script="""import fs from 'node:fs';import {transferDocument} from './docs/desktop_transfer.js';
    const list=JSON.parse(fs.readFileSync('./docs/data/index.json','utf8')).cases;
    console.log(JSON.stringify(list.map(row=>{const c=JSON.parse(fs.readFileSync('./docs/data/cases/'+row.id+'.json','utf8'));if(c.desktop_record_url)c.desktop_record=JSON.parse(fs.readFileSync('./docs/'+c.desktop_record_url,'utf8'));return transferDocument(c);})));"""
    result=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',check=True)
    return json.loads(result.stdout)

class WebsiteTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('node'):raise unittest.SkipTest('Node is used to test actual browser package generation')
        cls.documents=documents()
        cls.document=next(d for d in cls.documents if d['source_candidate_id']=='4d76acaf1f6f')
    def test_all_curated_downloads_are_valid_portable_options(self):
        expected=json.loads((ROOT/'docs/data/index.json').read_text(encoding='utf-8'))['cases']
        self.assertEqual(len(self.documents),len(expected));self.assertGreaterEqual(len(expected),94)
        for d in self.documents:
            with self.subTest(id=d['source_candidate_id']):
                result=import_options(d);self.assertEqual(len(result['config']['sequences']),1)
                if d.get('trajectory'):checked_record(d['trajectory'])
    def test_reproduces_selected_chain_without_search_or_cost_refinement(self):
        c=normalize(import_options(self.document)['config']);route=routes_for(c)[0]
        with patch('scipy.optimize.least_squares',side_effect=AssertionError('No optimizer during import')),patch('mission_search.run',side_effect=AssertionError('No new search')):
            q=materialize(self.document['trajectory'],c,route,EventEphemerides())
        self.assertAlmostEqual(q['launch_c3_km2_s2'],6.25,places=6)
        self.assertAlmostEqual(q['total_dsm_kms'],.4939246300633,places=5)
        self.assertFalse(q['import_verification']['optimization_performed'])
        self.assertLess(q['import_verification']['maximum_coast_velocity_difference_kms'],.00001)
        self.assertEqual(len(q['dsms']),1);self.assertEqual(len(q['bodies']),6)
    def test_rejects_changed_saved_states_instead_of_substituting_a_trajectory(self):
        c=normalize(import_options(self.document)['config']);r=deepcopy(self.document['trajectory']);r['segments'][0]['v'][0]+=.1
        with self.assertRaisesRegex(ValueError,'No replacement trajectory'):materialize(r,c,routes_for(c)[0],EventEphemerides())
    def test_selected_numeric_julian_dates_survive_browser_millisecond_rounding(self):
        d=next(d for d in self.documents if d['source_candidate_id']=='c16155480c4d')
        from datetime import datetime
        legacy=deepcopy(d)
        legacy['settings']['event_windows']=[[datetime.fromisoformat(a).isoformat(timespec='milliseconds'),datetime.fromisoformat(b).isoformat(timespec='milliseconds')] for a,b in d['settings']['event_windows']]
        c=normalize(import_options(legacy)['config']);exact=d['trajectory']['dates_jd_tdb']
        self.assertTrue(any(a!=t for (a,b),t in zip(c['event_windows_jd'],exact)))
        pinned=pin_record_epochs(c,d['trajectory']);again=normalize(pinned)
        self.assertEqual(again['event_windows_jd'],[[t,t] for t in exact])
        self.assertEqual(normalize(import_options(d)['config'])['event_windows_jd'],[[t,t] for t in exact])
        changed=deepcopy(d['trajectory']);changed['dates_jd_tdb'][1]+=.1
        with self.assertRaisesRegex(ValueError,'outside'):pin_record_epochs(c,changed)

    def test_malformed_numeric_state_and_duplicate_burns_are_rejected(self):
        original=self.document['trajectory']
        for alter in (lambda r:r['dates_jd_tdb'].__setitem__(0,float('nan')),lambda r:r['segments'][0].__setitem__('v',[float('inf'),0,0]),lambda r:r['branches'][0].__setitem__(0,'2'),lambda r:r['dsm_controls'].append(r['dsm_controls'][0])):
            r=deepcopy(original);alter(r)
            with self.assertRaises(ValueError):checked_record(r)
        r=deepcopy(original);r['cache']='C:/arbitrary';r['script']='evil.py';clean=checked_record(r)
        self.assertNotIn('cache',clean);self.assertNotIn('script',clean)
    def test_gui_import_publishes_one_candidate_and_never_launches_search(self):
        from gui import App,read_json
        with tempfile.TemporaryDirectory() as tmp,patch('gui.HERE',Path(tmp)),patch('gui.ensure_data'):
            app=App();app.cache=Path(tmp)/'cache'
            with patch('mission_search.prepare'),patch('gui.get_ephemerides',return_value=EventEphemerides()),patch.object(app,'_register_render_run') as renderer,patch.object(app,'start',side_effect=AssertionError('No optimizer')),patch('gui.threading.Thread',side_effect=lambda target,**kw:type('InlineThread',(),{'start':staticmethod(target)})()):
                loaded=app.import_website_candidate(self.document);out=app.folder(loaded['run'])
                for _ in range(100):
                    status=read_json(out/'gui_status.json',{})
                    if status.get('state') in ('finished','failed'):break
                    time.sleep(.02)
                self.assertEqual(status['state'],'finished',status)
                candidate=read_json(out/'candidates'/(status['candidate_id']+'.json'))
                self.assertEqual(candidate['source_candidate_id'],'4d76acaf1f6f')
                self.assertFalse(candidate['import_verification']['optimization_performed'])
                self.assertEqual(len(read_json(out/'live.json')['candidates']),1)
                self.assertEqual(read_json(out/'candidate_names.json')[candidate['id']],self.document['display_name'])
                renderer.assert_called_once()

    def test_explicit_share_rechecks_import_and_requires_confirmation(self):
        from gui import App
        from ephemeris import atomic_json
        with tempfile.TemporaryDirectory() as tmp,patch('gui.HERE',Path(tmp)),patch('gui.ensure_data'):
            app=App();root=app.folder('share_test');(root/'candidates').mkdir(parents=True)
            c=normalize(self.document['settings']);route=routes_for(c)[0]
            q=materialize(self.document['trajectory'],c,route,EventEphemerides());q['id']='abcdef123456'
            atomic_json(root/'candidates'/(q['id']+'.json'),q)
            atomic_json(root/'run_manifest.json',dict(config=c))
            with self.assertRaisesRegex(ValueError,'Confirm'):app.share_candidate('share_test',q['id'])
            with patch('community.settings',return_value=dict(share_candidates=False,endpoint='https://example.com')):
                with self.assertRaisesRegex(ValueError,'Enable'):app.share_candidate('share_test',q['id'],True)
            with patch('community.settings',return_value=dict(share_candidates=True,endpoint='https://example.com')),patch('gui.get_ephemerides',return_value=EventEphemerides()),patch('community.exchange',side_effect=lambda url,payload:dict(ids=[payload['candidates'][0]['id']])) as upload:
                receipt=app.share_candidate('share_test',q['id'],True)
                self.assertEqual(len(receipt['record_id']),64);self.assertTrue((root/'community_upload.json').exists())
                record=upload.call_args.args[1]['candidates'][0]
                self.assertNotIn('settings',record);self.assertNotIn('cache',record);self.assertEqual(record['classification'],'pass')
if __name__=='__main__':unittest.main()
