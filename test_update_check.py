import tempfile,time,threading,unittest
from pathlib import Path
from update_check import release_status,UpdateCheck

def release(tag='rolamgas-v0.2.7',**kwargs):
    return dict(tag_name=tag,html_url='https://github.com/robertbarthellgaray/RoLaMGAS/releases/tag/'+tag,**kwargs)

class UpdateTests(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(release_status('0.2.6',release())['state'],'available')
        self.assertEqual(release_status('0.2.7-test3',release())['state'],'available')
        self.assertEqual(release_status('0.2.7-test3',release('rolamgas-v0.2.6'))['state'],'up_to_date')
        self.assertEqual(release_status('0.2.7',release())['state'],'up_to_date')
        self.assertEqual(release_status('0.2.9',release('rolamgas-v0.2.10'))['state'],'available')
    def test_rejects_unexpected_releases(self):
        with self.assertRaises(ValueError):release_status('0.2.6',release(prerelease=True))
        with self.assertRaises(ValueError):release_status('0.2.6',dict(release(),html_url='https://example.com/installer.exe'))
        with self.assertRaises(ValueError):release_status('0.2.6',release('not-a-version'))
    def test_nonblocking_and_one_request_at_a_time(self):
        event=threading.Event();calls=[]
        def fetch(url,timeout):calls.append((url,timeout));event.wait(2);return release()
        with tempfile.TemporaryDirectory() as tmp:
            check=UpdateCheck('0.2.6',Path(tmp)/'check.json',fetcher=fetch)
            start=time.monotonic();check.start();check.start()
            self.assertLess(time.monotonic()-start,.2);self.assertEqual(check.snapshot()['state'],'checking')
            event.set();check.thread.join(3);self.assertEqual(len(calls),1);self.assertEqual(check.snapshot()['state'],'available')
    def test_offline_is_nonfatal(self):
        def offline(*args,**kwargs):raise OSError('offline')
        with tempfile.TemporaryDirectory() as tmp:
            check=UpdateCheck('0.2.7-test3',Path(tmp)/'check.json',fetcher=offline);check.start();check.thread.join(3)
            self.assertEqual(check.snapshot()['state'],'unavailable')

if __name__=='__main__':unittest.main()
