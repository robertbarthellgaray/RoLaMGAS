"""Offline complete-chain startup smoke test for source or a native app.

Uses a disposable data directory and disables all community traffic.
"""
from pathlib import Path
import argparse,json,os,subprocess,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--app',type=Path);p.add_argument('--directory',required=True,type=Path);a=p.parse_args()
    root=a.directory.resolve();root.mkdir(parents=True,exist_ok=True)
    os.environ['ROLAMGAS_DATA_DIR']=str(root);os.environ['ROLAMGAS_COMMUNITY_URL']=''
    from app_paths import ensure_data,RESOURCE_ROOT
    from earth_return_seeds import chain_reference
    from ephemeris import atomic_json,calendar
    ensure_data();atomic_json(root/'community_settings.json',dict(share_candidates=False,use_candidates=False,endpoint=''))
    dates=chain_reference()['donor']['dates_jd_tdb']
    c=dict(target='Jupiter',sequences=['EdvEVEEJ'],launch_start='2029-01-01',launch_end='2043-01-01',
           event_windows=[[calendar(t-2).replace(' TDB',''),calendar(t+2).replace(' TDB','')] for t in dates],
           min_c3=6.25,max_c3=10.,max_dsm_kms=1.5,max_single_dsm_kms=.7,max_arrival_vinf_kms=15.,
           minimum_altitude_km={'Earth':200.,'Venus':300.},max_years=20.,cache=str(root/'cache'),
           workers=1,branch_families=1,samples_per_sequence=8,refinements_per_sequence=1,max_nfev=1,
           search_objective='c3',cost_refinements=1)
    output=root/'runs/full_chain';output.mkdir(parents=True,exist_ok=True);atomic_json(output/'request.json',c)
    command=([str(a.app.resolve()),'--rolamgas-module','gui_worker'] if a.app else [sys.executable,str(RESOURCE_ROOT/'gui_worker.py')])+['--output',str(output),'--local-search']
    started=time.monotonic()
    with (output/'console.log').open('w',encoding='utf-8') as log:
        fit=subprocess.run(command,env=dict(os.environ),stdout=log,stderr=subprocess.STDOUT,timeout=240)
    text=(output/'console.log').read_text(encoding='utf-8',errors='replace');assert fit.returncode==0,text[-8000:]
    state=json.loads((output/'gui_status.json').read_text(encoding='utf-8'));assert state['state']=='finished',state
    archive=json.loads((output/'reused_candidates.json').read_text(encoding='utf-8'))
    assert archive['chain_seed_stats']['accepted']==5,archive['chain_seed_stats']
    jobs=[json.loads(p.read_text(encoding='utf-8')) for p in (output/'checkpoints').glob('*.json')]
    assert len(jobs)==1 and jobs[0]['known_seed_refinements']>=5,jobs
    result=json.loads((output/'results.json').read_text(encoding='utf-8'));assert result['distinct_accepted']>=5
    low=min(result['candidates'],key=lambda q:q['launch_c3_km2_s2'])
    assert abs(low['launch_c3_km2_s2']-6.25)<1e-7 and low['total_dsm_kms']<.5
    assert low['max_vinf_mismatch_mps']<.03
    report=dict(frozen=bool(a.app),elapsed_seconds=time.monotonic()-started,complete_chain_starters=archive['chain_seed_stats']['accepted'],
                completed_jobs=len(jobs),known_seed_refinements=jobs[0]['known_seed_refinements'],
                c3=low['launch_c3_km2_s2'],dsm_mps=1000*low['total_dsm_kms'],max_mismatch_mps=low['max_vinf_mismatch_mps'],
                community_disabled=True,output=str(output))
    atomic_json(root/'full_chain_smoke_result.json',report);print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
