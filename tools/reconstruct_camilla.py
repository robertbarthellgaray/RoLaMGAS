"""Reconstruct Camilla's published Earth-Venus-Earth-Earth-Jupiter calendar days.

python tools/reconstruct_camilla.py --cache PATH --output studies/camilla_2026
Local JPL cache and CPU only. Resolves the Earth-return time, fits a July DSM,
audits all vectors and solar coasts, and writes an exact desktop import.
The Chariklo leg is outside this reconstruction.
"""
from pathlib import Path
import argparse,hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
import numpy as np
from scipy.optimize import brentq,minimize,minimize_scalar
from app_paths import DATA_ROOT
from ephemeris import Ephemerides,jd,calendar,atomic_json,BODIES
from dynamics import Model,lambert
from mission_search import normalize,routes_for
from community import public_record
from search_options import export_options
from study_resonant_transfers import audit_coasts,physical_record
from catalog_validation import audit_candidate

DAYS=['2026-09-09','2027-02-25','2027-12-29','2029-12-29','2031-10-25']
BRANCHES=[[0,True],[0,True],[1,True],[0,True]]
SOURCES=['https://doi.org/10.1016/j.pss.2018.07.008','https://authors.library.caltech.edu/records/4ep13-y2e40']

def earth_return_epoch(ep,dates):
    """Find a speed-matched second Earth encounter within its published day."""
    first=ep.state('Earth',dates[2]);axis=first[:3]/np.linalg.norm(first[:3]);day=jd(DAYS[3])
    def alignment(offset):
        s=ep.state('Earth',day+offset);return np.linalg.norm(np.cross(axis,s[:3]/np.linalg.norm(s[:3])))
    center=minimize_scalar(alignment,bounds=(0.,1.),method='bounded',options={'xatol':1e-12}).x
    def error(offset):
        date=day+offset;s=ep.state('Earth',date);last=ep.state('Jupiter',dates[4])
        _,incoming=lambert(first[:3],s[:3],date-dates[2],BRANCHES[2])
        outgoing,_=lambert(s[:3],last[:3],dates[4]-date,BRANCHES[3])
        return float(np.linalg.norm(incoming-s[3:])-np.linalg.norm(outgoing-s[3:]))
    previous=None
    for offset in center+np.logspace(-6,-.05,180):
        if offset>=1:break
        value=error(offset)
        if previous and previous[1]*value<0:
            return day+brentq(error,previous[0],float(offset),xtol=1e-12)
        previous=(float(offset),value)
    raise ValueError('No speed-matched Earth return on the published day')

def reconstruct(cache,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    dates=np.array([jd(day)+.5 for day in DAYS])
    ep=Ephemerides(cache,['Earth','Venus','Jupiter'],dates[0]-1,dates[-1]+1,1.)
    dates[3]=earth_return_epoch(ep,dates)
    config=normalize(dict(target='Jupiter',sequences=['EVdvEEJ'],launch_start=DAYS[0],launch_end=DAYS[0]+'T23:59:59',
        event_windows=[[d+'T00:00:00',d+'T23:59:59'] for d in DAYS],min_c3=5,max_c3=15,
        max_arrival_vinf_kms=15,max_years=6,max_dsm_kms=.7,max_single_dsm_kms=.7,
        vinf_tolerance_mps=.1,dsm_velocity_box_kms=2,minimum_altitude_km={'Earth':200,'Venus':300},cache=str(cache)))
    route=routes_for(config)[0];model=Model(route,config,ep);initial=np.full(model.dimension,.5)
    for i,(lo,hi) in enumerate(config['event_windows_jd']):initial[i]=(dates[i]-lo)/(hi-lo)
    def candidate(z):
        x=initial.copy();x[model.n]=(z[0]-.1)/.8
        x[model.n+1:model.n+4]=.5+np.array(z[1:])/(2*config['dsm_velocity_box_kms'])
        return model.evaluate(x,BRANCHES)
    def equality(z):
        q=candidate(z);return np.array([f['vinf_in_kms']-f['vinf_out_kms'] for f in q['flybys'][:2]])
    def margins(z):
        q=candidate(z);return np.array([(f['turn_margin_deg']-.001)/10 for f in q['flybys']]+[.7-q['total_dsm_kms']])
    lo=(jd('2027-07-01')-dates[1])/(dates[2]-dates[1]);hi=(jd('2027-08-01')-dates[1])/(dates[2]-dates[1])
    trials=[]
    for fraction in np.linspace(lo+.001,hi-.001,3):
        fit=minimize(lambda z:candidate(z)['total_dsm_kms'],[fraction,0,0,0],method='SLSQP',
            bounds=[(lo,hi)]+[(-.8,.8)]*3,constraints=[dict(type='eq',fun=equality),dict(type='ineq',fun=margins)],
            options=dict(maxiter=250,ftol=1e-12,eps=2e-6))
        q=candidate(fit.x);trials.append(q)
        print('July DSM',round(q['total_dsm_kms']*1000,6),'m/s; largest mismatch',round(q['max_vinf_mismatch_mps'],6),'m/s; pass',bool(model.accepted(q)),flush=True)
    q=min(trials,key=lambda q:(not model.accepted(q),q['total_dsm_kms']))
    if not model.accepted(q):raise ValueError('No candidate meets the configured physical limits')
    q.update(id=hashlib.sha256(json.dumps([q['sequence'],q['dates_jd_tdb'],q['x']]).encode()).hexdigest()[:12],
        status='passes_configured_patched_conic_screen',study_config=config)
    q=json.loads(json.dumps(q,default=lambda v:v.item()))
    audit=audit_candidate(q,config,BODIES);coasts=audit_coasts(q)
    if not audit['passed'] or not coasts['passed']:raise ValueError([audit,coasts])
    record=public_record(q,config,route)
    if record is None:raise ValueError('Public protocol admission failed')
    document=export_options(config)['document'];document.update(trajectory=physical_record(q,config),display_name='Camilla 2026 — Jupiter cruise recreation',source_candidate_id=q['id'])
    reference=dict(name='Camilla 2026 Jupiter cruise',sources=SOURCES,note='A reproduction of the supplied planetary calendar days with optimized times and an explicitly charged July DSM. This is the Jupiter-bound prefix; Chariklo is not included.',reported_c3=11.9,reported_cruise_budget_kms=.4)
    report=dict(reference=reference,id=q['id'],launch_c3=q['launch_c3_km2_s2'],dsm_mps=1000*q['total_dsm_kms'],
        dates=q['dates_jd_tdb'],max_vinf_mismatch_mps=q['max_vinf_mismatch_mps'],vector_audit=audit,solar_coast_audit=coasts,
        flyby_altitudes_km=[f['conservative_equal_speed_altitude_km'] for f in q['flybys']])
    q['study_config']=dict(config,cache='cache')
    for name,value in [('candidate.json',q),('public_record.json',record),('selected-trajectory.json',document),('report.json',report)]:atomic_json(output/name,value)
    print(json.dumps({k:report[k] for k in ['id','launch_c3','dsm_mps','max_vinf_mismatch_mps','flyby_altitudes_km']}),flush=True)
    return q,record,report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--cache',type=Path,default=DATA_ROOT/'cache');parser.add_argument('--output',type=Path,default=Path('studies/camilla_2026'))
    args=parser.parse_args();reconstruct(args.cache,args.output)
