"""Refresh exact JPL identities for public targets without changing trajectories.

The scheduled workflow resumes from a receipt watermark, resolves new IDs and
rechecks older names every 30 days. Browsers never need to query JPL directly.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,json,sys,time,urllib.parse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from network import request_json
ROOT=Path(__file__).resolve().parents[1]

def fetch(url):
    for attempt in range(4):
        try:return request_json(url,timeout=30)
        except RuntimeError:
            if attempt==3:raise
            time.sleep(1+attempt)

def resolve_label(body_id):
    body_id=str(body_id)
    # SBDB includes approved names and orbit classes. Never accept a fuzzy ID.
    if body_id.isdigit() and int(body_id)>=2000000:
        url='https://ssd-api.jpl.nasa.gov/sbdb.api?'+urllib.parse.urlencode({'spk':body_id})
        obj=fetch(url).get('object',{})
        if str(obj.get('spkid'))==body_id and (obj.get('shortname') or obj.get('fullname')):
            kind=obj.get('orbit_class',{})
            return dict(name=obj.get('shortname') or obj['fullname'],full_name=obj.get('fullname'),horizons_id=body_id,designation=obj.get('des'),
                object_type='comet' if str(obj.get('kind','')).startswith('c') else 'asteroid',lookup_url=url,
                orbit_class=kind.get('name'),orbit_class_code=kind.get('code'),classification_source=url)
    url='https://ssd.jpl.nasa.gov/api/horizons_lookup.api?'+urllib.parse.urlencode({'sstr':body_id})
    matches=[r for r in fetch(url).get('result',[]) if str(r['spkid'])==body_id]
    if len(matches)!=1:return None
    row=matches[0];name=row['name'];designation=row.get('pdes')
    if 'comet' in row.get('type','').lower() and designation and not name.startswith(designation):name=designation+'/'+name
    return dict(name=name,horizons_id=body_id,designation=designation,object_type=row.get('type'),lookup_url=url)

def live_rows(endpoint,since):
    rows=[];cursor=None;seen=set();watermark=since
    for _ in range(1000):
        args={'target':'all','limit':'100','since':since}
        if cursor:args['cursor']=cursor
        data=fetch(endpoint+'/v1/candidates?'+urllib.parse.urlencode(args));rows.extend(data['candidates'])
        watermark=max([watermark]+[r.get('received_at',since) for r in data['candidates']]);cursor=data.get('next_cursor')
        if not cursor:return rows,watermark
        if cursor in seen:raise ValueError('Repeated library cursor')
        seen.add(cursor)
    raise ValueError('Library pagination limit')

def refresh(live=False,extra=(),max_age_days=30):
    output=ROOT/'docs/data/body_names.json'
    saved=json.loads(output.read_text(encoding='utf-8')) if output.exists() else dict(schema_version=1,bodies={})
    archive=json.loads((ROOT/'docs/data/community_seed_catalog.json').read_text(encoding='utf-8'))
    rows=list(archive['candidates']);watermark=None
    if live:
        endpoint=json.loads((ROOT/'community_config.json').read_text(encoding='utf-8'))['endpoint']
        updates,watermark=live_rows(endpoint,saved.get('live_checked_through','1970-01-01T00:00:00.000Z'));rows.extend(updates)
    ids={str(b) for row in rows for b in row['body_ids']}|set(map(str,extra))|set(saved['bodies'])
    now=datetime.now(timezone.utc);stamp=now.isoformat(timespec='seconds').replace('+00:00','Z');cutoff=now-timedelta(days=max_age_days)
    changed=0;failed=[]
    def save():output.write_text(json.dumps(saved,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    for body_id in sorted(ids):
        if not body_id.isdigit() or int(body_id)<1000:continue
        old=saved['bodies'].get(body_id,{})
        try:recent=datetime.fromisoformat(old.get('resolved_at','').replace('Z','+00:00'))>=cutoff
        except (ValueError,TypeError):recent=False
        if recent and (old.get('orbit_class') or 'comet' in old.get('object_type','').lower()):continue
        try:row=resolve_label(body_id)
        except (RuntimeError,ValueError,OSError) as exc:
            print('JPL identity temporarily unavailable:',body_id,str(exc),flush=True);failed.append(body_id);continue
        if row is None:
            print('No exact JPL identity:',body_id,flush=True);failed.append(body_id);continue
        row['resolved_at']=stamp;saved['bodies'][body_id]=row;save();changed+=1
        print(body_id,row['name'],flush=True);time.sleep(.2)
    # Keep the watermark if a lookup failed so new unresolved IDs get retried.
    if watermark and not failed:saved['live_checked_through']=watermark
    saved['source']='JPL SBDB and Horizons Lookup APIs';save()
    print('JPL labels refreshed:',changed,'; unresolved:',len(failed),flush=True)
    return saved

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--live',action='store_true');p.add_argument('--ids',nargs='*',default=[]);p.add_argument('--max-age-days',type=float,default=30)
    a=p.parse_args();refresh(a.live,a.ids,a.max_age_days)
