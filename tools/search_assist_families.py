"""Repeatable local continuation searches for underrepresented Jupiter/Saturn routes.

Uses saved physical candidates as starting points, then re-solves encounter
dates and explicit DSM controls with current JPL vectors and screening limits.
No cloud AI service is involved. Results are local; no automatic publishing.
"""
from pathlib import Path
import argparse,json,sys,time,copy
from collections import Counter
from concurrent.futures import ProcessPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bootstrap,numpy as np
from scipy.optimize import least_squares
from mission_search import normalize,routes_for
from dynamics import Model,C3BoundsError
from ephemeris import Ephemerides,calendar,jd,atomic_json
from community import record_variables,public_record,encounter_key

def jobs_for(records):
    jobs=[]
    def add(record,sequence,shifts,fraction=.8):
        for shift in shifts:
            jobs.append(dict(source=record,sequence=sequence,shift_days=shift,fraction=fraction))
    # Keep distinct launch seasons, not dozens of near-identical seed records.
    def seeds(sequence,count):
        rows=sorted((r for r in records if r['sequence']==sequence and r['metrics']['max_vinf_mismatch_mps']<=1),key=lambda r:r['metrics']['duration_years'])
        chosen=[];months=set()
        for r in rows:
            month=calendar(r['dates_jd_tdb'][0])[:7]
            if month in months:continue
            chosen.append(r);months.add(month)
            if len(chosen)>=count:break
        return chosen
    for r in seeds('EVVEJ',8):add(r,'EVVEJ',[-32.,-16.,16.,32.])
    for r in seeds('EVdvEEJ',8):add(r,'EVdvEEJ',[-32.,-16.,16.,32.])
    for r in seeds('EVEEJ',6):add(r,'EVdvEEJ',[-45.,45.])
    for r in seeds('EVVEJS',3):
        add(r,'EVdvVEJS',[-45.,0.,45.])
        add(r,'EVdvVEJS',[-365.25,365.25,8*365.25,16*365.25])
    # Cassini's own calendar cannot simply be translated: explicitly try and
    # record failures too, rather than treating a resonance as a guarantee.
    for r in seeds('EVdvVEJS',2):add(r,'EVdvVEJS',[32*365.25,40*365.25,48*365.25])
    for r in seeds('EVEES',4):add(r,'EVdvEES',[-30.,30.])
    return jobs

def solve(job,cache,max_nfev):
    started=time.monotonic();source=job['source'];sequence=job['sequence'];saturn=sequence.endswith('S')
    record=copy.deepcopy(source);record['sequence']=sequence
    if 'dv' in sequence and not record['dsm_controls']:
        record['dsm_controls']=[dict(leg_index=1,fraction=job['fraction'],departure_offset_kms=[0.,0.,0.])]
    dates=np.array(record['dates_jd_tdb'])+job['shift_days'];record['dates_jd_tdb']=dates.tolist()
    if not jd('2027-01-01')<=dates[0]<jd('2056-01-01'):return dict(skipped=True)
    # Give downstream encounters progressively more freedom than launch.
    widths=[60.]+[100.+35*i for i in range(1,len(dates))]
    max_years=12. if sequence=='EVdvEES' else (8.5 if saturn else 9.)
    config=normalize(dict(target='Saturn' if saturn else 'Jupiter',sequences=[sequence],
        launch_start=calendar(dates[0]-widths[0])[:10],launch_end=calendar(dates[0]+widths[0])[:10],
        event_windows_jd=[[float(t-w),float(t+w)] for t,w in zip(dates,widths)],
        route_overrides={sequence:dict(leg_days=[[max(1.,float(d)*.5),float(d)*1.5+1] for d in np.diff(dates)],branch_options=[[b] for b in record['branches']])},
        min_c3=5.,max_c3=30.,max_years=max_years,max_arrival_vinf_kms=12.,max_dsm_kms=.7,
        max_single_dsm_kms=.7,vinf_tolerance_mps=1.,powered_flybys=False,
        minimum_altitude_km={'Earth':200.,'Venus':300.},cache=str(cache)))
    route=routes_for(config)[0];ep=Ephemerides(cache,route['bodies'],float(dates[0]-widths[0]-2),float(dates[-1]+widths[-1]+2),1.)
    model=Model(route,config,ep);x,branches=record_variables(record,model)
    try:
        fit=least_squares(lambda z:model.residual(z,branches),x,bounds=(0,1),max_nfev=max_nfev,ftol=1e-10,xtol=1e-10,gtol=1e-10)
        q=model.evaluate(fit.x,branches)
        accepted=bool(model.accepted(q))
        result=dict(sequence=sequence,source_id=source['id'],shift_days=job['shift_days'],accepted=accepted,nfev=fit.nfev,
            elapsed_seconds=time.monotonic()-started,launch_date=q['launch_date'],c3=q['launch_c3_km2_s2'],years=q['duration_years'],
            vinf=q['arrival_vinf_kms'],dsm_mps=1000*q['total_dsm_kms'],gap_mps=q['max_vinf_mismatch_mps'],turn_margin=q['min_turn_margin_deg'])
        if accepted:
            q.update(status='passes_configured_patched_conic_screen',discovered_unix=time.time(),study_config=config)
            public=public_record(q,config,route)
            if public:q['id']=public['id'][:12];result.update(candidate=q,public_record=public)
        return result
    except (ValueError,RuntimeError,AssertionError,ZeroDivisionError,OverflowError) as error:
        return dict(sequence=sequence,source_id=source['id'],shift_days=job['shift_days'],accepted=False,error=str(error),elapsed_seconds=time.monotonic()-started)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',type=Path,default=ROOT/'cache');p.add_argument('--output',type=Path,default=ROOT/'runs/assist_families');p.add_argument('--workers',type=int,default=2);p.add_argument('--max-nfev',type=int,default=110);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    records=json.loads((ROOT/'community_seed_catalog.json').read_text(encoding='utf-8'))['candidates'];jobs=jobs_for(records);results=[]
    print('Jobs:',len(jobs),dict(Counter(j['sequence'] for j in jobs)),flush=True)
    with ProcessPoolExecutor(max_workers=max(1,min(4,a.workers))) as pool:
        tasks={}
        for index,job in enumerate(jobs):
            path=a.output/f'job_{index:03d}.json'
            if path.exists():results.append(json.loads(path.read_text()));continue
            tasks[pool.submit(solve,job,a.cache,a.max_nfev)]=(index,path)
        for future in as_completed(tasks):
            index,path=tasks[future]
            try:result=future.result()
            except Exception as error:result=dict(accepted=False,error=str(error),sequence=jobs[index]['sequence'])
            atomic_json(path,result);results.append(result)
            print('Finished',len(results),'/',len(jobs),'passing',sum(r.get('accepted',False) for r in results),result.get('sequence'),round(result.get('elapsed_seconds',0),1),'s',flush=True)
    found={encounter_key(r['public_record']):r for r in results if r.get('public_record')}
    atomic_json(a.output/'all_candidates.json',[r['candidate'] for r in found.values()]);atomic_json(a.output/'public_candidates.json',[r['public_record'] for r in found.values()])
    atomic_json(a.output/'report.json',dict(jobs=len(jobs),by_sequence=dict(Counter(j['sequence'] for j in jobs)),accepted=len(found),accepted_by_sequence=dict(Counter(r['sequence'] for r in found.values())),attempts=[{k:v for k,v in r.items() if k not in ['candidate','public_record']} for r in results]))
    print('FINISHED:',len(found),'distinct encounter schedules',flush=True)
if __name__=='__main__':main()
