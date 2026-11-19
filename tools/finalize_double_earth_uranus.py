"""Refine experiment results and prove they round-trip through the desktop model."""
from pathlib import Path
import sys,json,hashlib,itertools,argparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
import bootstrap,numpy as np
from scipy.optimize import minimize
from explore_double_earth_uranus import evaluate,LOW,HIGH,START
from ephemeris import Ephemerides,jd,atomic_json
from dynamics import Model,lambert
from mission_search import normalize
from search_options import export_options
from community import public_record,record_variables

parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,default=ROOT/'studies/double_earth_uranus');parser.add_argument('--no-refine',action='store_true');parser.add_argument('--hold-duration',action='store_true',help='Tighten speed matching without lengthening the flight by more than 0.001 yr');args=parser.parse_args()
out=args.input;cache=Path.home()/'AppData/Local/RoLaMGAS/cache'
ep=Ephemerides(cache,['Earth','Uranus'],START-2,jd('2080-01-01'),1.)
LOW[3]=1500.
route=dict(id='EdvEdvEU',target='Uranus',bodies=['Earth','Earth','Earth','Uranus'],dsm_legs=[0,1],leg_days=[[680,1200],[900,2600],[1500,6500]],branch_options=[[[m,low] for m in range(6) for low in [True,False]],[[m,low] for m in range(6) for low in [True,False]],[[0,True]]])
config=normalize(dict(target='Uranus',sequences=['EdvEdvEU'],launch_start='2028-01-01',launch_end='2045-12-31',min_c3=25.,max_c3=90.,max_years=30,max_arrival_vinf_kms=15.,max_dsm_kms=1.5,max_single_dsm_kms=.7,vinf_tolerance_mps=1.,cache=str(cache),minimum_altitude_km={'Earth':200.},dsm_velocity_box_kms=40.,route_overrides={'EdvEdvEU':{k:route[k] for k in ['leg_days','branch_options']}}))
model=Model(route,config,ep);records=[]
for path in sorted(out.glob('passing_*.json')):
 raw=json.loads(path.read_text())
 def q(z):
  try:return evaluate(z,ep,True,energy=raw['launch_c3_km2_s2'])
  except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):return None
 def cost(z):
  a=q(z);return a['total_dsm_kms']+.002*a['duration_years'] if a else 1e5
 def eq(z):
  a=q(z);return (a['flybys'][-1]['vinf_in_kms']-a['flybys'][-1]['vinf_out_kms']) if a else 1000.
 def ine(z):
  a=q(z)
  values=[a['flybys'][-1]['turn_margin_deg']-.02,.7-max(a['dsms_kms'])] if a else [-1000,-1000]
  if args.hold_duration:values.append(raw['duration_years']+.001-a['duration_years'] if a else -1000)
  return np.array(values)
 if not args.no_refine:
  initial=(np.array(raw['parameters'])-LOW)/(HIGH-LOW)
  fit=minimize(cost,initial,method='SLSQP',bounds=[(0.,1.)]*8,constraints=[dict(type='eq',fun=eq),dict(type='ineq',fun=ine)],options=dict(maxiter=180,ftol=1e-10,eps=5e-7))
  refined=q(fit.x)
  if refined and refined['passed'] and refined['combined_mismatch_mps']<.01:raw=refined
 dates=raw['dates_jd_tdb'];x=[(dates[0]-LOW[0])/(HIGH[0]-LOW[0])]+[(d-a)/(b-a) for d,(a,b) in zip(np.diff(dates),route['leg_days'])];branches=[]
 for i in range(2):
  candidates=[]
  for m in range(6):
   for low in [True,False]:
    try:
     va,_=lambert(ep.state('Earth',dates[i])[:3],ep.state('Earth',dates[i+1])[:3],dates[i+1]-dates[i],(m,low));offset=np.array(raw['departure_velocities_kms'][i])-va
     if np.max(abs(offset))<config['dsm_velocity_box_kms']:candidates.append((np.linalg.norm(offset),[m,low],offset))
    except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError):pass
  if not candidates:raise ValueError('No desktop-compatible departure-offset branch')
  _,branch,offset=min(candidates,key=lambda r:r[0]);branches.append(branch);x.extend([(raw['dsm_fractions'][i]-.1)/.8,*list(.5+offset/(2*config['dsm_velocity_box_kms']))])
 branches.append([0,True]);candidate=model.evaluate(np.array(x),branches)
 if not all(f['passes_turn_screen'] and f['passes_speed_tolerance'] for f in candidate['flybys']):raise ValueError('Desktop flyby validation failed')
 if max(b['magnitude_kms'] for b in candidate['dsms'])>.70001:raise ValueError('Desktop DSM cap failed')
 candidate['status']='passes_configured_patched_conic_screen';candidate['id']=hashlib.sha256(json.dumps([dates,branches,x],separators=(',',':')).encode()).hexdigest()[:12]
 record=public_record(candidate,config,route)
 if not record:raise ValueError('Candidate cannot be exported as a portable science record')
 mapped,again=record_variables(record,model);check=model.evaluate(mapped,again)
 assert abs(check['launch_c3_km2_s2']-candidate['launch_c3_km2_s2'])<1e-6
 assert abs(check['total_dsm_kms']-candidate['total_dsm_kms'])<1e-6
 records.append(dict(candidate=candidate,record=record,physical_initialization=raw))
 atomic_json(out/(candidate['id']+'.json'),candidate)
 atomic_json(out/(candidate['id']+'_handoff.json'),dict(format='rolamgas-search-options',schema_version=1,settings=export_options(config)['document']['settings'],trajectory=record))
 print(candidate['id'],candidate['launch_date'],candidate['duration_years'],candidate['total_dsm_kms'],candidate['max_vinf_mismatch_mps'],flush=True)
atomic_json(out/'validated.json',dict(route=route,config=config,candidates=records))
