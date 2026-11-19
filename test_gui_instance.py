"""Opening a preview must not silently launch workers from an older copy."""
import bootstrap
import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import gui


class GuiInstanceTests(unittest.TestCase):
    def launch(self,ping):
        with tempfile.TemporaryDirectory() as directory:
            instance=Path(directory)/'gui_instance.json'
            previous=dict(url='http://127.0.0.1:1600/',version=gui.APP_VERSION,instance_id='old-instance')
            instance.write_text(json.dumps(previous),encoding='utf-8')
            server=Mock(server_port=12345)
            with patch('sys.argv',['gui.py','--instance-file',str(instance)]),patch('gui.runtime_path',return_value='preview/RoLaMGAS.exe'),patch('gui.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(ping).encode())),patch('gui.webbrowser.open') as browser,patch('gui.App'),patch('gui.ThreadingHTTPServer',return_value=server) as factory,patch('builtins.print'):
                gui.main()
            return browser.call_args.args[0],factory.called,server.serve_forever.called

    def test_same_version_different_executable_starts_the_requested_preview(self):
        ping=dict(app='trajectory-explorer-gui',version=gui.APP_VERSION,instance_id='old-instance',runtime_path='old-release/RoLaMGAS.exe')
        self.assertEqual(self.launch(ping),('http://127.0.0.1:12345/',True,True))

    def test_legacy_server_without_runtime_identity_is_not_reused(self):
        ping=dict(app='trajectory-explorer-gui',version=gui.APP_VERSION,instance_id='old-instance')
        self.assertEqual(self.launch(ping),('http://127.0.0.1:12345/',True,True))

    def test_matching_version_executable_and_instance_still_reuse_the_server(self):
        ping=dict(app='trajectory-explorer-gui',version=gui.APP_VERSION,instance_id='old-instance',runtime_path='preview/RoLaMGAS.exe')
        self.assertEqual(self.launch(ping),('http://127.0.0.1:1600/',False,False))

    def test_stale_instance_id_is_not_reused_even_for_the_same_executable(self):
        ping=dict(app='trajectory-explorer-gui',version=gui.APP_VERSION,instance_id='another-instance',runtime_path='preview/RoLaMGAS.exe')
        self.assertEqual(self.launch(ping),('http://127.0.0.1:12345/',True,True))


if __name__=='__main__':unittest.main()
