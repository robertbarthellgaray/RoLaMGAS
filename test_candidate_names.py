"""Names persist locally while candidate physics, IDs and uploads remain unchanged."""
import bootstrap
import unittest,tempfile,json,threading
from pathlib import Path
from unittest.mock import patch
from gui import App
class CandidateNameTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.folder=self.root/'runs/trial/candidates';self.folder.mkdir(parents=True)
        self.file=self.folder/'0123456789ab.json';self.file.write_text('{"id":"0123456789ab","launch_c3_km2_s2":20}',encoding='utf-8');self.original=self.file.read_bytes()
        self.app=App.__new__(App);self.app.lock=threading.RLock();self.patch=patch('gui.HERE',self.root);self.patch.start()
    def tearDown(self):self.patch.stop();self.temp.cleanup()
    def test_save_replace_clear_and_reload_preserve_scientific_record(self):
        self.assertEqual(self.app.name_candidate('trial','0123456789ab',' Cassini reproduction ')['name'],'Cassini reproduction')
        self.app.name_candidate('trial','0123456789ab','カッシーニ / Cassini')
        names=json.loads((self.folder.parent/'candidate_names.json').read_text(encoding='utf-8'));self.assertEqual(names['0123456789ab'],'カッシーニ / Cassini');self.assertEqual(self.file.read_bytes(),self.original)
        self.app.name_candidate('trial','0123456789ab','');self.assertEqual(json.loads((self.folder.parent/'candidate_names.json').read_text(encoding='utf-8')),{})
    def test_malformed_names_and_paths_are_rejected(self):
        for name in ['x'*101,'bad\nname','bad\x00name',123]:
            with self.assertRaises(ValueError):self.app.name_candidate('trial','0123456789ab',name)
        with self.assertRaises(ValueError):self.app.name_candidate('../trial','0123456789ab','a')
        with self.assertRaises(ValueError):self.app.name_candidate('trial','../bad','a')
        with self.assertRaises(ValueError):self.app.name_candidate('trial','111111111111','a')
if __name__=='__main__':unittest.main()
