"""Return actions preserve the outbound candidate and confirmed Horizons identity."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
from gui import App,Handler
from search_options import export_options

ID='abcdef123456'
TARGET=dict(name='Example asteroid',id='12345678',command='DES=2026 AB;',kind='small_body',designation='2026 AB')


class ReturnEarthBackendTests(unittest.TestCase):
    def saved(self,folder,body='Example asteroid',descriptor=None):
        root=Path(folder);(root/'candidates').mkdir()
        candidate=dict(id=ID,sequence='EX',bodies=['Earth',body])
        (root/'candidates'/(ID+'.json')).write_text(json.dumps(candidate))
        config=dict(target_object=descriptor or deepcopy(TARGET))
        route=dict(id='EX',bodies=['Earth',body])
        (root/'run_manifest.json').write_text(json.dumps(dict(config=config,routes=[route])))
        app=App.__new__(App);app.targets={};app.folder=lambda name:root;app.start=Mock(return_value={'run':'returned'})
        return app,candidate,config

    def test_return_alias_locks_destination_and_keeps_date_controls(self):
        app=App.__new__(App);app.append_candidate=Mock(return_value={'run':'new'})
        result=app.return_to_earth('saved',ID,120,900,True)
        self.assertEqual(result,{'run':'new'})
        app.append_candidate.assert_called_once_with('saved',ID,body='Earth',count=1,minimum_days=120,maximum_days=900,dsm=True)

    def test_unconfirmed_minor_body_is_rejected_before_search(self):
        with tempfile.TemporaryDirectory() as folder:
            app,candidate,config=self.saved(folder)
            with patch('append_flyby.extension_request') as extend:
                with self.assertRaisesRegex(ValueError,'Resolve and confirm'):
                    app.return_to_earth('saved',ID)
                extend.assert_not_called();app.start.assert_not_called()

    def test_confirmed_identity_replaces_a_saved_command_without_changing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            forged=dict(TARGET,command='wrong command')
            app,candidate,config=self.saved(folder,descriptor=forged);app.targets={'cached':TARGET}
            before=(Path(folder)/'run_manifest.json').read_bytes()
            with patch('append_flyby.extension_request',return_value={'marker':'extension'}) as extend:
                self.assertEqual(app.return_to_earth('saved',ID),{'run':'returned'})
                arguments=extend.call_args.args
                self.assertEqual(arguments[0]['target_object'],TARGET)
                self.assertEqual(arguments[2],candidate)
                self.assertEqual(arguments[4],'Earth');self.assertEqual(arguments[5],1)
            self.assertEqual((Path(folder)/'run_manifest.json').read_bytes(),before)

    def test_other_unconfirmed_midroute_body_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            app,candidate,config=self.saved(folder,body='Other asteroid');app.targets={'cached':TARGET}
            with self.assertRaisesRegex(ValueError,'original resolved Horizons'):
                app.return_to_earth('saved',ID)
            app.start.assert_not_called()

    def test_direct_start_cannot_bypass_nested_identity_confirmation(self):
        app=App.__new__(App);app.lock=threading.RLock();app.process=None;app.cache=Path('cache');app.targets={}
        with self.assertRaisesRegex(ValueError,'original Horizons target'):
            app.start(dict(append_flyby={'original_target_object':TARGET}))

    def test_frozen_small_body_or_earth_return_options_are_not_silently_converted(self):
        for route in (dict(id='EXE',target='Earth',bodies=['Earth','Example asteroid','Earth']),
                      dict(id='EXV',target='Venus',bodies=['Earth','Example asteroid','Venus']),
                      dict(id='EVE',target='Earth',bodies=['Earth','Venus','Earth'])):
            with self.subTest(route=route):
                with self.assertRaisesRegex(ValueError,'frozen cruise'):
                    export_options(dict(append_flyby={'route':route}))

    def test_return_http_alias_ignores_client_destination_override(self):
        import urllib.request
        from http.server import ThreadingHTTPServer
        app=App.__new__(App);app.token='return-token';app.return_to_earth=Mock(return_value={'run':'new-return'})
        with ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
            server.app=app;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url='http://127.0.0.1:'+str(server.server_port)
            try:
                body=dict(run='saved',candidate=ID,minimum_days=200,maximum_days=900,dsm=True,body='Jupiter',count=3)
                request=urllib.request.Request(url+'/api/return-earth',data=json.dumps(body).encode(),
                    headers={'X-Explorer-Token':'return-token','Content-Type':'application/json','Origin':url})
                with urllib.request.urlopen(request,timeout=5) as response:result=json.load(response)
                self.assertEqual(result,{'run':'new-return'})
                app.return_to_earth.assert_called_once_with('saved',ID,200,900,True)
            finally:server.shutdown();thread.join(timeout=3)


if __name__=='__main__':unittest.main()
