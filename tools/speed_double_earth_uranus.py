"""Minimize Earth-only Uranus flight time, allowing C3 25–90 and high arrival V∞."""
from pathlib import Path
import sys,json,argparse,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
import bootstrap,numpy as np
from scipy.optimize import minimize
from explore_double_earth_uranus import evaluate,LOW,HIGH,START
from ephemeris import Ephemerides,jd,atomic_json

def main():
 p=argparse.ArgumentParser();p.add_argument('--single-dsm',type=float,default=.7);p.add_argument('--starts',type=int,default=42);a=p.parse_args()
 out=ROOT/'studies/time_priority_earth_uranus';out.mkdir(parents=True,exist_ok=True)
 ep=Ephemerides(Path.home()/'AppData/Local/RoLaMGAS/cache',['Earth','Uranus'],START-2,jd('2080-01-01'),1.)
 donors=[]
 for folder in ['double_earth_uranus','planar_earth_uranus_grid']:
  donors+=json.loads((ROOT/'studies'/folder/'validated.json').read_text())['candidates']
 donors.sort(key=lambda r:r['candidate']['duration_years']);LOW[3]=1500.
 accepted=[];best=None;started=time.time()
 for i in range(a.starts):
  donor=donors[i%len(donors)]['physical_initialization'];energy=float(np.clip(donor['launch_c3_km2_s2']+[0,10,25][(i//len(donors))%3],25,90))
  z=np.r_[(np.array(donor['parameters'])-LOW)/(HIGH-LOW),(energy-25)/65];z=np.clip(z,.0000001,.9999999)
  def q(z):
   try:return evaluate(z[:8],ep,True,energy=25+65*z[8])
   except (ValueError,RuntimeError,AssertionError,OverflowError,FloatingPointError,ZeroDivisionError):return None
  def cost(z):
   r=q(z);return r['duration_years']/20+.00001*r['total_dsm_kms'] if r else 10000.
  def eq(z):
   r=q(z);return r['flybys'][-1]['vinf_in_kms']-r['flybys'][-1]['vinf_out_kms'] if r else 1000.
  def ine(z):
   r=q(z)
   return np.array([a.single_dsm-.00001-r['dsms_kms'][0],a.single_dsm-.00001-r['dsms_kms'][1],r['flybys'][-1]['turn_margin_deg']/10-.002,15-r['arrival_vinf_kms']]) if r else np.full(4,-1000.)
  fit=minimize(cost,z,method='SLSQP',bounds=[(0.,1.)]*9,constraints=[dict(type='eq',fun=eq),dict(type='ineq',fun=ine)],options=dict(maxiter=250,ftol=2e-9,eps=5e-7))
  result=q(fit.x)
  atomic_json(out/f'trial_{i+1:03}.json',dict(optimizer_success=bool(fit.success),message=str(fit.message),constraints=ine(fit.x).tolist(),result=result))
  if result and result['passed'] and result['arrival_vinf_kms']<=15 and result['combined_mismatch_mps']<.1:
   result['objective']='minimum flight time';result['optimization_energy_range_km2_s2']=[25,90]
   accepted.append(result);atomic_json(out/f'passing_{len(accepted):03}.json',result)
   if best is None or result['duration_years']<best['duration_years']:
    best=result;atomic_json(out/'best.json',best);print(i+1,'FASTEST',round(result['duration_years'],3),'yr; C3',round(result['launch_c3_km2_s2'],3),'DSM',result['dsms_kms'],'arrival Vinf',round(result['arrival_vinf_kms'],3),flush=True)
  atomic_json(out/'progress.json',dict(attempted=i+1,starts=a.starts,accepted=len(accepted),elapsed_seconds=time.time()-started))
 print('DONE',len(accepted),'time-optimized solutions',flush=True)

if __name__=='__main__':main()
