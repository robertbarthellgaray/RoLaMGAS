"""Exercise seeded jobs through filenames, executor bookkeeping and resume."""
import bootstrap
import json,queue,tempfile,unittest
from pathlib import Path
from concurrent.futures import Future
from unittest.mock import Mock,patch
from dynamics import Model
from mission_search import normalize,routes_for,run
from test_hard_c3_generation import CircularStates

class InlinePool:
    def __init__(self,**kwargs):self._processes={}
    def submit(self,function,job):
        future=Future()
        try:future.set_result(function(job))
        except BaseException as exc:future.set_exception(exc)
        return future
    def shutdown(self,**kwargs):pass

class SeededSchedulerTests(unittest.TestCase):
    def exercise(self,seeded):
        c=normalize(dict(target='Jupiter',sequences=['EJ'],max_c3=1e9,max_arrival_vinf_kms=1000,max_years=100,
                         samples_per_sequence=8,refinements_per_sequence=1,max_nfev=6,workers=1))
        route=routes_for(c)[0];ep=CircularStates();ep.manifest={'Earth':[],'Jupiter':[]}
        model=Model(route,c,ep);q=model.evaluate([.4,.5],[[0,True]])
        self.assertTrue(model.accepted(q));q.update(status='passes_configured_patched_conic_screen',community_source=dict(id='known',revalidated=True))
        manager=Mock();manager.Queue.side_effect=lambda maxsize:queue.Queue(maxsize)
        context=Mock();context.Manager.return_value=manager
        library=dict(accepted=[q] if seeded else [],near_misses=[])
        with tempfile.TemporaryDirectory() as folder,patch('mission_search.HERE',Path(folder)),patch('mission_search.get_ephemerides',return_value=ep),patch('mission_search._WORKER_EP',ep),patch('mission_search._PROGRESS_QUEUE',None),patch('mission_search.multiprocessing.get_context',return_value=context),patch('mission_search.ProcessPoolExecutor',InlinePool),patch('community.download_candidates',return_value=library),patch('community.CommunitySync'),patch('presentation.publish'),patch('live_gallery.LiveGallery'):
            output=Path(folder)/'search'
            run(c,[route],output)
            checkpoints=list((output/'checkpoints').glob('*.json'))
            self.assertEqual([p.name for p in checkpoints],['b000_r00_f000.json'])
            result=json.loads(checkpoints[0].read_text())
            self.assertEqual(result['job_id'],'b000_r00_f000')
            self.assertEqual(result['known_seed_refinements'],1 if seeded else 0)
            self.assertEqual(json.loads((output/'results.json').read_text())['completed_jobs'],1)
            if seeded:
                run(c,[route],output,resume=True)
                self.assertEqual(len(list((output/'checkpoints').glob('*.json'))),1)
                self.assertEqual(json.loads((output/'results.json').read_text())['completed_jobs'],1)
    def test_seeded_job_keeps_string_identifier_and_resumes(self):self.exercise(True)
    def test_unseeded_job_keeps_original_identifier(self):self.exercise(False)

if __name__=='__main__':unittest.main()
