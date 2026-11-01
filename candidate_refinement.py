"""Create a fresh, reproducible neighborhood search from a saved candidate."""
import bootstrap  # noqa: F401
from copy import deepcopy
from datetime import timedelta
import math
import numpy as np
from ephemeris import EPOCH,JD0


def neighborhood_request(config,route,candidate,parent_run,days=30.):
    days=float(days)
    if not math.isfinite(days) or not 0<days<=365.25:
        raise ValueError('Date variation must be greater than zero and at most 365.25 days')
    dates=np.asarray(candidate['dates_jd_tdb'],dtype=float)
    if len(dates)!=len(route['bodies']) or np.any(np.diff(dates)<=0) or not np.all(np.isfinite(dates)):
        raise ValueError('Candidate encounter dates are invalid')
    request=deepcopy(config)
    for key in ('launch_jd','event_windows_jd','event_windows','local_refinement'):
        request.pop(key,None)
    windows=[]
    for i,t in enumerate(dates):
        half=min(days,*(.45*gap for gap in (np.diff(dates[max(0,i-1):min(len(dates),i+2)]))))
        a,b=t-half,t+half
        if i==0:
            a=max(a,config['launch_jd'][0]);b=min(b,config['launch_jd'][1])
        if b<=a:raise ValueError('No room for nearby dates within the saved launch window')
        windows.append([a,b])
    iso=lambda t:(EPOCH+timedelta(days=float(t)-JD0)).isoformat(timespec='microseconds')
    request.update(sequences=[route['id']],search_objective='c3',
                   event_windows=[[iso(a),iso(b)] for a,b in windows],
                   launch_start=iso(windows[0][0]),launch_end=iso(windows[0][1]),
                   max_c3=min(config['max_c3'],float(candidate['launch_c3_km2_s2'])+1e-7),
                   seed=int(config.get('seed',502))+1)
    # Preserve historical searches whose limits predate individual burn caps.
    for key in ('max_single_dsm_kms','max_powered_flyby_kms'):
        request.setdefault(key,config['max_dsm_kms'])
    request['route_overrides']={route['id']:{key:deepcopy(route[key]) for key in ('leg_days','branch_options')}}
    for options,branch in zip(request['route_overrides'][route['id']]['branch_options'],candidate['branches']):
        if list(branch) not in options:options.insert(0,list(branch))
    seed_x=list(candidate['x'])
    seed_x[:len(dates)]=[(t-a)/(b-a) for t,(a,b) in zip(dates,windows)]
    request['local_refinement']=dict(parent_run=parent_run,parent_candidate=candidate['id'],
        sequence=route['id'],date_variation_days=days,reference_c3_km2_s2=float(candidate['launch_c3_km2_s2']),
        dates_jd_tdb=dates.tolist(),seed_x=seed_x,branches=deepcopy(candidate['branches']))
    request['cost_refinements']=max(8,int(config.get('cost_refinements',3)))
    if request.get('append_flyby'):
        request['search_objective']='arrival'
        request['append_flyby']['route']=deepcopy(route)
    return request
