"""Refresh public small-body labels from JPL Horizons Lookup; no science is changed.
Run manually after new unnamed target IDs appear. Sequential requests, saved
identities and lookup URLs ship with the static site; browsers never need JPL.
"""
from pathlib import Path
import argparse,json,sys,time,urllib.parse,urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from network import request_json
ROOT=Path(__file__).resolve().parents[1]
def fetch(url):
    for attempt in range(4):
        try:return request_json(url,timeout=30)
        except RuntimeError:
            if attempt==3:raise
            time.sleep(1+attempt)

def refresh(live=False,extra=()):
    output=ROOT/'docs/data/body_names.json'
    saved=json.loads(output.read_text(encoding='utf-8')) if output.exists() else dict(schema_version=1,source='JPL Horizons Lookup API',bodies={})
    rows=json.loads((ROOT/'docs/data/community_seed_catalog.json').read_text(encoding='utf-8'))['candidates']
    if live:
        endpoint=json.loads((ROOT/'community_config.json').read_text(encoding='utf-8'))['endpoint'];cursor=None;seen=set()
        for page in range(100):
            args={'target':'all','limit':'100'}
            if cursor:args['cursor']=cursor
            data=fetch(endpoint+'/v1/candidates?'+urllib.parse.urlencode(args));rows.extend(data['candidates']);cursor=data.get('next_cursor')
            if not cursor:break
            if cursor in seen:raise ValueError('Repeated library cursor')
            seen.add(cursor)
        else:raise ValueError('Library pagination limit')
    counts={}
    for row in rows:
        key=str(row['body_ids'][-1]);counts[key]=counts.get(key,0)+1
    ids={str(b) for row in rows for b in row['body_ids']}|set(extra)
    for body_id in sorted(ids):
        if int(body_id)<1000 or body_id in saved['bodies']:continue
        url='https://ssd.jpl.nasa.gov/api/horizons_lookup.api?'+urllib.parse.urlencode({'sstr':body_id})
        data=fetch(url);matches=[r for r in data.get('result',[]) if str(r['spkid'])==body_id]
        if len(matches)!=1:
            print('No exact JPL identity:',body_id,flush=True);continue
        m=matches[0];saved['bodies'][body_id]=dict(name=m['name'],horizons_id=body_id,designation=m.get('pdes'),object_type=m.get('type'),lookup_url=url)
        print(body_id,m['name'],flush=True)
        # Save each identity so an interrupted run can resume without repeat calls.
        output.write_text(json.dumps(saved,indent=2)+'\n',encoding='utf-8');time.sleep(.2)
    print('Library target counts:',json.dumps(counts,sort_keys=True),flush=True)
    return saved
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--live',action='store_true');p.add_argument('--ids',nargs='*',default=['20225088','20469219','20010253']);a=p.parse_args();refresh(a.live,a.ids)
