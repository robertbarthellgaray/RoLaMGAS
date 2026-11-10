"""Contracts for custom Horizons targets, finite flybys and local file access."""
import bootstrap  # noqa: F401
import unittest
import json
import tempfile
import multiprocessing
import queue
from pathlib import Path
from unittest.mock import patch
import numpy as np
from ephemeris import AU,BODIES,DAY,JD0,parse_horizons
from horizons_targets import cache_stem,identity,register_target,resolve
from mission_search import load_database,normalize,routes_for
from integrate_export import hyperbolic_state,planet_pieces


def _fill_progress_proxy(progress):
    for _ in range(50):
        try:
            progress.put_nowait({'payload':'x'*100000})
        except queue.Full:
            pass


class GuiBackendTests(unittest.TestCase):
    def test_old_low_c3_rows_are_removed_before_hydration_and_render_queue(self):
        from gui import App
        with tempfile.TemporaryDirectory() as folder,patch('gui.HERE',Path(folder)):
            app=App();root=app.folder('legacy');root.mkdir()
            rows=[dict(id=f'{i:012x}',launch_c3_km2_s2=c3,status='passes_configured_patched_conic_screen') for i,c3 in enumerate((0.,4.999,6.25,20.))]
            (root/'live.json').write_text(json.dumps(dict(candidates=rows,distinct_accepted=4)))
            (root/'request.json').write_text(json.dumps(dict(min_c3=0)))
            with patch.object(app,'_register_render_run'),patch.object(app,'_hydrate_render_row',side_effect=lambda name,q,c:q) as hydrate:
                live=app.snapshot('legacy')['live']
            self.assertEqual([q['launch_c3_km2_s2'] for q in live['candidates']],[6.25,20.])
            self.assertEqual(live['excluded_below_hard_c3_floor'],2)
            self.assertEqual(live['distinct_accepted'],2)
            self.assertEqual(hydrate.call_count,2)
            app.render_runs={'legacy':0.}
            (root/'live.json').write_text(json.dumps(dict(candidates=rows[:2])))
            with patch.object(app,'_hydrate_render_row',side_effect=AssertionError('Low energy candidate was queued')):
                self.assertIsNone(app._next_render_task())

    def test_full_progress_queue_does_not_block_worker_exit(self):
        context=multiprocessing.get_context('spawn')
        with context.Manager() as manager:
            progress=manager.Queue(maxsize=1)
            worker=context.Process(target=_fill_progress_proxy,args=(progress,))
            worker.start();worker.join(timeout=12)
            alive=worker.is_alive()
            if alive:
                worker.terminate();worker.join(timeout=3)
            self.assertFalse(alive,'Progress delivery blocked worker shutdown')
            self.assertEqual(worker.exitcode,0)

    def test_plot_failure_preserves_candidate_and_live_status(self):
        from live_gallery import LiveGallery
        q=dict(id='0123456789ab',status='passes_configured_patched_conic_screen',sequence='EX',launch_c3_km2_s2=10.)
        summary=dict(candidates=[q],near_misses=[],distinct_accepted=1,raw_accepted=1,model='test')
        with tempfile.TemporaryDirectory() as folder:
            with patch('live_gallery.card_data',side_effect=ValueError('test plot failure')):
                LiveGallery(folder,None).update(summary,dict(state='running'))
            snapshot=json.loads((Path(folder)/'live.json').read_text())
            self.assertEqual(snapshot['candidates'][0]['render_error'],'test plot failure')
            self.assertTrue((Path(folder)/'candidates/0123456789ab.json').exists())

    def test_custom_routes_and_zero_dsm_budget(self):
        descriptor=dict(name='Example (2030 AA)',id='54321000',command='DES=2030 AA;',kind='small_body',designation='2030 AA')
        for route,expected in [('EX',[]),('EdvX',[0]),('EdvEJX',[0])]:
            c=normalize(dict(target_object=descriptor,sequences=[route],max_dsm_kms=0,custom_leg_days=[600,900]))
            r=routes_for(c)[0]
            self.assertEqual(r['dsm_legs'],expected)
            self.assertEqual(r['leg_days'][-1],[600,900])
            self.assertEqual(r['bodies'][-1],descriptor['name'])

    def test_small_body_header_without_numeric_id(self):
        descriptor=dict(name='1 Ceres (A801 AA)',id='20000001',command='DES=1;',kind='small_body',designation='1')
        register_target(descriptor)
        self.assertEqual(identity(descriptor['name'])['command'],'1;')
        self.assertEqual(cache_stem(descriptor['name']),'object_20000001')
        header='Target body name: 1 Ceres (A801 AA) {source: JPL#48}\nCenter body name: Sun (10)\nOutput units : KM-S\nGEOMETRIC cartesian states\nEcliptic of J2000.0\nJDTDB,\n$$SOE\n'
        rows=[f'{JD0+i}, A.D. 2000-Jan-0{i+1} 00:00:00.000000,1,2,3,0,0,0,' for i in range(4)]
        times,states=parse_horizons(header+'\n'.join(rows)+'\n$$EOE',descriptor['name'])
        self.assertEqual(states.shape,(4,6))
        with self.assertRaises(ValueError):
            parse_horizons((header+'\n'.join(rows)+'\n$$EOE').replace('1 Ceres (A801 AA)','2 Pallas (A802 FA)'),descriptor['name'])

    def test_ambiguous_lookup_never_selects_first_result(self):
        payload={'signature':{'version':'1.1'},'result':[{'spkid':'606','name':'Titan','type':'natural satellite'},
                  {'spkid':'20000606','name':'606 Brangane','type':'asteroid (integrated barycenter)'}]}
        with patch('horizons_targets.request_json',return_value=payload):
            result=resolve('ambiguous')
        self.assertTrue(result['ambiguous'])
        self.assertEqual(len(result['choices']),2)
        self.assertNotIn('command',result)

    def test_moon_lookup_skips_sbdb_and_normalizes_display_alias(self):
        from urllib.parse import urlparse,parse_qs
        calls=[]
        def response(url):
            calls.append(url)
            if 'horizons_lookup' in url:
                self.assertEqual(parse_qs(urlparse(url).query)['sstr'],['Titan'])
                return {'signature':{'version':'1.1'},'result':[{'name':'Titan','spkid':'606','type':'natural satellite'}]}
            self.assertNotIn('sbdb',url)
            self.assertEqual(parse_qs(urlparse(url).query)['COMMAND'],["'606'"])
            return {'result':'Target body name: Titan (606)\n$$SOE\n$$EOE'}
        with patch('horizons_targets.request_json',side_effect=response):
            result=resolve('Titan (SVI)')
        self.assertEqual(result['parent_body'],'Saturn')
        self.assertEqual(result['kind'],'natural_satellite')
        self.assertEqual(len(calls),2)
        with self.assertRaisesRegex(ValueError,'parent-centered arrival'):
            normalize(dict(target_object=result,sequences=['EEX']))
        # Old cached moon descriptors must not bypass the model restriction.
        with self.assertRaisesRegex(ValueError,'parent-centered arrival'):
            normalize(dict(target_object=dict(name='Titan',id='606',command='606',kind='horizons_object')))

    def test_explicit_spk_selection_disambiguates_moon_from_asteroid(self):
        payload={'signature':{'version':'1.1'},'result':[{'spkid':'606','name':'Titan','type':'natural satellite'},
                  {'spkid':'20000606','name':'606 Brangane','type':'asteroid (integrated barycenter)'}]}
        with patch('horizons_targets.request_json',side_effect=[payload,{'result':'Target body name: Titan (606)\n$$SOE\n$$EOE'}]):
            result=resolve('SPK=606')
        self.assertEqual(result['id'],'606')

    def test_small_body_lookup_still_loads_orbital_metadata(self):
        lookup={'signature':{'version':'1.1'},'result':[{'spkid':'20000001','name':'1 Ceres','pdes':'A801 AA','type':'asteroid (integrated barycenter)'}]}
        sb={'object':{'fullname':'1 Ceres (A801 AA)','spkid':'20000001','des':'1','orbit_class':{'name':'Main-belt asteroid'}},'orbit':{'elements':[{'name':'a','value':'2.77'}]}}
        with patch('horizons_targets.request_json',side_effect=[lookup,sb]):
            result=resolve('Ceres')
        self.assertEqual(result['command'],'1;')
        self.assertEqual(result['semimajor_axis_au'],2.77)

    def test_hyperbola_energy_and_periapsis(self):
        mu=BODIES['Earth'][1];rp=BODIES['Earth'][2]+300.;vinf=8.
        r=np.array([rp,0.,0.]);v=np.array([0.,np.sqrt(vinf**2+2*mu/rp),0.])
        for t in (-100000.,0.,100000.):
            y=hyperbolic_state(mu,r,v,t)
            energy=y[3:]@y[3:]/2-mu/np.linalg.norm(y[:3])
            self.assertAlmostEqual(energy,vinf**2/2,places=8)
            self.assertGreaterEqual(np.linalg.norm(y[:3]),rp-1e-6)

    def test_finite_flyby_geometry_and_no_position_jump(self):
        class FixedEphemeris:
            def state(self,body,date):
                return np.array([AU,0.,0.,0.,0.,0.])
        angle=np.radians(30)
        uin=np.array([8.,0.,0.]);uout=8*np.array([np.cos(angle),np.sin(angle),0.])
        node=planet_pieces('Earth',JD0,FixedEphemeris(),uin,uout,altitude=200.)
        self.assertGreater(node['altitude'],200)
        a,b=node['pieces']
        self.assertLess(np.linalg.norm(a['state'](JD0)[:3]-b['state'](JD0)[:3]),1e-4)
        self.assertLess(np.linalg.norm(node['peri_in_velocity']-node['peri_out_velocity']),1e-10)

    def test_local_run_path_rejects_traversal(self):
        from gui import App
        app=App()
        with self.assertRaises(ValueError):
            app.folder('../outside')


if __name__=='__main__':
    unittest.main()
