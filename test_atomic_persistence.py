import bootstrap  # noqa: F401
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json,tempfile,unittest
from unittest.mock import patch
from ephemeris import atomic_json


class PersistenceTests(unittest.TestCase):
    def test_brief_windows_lock_does_not_lose_a_saved_result(self):
        original=Path.replace;attempts=[]
        def locked(path,target):
            attempts.append(path)
            if len(attempts)<3:raise PermissionError('Simulated brief file lock')
            return original(path,target)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'candidate.json'
            atomic_json(path,{'version':'old'})
            with patch.object(Path,'replace',locked):atomic_json(path,{'version':'new'})
            self.assertEqual(json.loads(path.read_text()),{'version':'new'})
            self.assertFalse(list(Path(folder).glob('*.tmp')))

    def test_concurrent_writers_publish_complete_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'status.json'
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda n:atomic_json(path,dict(index=n,payload='x'*10000)),range(24)))
            row=json.loads(path.read_text());self.assertIn(row['index'],range(24))
            self.assertEqual(row['payload'],'x'*10000)
            self.assertFalse(list(Path(folder).glob('*.tmp')))


if __name__=='__main__':unittest.main()
