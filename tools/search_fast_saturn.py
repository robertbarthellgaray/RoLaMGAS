"""Fast Saturn root-tree search with Venus/Earth/Jupiter unpowered assists."""
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
    date,energy,output,*options=job;settings=options[0] if options else {}
    max_years=settings.get('max_years',8.99999);max_c3=settings.get('max_c3',29.999)
    started=time.monotonic();t0=jd(date)
    ep=Ephemerides(Path(settings.get('cache',ROOT/'cache')),['Earth','Venus','Jupiter','Saturn'],t0-2,t0+max_years*365.25+2,1.)
    answers=[];counts=dict(first_venus=0,inner_returns=0,earth_departures=0,saturn=0)
    @lru_cache(maxsize=4096)
    def coast(a,t,b,days,branch):
        sa=ep.state(a,t);sb=ep.state(b,t+days);va,vb=lambert(sa[:3],sb[:3],days,branch)
        return va-sa[3:],vb-sb[3:]
    def safe_turn(body,incoming,outgoing):
        f=flyby(body,incoming,outgoing,{'Earth':200.,'Venus':300.,'Saturn':10000.,'Jupiter':10000.}[body],.02)
        return f['passes_speed_tolerance'] and f['passes_turn_screen']
    def candidate(bodies,dates,branches):
        seq=''.join(dict(Earth='E',Venus='V',Saturn='S',Jupiter='J')[b] for b in bodies)
        durations=np.diff(dates).tolist();target=bodies[-1]
        c=normalize(dict(target=target,sequences=[seq],launch_start=date,launch_end=date,min_c3=6.25,max_c3=max_c3,max_dsm_kms=.7,
                         max_single_dsm_kms=.7,max_arrival_vinf_kms=12.,max_years=max_years,vinf_tolerance_mps=.1,
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
        if t-t0>2200:return
        end=min(1300.,t0+max_years*365.25-t-650.)
        fun=lambda d:np.linalg.norm(coast('Earth',t,'Jupiter',d,(0,True))[0])-speed
        for days in bracket_roots(fun,300.,end,10.):
            vo,jupiter_in=coast('Earth',t,'Jupiter',days,(0,True))
            if not safe_turn('Earth',incoming,vo):continue
            jt=t+days;u=np.linalg.norm(jupiter_in);upper=min(2500.,t0+max_years*365.25-jt)
            for js_days in bracket_roots(lambda d:np.linalg.norm(coast('Jupiter',jt,'Saturn',d,(0,True))[0])-u,650.,upper,12.):
                exit_velocity,_=coast('Jupiter',jt,'Saturn',js_days,(0,True))
                if safe_turn('Jupiter',jupiter_in,exit_velocity):candidate(bodies+['Jupiter','Saturn'],dates+[jt,jt+js_days],branches+[(0,True),(0,True)])
    for first_branch in [(0,True),(1,True),(1,False)]:
        first_fun=lambda d:np.linalg.norm(coast('Earth',t0,'Venus',d,first_branch)[0])**2-energy
        for d0 in bracket_roots(first_fun,45.,400.,3.):
            incoming=coast('Earth',t0,'Venus',d0,first_branch)[1];t1=t0+d0;counts['first_venus']+=1
            # Compare two Earth returns with a pair of Venus assists.
            for middle in ['Earth','Venus']:
                branches=[(0,True),(1,True),(1,False)]+([(2,True),(2,False),(3,True),(3,False)] if middle=='Venus' else [])
                lo,hi=(180.,600.) if middle=='Venus' else (45.,700.)
                extra=resonance_grid(224.701,hi) if middle=='Venus' else []
                for middle_branch in branches:
                    f=lambda d:np.linalg.norm(coast('Venus',t1,middle,d,middle_branch)[0])-np.linalg.norm(incoming)
                    for d1 in bracket_roots(f,lo,hi,5.,extra):
                        vo,next_in=coast('Venus',t1,middle,d1,middle_branch)
                        if not safe_turn('Venus',incoming,vo):continue
                        t2=t1+d1;counts['inner_returns']+=1
                        if middle=='Earth':
                            next_branches=[(0,True),(1,True),(1,False),(2,True),(2,False),(3,True),(3,False)];next_lo,next_hi=300.,1000.;extras=resonance_grid(365.256,1000.)
                        else:next_branches=[(0,True),(1,True),(1,False)];next_lo,next_hi=45.,700.;extras=[]
                        for b2 in next_branches:
                            func=lambda d:np.linalg.norm(coast(middle,t2,'Earth',d,b2)[0])-np.linalg.norm(next_in)
                            for d2 in bracket_roots(func,next_lo,next_hi,6.,extras):
                                out,last_in=coast(middle,t2,'Earth',d2,b2)
                                if not safe_turn(middle,next_in,out):continue
                                counts['earth_departures']+=1
                                outer_legs(['Earth','Venus',middle,'Earth'],[t0,t1,t2,t2+d2],[first_branch,middle_branch,b2],last_in)
    report=dict(date=date,c3_requested=energy,max_c3=max_c3,max_years=max_years,counts=counts,elapsed_seconds=time.monotonic()-started,candidates=answers)
    atomic_json(Path(output)/f'{date}_c3_{energy:g}.json',report)
    print(date,'C3',energy,counts,'seconds',round(report['elapsed_seconds'],1),flush=True)
    return {k:v for k,v in report.items() if k!='candidates'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'runs/fast_saturn');p.add_argument('--date',action='append');p.add_argument('--c3',type=float,action='append');p.add_argument('--workers',type=int,default=2);p.add_argument('--monthly',action='store_true',help='Survey the first of every month in the selected years');p.add_argument('--start-year',type=int,default=2030);p.add_argument('--end-year',type=int,default=2039);p.add_argument('--max-years',type=float,default=8.99999);p.add_argument('--max-c3',type=float,default=29.999);p.add_argument('--cache',type=Path,default=ROOT/'cache');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    if not math.isfinite(a.max_years) or not 1<=a.max_years<=20:raise ValueError('Flight-time limit must be between 1 and 20 years')
    if not math.isfinite(a.max_c3) or not 6.25<=a.max_c3<=30:raise ValueError('This survey needs 6.25 <= maximum C3 <= 30')
    if not 2030<=a.start_year<=a.end_year<=2065:raise ValueError('Launch years must be ordered within 2030–2065 for the configured ephemeris coverage')
    dates=a.date or ([] if a.monthly else ['2033-01-01','2033-02-01','2033-03-01','2033-04-01']);energies=a.c3 or [12.,16.,23.1,28.]
    if a.monthly:dates=list(dict.fromkeys(dates+[f'{y}-{m:02d}-01' for y in range(a.start_year,a.end_year+1) for m in range(1,13)]))
    if any(not math.isfinite(e) or not 6.25<=e<=a.max_c3 for e in energies):raise ValueError('Requested seed C3 must be between 6.25 and the maximum C3')
    settings=dict(max_years=a.max_years,max_c3=a.max_c3,cache=str(a.cache.resolve()))
    def matching_checkpoint(d,e):
        try:report=json.loads((a.output/f'{d}_c3_{e:g}.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):return None
        if report.get('date')!=d or report.get('c3_requested')!=e:return None
        if report.get('max_c3',29.999)!=a.max_c3 or report.get('max_years',8.99999)!=a.max_years:return None
        return report
    jobs=[(d,e,str(a.output.resolve()),settings) for d in dates for e in energies if matching_checkpoint(d,e) is None]
    if a.workers==1:
        for job in jobs:worker(job)
    else:
        from concurrent.futures import ProcessPoolExecutor,as_completed
        with ProcessPoolExecutor(max_workers=max(1,min(4,a.workers))) as pool:
            for future in as_completed([pool.submit(worker,job) for job in jobs]):future.result()
    reports=[matching_checkpoint(d,e) for d in dates for e in energies];answers=[q for r in reports if r is not None for q in r['candidates']]
    atomic_json(a.output/'all_candidates.json',answers);print('TOTAL PASSING',len(answers),flush=True)

if __name__=='__main__':main()
