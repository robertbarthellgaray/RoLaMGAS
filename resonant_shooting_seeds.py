"""ReachStar-informed starters; every result is rechecked against user limits.

The generic Venus return uses an explicitly requested DSM leg. It never turns
an unpowered sequence into a powered one, or relaxes an altitude/energy limit.
"""
import bootstrap
from functools import lru_cache
import json,math,time
import numpy as np
from app_paths import RESOURCE_ROOT
from ephemeris import MU_SUN,DAY
from earth_return_seeds import rtn_basis


@lru_cache(maxsize=1)
def reference():
    path=RESOURCE_ROOT/'departure_seeds/reachstar_tour.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(records=[])


def resonant_velocity(state,period_days,vinf_kms,hint):
    """Intersect a solar-period energy sphere and a planet-relative speed sphere.

    This restores the velocity-direction freedom lost at coincident Lambert
    endpoints. It is an initial guess, not proof of a safe returning encounter.
    """
    state=np.asarray(state,float);hint=np.asarray(hint,float)
    if state.shape!=(6,) or hint.shape!=(3,) or not np.isfinite(np.r_[state,hint,period_days,vinf_kms]).all() or period_days<=0 or vinf_kms<=0:
        raise ValueError('Require finite planet state, hint, positive period and excess speed')
    radius=float(np.linalg.norm(state[:3]));speed=float(np.linalg.norm(state[3:]))
    if min(radius,speed)<=0:raise ValueError('Degenerate planet state')
    axis=state[3:]/speed
    semimajor=(MU_SUN*(period_days*DAY/(2*math.pi))**2)**(1/3)
    solar_speed_squared=MU_SUN*(2/radius-1/semimajor)
    parallel=(solar_speed_squared-speed*speed-vinf_kms*vinf_kms)/(2*speed)
    if solar_speed_squared<=0 or abs(parallel)>vinf_kms+1e-10:
        raise ValueError('No velocity satisfies this period and excess speed')
    lateral=hint-axis*float(hint@axis)
    if np.linalg.norm(lateral)<1e-10:
        basis=np.eye(3)[np.argmin(abs(axis))];lateral=basis-axis*float(basis@axis)
    lateral/=np.linalg.norm(lateral)
    return state[3:]+parallel*axis+math.sqrt(max(0.,vinf_kms**2-parallel**2))*lateral


def coherent_families(route):
    legs=[i for i,(a,b) in enumerate(zip(route['bodies'],route['bodies'][1:])) if a==b=='Venus' and i in route.get('dsm_legs',[])]
    if not legs:return []
    rows=[]
    for preferred in ((1,True),(0,True)):
        family=[list(options[0]) for options in route['branch_options']]
        for i in legs:
            family[i]=next((list(b) for b in route['branch_options'][i] if tuple(b[:2])==preferred),family[i])
        for i,(a,b) in enumerate(zip(route['bodies'],route['bodies'][1:])):
            if a=='Venus' and b=='Mercury':
                family[i]=next((list(v) for v in route['branch_options'][i] if v[:2]==[2,False]),family[i])
        if family not in rows:rows.append(family)
    return rows


def preferred_branch(config,route):
    if not config.get('historical_mission_seeds',True) or config.get('local_refinement') or config.get('append_flyby'):return None
    from dynamics import Model
    from community import record_variables
    model=Model(route,config,None)
    for record in reference()['records']+reference().get('future_records',[]):
        if record['sequence']!=route['id'] or not model.c3_in_bounds(record['metrics']['launch_c3_km2_s2']):continue
        try:_,branches=record_variables(record,model)
        except (ValueError,KeyError,TypeError):continue
        return branches
    return None


