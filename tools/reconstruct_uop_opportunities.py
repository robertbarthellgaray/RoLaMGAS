"""Reconstruct the 16 UOP Exhibit 3-24 windows using saved routes as guesses.

Standalone local numerical search. No automatic upload and no claimed UOI match.
Source: Uranus-Orbiter-and-Probe report, printed pp.25-26 (PDF pp.31-32).
"""
from pathlib import Path
import argparse, json, sys, time, itertools, hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import bootstrap
import numpy as np
from scipy.optimize import least_squares, brentq
from dynamics import lambert, kepler, flyby, Model
from ephemeris import Ephemerides, jd, calendar, BODIES, DAY, atomic_json
from mission_search import normalize, routes_for
from community import record_variables, public_record

WINDOWS=[
 ('2029-09-30',13.7,'EVEEJU',0.,14.5),
 ('2029-10-31',11.3,'EVEEJU',0.,13.1),
 ('2031-03-07',17.5,'EVEEJU',.05,12.5),
 ('2031-04-03',28.6,'EdvEJU',.65,13.5),
 ('2031-06-13',27.1,'EdvEJU',.77,13.4),
 ('2031-06-15',27.,'EdvEJU',.72,12.7),
 ('2031-07-18',19.8,'EVEJU',1.07,11.6),
 ('2031-08-01',18.,'EVEJU',1.05,12.3),
 ('2031-08-09',20.2,'EVEJU',1.06,12.),
 ('2032-04-29',28.8,'EdvEJU',.60,12.8),
 ('2032-05-03',29.2,'EdvEJU',.76,12.2),
 ('2032-08-15',49.5,'EdvEJU',.42,11.8),
 ('2033-01-08',23.6,'EVEEU',.42,15.3),
 ('2034-05-27',23.1,'EVEEU',.68,15.2),
 ('2036-02-28',28.2,'EVEEU',.54,15.3),
 ('2038-01-08',35.5,'EVEEU',0.,14.2),
]
TOKENS={'Earth':'E','Venus':'V','Jupiter':'J','Uranus':'U'}
IDNAME={str(v[0]):k for k,v in BODIES.items()}
FLOORS={'Earth':200.,'Venus':300.,'Jupiter':10000.,'Uranus':1000.}
OUT=ROOT/'runs/uop_report_reconstruction_20261116'


def sequence(bodies,leg):
 return ''.join(TOKENS[b]+('dv' if i==leg else '') for i,b in enumerate(bodies))


def donors_for(rows,base):
 desired={'EVEEJU':['Earth','Venus','Earth','Earth','Jupiter','Uranus'],
          'EdvEJU':['Earth','Earth','Jupiter','Uranus'],
          'EVEJU':['Earth','Venus','Earth','Jupiter','Uranus'],
          'EVEEU':['Earth','Venus','Earth','Earth','Uranus']}[base]
 out=[]
 for r in rows:
  bodies=[IDNAME.get(str(b)) for b in r['body_ids']]
  if bodies==desired:out.append(r)
 if not out and base=='EVEJU':
  for r in rows:
   if r['sequence']!='EVEEJU':continue
   d=dict(r,body_ids=r['body_ids'][:2]+r['body_ids'][3:],
          dates_jd_tdb=r['dates_jd_tdb'][:2]+r['dates_jd_tdb'][3:],
          branches=r['branches'][:1]+r['branches'][2:],dsm_controls=[])
   d['branches'][1]=[0,True];out.append(d)
 return desired,out


