"""Background release notification. Never downloads or executes an installer."""
import re,threading,time
from urllib.parse import urlparse
from network import request_json
from ephemeris import atomic_json

LATEST='https://api.github.com/repos/robertbarthellgaray/RoLaMGAS/releases/latest'
RELEASES='https://github.com/robertbarthellgaray/RoLaMGAS/releases/latest'

def version_key(value):
    match=re.fullmatch(r'(?:rolamgas-)?v?(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc|test)(\d+))?',str(value),re.I)
    if not match:raise ValueError('Invalid release version')
    major,minor,patch,stage,build=match.groups()
    return int(major),int(minor),int(patch),1 if stage is None else 0,int(build or 0)

def release_status(current,release):
    if not isinstance(release,dict) or release.get('draft') or release.get('prerelease'):raise ValueError('Not a public stable release')
    tag=release.get('tag_name','');latest=version_key(tag);installed=version_key(current)
    link=release.get('html_url','');parsed=urlparse(link)
    if parsed.scheme!='https' or parsed.netloc!='github.com' or not parsed.path.startswith('/robertbarthellgaray/RoLaMGAS/releases/tag/') or parsed.query or parsed.fragment:
        raise ValueError('Unexpected release URL')
    return dict(state='available' if latest>installed else 'up_to_date',current=current,latest=tag.removeprefix('rolamgas-').removeprefix('v'),url=link,checked_at=time.time())

class UpdateCheck:
    def __init__(self,current,cache_path,fetcher=request_json):
        self.current=current;self.path=cache_path;self.fetcher=fetcher;self.lock=threading.Lock();self.thread=None
        self.result=dict(state='not_checked',current=current,url=RELEASES)
    def snapshot(self):
        with self.lock:return dict(self.result)
    def start(self):
        with self.lock:
            if self.thread is not None and self.thread.is_alive():return
            self.result=dict(self.result,state='checking')
            self.thread=threading.Thread(target=self._check,name='release-update-check',daemon=True);self.thread.start()
    def _check(self):
        try:
            result=release_status(self.current,self.fetcher(LATEST,timeout=8))
            try:atomic_json(self.path,result)
            except OSError:pass
        except Exception:
            result=dict(state='unavailable',current=self.current,url=RELEASES,checked_at=time.time())
        with self.lock:self.result=result