def verified_seeds(config,routes,ep):
    from dynamics import Model
    from community import record_variables
    accepted=[];stats=dict(mapped=0,rejected=0,accepted=0,credit='ReachStar on Bilibili')
    if not config.get('historical_mission_seeds',True) or config.get('local_refinement') or config.get('append_flyby'):
        return dict(accepted=accepted,stats=stats)
    for route in routes:
        model=Model(route,config,ep)
        for record in reference()['records']+reference().get('future_records',[]):
            if record['sequence']!=route['id']:continue
            stats['mapped']+=1
            try:
                x,branches=record_variables(record,model)
                if not model.c3_in_bounds(model.launch_c3(x,branches)):raise ValueError('C3 outside current limits')
                q=model.evaluate(x,branches)
                if not model.accepted(q):raise ValueError('Current mission limits reject this reference')
            except (ValueError,KeyError,TypeError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):
                stats['rejected']+=1;continue
            q.update(status='passes_configured_patched_conic_screen',discovered_unix=time.time(),
                     screening_residual_norm=float(np.linalg.norm(model.residual(x,branches))),
                     reused_from=dict(library='ReachStar eight-planet reconstruction',candidate=record['id'],revalidated=True,credit='ReachStar on Bilibili'))
            accepted.append(q);stats['accepted']+=1
    return dict(accepted=accepted,stats=stats)


def seed_venus_returns(samples,model,branches):
    """Seed at most four requested V-dv-V guesses at the query's actual epochs."""
    stats=dict(attempted=0,retained=0,c3_rejected=0,source='ReachStar-informed solar-period shooting cone')
    if not model.config.get('historical_mission_seeds',True) or model.extension or model.config.get('local_refinement'):
        return [],stats
    legs=[i for i in model.dsm_legs if i>0 and model.bodies[i:i+2]==['Venus','Venus'] and i-1 not in model.dsm_legs]
    if not legs:return [],stats
    from dynamics import lambert
    points=[]
    templates=reference().get('resonant_templates',[])
    for j,original in enumerate(samples[:4]):
        point=np.asarray(original,float).copy();stats['attempted']+=1
        try:
            # Reject the departure before looking up any later planet state.
            if not model.c3_in_bounds(model.launch_c3(point,branches)):
                stats['c3_rejected']+=1;continue
            for i in legs:
                dates=model.dates(point);period=224.701
                if j%2:
                    duration=max(1,round((dates[i+1]-dates[i])/period))*period+.001
                    windows=model.config.get('event_windows_jd')
                    if windows:
                        lo,hi=windows[i+1];desired=dates[i]+duration
                    elif i+1==model.n-1 and model.config.get('arrival_window_jd'):
                        lo,hi=model.config['arrival_window_jd'];desired=dates[i]+duration
                    else:lo,hi=model.route['leg_days'][i];desired=duration
                    if lo<=desired<=hi and hi>lo:point[i+1]=(desired-lo)/(hi-lo)
                    dates=model.dates(point)
                state=model.ep.state('Venus',dates[i]);prior=model.ep.state(model.bodies[i-1],dates[i-1])
                _,arrival=lambert(prior[:3],state[:3],dates[i]-dates[i-1],branches[i-1])
                incoming=arrival-state[3:];hint=incoming
                if j>=2 and templates:
                    template=templates[(j-2)%len(templates)]
                    hint=rtn_basis(state)@np.array(template['departure_vinf_direction_rtn'])
                va=resonant_velocity(state,dates[i+1]-dates[i],float(np.linalg.norm(incoming)),hint)
                end=model.ep.state('Venus',dates[i+1]);base,_=lambert(state[:3],end[:3],dates[i+1]-dates[i],branches[i])
                k=model.n+4*model.dsm_legs.index(i);point[k]=.5
                point[k+1:k+4]=.5+(va-base)/(2*model.config['dsm_velocity_box_kms'])
            if not np.isfinite(point).all() or np.any(point<0) or np.any(point>1):continue
            if not any(np.linalg.norm(point-p)<1e-9 for p in points):points.append(point)
        except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):continue
    stats['retained']=len(points)
    return points,stats
