"""Local EdvEdvEU experiment: C3=30, two aphelion DSMs, physical Earth turns.

Standalone numerical study; no automatic public upload or relaxed flyby floors.
"""
from pathlib import Path
import sys,json,math,time,argparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bootstrap
import numpy as np
from scipy.optimize import least_squares
from ephemeris import Ephemerides,DAY,MU_SUN,BODIES,jd,calendar,atomic_json,AU
from dynamics import lambert,kepler,flyby
from earth_return_seeds import rtn_basis

MU_E=BODIES['Earth'][1];RP=BODIES['Earth'][2]+200.
START=jd('2028-01-01');STOP=jd('2045-12-31')
LOW=np.array([START,680.,900.,3000.,-65.,-15.,.02,-math.pi])
HIGH=np.array([STOP,1200.,2600.,6500.,65.,15.,.99,math.pi])

def aphelion(r,v):
 radius=np.linalg.norm(r);energy=float(v@v)/2-MU_SUN/radius
 if energy>=0:raise ValueError('No bound aphelion')
 a=-MU_SUN/(2*energy);h=np.cross(r,v);ev=np.cross(v,h)/MU_SUN-r/radius;e=np.linalg.norm(ev)
 if e<1e-5:raise ValueError('No distinct aphelion')
 E=math.atan2(float(r@v)/(e*math.sqrt(MU_SUN*a)),(1-radius/a)/e)
 M=E-e*math.sin(E);seconds=((math.pi-M)%(2*math.pi))/math.sqrt(MU_SUN/a**3)
 return seconds/DAY,a*(1+e)/AU

def evaluate(z,ep,path=False,energy=30.):
 p=LOW+np.asarray(z)*(HIGH-LOW);launch,d1,d2,d3,alpha,beta,kappa,phi=p
 dates=np.r_[launch,launch+np.cumsum([d1,d2,d3])]
 planets=[ep.state(b,t) for b,t in zip(['Earth','Earth','Earth','Uranus'],dates)]
 alpha,beta=np.radians([alpha,beta]);direction=np.array([math.sin(alpha)*math.cos(beta),math.cos(alpha)*math.cos(beta),math.sin(beta)])
 velocity=planets[0][3:]+rtn_basis(planets[0])@direction*math.sqrt(energy)
 departures=[];arrivals=[];burns=[];fractions=[];segments=[];apos=[]
 for i,duration in enumerate([d1,d2]):
  if i:
   incoming=arrivals[-1]-planets[i][3:];speed=np.linalg.norm(incoming);u=incoming/speed
   hint=planets[i][3:]/np.linalg.norm(planets[i][3:]);x=hint-u*float(hint@u)
   if np.linalg.norm(x)<1e-8:x=np.cross(u,[0,0,1])
   x/=np.linalg.norm(x);y=np.cross(u,x)
   turn=kappa*2*math.asin(1/(1+RP*speed**2/MU_E))
   velocity=planets[i][3:]+speed*(math.cos(turn)*u+math.sin(turn)*(math.cos(phi)*x+math.sin(phi)*y))
  apo,apo_au=aphelion(planets[i][:3],velocity);fraction=apo/duration
  if not .10001<fraction<.89999:raise ValueError('Aphelion outside DSM fraction bounds')
  position,before=kepler(planets[i][:3],velocity,apo*DAY)
  after,arrival=lambert(position,planets[i+1][:3],duration-apo,(0,True))
  departures.append(velocity);arrivals.append(arrival);burns.append(after-before);fractions.append(fraction);apos.append(apo_au)
  segments.extend([dict(start_jd=dates[i],end_jd=dates[i]+apo,r=planets[i][:3].tolist(),v=velocity.tolist()),dict(start_jd=dates[i]+apo,end_jd=dates[i+1],r=position.tolist(),v=after.tolist())])
 va,vb=lambert(planets[2][:3],planets[3][:3],d3,(0,True));departures.append(va);arrivals.append(vb)
 segments.append(dict(start_jd=dates[2],end_jd=dates[3],r=planets[2][:3].tolist(),v=va.tolist()))
 fs=[flyby('Earth',arrivals[i-1]-planets[i][3:],departures[i]-planets[i][3:],200.,1.) for i in [1,2]]
 gap=fs[-1]['vinf_in_kms']-fs[-1]['vinf_out_kms']
 residual=np.r_[burns[0]/.35,burns[1]/.35,gap/.06,min(0.,fs[-1]['turn_margin_deg']-.02)/3]
 if not path:return residual
 return dict(sequence='EdvEdvEU',parameters=p.tolist(),z=np.asarray(z).tolist(),dates_jd_tdb=dates.tolist(),dates=[calendar(t) for t in dates],launch_c3_km2_s2=energy,
  dsms_kms=[float(np.linalg.norm(b)) for b in burns],dsm_vectors_kms=[b.tolist() for b in burns],dsm_fractions=fractions,
  total_dsm_kms=float(sum(np.linalg.norm(b) for b in burns)),flybys=fs,combined_mismatch_mps=sum(f['speed_mismatch_mps'] for f in fs),
  launch_direction_rtn=direction.tolist(),aphelia_au=apos,duration_years=(dates[-1]-dates[0])/365.25,
  arrival_vinf_kms=float(np.linalg.norm(vb-planets[-1][3:])),segments=segments,departure_velocities_kms=[v.tolist() for v in departures],arrival_velocities_kms=[v.tolist() for v in arrivals],
  events=[dict(body=b,julian_date_tdb=float(t),date=calendar(t),planet_state_km_kms=s.tolist()) for b,t,s in zip(['Earth','Earth','Earth','Uranus'],dates,planets)],
  score=float(residual@residual),passed=bool(max(np.linalg.norm(b) for b in burns)<=.7 and sum(np.linalg.norm(b) for b in burns)<=1.4 and all(f['speed_mismatch_mps']<=1. and f['turn_margin_deg']>=0 for f in fs)))

