"""Red suppression and selected-candidate scheduling without optimizer disruption."""
import bootstrap
import json,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from live_gallery import LiveGallery,RenderPreempted,plot_status
from candidate_status import red_reason,unresolved_mismatch_sum,modeled_plus_unresolved_mismatch
from ephemeris import atomic_json


def candidate(identifier='abcdef123456',**extra):
    return dict(id=identifier,sequence='EVEEJ',status='passes_configured_patched_conic_screen',
        total_dsm_kms=.1,max_vinf_mismatch_mps=0.,max_single_dsm_kms=.1,max_powered_flyby_kms=0.,
        periapsis_violation=False,**extra)


def summary(*rows):return dict(candidates=list(rows),near_misses=[],distinct_accepted=len(rows),raw_accepted=len(rows),model='test')


class RenderPriorityTests(unittest.TestCase):
    def test_deferred_snapshots_publish_all_science_without_sampling(self):
        a=candidate();b=candidate('0123456789ab');b['periapsis_violation']=True
        with tempfile.TemporaryDirectory() as folder,patch('live_gallery.card_data') as data,patch('live_gallery.thumbnail') as image:
            LiveGallery(folder,None,deferred=True,config={'max_single_dsm_kms':.7}).update(summary(a,b),{},final=True)
            data.assert_not_called();image.assert_not_called()
            p=Path(folder);live=json.loads((p/'live.json').read_text());rows={r['id']:r for r in live['candidates']}
            self.assertTrue(rows[a['id']]['render_pending']);self.assertFalse(rows[b['id']]['render_pending'])
            self.assertTrue(rows[b['id']]['render_skipped'])
            for q in (a,b):self.assertEqual(json.loads((p/'candidates'/(q['id']+'.json')).read_text()),q)
            card=json.loads((p/'candidates'/(b['id']+'.card.json')).read_text());self.assertEqual(card['paths'],[])

    def test_red_has_no_plot_even_if_an_old_png_exists(self):
        q=candidate();q['periapsis_violation']=True
        with tempfile.TemporaryDirectory() as folder,patch('live_gallery.card_data') as data,patch('live_gallery.thumbnail') as image:
            gallery=LiveGallery(folder,None);(gallery.folder/(q['id']+'.png')).write_bytes(b'old')
            gallery.update(summary(q),{},final=True)
            self.assertFalse(plot_status(gallery.folder,q)['image_ready'])
            data.assert_not_called();image.assert_not_called()

    def test_combined_screen_excludes_powered_flybys_and_preserves_soft_budget(self):
        q=candidate();q.update(total_dsm_kms=.2,flybys=[{'speed_mismatch_mps':450},{'speed_mismatch_mps':400},{'speed_mismatch_mps':9000,'passes_powered_geometry':True}])
        c={'max_dsm_kms':1.,'max_single_dsm_kms':.7,'max_powered_flyby_kms':.2}
        self.assertAlmostEqual(unresolved_mismatch_sum(q),850.);self.assertAlmostEqual(modeled_plus_unresolved_mismatch(q),1.05)
        self.assertIn('screening budget',red_reason(q,c))
        q['flybys']=[{'speed_mismatch_mps':9000,'passes_powered_geometry':True}];q['max_vinf_mismatch_mps']=9000
        q['total_dsm_kms']=2.;self.assertIsNone(red_reason(q,c))
        q['max_powered_flyby_kms']=.201;self.assertIn('Powered',red_reason(q,c))

    def test_pure_modeled_total_over_budget_remains_soft_when_each_burn_is_under_cap(self):
        q=candidate();q.update(total_dsm_kms=2.,flybys=[],max_single_dsm_kms=.6,max_vinf_mismatch_mps=0.)
        self.assertIsNone(red_reason(q,{'max_dsm_kms':1.,'max_single_dsm_kms':.7}))
        q['flybys']=[{'speed_mismatch_mps':1.}]
        self.assertIn('screening budget',red_reason(q,{'max_dsm_kms':1.,'max_single_dsm_kms':.7}))

    def test_preempted_sampling_never_becomes_a_plot_error(self):
        q=candidate()
        with tempfile.TemporaryDirectory() as folder,patch('live_gallery.card_data',side_effect=RenderPreempted()),patch('live_gallery.thumbnail') as image:
            gallery=LiveGallery(folder,None);gallery.placeholder(q)
            self.assertEqual(gallery.render(q),'preempted');image.assert_not_called()
            self.assertFalse((gallery.folder/(q['id']+'.plot_error.json')).exists())
            self.assertTrue(plot_status(gallery.folder,q)['render_pending'])

    def test_latest_click_preempts_background_at_safe_sampling_point(self):
        from gui import App
        q1,q2,q3=candidate('111111111111'),candidate('222222222222'),candidate('333333333333')
        with tempfile.TemporaryDirectory() as folder,patch('gui.HERE',Path(folder)):
            app=App.__new__(App);app.lock=threading.RLock();app.render_priority=None;app.render_runs={'run':1};app.render_stop=threading.Event();app.render_event=threading.Event();app.render_revision={};app.render_lock=threading.Lock()
            out=Path(folder)/'runs/run';out.mkdir(parents=True);LiveGallery(out,None,deferred=True).update(summary(q1,q2,q3),{})
            atomic_json(out/'request.json',{'max_single_dsm_kms':.7})
            app.render_priority=('run',q3['id'],1)
            self.assertEqual(app._next_render_task()[1]['id'],q3['id'])
            app.render_priority=('run',q2['id'],2)
            self.assertEqual(app._next_render_task()[1]['id'],q2['id'])
            self.assertFalse(app.render_stop.is_set())

    def test_incomplete_legacy_card_is_queued_until_both_outputs_are_ready(self):
        q=candidate()
        with tempfile.TemporaryDirectory() as folder:
            gallery=LiveGallery(folder,None)
            atomic_json(gallery.folder/(q['id']+'.card.json'),dict(q,paths=[[1]],planet_paths=[]))
            gallery.placeholder(q)
            card=json.loads((gallery.folder/(q['id']+'.card.json')).read_text());self.assertTrue(card['render_pending'])
            self.assertFalse(plot_status(gallery.folder,q)['image_ready'])
            with patch('live_gallery.card_data',return_value=dict(q,paths=[],planet_paths=[])),patch('live_gallery.thumbnail',side_effect=lambda card,path:path.write_bytes(b'png')):
                self.assertEqual(gallery.render(q),'ready')
            self.assertTrue(plot_status(gallery.folder,q)['image_ready'])
            self.assertFalse((gallery.folder/(q['id']+'.render_pending.json')).exists())

    def test_api_queues_click_without_loading_ephemerides_and_red_is_diagnostic(self):
        from gui import App
        with tempfile.TemporaryDirectory() as folder,patch('gui.HERE',Path(folder)):
            app=App.__new__(App);app.lock=threading.RLock();app.render_priority=None
            q=candidate();out=Path(folder)/'runs/run';out.mkdir(parents=True);LiveGallery(out,None,deferred=True).update(summary(q),{})
            atomic_json(out/'request.json',{'max_single_dsm_kms':.7})
            with patch.object(app,'_register_render_run') as queue,patch('gui.get_ephemerides') as ep:
                result=app.render_candidate('run',q['id']);self.assertEqual(result['state'],'queued');queue.assert_called_once();ep.assert_not_called()
            q['periapsis_violation']=True;atomic_json(out/'candidates'/(q['id']+'.json'),q)
            with patch.object(app,'_register_render_run') as queue:
                self.assertEqual(app.render_candidate('run',q['id'])['state'],'queued');queue.assert_called_once()
            self.assertTrue(plot_status(out/'candidates',q)['manual_preview'])
            with patch('live_gallery.card_data',return_value=dict(q,paths=[],planet_paths=[])),patch('live_gallery.thumbnail',side_effect=lambda card,path:path.write_bytes(b'png')):
                self.assertEqual(LiveGallery(out,None).render(q),'ready')
            self.assertTrue(plot_status(out/'candidates',q)['image_ready'])
            self.assertTrue(json.loads((out/'candidates'/(q['id']+'.card.json')).read_text())['manual_preview'])
            with self.assertRaises(ValueError):app.render_candidate('../other',q['id'])
            with self.assertRaises(ValueError):app.render_candidate('run','../anything')

    def test_legacy_summary_hydrates_combined_mismatch_and_hides_cached_red_png(self):
        from gui import App,read_json
        q=candidate();q.update(flybys=[{'speed_mismatch_mps':700.},{'speed_mismatch_mps':700.}],max_vinf_mismatch_mps=700.)
        row={k:v for k,v in q.items() if k!='flybys'}
        with tempfile.TemporaryDirectory() as folder,patch('gui.HERE',Path(folder)):
            app=App.__new__(App);app.render_metadata={}
            out=Path(folder)/'runs/run/candidates';out.mkdir(parents=True);atomic_json(out/(q['id']+'.json'),q)
            (out/(q['id']+'.png')).write_bytes(b'legacy')
            atomic_json(out/(q['id']+'.card.json'),dict(q,paths=[[1]],planet_paths=[]))
            c={'max_dsm_kms':1.,'max_single_dsm_kms':.7}
            with patch('gui.read_json',wraps=read_json) as read:
                hydrated=app._hydrate_render_row('run',row,c)
                again=app._hydrate_render_row('run',row,c)
                self.assertEqual(read.call_count,1)
            self.assertEqual(hydrated['total_unresolved_vinf_mismatch_mps'],1400.)
            self.assertTrue(hydrated['mismatch_screening_budget_exceeded'])
            self.assertAlmostEqual(hydrated['modeled_plus_unresolved_mismatch_kms'],1.5)
            status=plot_status(out,hydrated,c);self.assertFalse(status['image_ready']);self.assertTrue(status['render_skipped'])
            self.assertEqual(hydrated,again)

    def test_ephemerides_are_reused_between_selected_candidates(self):
        from gui import App
        app=App.__new__(App);app.render_ephemerides={};app.cache=Path('.')
        with patch('gui.normalize',return_value={'cache':'.'}) as norm,patch('gui.routes_for',return_value=[]),patch('gui.get_ephemerides',return_value=object()) as ep:
            first=app._render_ephemeris('run',{});second=app._render_ephemeris('run',{})
            self.assertIs(first,second);self.assertEqual(ep.call_count,1);self.assertEqual(norm.call_count,1)

if __name__=='__main__':unittest.main()
