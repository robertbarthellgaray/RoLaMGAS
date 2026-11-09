"""Precompute numeric desktop handoff records for curated Lambert examples."""
from pathlib import Path
import json,sys,argparse,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap,numpy as np
from ephemeris import BODIES,Ephemerides,DAY
from dynamics import lambert,kepler
from horizons_targets import register_target
from trajectory_transfer import checked_record
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,d):p.write_text(json.dumps(d,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
def descriptor(cache,c):
    target=c['target'];target_id=str(c.get('target_id') or c.get('provenance',{}).get('target_horizons_id') or '')
    if target in BODIES:return None
    for file in Path(cache).glob('object_'+target_id+'_*.json'):
        obj=read(file).get('target_identity')
        if obj and str(obj.get('id'))==target_id:return dict(obj,name=target,query='SPK='+target_id)
    return dict(name=target,id=target_id,command=target_id,kind='horizons_object',query='SPK='+target_id)
def reconstruct(c,cache,obj):
    if obj:register_target(obj)
    dates=[e['jd'] for e in c['events']];bodies=c['bodies'];coasts=c['coasts']
    positions=[np.array(next(s for s in coasts if abs(s['start_jd']-t)<1e-6)['r']) for t in dates[:-1]]
    last=coasts[-1];positions.append(kepler(np.array(last['r']),np.array(last['v']),(last['end_jd']-last['start_jd'])*DAY)[0])
    branches=[];controls=[]
    for i,(a,b) in enumerate(zip(dates,dates[1:])):
        coast=next(s for s in c['coasts'] if abs(s['start_jd']-a)<1e-6);actual=np.array(coast['v']);burn=coast['end_jd']<b-1e-6
        choices=[]
        for revolutions in range(9):
            for prograde in (True,False):
                for low in ((True,) if revolutions==0 else (True,False)):
                    branch=[revolutions,low,prograde]
                    try:
                        v,_=lambert(positions[i],positions[i+1],b-a,branch);error=float(np.linalg.norm(actual-v));choices.append((error,branch,v))
                    except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError):pass
        if not choices:raise ValueError('No reference Lambert branch for '+c['id'])
        error,branch,base=min(choices,key=lambda x:x[0]);branches.append(branch)
        if burn:controls.append(dict(leg_index=i,fraction=(coast['end_jd']-a)/(b-a),departure_offset_kms=(actual-base).tolist()))
        elif error>.002:raise ValueError('Could not identify coast branch '+c['id']+' error '+str(error))
    return dict(schema_version=1,sequence=c['sequence'],body_ids=[str(BODIES[b][0]) if b in BODIES else obj['id'] for b in bodies],dates_jd_tdb=dates,branches=branches,dsm_controls=controls,segments=c['coasts'],metrics=dict(launch_c3_km2_s2=c['c3'],arrival_vinf_kms=c['vinf'],total_dsm_kms=c['burns_mps']/1000,duration_years=c['years']))
def build(cache):
    docs=ROOT/'docs';directory=docs/'data/desktop';directory.mkdir(exist_ok=True)
    archive=read(docs/'data/community_seed_catalog.json');known={archive.get('curated_aliases',{}).get(r['id']):r for r in archive['candidates'] if archive.get('curated_aliases',{}).get(r['id'])}
    count=0
    for summary in read(docs/'data/index.json')['cases']:
        p=docs/'data/cases'/(summary['id']+'.json');c=read(p)
        if c['model']!='Lambert candidate':continue
        obj=descriptor(cache,c);record=known.get(c['id']) or reconstruct(c,cache,obj);record=checked_record(record)
        save(directory/(c['id']+'.json'),record);c['desktop_record_url']='data/desktop/'+c['id']+'.json'
        if obj:c['target_descriptor']={k:v for k,v in obj.items() if k in ('name','id','command','kind','designation','query','object_type')}
        save(p,c);count+=1;print(c['id'],'desktop handoff prepared',flush=True)
    print('Prepared',count,'curated Lambert transfers',flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',type=Path,required=True);a=p.parse_args();build(a.cache)
