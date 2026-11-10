"""Offline low-C3 Earth/Venus/Saturn searches, explicitly excluding Jupiter."""
from pathlib import Path
import argparse,json,math,sys,time,hashlib
from functools import lru_cache
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
import numpy as np
from scipy.optimize import brentq
from dynamics import Model,lambert,flyby
from ephemeris import Ephemerides,BODIES,jd,atomic_json
from mission_search import normalize,routes_for
from community import record_variables
ROOT=Path(__file__).resolve().parents[1]


def bracket_roots(fun,lo,hi,step=6.,extra=()):
    if hi<=lo:return []
    grid=np.unique(np.r_[np.arange(lo,hi,step),hi,[d for d in extra if lo<d<hi]])
    found=[];previous=None
    for d in grid:
        try:
            value=float(fun(float(d)))
            if not math.isfinite(value):raise ValueError('Nonfinite root bracket')
            if previous and previous[1]*value<0:
                try:
                    root=brentq(fun,previous[0],float(d),xtol=2e-8)
                    if abs(fun(root))<1e-5 and all(abs(root-r)>.001 for r in found):found.append(float(root))
                except (ValueError,RuntimeError,AssertionError,ZeroDivisionError,FloatingPointError):pass
            previous=(float(d),value)
        except (ValueError,RuntimeError,AssertionError,ZeroDivisionError,FloatingPointError):previous=None
    return found


def resonance_grid(period,maximum):
    offsets=[0.,*[sign*10.**power for power in range(-5,2) for sign in (-1,1)]]
    return [k*period+offset for k in range(1,int(maximum/period)+1) for offset in offsets]


