"""JUICE-informed Earth-return guesses; all candidates retain their Lambert physics."""
import bootstrap  # noqa: F401
from functools import lru_cache
import json,math
import numpy as np
from scipy.optimize import minimize
from app_paths import RESOURCE_ROOT


def hyperbolic_departure(position,velocity,mu):
    """Osculating outgoing two-body Earth asymptote from finite-distance r/v.

    The finite velocity is not V-infinity. Solar/lunar perturbations make this
    estimate epoch-dependent once outside Earth's immediate neighborhood.
    """
    r=np.asarray(position,dtype=float);v=np.asarray(velocity,dtype=float)
    if r.shape!=(3,) or v.shape!=(3,) or not np.all(np.isfinite(r)) or not np.all(np.isfinite(v)) or not math.isfinite(mu) or mu<=0:
        raise ValueError('Require finite position, velocity and positive GM')
    radius=float(np.linalg.norm(r));h=np.cross(r,v);hn=float(np.linalg.norm(h))
    if radius<=0 or hn<1e-10 or float(r@v)<=0:raise ValueError('Require a nonradial outgoing hyperbolic state')
    c3=float(v@v)-2*mu/radius
    evec=np.cross(v,h)/mu-r/radius;e=float(np.linalg.norm(evec))
    if c3<=0 or e<=1:raise ValueError('State is not an escaping hyperbola')
    p=evec/e;q=np.cross(h/hn,p)
    asymptote=math.sqrt(c3)*(-p/e+math.sqrt(e*e-1)/e*q)
    return dict(c3_km2_s2=c3,vinf_kms=math.sqrt(c3),vinf_vector_kms=asymptote.tolist(),
                finite_speed_squared_km2_s2=float(v@v),distance_km=radius,eccentricity=e)


def rtn_basis(earth_state):
    """Columns R, T and N in heliocentric Ecliptic J2000 axes."""
    state=np.asarray(earth_state,dtype=float)
    if state.shape!=(6,) or not np.all(np.isfinite(state)):raise ValueError('Require a finite heliocentric six-state')
    r=state[:3];v=state[3:];rn=np.linalg.norm(r);h=np.cross(r,v);hn=np.linalg.norm(h)
    if rn<=0 or hn<=0:raise ValueError('Earth RTN basis is degenerate')
    radial=r/rn;normal=h/hn;tangent=np.cross(normal,radial)
    return np.column_stack([radial,tangent,normal])


@lru_cache(maxsize=1)
def reference():
    return json.loads((RESOURCE_ROOT/'departure_seeds/juice_departure.json').read_text(encoding='utf-8'))


def target_departure(earth_state,minimum_c3,maximum_c3):
    ref=reference();lo=float(minimum_c3);hi=float(maximum_c3)
    if not 0<=lo<=hi or not math.isfinite(lo+hi):raise ValueError('Invalid C3 bounds')
    margin=min(.01,(hi-lo)*.1)
    energy=float(np.clip(ref['selected']['c3_km2_s2'],lo+margin,hi-margin))
    local=np.asarray(ref['departure_direction_rtn'],dtype=float)
    return rtn_basis(earth_state)@local*math.sqrt(energy)


