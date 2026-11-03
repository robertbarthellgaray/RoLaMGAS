"""Archive historical passing results without applying today's search limits.

Only public science fields are emitted. Original classifications are submissions,
not a new validation. Consumers must recompute orbital dynamics before reuse.
Reads final results, checkpoints and individual cards; never uploads automatically.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
PLANETS=dict(Mercury='199',Venus='299',Earth='399',Mars='499',Jupiter='599',Saturn='699',Uranus='799',Neptune='899')
METRICS=['launch_c3_km2_s2','total_dsm_kms','arrival_vinf_kms','duration_years','max_vinf_mismatch_mps']

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def discover(roots):
    skip={'.git','.venv','node_modules','__pycache__','cache','numba_cache','.build','.build_deps','.browser_test','models','textures','dist','build'}
    folders=set()
    for root in roots:
        for folder,dirs,files in os.walk(root):
            dirs[:]=[d for d in dirs if d.lower() not in skip]
            if 'run_manifest.json' in files:folders.add(Path(folder))
    for i,folder in enumerate(sorted(folders)):
        try:manifest=read(folder/'run_manifest.json')
        except (ValueError,OSError) as error:
            print(f'Could not read saved manifest {folder}: {error}',file=sys.stderr,flush=True);continue
        files=[folder/'results.json',folder/'live.json']+list((folder/'checkpoints').glob('*.json'))
        cards=list((folder/'candidates').glob('*.json'))
        files += [p for p in cards if not p.name.endswith('.card.json') or not p.with_name(p.name.replace('.card.json','.json')).exists()]
        for source in files:
            if not source.is_file():continue
            try:
                doc=read(source)
                if not isinstance(doc,dict):continue
                if 'sequence' in doc:rows=[(doc,False)]
                else:rows=[(q,False) for q in doc.get('candidates',[])]+[(q,True) for q in doc.get('accepted',[])]
                for q,accepted in rows:
                    if isinstance(q,dict) and (q.get('status','').startswith('passes') or accepted):
                        yield str(source),q,manifest.get('config',{}),manifest.get('routes',[])
            except (ValueError,OSError,TypeError):continue
        print(f'Scanned {i+1}/{len(folders)} saved runs',flush=True)

def project(source,q,config,routes):
    if not q.get('status','').startswith('passes') and q.get('status'):
        raise ValueError('Not a historical passing classification')
    identities=dict(PLANETS)
    extension=config.get('append_flyby') or {}
    descriptors=[config.get('target_object'),extension.get('original_target_object')]+list(extension.get('original_target_objects') or [])
    for value in descriptors:
        if isinstance(value,dict) and value.get('name') and value.get('id'):identities[value['name']]=str(value['id'])
    bodies=q['bodies'];ids=[identities[name] for name in bodies]
    route=next((r for r in routes if r.get('id')==q['sequence'] and r.get('bodies')==bodies),None)
    if route is None and extension.get('route',{}).get('id')==q['sequence']:route=extension['route']
    n=len(bodies);controls=[]
    if route is not None and 'x' in q:
        for j,leg in enumerate(route.get('dsm_legs',[])):
            k=n+4*j;x=q['x']
            controls.append(dict(leg_index=leg,fraction=.1+.8*x[k],departure_offset_kms=[(v*2-1)*config['dsm_velocity_box_kms'] for v in x[k+1:k+4]]))
    else:
        # Some old gallery exports omit optimizer variables. Recover their
        # physical DSM controls from the saved arc and original Lambert branch.
        from dynamics import lambert
        import numpy as np
        for dsm in sorted(q.get('dsms',[]),key=lambda d:d['leg_index']):
            leg=dsm['leg_index'];a,b=q['dates_jd_tdb'][leg:leg+2]
            segment=next(v for v in q['segments'] if abs(v['start_jd']-a)<1e-8)
            end=q['events'][leg+1]['planet_state_km_kms'][:3]
            nominal,_=lambert(np.array(segment['r'],float),np.array(end,float),b-a,q['branches'][leg])
            controls.append(dict(leg_index=leg,fraction=(dsm['julian_date_tdb']-a)/(b-a),departure_offset_kms=(np.array(segment['v'])-nominal).tolist()))
    saved=q.get('discovered_unix')
    if not isinstance(saved,(int,float)) or not math.isfinite(saved):saved=Path(source).stat().st_mtime
    # Old runs lack discovery timestamps: their saved-file time is the fallback.
    stamp=datetime.fromtimestamp(min(saved,time.time()),timezone.utc).isoformat()
    metrics={key:float(q[key]) for key in METRICS}
    metrics['duration_years']=(q['dates_jd_tdb'][-1]-q['dates_jd_tdb'][0])/365.25
    return dict(schema_version=1,engine_version=q.get('engine_version','historical-import'),sequence=q['sequence'],body_ids=ids,
        dates_jd_tdb=q['dates_jd_tdb'],branches=q['branches'],dsm_controls=controls,classification='pass',solved_at=stamp,
        metrics=metrics,segments=[{key:s[key] for key in ['start_jd','end_jd','r','v']} for s in q['segments']])

def canonical_records(records):
    # Use the production validator and its hash, including JavaScript's canonical
    # number serialization. This avoids Python/JS 0.0-vs-0 duplicate IDs.
    script="""import {readFileSync} from 'node:fs';
