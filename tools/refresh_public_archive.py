"""Refresh the website's bundled public archive from the authoritative API.

Standard library only. All pages must succeed before the existing file changes.
"""
import argparse,json,sys,time,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from trajectory_policy import public_energy_reason,public_small_body_reason

def admitted(row,removed):
    try:
        return (row['id'] not in removed and row['classification'] in ('pass','yellow')
                and 5<=row['metrics']['launch_c3_km2_s2']<=250
                and not public_energy_reason(row) and not public_small_body_reason(row)
                and not (str(row['body_ids'][-1])=='699' and (row['dates_jd_tdb'][-1]-row['dates_jd_tdb'][0])/365.25>=20))
    except (KeyError,TypeError,ValueError,IndexError):return False

def download(endpoint,fetch=None):
    def request(url):
        for attempt in range(3):
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'RoLaMGAS-public-archive/1.0','Accept':'application/json'})
                with urllib.request.urlopen(req,timeout=40) as response:return json.load(response)
            except (OSError,ValueError):
                if attempt==2:raise
                time.sleep(2**attempt)
    fetch=fetch or request;cursor=None;seen=set();records={};watermark='1970-01-01T00:00:00.000Z'
    for page in range(2000):
        args={'target':'all','limit':'100','since':'1970-01-01T00:00:00.000Z'}
        if cursor:args['cursor']=cursor
        data=fetch(endpoint.rstrip('/')+'/v1/candidates?'+urllib.parse.urlencode(args))
        for row in data['candidates']:
            records[row['id']]=row;watermark=max(watermark,row['received_at'])
        cursor=data.get('next_cursor')
        if page%20==0:print('Downloaded',len(records),'records',flush=True)
        if not cursor:return list(records.values()),watermark
        if cursor in seen:raise ValueError('Repeated library cursor')
        seen.add(cursor)
    raise ValueError('Library page limit exceeded')

def refresh():
    output=ROOT/'docs/data/community_seed_catalog.json'
    previous=json.loads(output.read_text(encoding='utf-8'))
    endpoint=json.loads((ROOT/'docs/community_config.json').read_text())['endpoint']
    removed=json.loads((ROOT/'docs/data/library_removals.json').read_text()).get('removed',{})
    rows,watermark=download(endpoint)
    if not rows:raise ValueError('Refusing to replace archive with an empty API response')
    rows=[r for r in rows if admitted(r,removed)]
    rows.sort(key=lambda r:(r['received_at'],r['id']),reverse=True)
    doc=dict(previous,candidates=rows,received_through=watermark)
    if previous.get('candidates')==rows and previous.get('received_through')==watermark:
        print('Archive already current');return
    doc['snapshot_updated_at']=datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    text=json.dumps(doc,separators=(',',':'),ensure_ascii=False)+'\n'
    temporary=output.with_suffix('.json.tmp');temporary.write_text(text,encoding='utf-8');temporary.replace(output)
    print('Saved',len(rows),'public records; watermark',watermark,'bytes',len(text.encode()),flush=True)

if __name__=='__main__':refresh()
