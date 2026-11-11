"""Offline historical timing / Earth-RTN initialization, with hard user bounds.
These are numerical guesses, not learned model weights or accepted mission clones.
"""
import bootstrap
from functools import lru_cache
import json,math
import numpy as np
from scipy.optimize import minimize
from app_paths import RESOURCE_ROOT
from earth_return_seeds import rtn_basis

@lru_cache(maxsize=1)
def references():
    historical=json.loads((RESOURCE_ROOT/'departure_seeds/historical_missions.json').read_text(encoding='utf-8'))['missions']
    studies=[]
    for filename in ('mission_studies.json','decadal_missions.json'):
        study_path=RESOURCE_ROOT/'departure_seeds'/filename
        if study_path.exists():studies.extend(json.loads(study_path.read_text(encoding='utf-8'))['missions'])
    return historical+[m for m in studies if m.get('seed_eligible')]

def matching_references(model):
    if model.extension or model.config.get('local_refinement') or not model.config.get('historical_mission_seeds',True):return []
    rows=[]
    for mission in references():
        count=0
        for actual,known in zip(model.bodies,mission['bodies']):
            if actual!=known:break
            count+=1
        if count>=2:rows.append((count,mission))
    from ephemeris import jd
    lo,hi=model.config['launch_jd']
    def order(row):
        count,mission=row;date=(mission.get('dates') or [mission.get('launch_start')])[0]
        launch=jd(date) if date else (lo+hi)/2
        return (-count,max(lo-launch,launch-hi,0.))
    return [mission for count,mission in sorted(rows,key=order)]

def timing_guess(model,x,mission):
    """Use only matching prefix durations; fixed epochs/windows remain fixed."""
    point=np.array(x,dtype=float,copy=True);dates=model.dates(point);windows=model.config.get('event_windows_jd')
    launch=(mission.get('dates') or [mission.get('launch_start')])[0]
    if launch:
        from ephemeris import jd
        lo,hi=(windows[0] if windows else model.config['launch_jd']);desired=jd(launch)
        if lo<=desired<=hi:point[0]=.5 if lo==hi else (desired-lo)/(hi-lo)
        dates=model.dates(point)
    for i,days in enumerate(mission['planet_leg_days'],1):
        if i>=model.n or model.bodies[i]!=mission['bodies'][i]:break
        if windows:
            lo,hi=windows[i];desired=dates[i-1]+days
        elif model.config.get('arrival_window_jd') and i==model.n-1:
            lo,hi=model.config['arrival_window_jd'];desired=dates[i-1]+days
        else:
            lo,hi=model.route['leg_days'][i-1];desired=days
        point[i]=.5 if hi==lo else float(np.clip((desired-lo)/(hi-lo),0,1))
        dates=model.dates(point)
    maneuvers=mission.get('dsm_events',[])
    if mission.get('dsm_event'):maneuvers=[dict(mission['dsm_event'],fraction=mission['dsm_fraction']),*maneuvers]
    for dsm in maneuvers:
        if dsm['leg_index'] in model.dsm_legs:
            k=model.n+4*model.dsm_legs.index(dsm['leg_index'])
            point[k]=np.clip((dsm['fraction']-.1)/.8,0,1)
    return point

def seed_missions(samples,model,branches):
    stats=dict(source='NASA mission timing + JPL Horizons Earth-RTN departures',eligible=0,attempted=0,retained=0,c3_rejected=0,duplicates=0,missions=[])
    if len(samples)==0:return [],stats
    from cost_refinement import boundary_seed
    seeds=[]
    missions=matching_references(model);stats['eligible']=len(missions)
    for i,mission in enumerate(missions):
        stats['attempted']+=1
        point=timing_guess(model,samples[i%len(samples)],mission)
        if 0 in model.dsm_legs:
            k=model.n+4*model.dsm_legs.index(0);point[k+1:k+4]=.5
        # Keep a valid reference departure. Forcing an already permitted C3
        # onto the user's boundary destroys the report's encounter timing.
        try:in_range=model.c3_in_bounds(model.launch_c3(point,branches))
        except (ValueError,RuntimeError,AssertionError,OverflowError,FloatingPointError,ZeroDivisionError):in_range=False
        if not in_range:point=boundary_seed(model,point,branches)
        if point is None:
            stats['c3_rejected']+=1;continue
        departure=mission.get('departure')
        free=[index for index in (0,1) if index in model.free_indices]
        if departure and free:
            lo,hi=model.c3_minimum,model.config['max_c3'];margin=min(.01,(hi-lo)*.1)
            energy=float(np.clip(departure['selected']['c3_km2_s2'],lo+margin,hi-margin))
            direction=np.array(departure['direction_rtn'])
            def expanded(z):
                values=point.copy();values[free]=z;return values
            def objective(z):
                try:
                    values=expanded(z);launch=model.launch_solution(values,branches);offset=np.zeros(3)
                    if 0 in model.dsm_legs:
                        k=model.n+4*model.dsm_legs.index(0);offset=(values[k+1:k+4]*2-1)*model.config['dsm_velocity_box_kms']
                    earth=launch['states'][0];actual=launch['va']+offset-earth[3:]
                    delta=actual-rtn_basis(earth)@direction*math.sqrt(energy)
                    return float(delta@delta)
                except (ValueError,RuntimeError,AssertionError,OverflowError,FloatingPointError,ZeroDivisionError):return 1e8
            def constraints(z):
                try:
                    c3=model.launch_c3(expanded(z),branches);return np.array([c3-lo,hi-c3])
                except (ValueError,RuntimeError,AssertionError,OverflowError,FloatingPointError,ZeroDivisionError):return np.array([-1e8,-1e8])
            fit=minimize(objective,point[free],method='SLSQP',bounds=[(0.,1.)]*len(free),constraints=[dict(type='ineq',fun=constraints)],options=dict(maxiter=18,ftol=1e-8,eps=2e-6))
            candidate=expanded(np.clip(fit.x,0,1))
            if model.c3_in_bounds(model.launch_c3(candidate,branches)) and objective(candidate[free])<objective(point[free]):point=candidate
        if not model.c3_in_bounds(model.launch_c3(point,branches)):
            stats['c3_rejected']+=1;continue
        if any(np.linalg.norm(point-p)<1e-9 for p in seeds):
            stats['duplicates']+=1;continue
        seeds.append(point);stats['missions'].append(mission['name'])
    stats['retained']=len(seeds)
    return seeds,stats
