"""A failed or cancelled export must release the slot without losing candidates."""
import bootstrap
import io,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from gui import App
from ephemeris import atomic_json

class CancelIntegrationTests(unittest.TestCase):
    def fixture(self,folder):
        app=App();root=app.folder('saved');ident='a'*12;output=root/'exports'/ident
        output.mkdir(parents=True);(root/'candidates').mkdir();atomic_json(root/'candidates'/(ident+'.json'),dict(id=ident))
        atomic_json(root/'request.json',dict(target='Jupiter'))
        process=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        app.integrations[('saved',ident)]=process;app.integration_outputs[('saved',ident)]=output
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        return app,root,ident,output,process

    def test_cancel_waits_for_worker_and_preserves_candidate_and_old_export(self):
        with tempfile.TemporaryDirectory() as folder,patch('gui.HERE',Path(folder)):
            app,root,ident,out,process=self.fixture(folder);atomic_json(out/'integration_status.json',dict(state='running'))
            old=root/'export_history/previous';old.mkdir(parents=True);(old/'trajectory.xyzv').write_bytes(b'original')
            self.assertEqual(app.active_integration()['candidate'],ident)
            self.assertTrue(app.cancel_integration('saved',ident)['stopped']);self.assertIsNotNone(process.poll())
            self.assertEqual(app.export_status('saved',ident)['state'],'cancelled');self.assertIsNone(app.active_integration())
            self.assertTrue((root/'candidates'/(ident+'.json')).exists());self.assertEqual((old/'trajectory.xyzv').read_bytes(),b'original')
            self.assertFalse(app.cancel_integration('saved',ident)['stopped'])

    def test_failed_worker_is_reaped_and_another_candidate_can_see_active_job(self):
        with tempfile.TemporaryDirectory() as folder,patch('gui.HERE',Path(folder)):
            app,root,ident,out,process=self.fixture(folder);atomic_json(out/'integration_status.json',dict(state='running'))
            self.assertEqual(app.export_status('saved','b'*12)['active_integration']['candidate'],ident)
            atomic_json(out/'integration_status.json',dict(state='failed',message='Inclination unavailable'))
            self.assertIsNone(app.active_integration());self.assertIsNotNone(process.poll())
            self.assertEqual(app.export_status('saved',ident)['message'],'Inclination unavailable')

    def test_windowed_worker_errors_exit_without_unhandled_exception_dialog(self):
        import rolamgas
        with patch('app_paths.ensure_data'),patch.object(sys,'argv',['RoLaMGAS','--rolamgas-module','integrate_export']),patch('runpy.run_module',side_effect=ValueError('Inclination unavailable')),patch('sys.stderr',new_callable=io.StringIO) as error:
            with self.assertRaises(SystemExit) as raised:rolamgas.main()
            self.assertEqual(raised.exception.code,1);self.assertIn('Inclination unavailable',error.getvalue())

if __name__=='__main__':unittest.main()
