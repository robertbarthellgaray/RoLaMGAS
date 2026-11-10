"""Check dated study first-leg Lambert branches against a local JPL cache.

No downloads, optimization or uploads. A first-leg check does not validate an
entire mission. For first-leg DSM routes, the result is only the zero-offset
ballistic initialization, not the designed departure energy.
"""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
import numpy as np
from dynamics import lambert
from ephemeris import Ephemerides,jd
from mission_search import load_database,resolve_route

ROOT=Path(__file__).resolve().parents[1]

def check(mission,cache,database):
    a,b=mission['dates'][:2];start,end=jd(a),jd(b)
    route=resolve_route(mission['sequence'],database,mission.get('target_object'))
    ep=Ephemerides(cache,mission['bodies'][:2],start-1,end+1,1.)
    earth,target=(ep.state(body,t) for body,t in zip(mission['bodies'][:2],(start,end)))
    trials=[]
    for branch in route['branch_options'][0]:
        try:
            va,_=lambert(earth[:3],target[:3],end-start,branch)
            trials.append(dict(branch=branch,c3_km2_s2=float(np.sum((va-earth[3:])**2))))
        except (ValueError,RuntimeError,AssertionError,OverflowError):continue
    return dict(name=mission['name'],reported_c3=mission['c3'],first_leg_has_dsm=0 in route['dsm_legs'],
                trials=trials,full_chain_validated=False)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'studies/decadal_seed_review/departure_checks.json')
    args=parser.parse_args();db=load_database();rows=[]
    missions=json.loads((ROOT/'departure_seeds/decadal_missions.json').read_text(encoding='utf-8'))['missions']
    for mission in missions:
        if not mission['seed_eligible'] or not mission.get('dates'):continue
        try:row=check(mission,args.cache,db)
        except (ValueError,OSError) as exc:row=dict(name=mission['name'],error=str(exc),full_chain_validated=False)
        rows.append(row);print(json.dumps(row),flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(dict(purpose='First-leg initialization checks only; no accepted trajectories',checks=rows),indent=2)+'\n',encoding='utf-8')
    if any(r.get('error') or not r.get('trials') for r in rows):raise SystemExit(1)

if __name__=='__main__':main()
