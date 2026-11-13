"""Refine screened assist-family candidates using constrained SLSQP on local JPL data.

Minimize flight time, launch C3 and arrival speed separately. Convergence status
is retained: a feasible iterate is not claimed to be a global optimum.
"""
import sys,json,copy,time,argparse
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R));sys.path.insert(0,str(R/'tools'))
import bootstrap,numpy as np
from scipy.optimize import minimize
from mission_search import routes_for
from dynamics import Model
from ephemeris import Ephemerides,atomic_json
from community import public_record,record_variables
from study_resonant_transfers import physical_record
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--cache',type=Path,default=R/'cache');p.add_argument('--maxiter',type=int,default=250);p.add_argument('--include-zero',action='store_true',help='Also introduce a real DSM into an existing zero-DSM architecture and keep it below eight years');a=p.parse_args()
rows=json.loads((a.input/'all_candidates.json').read_text())
seeds=[q for q in rows if q['sequence'].endswith('S') and (q['total_dsm_kms']>.001 or a.include_zero)]
found=[];attempts=[]
for seed in seeds:
 for goal in ['time','c3','arrival']:
  c=copy.deepcopy(seed['study_config']);dates=seed['dates_jd_tdb'];c['event_windows_jd']=[[t-90,t+90] for t in dates]
  if seed['total_dsm_kms']<.001:c['max_years']=7.999
  route=routes_for(c)[0];ep=Ephemerides(a.cache,route['bodies'],dates[0]-92,dates[-1]+92,1.)
  model=Model(route,c,ep);x,bb=record_variables(physical_record(seed,seed['study_config']),model)
  cache={}
  def ev(z):
   key=tuple(z)
   if key not in cache:
    try:cache[key]=model.evaluate(z,bb,enforce_c3=False)
    except (ValueError,RuntimeError,AssertionError,OverflowError):cache[key]=None
   return cache[key]
  def objective(z):
   q=ev(z)
   if q is None:return 1e6
   return q['duration_years'] if goal=='time' else q['launch_c3_km2_s2']/10 if goal=='c3' else q['arrival_vinf_kms']
  def eq(z):
   q=ev(z);return np.array([f['vinf_in_kms']-f['vinf_out_kms'] for f in q['flybys']]) if q else np.ones(model.n-2)*1e3
  def ine(z):
   q=ev(z)
   if q is None:return np.ones(model.n-2+6)*-1e3
   return np.r_[[f['turn_margin_deg']-.02 for f in q['flybys']],q['launch_c3_km2_s2']-5.01,29.99-q['launch_c3_km2_s2'],c['max_years']-.001-q['duration_years'],11.99-q['arrival_vinf_kms'],.699-q['total_dsm_kms'],.699-q['max_single_dsm_kms']]
  fit=minimize(objective,x,method='SLSQP',bounds=[(.00001,.99999)]*len(x),constraints=[{'type':'eq','fun':eq},{'type':'ineq','fun':ine}],options={'maxiter':a.maxiter,'ftol':1e-9})
  q=ev(fit.x);accepted=q is not None and bool(model.accepted(q))
  summary=dict(sequence=seed['sequence'],source_id=seed['id'],goal=goal,accepted=accepted,optimizer_success=bool(fit.success),message=str(fit.message))
  if q:summary.update(c3=q['launch_c3_km2_s2'],years=q['duration_years'],vinf=q['arrival_vinf_kms'],dsm_mps=1000*q['total_dsm_kms'],gap_mps=q['max_vinf_mismatch_mps'])
  if accepted:
   q.update(status='passes_configured_patched_conic_screen',discovered_unix=time.time(),study_config=c);rec=public_record(q,c,route)
   if rec:q['id']=rec['id'][:12];found.append(q)
  attempts.append(summary);print(summary,flush=True)
atomic_json(a.input/'polished_candidates.json',found);atomic_json(a.input/'polish_report.json',attempts)
