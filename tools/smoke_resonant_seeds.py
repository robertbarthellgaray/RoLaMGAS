"""Offline source/frozen regression for the new UOP and Mercury physical starters."""
from pathlib import Path
import argparse,json,os,subprocess,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--app',type=Path);p.add_argument('--directory',required=True,type=Path);a=p.parse_args()
    root=a.directory.resolve();root.mkdir(parents=True,exist_ok=True)
    os.environ['ROLAMGAS_DATA_DIR']=str(root);os.environ['ROLAMGAS_COMMUNITY_URL']=''
    from app_paths import ensure_data,RESOURCE_ROOT
    from ephemeris import atomic_json
    ensure_data();atomic_json(root/'community_settings.json',dict(share_candidates=False,use_candidates=False,endpoint=''))
    reports=[]
    for target,seq,expected in [('Uranus','EVEdvEU',4),('Mercury','EVVMedvMedvMedvMedvMe',1)]:
        config=dict(target=target,sequences=[seq],launch_start='2034-05-01' if target=='Uranus' else '2033-01-01',
                    launch_end='2034-06-15' if target=='Uranus' else '2034-01-01',min_c3=20. if target=='Uranus' else 6.25,
                    max_c3=30. if target=='Uranus' else 50.,max_dsm_kms=.7 if target=='Uranus' else 1.5,
                    max_single_dsm_kms=.7,max_arrival_vinf_kms=7. if target=='Uranus' else 8.,max_years=17.,vinf_tolerance_mps=.1,
                    workers=1,branch_families=1,samples_per_sequence=8,refinements_per_sequence=1,max_nfev=1,cost_refinements=1,cache=str(root/'cache'))
        output=root/'runs'/target.lower();output.mkdir(parents=True,exist_ok=True);atomic_json(output/'request.json',config)
        command=([str(a.app.resolve()),'--rolamgas-module','gui_worker'] if a.app else [sys.executable,str(RESOURCE_ROOT/'gui_worker.py')])+['--output',str(output),'--local-search']
        started=time.monotonic()
        with (output/'console.log').open('w',encoding='utf-8') as log:
            run=subprocess.run(command,env=dict(os.environ),stdout=log,stderr=subprocess.STDOUT,timeout=240,
                               **({'creationflags':subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else {}))
        text=(output/'console.log').read_text(encoding='utf-8',errors='replace');assert run.returncode==0,text[-8000:]
        state=json.loads((output/'gui_status.json').read_text(encoding='utf-8'));assert state['state']=='finished',state
        archive=json.loads((output/'reused_candidates.json').read_text(encoding='utf-8'))
        assert archive['resonant_seed_stats']['accepted']==expected,archive['resonant_seed_stats']
        checkpoints=[json.loads(f.read_text(encoding='utf-8')) for f in (output/'checkpoints').glob('*.json')]
        assert len(checkpoints)==1 and checkpoints[0]['known_seed_refinements']>=expected,checkpoints
        summary=json.loads((output/'results.json').read_text(encoding='utf-8'));assert summary['distinct_accepted']>=expected
        best=min(summary['candidates'],key=lambda q:q['duration_years'] if target=='Uranus' else q['arrival_vinf_kms'])
        assert best['max_vinf_mismatch_mps']<.1 and best['min_turn_margin_deg']>-1e-8
        reports.append(dict(target=target,frozen=bool(a.app),starter_count=expected,elapsed_seconds=time.monotonic()-started,
                            known_seed_refinements=checkpoints[0]['known_seed_refinements'],c3=best['launch_c3_km2_s2'],dsm_mps=1000*best['total_dsm_kms'],
                            arrival_vinf_kms=best['arrival_vinf_kms'],years=best['duration_years'],community_disabled=True))
        print(json.dumps(reports[-1]),flush=True)
    atomic_json(root/'resonant_smoke_result.json',reports)

if __name__=='__main__':main()
