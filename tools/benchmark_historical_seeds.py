"""Offline, real-ephemeris benchmark of historical initialization (not full missions)."""
from pathlib import Path
import argparse,json,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap,numpy as np
from ephemeris import Ephemerides,jd
from mission_search import normalize,routes_for
from dynamics import Model
from historical_seeds import seed_missions
ROOT=Path(__file__).resolve().parents[1]
def benchmark(cache):
    rows=[]
    for sequence,target in [('EMEJ','Jupiter'),('EVEEJ','Jupiter'),('EVdvVEJS','Saturn'),('EdvEJ','Jupiter'),('EVMeMeMe','Mercury')]:
        c=normalize(dict(target=target,sequences=[sequence],launch_start='2030-01-01',launch_end='2036-01-01',min_c3=6.25,max_c3=80,cache=str(cache)))
        route=routes_for(c)[0];ep=Ephemerides(cache,route['bodies'][:2],c['launch_jd'][0],c['launch_jd'][1]+route['leg_days'][0][1],1.)
        model=Model(route,c,ep);rng=np.random.default_rng(502);samples=rng.random((64,model.dimension));branch=[(1,True) if a==b else (0,True) for a,b in zip(model.bodies,model.bodies[1:])]
        for k in range(len(model.dsm_legs)):
            offset=model.n+4*k+1;samples[:,offset:offset+3]=.5
        valid=0
        for x in samples:
            try:valid+=int(model.c3_in_bounds(model.launch_c3(x,branch)))
            except (ValueError,RuntimeError,AssertionError):pass
        start=time.monotonic();points,stats=seed_missions(samples,model,branch);energies=[model.launch_c3(x,branch) for x in points]
        row=dict(sequence=sequence,launch_years=[2030,2036],c3_bounds=[6.25,80],ordinary_in_range_first_legs=valid,ordinary_samples=len(samples),historical_seed_stats=stats,seed_c3_km2_s2=energies,elapsed_seconds=time.monotonic()-start,full_mission_validated=False)
        rows.append(row);print(json.dumps(row),flush=True)
    return dict(scope='Initialization only: first-leg solves under hard C3 bounds; downstream flybys remain unsolved.',rows=rows)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',type=Path,required=True);p.add_argument('--output',type=Path,default=ROOT/'departure_seeds/historical_benchmark.json');a=p.parse_args();a.output.write_text(json.dumps(benchmark(a.cache),indent=2)+'\n',encoding='utf-8')
