"""Offline frozen-app regression for the saved-seed scheduler on every native OS."""
from pathlib import Path
import argparse,json,os,subprocess,sys,time
from datetime import timedelta


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--app',required=True);parser.add_argument('--directory',required=True);args=parser.parse_args()
    root=Path(args.directory).resolve();root.mkdir(parents=True,exist_ok=True)
    os.environ['ROLAMGAS_DATA_DIR']=str(root);os.environ['ROLAMGAS_COMMUNITY_URL']=''
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from app_paths import ensure_data,RESOURCE_ROOT
    ensure_data()
    from ephemeris import EPOCH,JD0,atomic_json
    from mission_search import normalize,routes_for,get_ephemerides
    from community import record_variables
    from dynamics import Model
    record=next(r for r in json.loads((RESOURCE_ROOT/'community_seed_catalog.json').read_text())['candidates'] if r['sequence']=='EVEEJ')
    iso=lambda t:(EPOCH+timedelta(days=t-JD0)).isoformat(timespec='microseconds')
    dates=record['dates_jd_tdb'];sequence=record['sequence']
    config=dict(target='Jupiter',sequences=[sequence],launch_start=iso(dates[0]),launch_end=iso(dates[0]),
                event_windows=[[iso(t),iso(t)] for t in dates],
                route_overrides={sequence:dict(branch_options=[[b] for b in record['branches']])},
                min_c3=6.25,max_c3=1e6,max_arrival_vinf_kms=1000,vinf_tolerance_mps=2000,
                max_dsm_kms=1000,max_single_dsm_kms=1000,max_powered_flyby_kms=1000,max_years=100,
                samples_per_sequence=8,refinements_per_sequence=1,max_nfev=1,cost_refinements=1,
                workers=1,batches=1,branch_families=1,cache=str(root/'cache'))
    c=normalize(config);routes=routes_for(c);ep=get_ephemerides(c,routes);model=Model(routes[0],c,ep)
    x,branches=record_variables(record,model);q=model.evaluate(x,branches)
    assert model.accepted(q),'Fixture must be feasible under the deliberately broad scheduler-test limits'
    q.update(id='abcdef123456',status='passes_configured_patched_conic_screen',discovered_unix=time.time())
    prior=root/'runs/source';prior.mkdir(parents=True,exist_ok=True)
    atomic_json(prior/'run_manifest.json',dict(config=c,routes=routes));atomic_json(prior/'results.json',dict(candidates=[q]))
    output=root/'runs/seeded';output.mkdir(parents=True,exist_ok=True);atomic_json(output/'request.json',config)
    with (output/'console.log').open('w',encoding='utf-8') as log:
        process=subprocess.run([str(Path(args.app).resolve()),'--rolamgas-module','gui_worker','--output',str(output)],
                               env=dict(os.environ,ROLAMGAS_DATA_DIR=str(root),ROLAMGAS_COMMUNITY_URL=''),stdout=log,stderr=subprocess.STDOUT,timeout=200)
    text=(output/'console.log').read_text(encoding='utf-8',errors='replace')
    assert process.returncode==0,text[-6000:]
    state=json.loads((output/'gui_status.json').read_text());assert state['state']=='finished',state
    jobs=[json.loads(p.read_text()) for p in (output/'checkpoints').glob('*.json')]
    assert len(jobs)==1 and isinstance(jobs[0]['job_id'],str),jobs
    assert jobs[0]['known_seed_refinements']>0,'Frozen smoke did not exercise saved-seed jobs'
    result=dict(frozen_seeded_search=True,completed_jobs=1,known_seed_refinements=jobs[0]['known_seed_refinements'])
    atomic_json(root/'seeded_smoke_result.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