const {validate}=await import(process.argv[1]);const records=JSON.parse(readFileSync(0,'utf8'));
const valid=[],invalid=[];for(let i=0;i<records.length;i++)try{valid.push(await validate(records[i]))}catch(e){invalid.push({index:i,error:e.message})}
process.stdout.write(JSON.stringify({valid,invalid}));"""
    result=subprocess.run(['node','--input-type=module','-e',script,(ROOT/'community_backend/worker.mjs').as_uri()],
        input=json.dumps(records,allow_nan=False),text=True,encoding='utf-8',capture_output=True,check=True)
    return json.loads(result.stdout)

def build(entries,output,report,existing=None,private_report=None):
    entries=list(entries)
    by_id={q.get('id'):(source,q,config,routes) for source,q,config,routes in entries if q.get('bodies') and q.get('segments') and q.get('id')}
    projected=[];failures=[];count=0;seen=set();resolved_summaries=0
    for source,q,config,routes in entries:
        if not q.get('bodies') and q.get('id') in by_id:
            source,q,config,routes=by_id[q['id']];resolved_summaries+=1
        count+=1
        # Avoid repeatedly converting copies in final output, checkpoint and card.
        key=json.dumps([q.get('sequence'),q.get('bodies'),q.get('dates_jd_tdb'),q.get('branches'),q.get('x'),config.get('dsm_velocity_box_kms')],sort_keys=True)
        if key in seen:continue
        seen.add(key)
        try:projected.append(project(source,q,config,routes))
        except (ValueError,KeyError,TypeError,IndexError,OSError) as error:
            failures.append(dict(source=source,candidate=q.get('id'),error=str(error)))
    previous=read(existing) if existing else {}
    projected+=previous.get('candidates',[])
    validated=canonical_records(projected)
    records={}
    for record in validated['valid']:
        prior=records.get(record['id'])
        if prior is None or record['solved_at']<prior['solved_at']:records[record['id']]=record
    candidates=sorted(records.values(),key=lambda r:(r['body_ids'][-1],r['solved_at'],r['id']))
    doc=dict(schema_version=1,description='All recovered historical passing searches, deduplicated by physical encounter controls. Original search limits and solver versions differ; classifications are submitted and must be revalidated before reuse. Legacy solve timestamps fall back to file save time.',candidates=candidates)
    if previous.get('curated_aliases'):doc['curated_aliases']={k:v for k,v in previous['curated_aliases'].items() if k in records}
    if previous.get('received_through'):doc['received_through']=previous['received_through']
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text(json.dumps(doc,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    summary=dict(passing_occurrences=count,distinct_saved_parameterizations=len(seen),published_candidates=len(candidates),resolved_summary_references=resolved_summaries,projection_failures=len(failures),schema_failures=len(validated['invalid']),by_target=dict(Counter(r['body_ids'][-1] for r in candidates)),archive_bytes=Path(output).stat().st_size)
    Path(report).write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    if private_report:Path(private_report).write_text(json.dumps(dict(projection_failures=failures,schema_failures=validated['invalid']),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary),flush=True)
    return doc,summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',action='append',default=[]);p.add_argument('--snapshot',help='Optional private cached input snapshot from an interrupted/manual scan');p.add_argument('--existing');p.add_argument('--output',required=True);p.add_argument('--report',required=True);p.add_argument('--private-report')
    a=p.parse_args()
    if not a.root and not a.snapshot:p.error('Specify at least one --root or a private --snapshot')
    entries=read(a.snapshot) if a.snapshot else discover(a.root)
    build(entries,a.output,a.report,a.existing,a.private_report)
