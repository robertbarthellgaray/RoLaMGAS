"""Re-evaluate published concept schedules with the desktop app's actual model.

python tools/recreate_mission_studies.py --cache PATH --iterations 160
Reports failures as well as passes; never uploads or relabels a reference as solved.
"""
from pathlib import Path
import argparse,json,sys,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
import numpy as np
from dynamics import Model
from ephemeris import Ephemerides,fetch,jd,calendar,atomic_json
from mission_search import normalize,routes_for,branch_families
from historical_seeds import timing_guess
from cost_refinement import feasibility_refine
from search_options import export_options
from study_resonant_transfers import audit_coasts,physical_record
from catalog_validation import audit_candidate
from ephemeris import BODIES

ROOT=Path(__file__).resolve().parents[1]

def study_config(mission,cache):
    dates=mission.get('dates')
    if not dates:
        dates=[mission['launch_start']]
        for days in mission['planet_leg_days']:dates.append(calendar(jd(dates[-1])+days).split('T')[0])
    windows=[[day+'T00:00:00',day+'T23:59:59'] for day in dates]
    legs=mission['planet_leg_days'];sequence=mission['sequence']
    return normalize(dict(target=mission['bodies'][-1],target_object=mission.get('target_object'),
        sequences=[sequence],launch_start=windows[0][0],launch_end=windows[0][1],event_windows=windows,
        min_c3=5,max_c3=max(30,mission['c3']*1.35),max_years=max(15,sum(legs)/365.25+1),
        max_dsm_kms=.7,max_single_dsm_kms=.7,max_powered_flyby_kms=.2,powered_flybys=True,
        max_arrival_vinf_kms=30,vinf_tolerance_mps=1,dsm_velocity_box_kms=20,cache=str(cache),
        route_overrides={sequence:dict(leg_days=[[max(1,d*.5),d*1.5+1] for d in legs])}))

def attempt(mission,cache,output,iterations):
    slug=mission['name'].split(' — ')[0].replace('/','-').replace(' ','_')
    folder=output/slug;folder.mkdir(parents=True,exist_ok=True)
    c=study_config(mission,cache);route=routes_for(c)[0]
    atomic_json(folder/'search-options.json',export_options(c)['document'])
    # Only the actual dated study span is required here, not every broad search bound.
    start=min(w[0] for w in c['event_windows_jd'])-2;end=max(w[1] for w in c['event_windows_jd'])+2
    for body in set(route['bodies']):
        try:Ephemerides(cache,[body],start,end,1.)
        except ValueError:fetch(cache,body,start,end,1.)
    ep=Ephemerides(cache,route['bodies'],start,end,1.);model=Model(route,c,ep)
    x=timing_guess(model,np.full(model.dimension,.5),mission);trials=[];rejected=[]
    for branches in branch_families(route,8,502):
        try:
            q=model.evaluate(x,branches);score=float(np.linalg.norm(model.residual(x,branches)))
            trials.append((score,q))
        except (ValueError,RuntimeError,OverflowError) as exc:rejected.append(str(exc))
    for _,q in sorted(trials,key=lambda t:t[0])[:3]:
        if model.accepted(q):continue
        refined=feasibility_refine(model,q['x'],q['branches'],iterations)
        if refined is not None:trials.append((float(np.linalg.norm(model.residual(refined['x'],refined['branches']))),refined))
    report=dict(name=mission['name'],reference=mission,initialization_attempts=len(trials),preflight_rejections=rejected,
                note='Fresh local desktop-model calculation. Study reference numbers are not assumed reproduced.')
    if trials:
        _,q=min(trials,key=lambda item:(not model.accepted(item[1]),item[0]))
        q.update(id=hashlib.sha256(json.dumps([q['sequence'],q['dates_jd_tdb'],q['branches'],q['x']]).encode()).hexdigest()[:12],
                 status='passes_configured_patched_conic_screen' if model.accepted(q) else 'near_miss_not_accepted',screening_residual_norm=float(np.linalg.norm(model.residual(q['x'],q['branches']))))
        audit=audit_candidate(q,c,BODIES);coasts=audit_coasts(q)
        report.update(accepted=model.accepted(q) and audit['passed'] and coasts['passed'],audit=audit,coasts=coasts,
                      candidate_id=q['id'],launch_c3=q['launch_c3_km2_s2'],arrival_vinf=q['arrival_vinf_kms'],total_burn_mps=1000*q['total_dsm_kms'])
        atomic_json(folder/'candidate.json',q)
        if report['accepted']:
            document=export_options(c)['document'];document['trajectory']=physical_record(q,c)
            atomic_json(folder/'selected-trajectory.json',document)
        atomic_json(folder/'run_manifest.json',dict(config=c))
    else:report.update(accepted=False,reason='No valid in-range initial Lambert chain')
    atomic_json(folder/'report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('reference','audit','coasts','preflight_rejections')}),flush=True)
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',type=Path,required=True);p.add_argument('--output',type=Path,default=ROOT/'studies/mission_report_recreations');p.add_argument('--iterations',type=int,default=160);a=p.parse_args()
    missions=json.loads((ROOT/'departure_seeds/mission_studies.json').read_text(encoding='utf-8'))['missions']
    reports=[]
    for mission in missions:
        if not mission.get('seed_eligible') or mission['name'].startswith('Trident'):continue
        try:reports.append(attempt(mission,a.cache,a.output,a.iterations))
        except Exception as exc:
            row=dict(name=mission['name'],accepted=False,error=f'{type(exc).__name__}: {exc}');reports.append(row);print(json.dumps(row),flush=True)
    atomic_json(a.output/'summary.json',reports)

if __name__=='__main__':main()