def seed_departures(samples,model,branches):
    """Project a few first-EE dates toward JUICE's departure in Earth RTN.

    Only first-leg Lambert evaluations are used during projection. The original
    hard C3 bounds, event windows, branch family and full chain evaluation remain
    authoritative. Later dates and DSM controls are retained. No network calls.
    """
    stats=dict(source='JUICE Horizons -28 / Earth-RTN departure',attempted=0,retained=0)
    if len(samples)==0 or model.bodies[:2]!=['Earth','Earth'] or model.extension or model.config.get('local_refinement'):
        return [],stats
    if not model.config.get('earth_return_seeds',True):return [],stats
    c=model.config;windows=c.get('event_windows_jd');free=[]
    for i in (0,1):
        span=(windows[i][1]-windows[i][0]) if windows else ((c['launch_jd'][1]-c['launch_jd'][0]) if i==0 else (model.route['leg_days'][0][1]-model.route['leg_days'][0][0]))
        if span>1e-9:free.append(i)
    if not free:return [],stats
    ref=reference();stats['reference_c3_km2_s2']=ref['selected']['c3_km2_s2']
    count=min(6,max(1,len(samples)//8));points=[];errors=[]
    # Include the observed ~494-day JUICE return, shifted by whole Earth years
    # for branch families making a different number of heliocentric revolutions.
    m=int(branches[0][0]);reference_days=ref['first_earth_return_days']
    durations=[reference_days,reference_days+(m-1)*365.25,reference_days+m*365.25]
    for j in range(count):
        x=np.asarray(samples[j],dtype=float).copy()
        if 0 in model.dsm_legs:
            k=model.n+4*model.dsm_legs.index(0);x[k+1:k+4]=.5
        if not windows:
            a,b=model.route['leg_days'][0];duration=durations[j%len(durations)]
            if a+1<duration<b-1:x[1]=(duration-a)/(b-a)
        # Some EE Lambert branches include a nearly Earth-following C3≈0
        # basin. Project onto the user's energy boundary before optimizing
        # direction, rather than asking a flat zero-energy basin to escape.
        from cost_refinement import boundary_seed
        initial=boundary_seed(model,x,branches)
        if initial is None:continue
        x=np.asarray(initial,dtype=float)
        def expanded(z):
            point=x.copy();point[free]=z;return point
        def vector(point):
            launch=model.launch_solution(point,branches)
            a=launch['states'][0];offset=np.zeros(3)
            if 0 in model.dsm_legs:
                k=model.n+4*model.dsm_legs.index(0);offset=(point[k+1:k+4]*2-1)*c['dsm_velocity_box_kms']
            return launch['va']+offset-a[3:],a,launch['c3']
        def objective(z):
            try:
                actual,earth,_=vector(expanded(z));delta=actual-target_departure(earth,model.c3_minimum,c['max_c3'])
                return float(delta@delta)
            except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):return 1e8
        def constraints(z):
            try:
                energy=model.launch_c3(expanded(z),branches)
                return np.array([energy-model.c3_minimum,c['max_c3']-energy])
            except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):return np.array([-1e8,-1e8])
        stats['attempted']+=1
        fit=minimize(objective,x[free],method='SLSQP',bounds=[(0.,1.)]*len(free),
                     constraints=[dict(type='ineq',fun=constraints)],
                     options=dict(maxiter=24,ftol=1e-8,eps=2e-6))
        point=expanded(np.clip(fit.x,0.,1.))
        try:
            if not model.c3_in_bounds(model.launch_c3(point,branches)):continue
            if any(np.linalg.norm(point[:2]-p[:2])<.001 for p in points):continue
            error=math.sqrt(objective(point[free]))
            if not math.isfinite(error):continue
            points.append(point);errors.append(error)
        except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):continue
    ordered=sorted(zip(points,errors),key=lambda pair:(model.launch_c3(pair[0],branches),pair[1]) if c.get('search_objective')=='c3' else (pair[1],model.launch_c3(pair[0],branches)))
    points=[row[0] for row in ordered];errors=[row[1] for row in ordered]
    stats['retained']=len(points)
    if errors:
        stats['minimum_departure_vector_error_kms']=min(errors)
        stats['minimum_seed_c3_km2_s2']=min(model.launch_c3(p,branches) for p in points)
    return points,stats


@lru_cache(maxsize=1)
def chain_reference():
    """A complete solver-built EdvEVEEJ family, stored in physical coordinates."""
    return json.loads((RESOURCE_ROOT/'departure_seeds/eevee_chain.json').read_text(encoding='utf-8'))


def _chain_mappings(model):
    """Map fixed reference dates/velocities without moving any user boundary."""
    if (not model.config.get('earth_return_seeds',True) or model.extension
            or model.config.get('local_refinement') or model.dsm_legs!=[0]
            or model.bodies!=['Earth','Earth','Venus','Earth','Earth','Jupiter']):return []
    from community import record_variables
    mappings=[]
    for original in chain_reference().get('candidates',[]):
        record=dict(original,sequence=model.route['id'])
        try:
            x,branches=record_variables(record,model)
            mappings.append((record,x,branches))
        except (ValueError,KeyError,TypeError,OverflowError):continue
    return mappings


def preferred_chain_branch(config,route):
    """Schedule a compatible known family even when branch effort is small."""
    from dynamics import Model
    mappings=_chain_mappings(Model(route,config,None))
    for record,x,branches in mappings:
        if config.get('effective_min_c3',config.get('min_c3',6.25))-1e-8<=record['metrics']['launch_c3_km2_s2']<=config['max_c3']+1e-8:
            return branches
    if mappings and config.get('effective_min_c3',config.get('min_c3',6.25))<=10.:
        return mappings[0][2]
    return None


