"""Database-first lookup and explicit user decisions before optimizer processes."""
import bootstrap
import json,tempfile,queue,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import community
from dynamics import Model
from ephemeris import atomic_json
from gui_worker import database_decision
from mission_search import normalize,routes_for,run
from test_hard_c3_generation import CircularStates
from test_seeded_job_scheduler import InlinePool

class DatabaseFirstTests(unittest.TestCase):
    def fixture(self,count=3):
        c=normalize(dict(target='Jupiter',sequences=['EJ'],max_c3=1e9,max_arrival_vinf_kms=1000,max_years=100,samples_per_sequence=8,refinements_per_sequence=1,max_nfev=1,workers=1))
        r=routes_for(c)[0];ep=CircularStates();ep.manifest={'Earth':[],'Jupiter':[]};m=Model(r,c,ep);rows=[]
        for x in [.2,.4,.6][:count]:
            q=m.evaluate([x,.5],[[0,True]]);self.assertTrue(m.accepted(q));q.update(status='passes_configured_patched_conic_screen',community_source={'id':str(x),'library':'online','revalidated':True});rows.append(q)
        return c,r,ep,rows
    def test_three_matches_can_finish_without_any_optimizer_process(self):
        c,r,ep,rows=self.fixture();context=Mock()
        with tempfile.TemporaryDirectory() as folder,patch('mission_search.HERE',Path(folder)),patch('mission_search.get_ephemerides',return_value=ep),patch('community.download_candidates',return_value=dict(accepted=rows,near_misses=[],online_status='available')),patch('mission_search.multiprocessing.get_context',return_value=context),patch('mission_search.ProcessPoolExecutor') as pool,patch('presentation.publish'),patch('live_gallery.LiveGallery'):
            output=Path(folder)/'run';reports=[]
            run(c,[r],output,database_gate=lambda report:reports.append(report) or False)
            self.assertEqual(reports[0]['passing_matches'],3);pool.assert_not_called();context.Manager.assert_not_called()
            self.assertEqual(len(json.loads((output/'results.json').read_text())['candidates']),3)
            self.assertFalse(json.loads((output/'database_first.json').read_text())['cpu_search_started'])
    def test_zero_one_or_two_matches_start_local_search_automatically(self):
        for count in [0,1,2]:
            with self.subTest(count=count):
                c,r,ep,rows=self.fixture(count);manager=Mock();manager.Queue.side_effect=lambda maxsize:queue.Queue(maxsize);context=Mock();context.Manager.return_value=manager
                with tempfile.TemporaryDirectory() as folder,patch('mission_search.HERE',Path(folder)),patch('mission_search.get_ephemerides',return_value=ep),patch('mission_search._WORKER_EP',ep),patch('mission_search._PROGRESS_QUEUE',None),patch('community.download_candidates',return_value=dict(accepted=rows,near_misses=[],online_status='available')),patch('community.CommunitySync'),patch('mission_search.multiprocessing.get_context',return_value=context),patch('mission_search.ProcessPoolExecutor',side_effect=lambda **kwargs:InlinePool(**kwargs)) as pool,patch('presentation.publish'),patch('live_gallery.LiveGallery'):
                    output=Path(folder)/'run'
                    run(c,[r],output,database_gate=lambda report:database_decision(output,report,output/'stop.request',Mock()))
                    pool.assert_called_once();self.assertTrue(json.loads((output/'database_first.json').read_text())['cpu_search_started'])
    def test_user_can_choose_local_or_database_only_and_stop_waiting(self):
        for choice in [False,True]:
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder);atomic_json(root/'database_decision.json',dict(run_local=choice));state=Mock()
                self.assertEqual(database_decision(root,dict(passing_matches=3),root/'stop.request',state),choice)
                self.assertEqual(state.call_args_list[0].args[0],'awaiting_database_decision')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'stop.request').touch()
            with self.assertRaises(InterruptedError):database_decision(root,dict(passing_matches=3),root/'stop.request',Mock())
    def test_database_pagination_and_full_science_revalidation(self):
        c,r,ep,rows=self.fixture();records=[community.public_record(q,c,r) for q in rows]
        pages=[dict(candidates=records[:2],next_cursor='next-page'),dict(candidates=records[2:],next_cursor=None)]
        pref=dict(use_candidates=True,share_candidates=False,endpoint='https://example.test')
        with tempfile.TemporaryDirectory() as folder,patch.object(community,'RESOURCE_ROOT',Path(folder)),patch.object(community,'settings',return_value=pref),patch.object(community,'exchange',side_effect=pages) as network:
            found=community.download_candidates(c,[r],ep);self.assertEqual(len(found['accepted']),3);self.assertEqual(network.call_count,2)
            self.assertIn('max_arrival_vinf=',network.call_args_list[0].args[0]);self.assertIn('cursor=next-page',network.call_args_list[1].args[0])
        low=dict(c,max_arrival_vinf_kms=min(q['arrival_vinf_kms'] for q in rows)-.01)
        with tempfile.TemporaryDirectory() as folder,patch.object(community,'RESOURCE_ROOT',Path(folder)),patch.object(community,'settings',return_value=pref),patch.object(community,'exchange',return_value=dict(candidates=records)):
            self.assertEqual(community.download_candidates(low,[r],ep)['accepted'],[])
    def test_unavailable_database_is_not_an_optimizer_failure(self):
        c,r,ep,rows=self.fixture()
        with tempfile.TemporaryDirectory() as folder,patch.object(community,'RESOURCE_ROOT',Path(folder)),patch.object(community,'settings',return_value=dict(use_candidates=True,share_candidates=False,endpoint='https://example.test')),patch.object(community,'exchange',side_effect=TimeoutError):
            found=community.download_candidates(c,[r],ep);self.assertEqual(found['accepted'],[]);self.assertEqual(found['online_status'],'unavailable')
if __name__=='__main__':unittest.main()
