"""Portable settings round trips and local API boundaries."""
import bootstrap
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from search_options import FORMAT,SCHEMA_VERSION,export_options,import_options
from mission_search import normalize,routes_for


class SearchOptionsTests(unittest.TestCase):
    def request(self):
        return dict(target='Jupiter',sequences=['EVEEJ'],launch_start='2030-01-01',launch_end='2030-02-01',
                    min_c3=14.,max_c3=45.,max_dsm_kms=.8,powered_flybys=True,
                    search_objective='time',transfer_direction='both',seed=184,
                    minimum_altitude_km={'Venus':666.},cache='C:/Users/private/cache',workers=24,
                    local_refinement=dict(parent_run='private_run',parent_candidate='abcdef123456',seed_x=[.5]))

    def test_round_trip_preserves_bounds_routes_and_dates_without_machine_state(self):
        request=self.request();before=deepcopy(request)
        result=export_options(request);doc=result['document'];settings=doc['settings']
        self.assertEqual(doc['format'],FORMAT);self.assertEqual(doc['schema_version'],SCHEMA_VERSION)
        self.assertEqual(request,before)
        for key in ('cache','workers','launch_jd','event_windows_jd','arrival_window_jd','local_refinement','append_flyby'):
            self.assertNotIn(key,settings)
        text=json.dumps(doc);self.assertNotIn('private',text)
        imported=import_options(doc)['config']
        for key in ('min_c3','max_c3','max_dsm_kms','powered_flybys','search_objective','seed','launch_start','launch_end','transfer_direction'):
            self.assertEqual(imported[key],request[key])
        self.assertEqual(imported['minimum_altitude_km']['Venus'],666)
        expected=routes_for(normalize({k:v for k,v in request.items() if k!='local_refinement'}))
        actual=routes_for(normalize(imported))
        self.assertEqual(actual,expected)

    def test_effective_route_ranges_survive_a_recipient_database_change(self):
        doc=export_options(dict(target='Jupiter',sequences=['EJ'],min_c3=10))['document']
        expected=deepcopy(doc['settings']['route_overrides']['EJ'])
        from mission_search import load_database
        database=deepcopy(load_database())
        for route in database['sequences']:
            if route['id']=='EJ':route['leg_days']=[[20,30]]
        with patch('mission_search.load_database',return_value=database):
            imported=import_options(doc)['config'];route=routes_for(normalize(imported))[0]
        self.assertEqual(route['leg_days'],expected['leg_days'])

    def test_custom_target_import_stays_offline_and_requires_local_confirmation(self):
        descriptor=dict(name='Pluto',id='999',command='999',kind='horizons_object',
                        source='C:/Users/private/source',query='private lookup')
        request=dict(target_object=descriptor,sequences=['EJX'],min_c3=160,max_c3=170,
                     launch_start='2004-12-01',launch_end='2004-12-31',arrival_date='2012-12-15',
                     arrival_tolerance_days=15,event_windows=[['2004-12-01','2004-12-31'],
                     ['2006-03-01','2006-03-31'],['2012-12-01','2012-12-31']])
        with patch('horizons_targets.request_json',side_effect=AssertionError('Import must stay offline')):
            doc=export_options(request)['document'];result=import_options(doc)
        self.assertTrue(result['requires_target_resolution'])
        target=result['config']['target_object'];self.assertEqual(target['id'],'999')
        self.assertNotIn('source',target);self.assertEqual(target['query'],'SPK=999')
        self.assertEqual(result['config']['event_windows'],request['event_windows'])
        self.assertEqual(result['config']['arrival_date'],'2012-12-15')

    def test_invalid_or_incompatible_documents_are_rejected(self):
        doc=export_options(dict(target='Jupiter',sequences=['EJ'],min_c3=10))['document']
        for bad in (None,[],{},dict(doc,schema_version=2),dict(doc,schema_version=True),dict(doc,format='other'),
                    dict(doc,settings={'target':'Jupiter','min_c3':200,'max_c3':100}),
                    dict(doc,settings={'target':'Jupiter','max_c3':float('nan')})):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):import_options(bad)
        with self.assertRaisesRegex(ValueError,'1 MiB'):
            import_options(dict(doc,padding='x'*(1024*1024)))

    def test_app_import_cannot_bypass_the_confirmed_target_check(self):
        from gui import App
        app=App.__new__(App);app.targets={};app.process=None
        doc=export_options(dict(target_object=dict(name='Pluto',id='999',command='999',kind='horizons_object'),
                                sequences=['EJX'],min_c3=160,max_c3=170))['document']
        result=app.import_search_options(doc)
        self.assertTrue(result['requires_target_resolution']);self.assertFalse(app.targets)
        app.targets={'Pluto':dict(name='Pluto',id='999',command='999',kind='horizons_object',source='verified local lookup')}
        result=app.import_search_options(doc)
        self.assertFalse(result['requires_target_resolution'])
        self.assertEqual(result['config']['target_object']['source'],'verified local lookup')

    def test_saved_run_export_reads_only_its_options(self):
        from gui import App
        app=App.__new__(App)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'request.json').write_text(json.dumps(self.request()))
            app.folder=lambda name:root
            result=app.export_search_options(run='saved')
            self.assertEqual(result['document']['settings']['min_c3'],14.)
            with self.assertRaises(ValueError):app.export_search_options(config={},run='saved')


class SearchOptionsHttpTests(unittest.TestCase):
    def test_local_api_round_trip_requires_session_and_does_not_start_search(self):
        import threading
        import urllib.request
        import urllib.error
        from http.server import ThreadingHTTPServer
        from gui import App,Handler
        app=App.__new__(App);app.token='local-test-token';app.targets={}
        with ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
            server.app=app
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            def post(path,body,token='local-test-token'):
                request=urllib.request.Request(base+path,data=json.dumps(body).encode(),
                    headers={'Content-Type':'application/json','X-Explorer-Token':token,'Origin':base})
                try:
                    with urllib.request.urlopen(request,timeout=5) as response:
                        return response.status,json.load(response)
                except urllib.error.HTTPError as error:
                    return error.code,json.load(error)
            try:
                status,exported=post('/api/options/export',dict(config=dict(target='Jupiter',sequences=['EJ'],min_c3=14,max_c3=45)))
                self.assertEqual(status,200);self.assertEqual(exported['document']['format'],FORMAT)
                status,imported=post('/api/options/import',dict(document=exported['document']))
                self.assertEqual(status,200);self.assertEqual(imported['config']['min_c3'],14.)
                self.assertFalse(imported['requires_target_resolution'])
                self.assertFalse(hasattr(app,'process'),'Import must not create a search process')
                status,result=post('/api/options/import',dict(document=exported['document']),token='wrong')
                self.assertEqual(status,403)
                status,result=post('/api/options/import',dict(document={'format':'wrong'}))
                self.assertEqual(status,400)
            finally:
                server.shutdown();thread.join(timeout=3)


if __name__=='__main__':unittest.main()