def worker(job):
    date,energy,output=job;started=time.monotonic();t0=jd(date)
    ep=Ephemerides(ROOT/'cache',['Earth','Venus','Saturn','Neptune'],jd('2029-01-01'),jd('2075-01-01'),1.)
    answers=[];counts=dict(first_venus=0,inner_returns=0,earth_departures=0,saturn=0,neptune=0)
    @lru_cache(maxsize=4096)
    def coast(a,t,b,days,branch):
        sa=ep.state(a,t);sb=ep.state(b,t+days);va,vb=lambert(sa[:3],sb[:3],days,branch)
        return va-sa[3:],vb-sb[3:]
    def safe_turn(body,incoming,outgoing):
        f=flyby(body,incoming,outgoing,{'Earth':200.,'Venus':300.,'Saturn':10000.}[body],.02)
        return f['passes_speed_tolerance'] and f['passes_turn_screen']
    def candidate(bodies,dates,branches):
        seq=''.join(dict(Earth='E',Venus='V',Saturn='S',Neptune='N')[b] for b in bodies)
        durations=np.diff(dates).tolist();target=bodies[-1]
        c=normalize(dict(target=target,sequences=[seq],launch_start=date,launch_end=date,min_c3=6.25,max_c3=30.,max_dsm_kms=.7,
                         max_single_dsm_kms=.7,max_arrival_vinf_kms=12.,max_years=20. if target=='Saturn' else 30.,vinf_tolerance_mps=.1,
                         route_overrides={seq:dict(leg_days=[[max(1.,d*.5),d*1.5+1] for d in durations],branch_options=[[list(b)] for b in branches])}))
        route=routes_for(c)[0];model=Model(route,c,ep)
        record=dict(schema_version=1,sequence=seq,body_ids=[str(BODIES[b][0]) for b in bodies],dates_jd_tdb=dates,branches=[list(b) for b in branches],dsm_controls=[])
        x,bb=record_variables(record,model);q=model.evaluate(x,bb)
        if not model.accepted(q):return None
        q.update(status='passes_configured_patched_conic_screen',id=hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:12],study_config=c)
        answers.append(q);counts[target.lower()]+=1
        return q
    def outer_legs(bodies,dates,branches,incoming):
        t=dates[-1];speed=np.linalg.norm(incoming)
        # Bound terminal flight time and screen exact excess-speed matches.
        for target,lo,hi,max_years in [('Saturn',700.,5000.,20.),('Neptune',2800.,10000.,30.)]:
            earth=ep.state('Earth',t);vmax=np.linalg.norm(earth[3:])+speed;energy_max=.5*vmax*vmax-132712440041.27942/np.linalg.norm(earth[:3])
            if energy_max<0 and -132712440041.27942/energy_max<(8.9 if target=='Saturn' else 29.)*149597870.7:continue
            end=min(hi,t0+365.25*max_years-t)
            fun=lambda d:np.linalg.norm(coast('Earth',t,target,d,(0,True))[0])-speed
            for days in bracket_roots(fun,lo,end,14.):
                vo,terminal=coast('Earth',t,target,days,(0,True))
                if not safe_turn('Earth',incoming,vo):continue
                q=candidate(bodies+[target],dates+[t+days],branches+[(0,True)])
                if q is None or target!='Saturn':continue
                # Saturn is allowed; Jupiter never appears in this tree.
                st=t+days;u=np.linalg.norm(terminal);upper=min(8500.,t0+30*365.25-st)
                for sn_days in bracket_roots(lambda d:np.linalg.norm(coast('Saturn',st,'Neptune',d,(0,True))[0])-u,1200.,upper,18.):
                    exit_velocity,_=coast('Saturn',st,'Neptune',sn_days,(0,True))
                    if safe_turn('Saturn',terminal,exit_velocity):candidate(bodies+['Saturn','Neptune'],dates+[st,st+sn_days],branches+[(0,True),(0,True)])
    for first_branch in [(0,True),(1,True),(1,False)]:
        first_fun=lambda d:np.linalg.norm(coast('Earth',t0,'Venus',d,first_branch)[0])**2-energy
        for d0 in bracket_roots(first_fun,45.,700.,3.):
            incoming=coast('Earth',t0,'Venus',d0,first_branch)[1];t1=t0+d0;counts['first_venus']+=1
            # Compare two Earth returns with a pair of Venus assists.
            for middle in ['Earth','Venus']:
                branches=[(0,True),(1,True),(1,False)]+([(2,True),(2,False),(3,True),(3,False)] if middle=='Venus' else [])
                lo,hi=(180.,750.) if middle=='Venus' else (45.,700.)
                extra=resonance_grid(224.701,hi) if middle=='Venus' else []
                for middle_branch in branches:
                    f=lambda d:np.linalg.norm(coast('Venus',t1,middle,d,middle_branch)[0])-np.linalg.norm(incoming)
                    for d1 in bracket_roots(f,lo,hi,5.,extra):
                        vo,next_in=coast('Venus',t1,middle,d1,middle_branch)
                        if not safe_turn('Venus',incoming,vo):continue
                        t2=t1+d1;counts['inner_returns']+=1
                        if middle=='Earth':
                            next_branches=[(0,True),(1,True),(1,False),(2,True),(2,False),(3,True),(3,False)];next_lo,next_hi=300.,1800.;extras=resonance_grid(365.256,1800.)
                        else:next_branches=[(0,True),(1,True),(1,False)];next_lo,next_hi=45.,700.;extras=[]
                        for b2 in next_branches:
                            func=lambda d:np.linalg.norm(coast(middle,t2,'Earth',d,b2)[0])-np.linalg.norm(next_in)
                            for d2 in bracket_roots(func,next_lo,next_hi,6.,extras):
                                out,last_in=coast(middle,t2,'Earth',d2,b2)
                                if not safe_turn(middle,next_in,out):continue
                                counts['earth_departures']+=1
                                outer_legs(['Earth','Venus',middle,'Earth'],[t0,t1,t2,t2+d2],[first_branch,middle_branch,b2],last_in)
    report=dict(date=date,c3_requested=energy,counts=counts,elapsed_seconds=time.monotonic()-started,candidates=answers)
    atomic_json(Path(output)/f'{date}_c3_{energy:g}.json',report)
    print(date,'C3',energy,counts,'seconds',round(report['elapsed_seconds'],1),flush=True)
    return {k:v for k,v in report.items() if k!='candidates'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'runs/no_jupiter');p.add_argument('--date',action='append');p.add_argument('--c3',type=float,action='append');p.add_argument('--workers',type=int,default=2);p.add_argument('--monthly',action='store_true',help='Survey the first of every month in 2030–2039');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    dates=a.date or ['2030-09-01','2031-03-07','2032-07-01','2033-01-08','2034-05-27','2035-10-01','2036-02-28','2037-05-01','2038-01-08','2039-02-01'];energies=a.c3 or [10.,12.,14.,16.,23.1,28.]
    if a.monthly:dates=list(dict.fromkeys(dates+[f'{y}-{m:02d}-01' for y in range(2030,2040) for m in range(1,13)]))
    if any(not math.isfinite(e) or not 6.25<=e<=30 for e in energies):raise ValueError('This low-C3 survey requires 6.25 <= C3 <= 30')
    jobs=[(d,e,str(a.output.resolve())) for d in dates for e in energies if not (a.output/f'{d}_c3_{e:g}.json').exists()]
    if a.workers==1:
        for job in jobs:worker(job)
    else:
        from concurrent.futures import ProcessPoolExecutor,as_completed
        with ProcessPoolExecutor(max_workers=max(1,min(4,a.workers))) as pool:
            for future in as_completed([pool.submit(worker,job) for job in jobs]):future.result()
    reports=[json.loads(f.read_text(encoding='utf-8')) for f in a.output.glob('*_c3_*.json')];answers=[q for r in reports for q in r['candidates']]
    atomic_json(a.output/'all_candidates.json',answers);print('TOTAL PASSING',len(answers),flush=True)

if __name__=='__main__':main()