def main():
 p=argparse.ArgumentParser();p.add_argument('--starts',type=int,default=100);p.add_argument('--max-nfev',type=int,default=180);p.add_argument('--energies',type=float,nargs='+',default=[30.]);p.add_argument('--output',type=Path,default=ROOT/'studies/double_earth_uranus');args=p.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
 ep=Ephemerides(Path.home()/'AppData/Local/RoLaMGAS/cache',['Earth','Uranus'],START-2,jd('2080-01-01'),1.)
 rng=np.random.default_rng(502);best=None;by_energy={};accepted=[];started=time.time();attempts=[]
 for i in range(args.starts):
  energy=args.energies[i%len(args.energies)];previous=by_energy.get(energy)
  if previous is not None and (i//len(args.energies))%3==2:
   z=np.clip(np.array(previous['z'])+rng.normal(0,.035,8),.00001,.99999)
  else:
   values=np.array([jd(f'{2028+i%18}-06-01')+rng.uniform(-150,150),rng.choice([730.5,1095.75])+rng.uniform(-10,10),rng.choice([1095.75,1461.,1826.25,2191.5]),rng.uniform(3600,5700),rng.uniform(-25,25),rng.uniform(-2,2),rng.uniform(.65,.98),rng.uniform(-.5,.5)])
   z=np.clip((values-LOW)/(HIGH-LOW),.00001,.99999)
  def residual(x):
   try:return evaluate(x,ep,energy=energy)
   except (ValueError,RuntimeError,AssertionError,OverflowError,FloatingPointError,ZeroDivisionError):return np.full(8,1e4)
  fit=least_squares(residual,z,bounds=(np.zeros(8),np.ones(8)),max_nfev=args.max_nfev,diff_step=2e-6,ftol=2e-9,xtol=2e-9,gtol=2e-9)
  try:q=evaluate(fit.x,ep,True,energy=energy)
  except (ValueError,RuntimeError,AssertionError,OverflowError,FloatingPointError,ZeroDivisionError):continue
  attempts.append(dict(attempt=i,score=q['score'],dsm=q['dsms_kms'],gap=q['combined_mismatch_mps'],turn=q['flybys'][-1]['turn_margin_deg']))
  if previous is None or q['score']<previous['score']:by_energy[energy]=q
  if best is None or q['score']<best['score']:
   best=q;atomic_json(out/'best.json',q);print(f"{i+1}/{args.starts}: DSM {q['dsms_kms']}, mismatch {q['combined_mismatch_mps']:.3f} m/s, Earth2 turn margin {q['flybys'][-1]['turn_margin_deg']:.3f}, {q['dates'][0][:10]}, {q['duration_years']:.2f} yr, passed {q['passed']}",flush=True)
  if q['passed']:
   accepted.append(q);atomic_json(out/f'passing_{len(accepted):03}.json',q)
  atomic_json(out/'progress.json',dict(attempted=i+1,starts=args.starts,elapsed_seconds=time.time()-started,accepted=len(accepted),attempts=attempts))
 print('FINISHED',len(accepted),'passing',flush=True)

if __name__=='__main__':main()