def raw(ep,bodies,start,days,branches,leg,controls):
 dates=start+np.r_[0.,np.cumsum(days)]
 states=[ep.state(b,float(t)) for b,t in zip(bodies,dates)]
 va,vb=lambert(states[0][:3],states[1][:3],days[0],branches[0])
 off=controls[1:] if leg==0 else np.zeros(3)
 energy=float(np.sum((va+off-states[0][3:])**2))
 if energy<5:raise ValueError('Below hard C3 floor')
 dep=[];arr=[];dsm=0.
 for i in range(len(days)):
  if i:va,vb=lambert(states[i][:3],states[i+1][:3],days[i],branches[i])
  if i==leg:
   fraction=controls[0];va=va+controls[1:]
   rd,before=kepler(states[i][:3],va,days[i]*fraction*DAY)
   after,vb=lambert(rd,states[i+1][:3],days[i]*(1-fraction),(0,True))
   dsm=float(np.linalg.norm(after-before))
  dep.append(va);arr.append(vb)
 fs=[flyby(bodies[i],arr[i-1]-states[i][3:],dep[i]-states[i][3:],FLOORS[bodies[i]],1.) for i in range(1,len(bodies)-1)]
 gaps=[np.linalg.norm(arr[i-1]-states[i][3:])-np.linalg.norm(dep[i]-states[i][3:]) for i in range(1,len(bodies)-1)]
 return dates,energy,dsm,fs,np.array(gaps),float(np.linalg.norm(arr[-1]-states[-1][3:]))


def materialize(ep,spec,bodies,branches,leg,z,c3_tolerance=.08,time_tolerance=.055):
 date,c3,base,budget,years=spec;nl=len(bodies)-1
 start=jd(date)+.5+z[-1];days=z[:nl];ctrl=z[nl:-1]
 dates,energy,dsm,fs,gaps,vinf=raw(ep,bodies,start,days,branches,leg,ctrl)
 seq=sequence(bodies,leg)
 config=normalize(dict(target='Uranus',sequences=[seq],launch_start=date,launch_end=date,
  event_windows_jd=[[float(t),float(t)] for t in dates],min_c3=max(5,c3-c3_tolerance),max_c3=c3+c3_tolerance,
  max_years=years+time_tolerance,max_arrival_vinf_kms=15.,max_dsm_kms=budget+.025,max_venus_c3=None,
  max_single_dsm_kms=budget+.025,minimum_altitude_km=FLOORS,
  vinf_tolerance_mps=1.,dsm_velocity_box_kms=6.,
  route_overrides={seq:dict(leg_days=[[1.,12000.]]*nl,branch_options=[[b] for b in branches])}))
 route=routes_for(config)[0]
 record=dict(schema_version=1,sequence=seq,body_ids=[str(BODIES[b][0]) for b in bodies],
  dates_jd_tdb=dates.tolist(),branches=branches,dsm_controls=[])
 if leg is not None:record['dsm_controls']=[dict(leg_index=leg,fraction=float(ctrl[0]),departure_offset_kms=ctrl[1:].tolist())]
 model=Model(route,config,ep);x,bb=record_variables(record,model);q=model.evaluate(x,bb,enforce_c3=False)
 ok=model.accepted(q) and abs(q['duration_years']-years)<=time_tolerance and abs(energy-c3)<=c3_tolerance
 q.update(status='passes_configured_patched_conic_screen' if ok else 'near_miss_not_accepted',discovered_unix=time.time(),study_config=config)
 pub=public_record(q,config,route) if ok else None
 if pub:q['id']=pub['id'][:12]
 else:q['id']=hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest()[:12]
 return dict(accepted=ok,candidate=q,record=pub,config=config,route=route,reference=dict(launch_date=date,c3=c3,sequence=base,dsm_kms=budget,years=years,c3_tolerance=c3_tolerance,time_tolerance_years=time_tolerance))


