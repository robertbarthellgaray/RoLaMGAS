"""Build compact display-only JPL planet playback tables from verified local cache.
No network. Preserves coverage gaps; no interpolation across gaps or extrapolation.
Run: python tools/build_planet_playback.py --cache PATH
"""
from pathlib import Path
import argparse,json,sys,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from ephemeris import Ephemerides,BODIES,AU,DAY
PERIODS=dict(Mercury=87.969,Venus=224.701,Earth=365.256,Mars=686.980,Jupiter=4332.59,Saturn=10759.22,Uranus=30688.5,Neptune=60182.)

def build(cache,output):
    result=dict(schema_version=1,source='JPL Horizons cached geometric vectors',frame='Heliocentric Ecliptic J2000',time_scale='TDB',columns=['jd_tdb','x_au','y_au','z_au','vx_au_day','vy_au_day','vz_au_day'],note='Display-only Hermite interpolation, not solver ephemerides. Coverage gaps and out-of-range dates are never extrapolated.',bodies={})
    for body in BODIES:
        metas=[json.loads(p.read_text(encoding='utf-8')) for p in Path(cache).glob(body+'_*.json')]
        ranges=[]
        for m in sorted(metas,key=lambda m:m['start_jd']):
            if m['max_step_days']>1.001:continue
            lo,hi=m['start_jd'],m['end_jd']
            if ranges and lo<=ranges[-1][1]+1e-8:ranges[-1][1]=max(hi,ranges[-1][1])
            else:ranges.append([lo,hi])
        segments=[];worst=0.
        step={'Mercury':2.,'Venus':4.,'Earth':4.,'Mars':8.}.get(body,20.)
        for lo,hi in ranges:
            ep=Ephemerides(cache,[body],lo,hi,max_step_days=1.,mercury_fine=False)
            dates=np.unique(np.r_[np.arange(lo,hi,step),hi]);full=np.array([ep.state(body,t) for t in dates])
            states=np.column_stack([dates,np.round(full[:,:3]/AU,10),np.round(full[:,3:]*DAY/AU,12)])
            spline=CubicHermiteSpline(dates,states[:,1:4],states[:,4:7],extrapolate=False)
            mids=(dates[:-1]+dates[1:])/2
            errors=np.array([np.linalg.norm((spline(t)-ep.state(body,t)[:3]/AU)*AU) for t in mids])
            worst=max(worst,float(np.max(errors,initial=0)))
            segments.append(dict(start=lo,end=hi,states=states.tolist()))
        result['bodies'][body]=dict(horizons_id=str(BODIES[body][0]),period_days=PERIODS[body],segments=segments,display_step_days=step,max_midpoint_error_km=worst)
        print(body,len(ranges),'coverage segments; max midpoint interpolation error km',round(worst,3),flush=True)
    raw=json.dumps(result,separators=(',',':'),allow_nan=False)+'\n';Path(output).write_text(raw,encoding='utf-8')
    print('Saved',output,'bytes',len(raw.encode()),'sha256',hashlib.sha256(raw.encode()).hexdigest(),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',required=True,type=Path);p.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'docs/data/planet_playback.json');a=p.parse_args();build(a.cache,a.output)