def fit_initial_dsm(model,dates,branches,energy,fractions=(.7,.82,.8999)):
    """Lower first-EE launch energy while keeping a working later chain.

    Energy is an explicit bounded value. Direction and DSM epoch are fitted;
    the DSM vector itself is constructed by the existing Kepler/Lambert model.
    Every full evaluation stays inside the user's launch-energy interval.
    """
    if model.dsm_legs!=[0] or model.bodies[:2]!=['Earth','Earth'] or model.extension:
        raise ValueError('DSM continuation needs a fresh first-Earth-return route with one DSM')
    energy=float(energy)
    if not model.c3_in_bounds(energy):raise ValueError('Continuation energy is outside the requested C3 bounds')
    from community import record_variables,body_ids
    record=dict(schema_version=1,sequence=model.route['id'],body_ids=body_ids(model.config,model.route),
                dates_jd_tdb=list(dates),branches=branches,
                dsm_controls=[dict(leg_index=0,fraction=.7,departure_offset_kms=[0.,0.,0.])])
    x,_=record_variables(record,model)
    # This is only a launch-leg preflight; a high-energy full chain is never
    # evaluated to prepare the bounded lower-energy starting point.
    launch=model.launch_solution(x,branches);earth=launch['states'][0]
    basis=rtn_basis(earth);coast=launch['va']-earth[3:];local=basis.T@coast
    alpha=math.atan2(local[1],local[0]);beta=math.asin(np.clip(local[2]/np.linalg.norm(local),-1.,1.))
    def candidate(z):
        point=x.copy();point[model.n]=(z[2]-.1)/.8
        direction=basis@np.array([math.cos(z[0])*math.cos(z[1]),math.sin(z[0])*math.cos(z[1]),math.sin(z[1])])
        point[model.n+1:model.n+4]=.5+(direction*math.sqrt(energy)-coast)/(2*model.config['dsm_velocity_box_kms'])
        if not np.all(np.isfinite(point)) or np.any(point<0) or np.any(point>1):return None
        try:return model.evaluate(point,branches)
        except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):return None
    def objective(z):
        q=candidate(z)
        return q['total_dsm_kms'] if q else 1000.
    def speed(z):
        q=candidate(z)
        return q['flybys'][0]['vinf_in_kms']-q['flybys'][0]['vinf_out_kms'] if q else 1000.
    def turn(z):
        q=candidate(z)
        return (q['flybys'][0]['turn_margin_deg']-.02)/10 if q else -1000.
    best=None
    for fraction in fractions:
        start=[alpha,beta,float(np.clip(fraction,.1001,.8999))]
        fit=minimize(objective,start,method='SLSQP',bounds=[(alpha-.5,alpha+.5),(-.3,.3),(.1001,.8999)],
                     constraints=[dict(type='eq',fun=speed),dict(type='ineq',fun=turn)],
                     options=dict(maxiter=160,ftol=1e-11,eps=1e-6))
        q=candidate(fit.x)
        if q is not None and model.accepted(q) and (best is None or q['total_dsm_kms']<best['total_dsm_kms']):
            best=q
            best['departure_continuation']=dict(energy_km2_s2=energy,optimizer_success=bool(fit.success),
                optimizer_message=str(fit.message),fixed_encounter_dates=True,all_current_limits_revalidated=True)
    return best


def verified_chain_seeds(config,routes,ephemerides):
    """Recompute complete local starters; no network or historical pass flags."""
    from dynamics import Model
    import time
    candidates=[];stats=dict(mapped=0,rejected=0,accepted=0,continuations=0)
    for route in routes:
        model=Model(route,config,ephemerides);mappings=_chain_mappings(model)
        in_range=False
        for record,x,branches in mappings:
            stats['mapped']+=1
            try:
                if not model.c3_in_bounds(model.launch_c3(x,branches)):continue
                in_range=True
                q=model.evaluate(x,branches)
                if not model.accepted(q):stats['rejected']+=1;continue
            except (ValueError,KeyError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):
                stats['rejected']+=1;continue
            q.update(status='passes_configured_patched_conic_screen',discovered_unix=time.time(),
                     screening_residual_norm=float(np.linalg.norm(model.residual(x,branches))),
                     reused_from=dict(library='bundled_eevee_chain',candidate=record.get('id'),revalidated=True))
            candidates.append(q);stats['accepted']+=1
        # A narrow interval between the stored energy levels can still use the
        # same complete chain by solving a new, explicitly charged first DSM.
        if mappings and not in_range and model.c3_minimum<=10.:
            energy=model.c3_minimum if config.get('c3_seed_boundary','minimum')=='minimum' else config['max_c3']
            if energy<=10.:
                stats['continuations']+=1;record,x,branches=mappings[0]
                q=fit_initial_dsm(model,record['dates_jd_tdb'],branches,energy)
                if q is not None:
                    q.update(status='passes_configured_patched_conic_screen',discovered_unix=time.time(),
                             screening_residual_norm=float(np.linalg.norm(model.residual(q['x'],branches))),
                             reused_from=dict(library='bundled_eevee_chain_continuation',candidate=record.get('id'),revalidated=True))
                    candidates.append(q);stats['accepted']+=1
    return dict(accepted=candidates,stats=stats)