def worker(job):
 index,attempts,max_nfev=job[:3];c3_tol,time_tol=job[3:5] if len(job)>3 else (.08,.055)
 launch_tol=job[5] if len(job)>5 else .499
 spec=WINDOWS[index];date,target_c3,base,budget,years=spec
 ep=Ephemerides(ROOT/'cache',['Earth','Venus','Jupiter','Uranus'],jd('2028-01-01'),jd('2056-01-01'),1.)
 library=OUT/'existing_library.json'
 if not library.exists():library=ROOT/'studies/uop_opportunities_2026/seed_donors.json'
 rows=json.loads(library.read_text(encoding='utf-8'))
 bodies,donors=donors_for(rows,base);nl=len(bodies)-1;start=jd(date)+.5
 donors=sorted(donors,key=lambda r:abs(r['dates_jd_tdb'][0]-start)+20*r['metrics'].get('max_vinf_mismatch_mps',0))
 # Diversify genuinely different encounter schedules instead of many nearly identical records.
 chosen=[];keys=set()
 for r in donors:
  key=tuple(round((t-r['dates_jd_tdb'][0])/30) for t in r['dates_jd_tdb'][1:-1])+tuple(tuple(b) for b in r['branches'])
  if key in keys:continue
  chosen.append(r);keys.add(key)
 donors=chosen or donors
 prior_path=OUT/(date+'_best.json')
 if prior_path.exists():
  saved=json.loads(prior_path.read_text(encoding='utf-8'));q=saved['candidate']
  if saved.get('optimization',{}).get('residual_norm',1e5)<1:
   controls=[]
   for j,leg in enumerate(saved['route']['dsm_legs']):
    k=len(bodies)+4*j;controls.append(dict(leg_index=leg,fraction=.1+.8*q['x'][k],departure_offset_kms=((np.array(q['x'][k+1:k+4])*2-1)*saved['config']['dsm_velocity_box_kms']).tolist()))
   donors.insert(0,dict(reconstruction_warm_start=True,body_ids=[str(BODIES[b][0]) for b in bodies],dates_jd_tdb=q['dates_jd_tdb'],branches=q['branches'],dsm_controls=controls,metrics=dict(max_vinf_mismatch_mps=q['max_vinf_mismatch_mps'])))
 rng=np.random.default_rng(502+index);best=None;bestscore=float('inf');solutions=[];began=time.monotonic()
 legs=([None] if budget==0 else [0] if base=='EdvEJU' else [2,1,3,0] if base=='EVEEU' else [1,2,0,3] if base=='EVEJU' else [2,1,3,0,4])
 first_roots=[]
 if base!='EdvEJU':
  earth=ep.state('Earth',start)
  for branch in [[0,True],[1,True],[1,False]]:
   def energy_error(d):
    va,_=lambert(earth[:3],ep.state('Venus',start+d)[:3],d,branch)
    return float(np.sum((va-earth[3:])**2)-target_c3)
   previous=None
   for d in np.arange(45.,1301.,4.):
    try:
     value=energy_error(d)
     if previous and previous[1]*value<0:
      root=brentq(energy_error,previous[0],d,xtol=1e-9)
      if abs(energy_error(root))<1e-5:first_roots.append((branch.copy(),root))
     previous=(d,value)
    except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):previous=None
  print(date,'feasible Earth-Venus departure roots',first_roots,flush=True)
 chain_guesses=[]
 if base=='EVEJU':
  from search_no_jupiter import bracket_roots
  for branch,d0 in first_roots:
   t1=start+d0;venus=ep.state('Venus',t1)
   _,vb=lambert(earth[:3],venus[:3],d0,branch);incoming=vb-venus[3:]
   for middle_branch in [[0,True],[1,True],[1,False],[2,True],[2,False]]:
    def middle(d):
     va,vb=lambert(venus[:3],ep.state('Earth',t1+d)[:3],d,middle_branch)
     return va-venus[3:],vb-ep.state('Earth',t1+d)[3:]
    for d1 in bracket_roots(lambda d:np.linalg.norm(middle(d)[0])-np.linalg.norm(incoming),45,1500,5):
     vo,ein=middle(d1);f=flyby('Venus',incoming,vo,300.,1.)
     if f['turn_margin_deg'] < -15:continue
     t2=t1+d1;state=ep.state('Earth',t2)
     def ej(d):
      va,vb=lambert(state[:3],ep.state('Jupiter',t2+d)[:3],d,[0,True])
      return va-state[3:]
     for d2 in bracket_roots(lambda d:np.linalg.norm(ej(d))-np.linalg.norm(ein),300,2200,8):
      f2=flyby('Earth',ein,ej(d2),200,1.)
      if f2['turn_margin_deg'] < -20:continue
      d3=years*365.25-d0-d1-d2
      if d3<1000:continue
      chain_guesses.append(([branch,middle_branch,[0,True],[0,True]],np.array([d0,d1,d2,d3])))
  print(date,'root-matched Venus/Earth/Jupiter chain guesses',len(chain_guesses),flush=True)
 if base=='EVEEU':
  from search_no_jupiter import bracket_roots, resonance_grid
  ranked=[]
  for branch,d0 in first_roots:
   t1=start+d0;venus=ep.state('Venus',t1)
   _,vb=lambert(earth[:3],venus[:3],d0,branch);incoming=vb-venus[3:]
   for middle_branch in [[0,True],[1,True],[1,False]]:
    def middle(d):
     st=ep.state('Earth',t1+d);va,vb=lambert(venus[:3],st[:3],d,middle_branch)
     return va-venus[3:],vb-st[3:]
    for d1 in bracket_roots(lambda d:np.linalg.norm(middle(d)[0])-np.linalg.norm(incoming),45,1000,6):
     vo,ein=middle(d1)
     if flyby('Venus',incoming,vo,300,1)['turn_margin_deg'] < -8:continue
     t2=t1+d1;st=ep.state('Earth',t2)
     for return_branch in [[0,True],[1,True],[1,False],[2,True],[2,False],[3,True],[3,False]]:
      def ret(d):
       end=ep.state('Earth',t2+d);va,vb=lambert(st[:3],end[:3],d,return_branch)
       return va-st[3:],vb-end[3:]
      for d2 in bracket_roots(lambda d:np.linalg.norm(ret(d)[0])-np.linalg.norm(ein),350,1800,8,resonance_grid(365.256,1800)):
       vo,final_in=ret(d2)
       if flyby('Earth',ein,vo,200,1)['turn_margin_deg'] < -12:continue
       d3=years*365.25-d0-d1-d2
       if d3<1600:continue
       bb=[branch.copy(),middle_branch.copy(),return_branch.copy(),[0,True]]
       dd=np.array([d0,d1,d2,d3])
       try:
        _,e,_,ff,gg,v=raw(ep,bodies,start,dd,bb,None,np.array([]))
        score=float(np.linalg.norm(gg)+sum(max(0,-f['turn_margin_deg'])/20 for f in ff))
        ranked.append((score,bb,dd))
       except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):pass
  ranked.sort(key=lambda a:a[0]);chain_guesses=[(b,d) for score,b,d in ranked[:24]]
  atomic_json(OUT/(date+'_resonant_guesses.json'),[dict(score=s,branches=b,days=d.tolist()) for s,b,d in ranked[:24]])
  print(date,'root-matched Venus/Earth/Earth chain guesses',len(ranked),'best scores',[round(r[0],3) for r in ranked[:5]],flush=True)
 for attempt in range(attempts):
  donor=donors[(attempt//max(1,len(legs)))%len(donors)];leg=legs[attempt%len(legs)]
  branches=[list(b) for b in donor['branches']]
  duration=np.diff(donor['dates_jd_tdb']);duration[-1]=max(900.,years*365.25-sum(duration[:-1]))
  if attempt>=len(legs)*min(3,len(donors)):
   duration[:-1]+=rng.normal(0,65.,nl-1)
   duration[-1]=max(900.,years*365.25-sum(duration[:-1]))
  if base=='EVEEU' and attempt%8>=4:branches[2]=[attempt%3,True]
  if base=='EdvEJU' and attempt%5==4:branches[0]=[(attempt//5)%3,True]
  if first_roots and not donor.get('reconstruction_warm_start'):
   branch,days=first_roots[(attempt//len(legs))%len(first_roots)]
   branches[0]=branch;duration[0]=days
   duration[-1]=max(900.,years*365.25-sum(duration[:-1]))
  if chain_guesses and not donor.get('reconstruction_warm_start'):
   bb,dd=chain_guesses[max(0,attempt//len(legs)-1)%len(chain_guesses)]
   branches=[b.copy() for b in bb];duration=dd.copy()
  lower=np.array([200. if bodies[i]==bodies[i+1] else 45. for i in range(nl)])
  upper=np.array([2000. if bodies[i]==bodies[i+1] else 1300. if i<nl-1 else 9000. for i in range(nl)])
  if base=='EVEJU':upper[1]=1600.
  duration=np.clip(duration,lower+.001,upper-.001)
  if leg is not None:
   control=next((c for c in donor['dsm_controls'] if c['leg_index']==leg),None)
   ctrl=np.r_[control['fraction'],control['departure_offset_kms']] if control else np.array([.5,0.,0.,0.])
   z=np.r_[duration,ctrl];lo=np.r_[lower,.1,-6.,-6.,-6.];hi=np.r_[upper,.9,6.,6.,6.]
  else:z=duration;lo=lower;hi=upper
  z=np.r_[z,0.];lo=np.r_[lo,-launch_tol];hi=np.r_[hi,launch_tol]
  nres=2+2*(len(bodies)-2)+2
  def residual(z):
   try:
    dates,e,d,fs,gaps,v=raw(ep,bodies,start+z[-1],z[:nl],branches,leg,z[nl:-1])
    turns=[max(0.,-f['turn_margin_deg']+.005)/20 for f in fs]
    c3_deadband=min(.04,c3_tol) if c3_tol<=.08 else c3_tol*.8
    energy_error=np.sign(e-target_c3)*max(0.,abs(e-target_c3)-c3_deadband)/(2*np.sqrt(target_c3))
    time_error=np.sign(sum(z[:nl])-years*365.25)*max(0.,abs(sum(z[:nl])-years*365.25)-(min(.04,time_tol) if time_tol<=.055 else time_tol*.8)*365.25)/365.25
    return np.r_[energy_error,time_error,
                 gaps,turns,max(0.,d-budget)/.3,max(0.,v-14.)]
   except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):return np.full(nres,1e4)
  try:
   fit=least_squares(residual,z,bounds=(lo,hi),max_nfev=max_nfev,x_scale='jac',
                     diff_step=2e-7,ftol=1e-11,xtol=1e-11,gtol=1e-11)
   score=float(np.linalg.norm(residual(fit.x)))
   if score<bestscore:
    result=materialize(ep,spec,bodies,branches,leg,fit.x,c3_tol,time_tol)
    bestscore=score;best=result;best['optimization']=dict(attempt=attempt,residual_norm=score,nfev=fit.nfev)
    atomic_json(OUT/(date+'_best.json'),best)
    q=result['candidate'];print(date,'attempt',attempt,'score',round(score,6),'C3',round(q['launch_c3_km2_s2'],4),'DSM',round(q['total_dsm_kms'],4),'years',round(q['duration_years'],4),'gap_mps',round(q['max_vinf_mismatch_mps'],4),'turn',round(q['min_turn_margin_deg'],3),'PASS',bool(result['record']),flush=True)
    if result['accepted']:
     atomic_json(OUT/(date+'_solution.json'),result);solutions.append(result)
     break
  except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError) as e:
   if attempt==0:print(date,'initial error',str(e),flush=True)
 report=dict(date=date,attempts=attempt+1,elapsed_seconds=time.monotonic()-began,passed=bool(solutions),best_residual=bestscore if np.isfinite(bestscore) else None)
 atomic_json(OUT/(date+'_search.json'),report);print('FINISHED',json.dumps(report),flush=True)
 return report


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--date',action='append');p.add_argument('--attempts',type=int,default=40);p.add_argument('--max-nfev',type=int,default=250);p.add_argument('--workers',type=int,default=3);p.add_argument('--c3-tolerance',type=float,default=.08);p.add_argument('--time-tolerance',type=float,default=.055);p.add_argument('--launch-tolerance',type=float,default=.499);a=p.parse_args()
 OUT.mkdir(exist_ok=True);atomic_json(OUT/'reference_windows.json',[dict(launch_date=d,c3=c,sequence=s,dsm_kms=b,years=y) for d,c,s,b,y in WINDOWS])
 jobs=[(i,a.attempts,a.max_nfev,a.c3_tolerance,a.time_tolerance,a.launch_tolerance) for i,s in enumerate(WINDOWS) if not a.date or s[0] in a.date]
 if a.workers==1:
  for job in jobs:worker(job)
 else:
  from concurrent.futures import ProcessPoolExecutor,as_completed
  with ProcessPoolExecutor(max_workers=a.workers) as pool:
   for f in as_completed([pool.submit(worker,j) for j in jobs]):f.result()

if __name__=='__main__':main()
