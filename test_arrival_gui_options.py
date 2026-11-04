"""GUI export options preserve zero inclination and invalidate stale packages."""
import bootstrap
import io,json,math,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np
from gui import App,Handler
from integrate_export import planet_pieces
from ephemeris import AU,JD0

ID='0123456789ab'

class ArrivalGuiOptionsTests(unittest.TestCase):
    def saved_app(self,folder):
        root=Path(folder);(root/'candidates').mkdir(exist_ok=True)
        (root/'candidates'/(ID+'.json')).write_text('{}')
        (root/'request.json').write_text(json.dumps({'target':'Jupiter'}))
        app=App.__new__(App);app.folder=lambda name:root;app.lock=threading.RLock()
        app.integrations={};app.cache=root/'cache';app.token='arrival-token'
        return app

    def request(self,app,path,payload):
        raw=json.dumps(payload).encode()
        handler=Handler.__new__(Handler);handler.server=SimpleNamespace(app=app,server_port=41234)
        handler.path=path;handler.rfile=io.BytesIO(raw)
        handler.headers={'X-Explorer-Token':app.token,'Origin':'http://127.0.0.1:41234','Content-Length':str(len(raw))}
        handler.json=Mock();handler.do_POST()
        return handler.json

    def test_http_api_forwards_zero_and_polar_targets_on_both_exports(self):
        for endpoint,method in [('/api/integrate','integrate'),('/api/package','package')]:
            for desired in (0.,90.):
                with self.subTest(endpoint=endpoint,desired=desired):
                    app=SimpleNamespace(token='arrival-token',integrate=Mock(return_value={'started':True}),package=Mock(return_value={'state':'finished'}))
                    self.request(app,endpoint,dict(run='saved',candidate=ID,arrival_inclination_deg=desired))
                    expected=('saved',ID,None,None,0.,desired) if method=='integrate' else ('saved',ID,'auto',None,None,0.,desired)
                    getattr(app,method).assert_called_once_with(*expected)

    def test_worker_flags_keep_zero_and_omit_unspecified_inclination(self):
        for desired in (None,0.,90.):
            with self.subTest(desired=desired),tempfile.TemporaryDirectory() as folder:
                app=self.saved_app(folder)
                with patch('gui.subprocess.Popen') as popen:
                    result=app.integrate('saved',ID,arrival_inclination_deg=desired)
                self.assertTrue(result['started']);command=popen.call_args.args[0]
                if desired is None:self.assertNotIn('--arrival-inclination-deg',command)
                else:self.assertEqual(float(command[command.index('--arrival-inclination-deg')+1]),desired)

    def test_invalid_inclinations_are_rejected_before_spawning_processes(self):
        for value in (-.1,180.1,float('nan'),float('inf'),-float('inf')):
            for endpoint in ('/api/integrate','/api/package'):
                with self.subTest(value=value,endpoint=endpoint),tempfile.TemporaryDirectory() as folder:
                    app=self.saved_app(folder)
                    with patch('gui.subprocess.Popen') as popen:
                        response=self.request(app,endpoint,dict(run='saved',candidate=ID,arrival_inclination_deg=value))
                    popen.assert_not_called()
                    arguments=response.call_args.args
                    self.assertEqual(arguments[1],400)
                    self.assertIn('between 0 and 180',arguments[0]['error'])

    def test_package_reintegrates_when_target_is_changed_or_cleared(self):
        for old,new in [(None,90.),(90.,0.),(0.,None)]:
            with self.subTest(old=old,new=new),tempfile.TemporaryDirectory() as folder:
                app=self.saved_app(folder);app.export_status=Mock(return_value={'state':'finished','report':{'arrival_inclination_option_deg':old}})
                app.integrate=Mock(return_value={'started':True})
                with patch('celestia_package.build_package') as build:
                    result=app.package('saved',ID,arrival_inclination_deg=new)
                self.assertEqual(result['state'],'integrating');build.assert_not_called()
                app.integrate.assert_called_once_with('saved',ID,None,None,0.,new)

    def test_legacy_or_unchanged_reports_reuse_the_existing_export(self):
        for report,desired in [({},None),({'arrival_inclination_option_deg':90.},90.),({'arrival_inclination_option_deg':0.},0.)]:
            with self.subTest(report=report,desired=desired),tempfile.TemporaryDirectory() as folder:
                app=self.saved_app(folder);app.export_status=Mock(return_value={'state':'finished','report':report})
                app.integrate=Mock()
                with patch('celestia_package.build_package',return_value={'state':'finished','package':'saved.zip'}) as build:
                    result=app.package('saved',ID,arrival_inclination_deg=desired)
                self.assertEqual(result['package'],'saved.zip');app.integrate.assert_not_called();build.assert_called_once()

    def test_hypothetical_capture_impulse_is_tangent_and_does_not_rotate_the_plane(self):
        class Ep:
            def state(self,body,date):return np.array([AU,0.,0.,0.,30.,0.])
        node=planet_pieces('Earth',JD0,Ep(),uin=np.array([6.,-3.,1.]),terminal=True,arrival_inclination_deg=90.)
        report=node['capture_assessment'];r=node['peri_position'];incoming=node['peri_in_velocity']
        burn=np.array(report['hypothetical_circular_capture_burn_vector_kms']);circular=np.array(report['hypothetical_circular_state_km_kms'])
        self.assertAlmostEqual(float(r@burn),0.,delta=1e-8)
        self.assertLess(float(incoming@burn),0.)
        h0=np.cross(r,incoming);h1=np.cross(circular[:3],circular[3:])
        np.testing.assert_allclose(h0/np.linalg.norm(h0),h1/np.linalg.norm(h1),atol=1e-14)
        self.assertFalse(report['capture_applied']);self.assertFalse(report['capture_cost_included_in_onboard_budget'])

if __name__=='__main__':unittest.main()
