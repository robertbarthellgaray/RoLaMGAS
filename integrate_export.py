"""Finite-radius patched-conic visualization, explicit junction burns, CSV/XYZV."""
import bootstrap  # noqa: F401
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import traceback
from functools import lru_cache
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq
from dynamics import kepler,lambert,HARD_MIN_C3,supported_launch_energy
from arrival_geometry import planet_pole,target_plane_axis,capture_assessment,validate_inclination
from ephemeris import AU,BODIES,DAY,JD0,MU_SUN,Ephemerides,atomic_json,calendar,fetch
from mission_search import normalize,routes_for,get_ephemerides


def unit(v):
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise ValueError('Degenerate asymptote geometry')
    return np.asarray(v)/n


def rotate(v,h,angle):
    return v*np.cos(angle)+np.cross(h,v)*np.sin(angle)+h*np.dot(h,v)*(1-np.cos(angle))


def plane_axis(r,u):
    h = np.cross(r,u)
    if np.linalg.norm(h) < 1e-8:
        h = np.cross([0.,0.,1.],u)
    if np.linalg.norm(h) < 1e-8:
        h = np.cross([1.,0.,0.],u)
    return unit(h)


def hyperbolic_time(mu,rp,speed,radius):
    a = mu/speed**2
    e = 1+rp/a
    H = np.arccosh(max(1.,(radius/a+1)/e))
    return float(np.sqrt(a**3/mu)*(e*np.sinh(H)-H))


def hyperbolic_state(mu,r,v,t):
    rp=float(np.linalg.norm(r));speed2=float(v@v)-2*mu/rp
    if speed2<=0:
        raise ValueError('Require positive hyperbolic excess energy')
    a=mu/speed2;e=1+rp/a;n=np.sqrt(mu/a**3)
    M=n*abs(t)
    if M==0:
        return np.r_[r,v]
    high=max(1.,float(np.arcsinh(M/e))+2)
    H=brentq(lambda h:e*np.sinh(h)-h-M,0.,high,xtol=1e-13)
    H=math.copysign(H,t)
    p,q=unit(r),unit(v)
    position=a*(e-np.cosh(H))*p+a*np.sqrt(e*e-1)*np.sinh(H)*q
    rate=n/(e*np.cosh(H)-1)
    velocity=a*rate*(-np.sinh(H)*p+np.sqrt(e*e-1)*np.cosh(H)*q)
    return np.r_[position,velocity]


def two_body_rhs(t,state,mu):
    """One point-mass acceleration only, expressed in that body's inertial axes."""
    return np.r_[state[3:],-mu*state[:3]/np.linalg.norm(state[:3])**3]


def integrate_relative(mu,r,v,t0,t1):
    initial = hyperbolic_state(mu,r,v,t0)
    def rhs(t,y):return two_body_rhs(t,y,mu)
    fit = solve_ivp(rhs,(t0,t1),initial,method='DOP853',rtol=2.5e-13,
                    atol=np.r_[np.full(3,1e-8),np.full(3,1e-12)],dense_output=True)
    if not fit.success:
        raise ValueError('Planet-centered integration failed: '+fit.message)
    expected = hyperbolic_state(mu,r,v,t1)
    error = float(np.linalg.norm(fit.y[:3,-1]-expected[:3]))
    return fit.sol,error


def planet_pieces(body,date,ep,uin=None,uout=None,altitude=200.,departure=False,terminal=False,powered=False,arrival_inclination_deg=None):
    _,mu,radius,_ = BODIES[body]
    desired_inclination=validate_inclination(arrival_inclination_deg)
    if desired_inclination is not None and (not terminal or departure):
        raise ValueError("Arrival inclination targets apply only to the terminal planetary encounter")
    planet = ep.state(body,date)
    soi = np.linalg.norm(planet[:3])*(mu/MU_SUN)**.4
    if departure or terminal:
        rp = radius+altitude
        speed = float(np.linalg.norm(uout if departure else uin))
        alpha = float(np.arcsin(1/(1+rp*speed*speed/mu)))
        direction = unit(uout if departure else uin)
        h = plane_axis(planet[:3],direction)
        if desired_inclination is not None:
            h=target_plane_axis(direction,planet_pole(body,date),h,desired_inclination)
        tangent = rotate(direction,h,-alpha if departure else alpha)
        radial = np.cross(tangent,h)
        ni=no=speed
    elif powered:
        from powered_flyby import geometry
        power=geometry(mu,radius+altitude,uin,uout,.799*soi)
        rp=power['periapsis_radius_km'];ni=float(np.linalg.norm(uin));no=float(np.linalg.norm(uout))
    else:
        ni,no = float(np.linalg.norm(uin)),float(np.linalg.norm(uout))
        a,b = unit(uin),unit(uout)
        angle = float(np.arctan2(np.linalg.norm(np.cross(a,b)),np.dot(a,b)))
        def mismatch(rp):
            return np.arcsin(1/(1+rp*ni*ni/mu))+np.arcsin(1/(1+rp*no*no/mu))-angle
        low = radius+altitude
        high = .8*soi
        if low>=high or mismatch(low)<-1e-10 or mismatch(high)>0:
            raise ValueError(f'{body}: this ideal flyby cannot be represented inside the selected sphere of influence. Refine its geometry or select another candidate.')
        rp = brentq(mismatch,low,high,xtol=1e-7) if mismatch(low)>0 else low
        h = unit(np.cross(a,b))
        alpha = float(np.arcsin(1/(1+rp*ni*ni/mu)))
        tangent = rotate(a,h,alpha)
        radial = np.cross(tangent,h)
    if rp>=.8*soi:
        raise ValueError(f'{body}: periapsis is too close to its patch boundary')
    if powered and not departure and not terminal:
        relr=np.array(power['peri_position_km']);vpin=np.array(power['peri_in_velocity_kms']);vpout=np.array(power['peri_out_velocity_kms'])
    else:
        relr = rp*radial
        vpin = np.sqrt(ni*ni+2*mu/rp)*tangent
        vpout = np.sqrt(no*no+2*mu/rp)*tangent
    tin = hyperbolic_time(mu,rp,ni,soi)
    tout = hyperbolic_time(mu,rp,no,soi)
    pieces = []
    for begin,end,velocity in ([] if departure else [(-tin,0.,vpin)])+([] if terminal else [(0.,tout,vpout)]):
        solution,error = integrate_relative(mu,relr,velocity,begin,end)
        def state(j,solution=solution,date=date,body=body):
            return ep.state(body,j)+solution((j-date)*DAY)
        pieces.append(dict(start=date+begin/DAY,end=date+end/DAY,state=state,
                           label=body+' hyperbola',kind='planet',body=body,numerical_error_km=error,
                           force_center=body,gm_km3_s2=mu,soi_radius_km=float(soi)))
    return dict(pieces=pieces,rp=rp,altitude=rp-radius,body=body,date=date,soi=soi,
                peri_position=relr,peri_in_velocity=vpin,peri_out_velocity=vpout,
                capture_assessment=capture_assessment(body,date,mu,uin,relr,vpin,desired_inclination) if terminal else None)


@lru_cache(maxsize=256)
def reference_sweep(r_values,v_values,dt):
    r,v = np.asarray(r_values),np.asarray(v_values)
    energy = np.dot(v,v)/2-MU_SUN/np.linalg.norm(r)
    if energy>=0:
        return 0.
    a = -MU_SUN/(2*energy)
    period = 2*np.pi*np.sqrt(a**3/MU_SUN)
    h = unit(np.cross(r,v)); p=unit(r); q=np.cross(h,p)
    times = np.linspace(0,dt,min(3000,max(60,int(dt/period*60)+60)))
    points = np.asarray([kepler(r,v,float(t))[0] for t in times])
    angles = np.unwrap(np.arctan2(points@q,points@p))
    return float(angles[-1]-angles[0])


def revolutions(segment):
    sweep=reference_sweep(tuple(segment['r']),tuple(segment['v']),
                          (segment['end_jd']-segment['start_jd'])*DAY)
    return max(0,int(np.floor(sweep/(2*np.pi)+1e-8)))


def continued_reference_sweep(r,v,ra,rb,start_seconds,end_seconds):
    """Unwrapped true-anomaly change, including date shifts exceeding an orbit."""
    radius=np.linalg.norm(r);energy=v@v/2-MU_SUN/radius
    if energy>=0:return 0.
    h=unit(np.cross(r,v));eccentricity=np.cross(v,np.cross(r,v))/MU_SUN-r/radius
    eccentricity_norm=np.linalg.norm(eccentricity);a=-MU_SUN/(2*energy);rate=np.sqrt(MU_SUN/a**3)
    if eccentricity_norm<1e-9:return float(rate*(end_seconds-start_seconds))
    def wrapped_angle(point):
        value=np.arctan2(h@np.cross(eccentricity,point),eccentricity@point)
        return float((value+np.pi)%(2*np.pi)-np.pi)
    first=wrapped_angle(r)
    E=np.arctan2(np.sqrt(max(0.,1-eccentricity_norm**2))*np.sin(first),eccentricity_norm+np.cos(first))
    mean0=E-eccentricity_norm*np.sin(E)
    def phase(point,seconds):return wrapped_angle(point)+2*np.pi*np.floor((mean0+rate*seconds+np.pi)/(2*np.pi))
    return float(phase(rb,end_seconds)-phase(ra,start_seconds))


def solar_velocities(start,end,r0,r1,reference,low=True,boundary_velocities=None):
    """Keep the physical winding, even when finite SOI endpoints cross 0/360°."""
    if end<=start:
        raise ValueError('Finite flyby patches overlap a DSM or the next encounter')
    r,v=np.asarray(reference['r']),np.asarray(reference['v'])
    h=unit(np.cross(r,v));prograde=bool(h[2]>=0)
    def angle(a,b):return float(np.arctan2(np.dot(h,np.cross(a,b)),np.dot(a,b)))
    ra,reference_departure=kepler(r,v,(start-reference['start_jd'])*DAY)
    rb,_=kepler(r,v,(end-reference['start_jd'])*DAY)
    sweep=continued_reference_sweep(r,v,ra,rb,(start-reference['start_jd'])*DAY,(end-reference['start_jd'])*DAY)
    finite_angle=angle(r0,r1)%(2*np.pi)
    m=max(0,int(round((sweep-finite_angle)/(2*np.pi))))
    choices=[]
    for path in ([low,not low] if m else [True]):
        try:
            va,vb=lambert(np.asarray(r0),np.asarray(r1),end-start,(m,path,prograde))
            if boundary_velocities is None:score=np.linalg.norm(va-reference_departure)
            else:
                score=sum(np.linalg.norm(velocity-np.asarray(target)) for velocity,target in
                          zip((va,vb),boundary_velocities) if target is not None)
            choices.append((float(score),va,vb))
        except (ValueError,RuntimeError,AssertionError):pass
    if not choices:
        raise ValueError('No finite-boundary Lambert solution near the original winding. This candidate needs further targeting.')
    cost,va,vb=min(choices,key=lambda q:q[0])
    return va,vb,m,cost


def solar_piece(start,end,r0,r1,reference,low=True,boundary_velocities=None):
    va,vb,m,selection_cost=solar_velocities(start,end,r0,r1,reference,low,boundary_velocities)
    def rhs(t,y):return two_body_rhs(t,y,MU_SUN)
    duration = (end-start)*DAY
    fit = solve_ivp(rhs,(0,duration),np.r_[r0,va],method='DOP853',rtol=2.5e-13,
                    atol=np.r_[np.full(3,1e-6),np.full(3,1e-13)],dense_output=True)
    if not fit.success:
        raise ValueError('Heliocentric integration failed: '+fit.message)
    def state(j):
        return fit.sol((j-start)*DAY)
    error = float(np.linalg.norm(fit.y[:3,-1]-r1))
    return dict(start=start,end=end,state=state,label='Heliocentric coast',kind='solar',
                numerical_error_km=error,revolutions=m,force_center='Sun',gm_km3_s2=MU_SUN,
                boundary_selection_delta_v_kms=selection_cost if boundary_velocities is not None else None)


MONTH_DAYS=365.25/12


def validate_post_flyby_months(value):
    value=float(value)
    if not math.isfinite(value) or value<0:raise ValueError('Months after flyby must be nonnegative and finite')
    return value


def extend_planet_ephemerides(ep,c,start,end,status,bodies=None):
    """Load cached coverage first; download only a missing future interval."""
    for body in (list(ep.splines) if bodies is None else bodies):
        if body not in BODIES:continue
        old_end=JD0+ep.splines[body].x[-1]/DAY
        if old_end>=end:continue
        status('Checking '+body+' position coverage for the SOI patch frame (not n-body gravity)…')
        step=min(c['max_ephemeris_step_days'],.25) if body=='Mercury' else c['max_ephemeris_step_days']
        try:extended=Ephemerides(c['cache'],[body],start,end,step)
        except ValueError:
            cursor=old_end-2*step
            while cursor<end:
                stop=min(end+step,cursor+5000*step)
                status('Downloading '+body+' through '+calendar(stop))
                fetch(c['cache'],body,cursor,stop,step)
                if stop>=end:break
                cursor=stop-step
            extended=Ephemerides(c['cache'],[body],start,end,step)
        ep.splines[body]=extended.splines[body];ep.manifest[body]=extended.manifest[body]


def heliocentric_orbit_summary(state,epoch):
    """Sun-only osculating diagnostics; does not alter propagation or add a burn."""
    def display_date(value):
        try:return calendar(value)
        except (OverflowError,ValueError):return None
    y=np.asarray(state,float);r=float(np.linalg.norm(y[:3]));speed=float(np.linalg.norm(y[3:]))
    energy=speed*speed/2-MU_SUN/r;h=np.cross(y[:3],y[3:]);ecc=float(np.linalg.norm(np.cross(y[3:],h)/MU_SUN-y[:3]/r))
    result=dict(epoch_jd_tdb=float(epoch),specific_energy_km2_s2=energy,speed_kms=speed,
                solar_escape_speed_kms=float(np.sqrt(2*MU_SUN/r)),radial_velocity_kms=float(y[:3]@y[3:]/r),
                eccentricity=ecc,sun_bound=bool(energy < -1e-10),reference='Sun-only osculating conic; later planetary encounters are not modeled')
    if result['sun_bound']:
        a=-MU_SUN/(2*energy);result.update(semimajor_axis_au=a/AU,perihelion_au=a*(1-ecc)/AU,aphelion_au=a*(1+ecc)/AU,period_years=float(2*np.pi*np.sqrt(a**3/MU_SUN)/(365.25*DAY)))
        if 1e-8<ecc<1:
            E=float(np.arctan2(y[:3]@y[3:]/(ecc*np.sqrt(MU_SUN*a)),(1-r/a)/ecc))
            mean=(E-ecc*np.sin(E))%(2*np.pi);to_apo=(np.pi-mean)%(2*np.pi)/np.sqrt(MU_SUN/a**3)/DAY
            apo_epoch=float(epoch+to_apo);peri_epoch=float(epoch+(-mean)%(2*np.pi)/np.sqrt(MU_SUN/a**3)/DAY);result.update(next_aphelion_jd_tdb=apo_epoch,next_aphelion_date=display_date(apo_epoch),next_perihelion_jd_tdb=peri_epoch,next_perihelion_date=display_date(peri_epoch))
    return result


def solar_continuation(start,end,initial):
    initial=np.array(initial,dtype=float);seconds=(end-start)*DAY
    expected,_=kepler(initial[:3],initial[3:],seconds)
    def rhs(t,y):return two_body_rhs(t,y,MU_SUN)
    fit=solve_ivp(rhs,(0,seconds),initial,method='DOP853',rtol=2.5e-13,
                  atol=np.r_[np.full(3,1e-6),np.full(3,1e-13)],dense_output=True,max_step=2*DAY)
    if not fit.success:raise ValueError('Post-flyby heliocentric integration failed: '+fit.message)
    def state(date):return fit.sol((date-start)*DAY)
    return dict(start=start,end=end,state=state,label='Post-flyby heliocentric coast',kind='solar',
                numerical_error_km=float(np.linalg.norm(fit.y[:3,-1]-expected)),force_center='Sun',gm_km3_s2=MU_SUN)


def post_flyby_pieces(node,ep,end,initial):
    """Unpowered outgoing hyperbola to SOI, followed by a continuous solar IVP."""
    date=node['date']
    if end<=date:return []
    if node['body'] not in BODIES:return [solar_continuation(date,end,initial)]
    body=node['body'];mu=BODIES[body][1]
    r=np.array(node['peri_position']);v=np.array(node['peri_in_velocity'])
    excess=math.sqrt(float(v@v)-2*mu/node['rp'])
    exit_seconds=hyperbolic_time(mu,node['rp'],excess,node['soi'])
    boundary=date+exit_seconds/DAY
    stop=min(end,boundary)
    solution,error=integrate_relative(mu,r,v,0,(stop-date)*DAY)
    def state(epoch):return ep.state(body,epoch)+solution((epoch-date)*DAY)
    outgoing=dict(start=date,end=stop,state=state,label=body+' outbound flyby',kind='planet',body=body,numerical_error_km=error,
                  force_center=body,gm_km3_s2=mu,soi_radius_km=float(node['soi']))
    result=[outgoing]
    if end>boundary:result.append(solar_continuation(boundary,end,state(boundary)))
    return result


def sample_piece(piece,exclude_end=False):
    a,b = piece['start'],piece['end']
    if exclude_end:
        b -= .02/DAY  # Strictly increasing XYZV epochs around an impulse.
    fn = piece['state']
    result = []
    def subdivide(t0,y0,t1,y1,depth=0):
        dt = (t1-t0)*DAY
        tm=(t0+t1)/2
        ym=fn(tm)
        # Midpoint Hermite interpolation error; use a conservative 0.1 km
        # tolerance, with at most 2-day solar samples and 2-hour flyby samples.
        estimate=.5*(y0[:3]+y1[:3])+dt/8*(y0[3:]-y1[3:])
        maximum = 2. if piece['kind']=='solar' else 2/24
        if depth<24 and ((t1-t0)>maximum or np.linalg.norm(estimate-ym[:3])>.1):
            subdivide(t0,y0,tm,ym,depth+1)
            subdivide(tm,ym,t1,y1,depth+1)
        else:
            result.append((t0,y0))
    subdivide(a,fn(a),b,fn(b))
    result.append((b,fn(b)))
    return result


def clearances(pieces,samples,ep):
    rows = []
    for body in list(ep.splines)+['Sun']:
        if body!='Sun' and body not in BODIES:
            continue
        radius = 695700. if body=='Sun' else BODIES[body][2]
        best = None
        for piece,knots in zip(pieces,samples):
            fn=piece['state']
            def relative(date):
                return fn(date)-(np.zeros(6) if body=='Sun' else ep.state(body,date))
            def derivative(date):
                y=relative(date)
                return float(y[:3]@y[3:])
            dates=[t for t,y in knots]
            # Evaluate every stored knot, and bracket local range minima in
            # each interval. This is not an exhaustive polynomial-root audit.
            for t in dates:
                y=relative(t);r=float(np.linalg.norm(y[:3]))
                if best is None or r<best[0]: best=(r,t)
            values=[derivative(t) for t in dates]
            for t0,t1,d0,d1 in zip(dates,dates[1:],values,values[1:]):
                if d0<0<d1:
                    t=brentq(derivative,t0,t1,xtol=1e-10)
                    r=float(np.linalg.norm(relative(t)[:3]))
                    if r<best[0]: best=(r,t)
        rows.append(dict(body=body,julian_date_tdb=best[1],date=calendar(best[1]),
                         center_distance_km=best[0],altitude_km=best[0]-radius))
    return rows


def requirement_violations(q,c):
    failures=[]
    for field,limit,label in [('launch_c3_km2_s2','max_c3','Launch C3'),
                             ('total_dsm_kms','max_dsm_kms','Designed DSM (km/s)'),
                             ('arrival_vinf_kms','max_arrival_vinf_kms','Arrival V-infinity (km/s)'),
                             ('duration_years','max_years','Duration (years)')]:
        if q[field]>c[limit]+1e-8:
            failures.append(f'{label}: {q[field]:.8g} exceeds requested {c[limit]:.8g}')
    energy_floor=c.get('effective_min_c3',c.get('min_c3',0))
    if q['launch_c3_km2_s2']<energy_floor-1e-8:
        failures.append(f"Launch C3 is below the effective requested minimum {energy_floor:.8g}")
    window=c.get('arrival_window_jd')
    if window and not window[0]-1e-8<=q['dates_jd_tdb'][-1]<=window[1]+1e-8:
        failures.append('Arrival epoch is outside the requested arrival-date window')
    for f in q['flybys']:
        if f.get('powered_flyby',{}).get('magnitude_kms',0.)>c['max_powered_flyby_kms']+1e-9:
            failures.append(f"{f['body']} powered flyby exceeds individual cap {c['max_powered_flyby_kms']*1000:.8g} m/s")
        if f.get('passes_powered_geometry'):continue
        if f['speed_mismatch_mps']>c['vinf_tolerance_mps']+1e-8:
            failures.append(f"{f['body']} V-infinity mismatch: {f['speed_mismatch_mps']:.8g} m/s exceeds requested {c['vinf_tolerance_mps']:.8g}")
        if f['turn_margin_deg'] < -1e-8:
            failures.append(f"{f['body']} turn angle exceeds the limit at the requested minimum altitude")
    if any(b['magnitude_kms']>c['max_single_dsm_kms']+1e-9 for b in q.get('dsms',[])):
        failures.append(f"A DSM exceeds individual cap {c['max_single_dsm_kms']*1000:.8g} m/s")
    if any(b['magnitude_kms']>c['max_single_dsm_kms']+1e-9 for b in q.get('event_burns',[])):
        failures.append(f"A target-turnaround burn exceeds the individual DSM cap {c['max_single_dsm_kms']*1000:.8g} m/s")
    return failures


def export_budget_breakdown(candidate,burns):
    """Do not mistake a scalar V-infinity residual for a feasible vector burn."""
    unresolved=[f for f in candidate.get('flybys',[]) if not f.get('passes_powered_geometry',False)
                and (not f.get('speed_matched_to_1_mm_s',f.get('speed_mismatch_mps',0.)<=.001)
                     or not f.get('passes_turn_screen',True))]
    def total(kinds):return float(sum(b['magnitude_kms'] for b in burns if b['kind'] in kinds))
    return dict(candidate_cruise_dsm_kms=float(candidate.get('cruise_dsm_kms',sum(b['magnitude_kms'] for b in candidate.get('dsms',[])))),
        candidate_modeled_flyby_burns_kms=float(candidate.get('powered_flyby_delta_v_kms',0.)),
        candidate_modeled_target_turnaround_kms=float(candidate.get('turnaround_delta_v_kms',sum(b['magnitude_kms'] for b in candidate.get('event_burns',[]) if b.get('kind')=='target_turnaround'))),
        candidate_modeled_maneuver_total_kms=float(candidate.get('total_dsm_kms',0.)),
        candidate_maneuver_budget_complete=bool(candidate.get('maneuver_budget_complete',not unresolved)),
        unresolved_flyby_count=int(candidate.get('unresolved_flyby_count',len(unresolved))),
        unresolved_speed_mismatch_total_mps=float(candidate.get('unresolved_speed_mismatch_total_mps',sum(f.get('speed_mismatch_mps',0.) for f in unresolved))),
        unresolved_speed_mismatch_is_delta_v=False,
        exported_cruise_dsm_kms=total({'retargeted_DSM'}),
        exported_target_turnaround_kms=total({'target_turnaround'}),
        exported_modeled_powered_flyby_kms=total({'powered_flyby'}),
        exported_additional_periapsis_speed_match_kms=total({'flyby_speed_match_burn'}),
        exported_finite_soi_boundary_junction_kms=total({'finite_patch_junction'}),
        exported_total_onboard_kms=float(sum(b['magnitude_kms'] for b in burns if not b['kind'].startswith('launch'))),
        note='The candidate modeled total excludes unresolved joins. Exported periapsis impulses and finite SOI-boundary retargeting impulses are explicit vector burns; no scalar V-infinity residual is silently substituted for either.')


def small_body_node(body,date,ep,incoming_vinf,distance_km=10000.):
    """Geometric center-distance targeting; no invented target GM or radius."""
    distance_km=float(distance_km)
    if not math.isfinite(distance_km) or distance_km<=0:
        raise ValueError('Target-center encounter distance must be positive and finite')
    direction=unit(incoming_vinf)
    target_state=ep.state(body,date).copy()
    h=plane_axis(target_state[:3],direction)
    target_state[:3]+=distance_km*unit(np.cross(direction,h))
    return dict(pieces=[],body=body,date=date,target_state=target_state,rp=None,
                altitude=None,center_distance_km=distance_km)


def minor_body_event_node(candidate,index,ep,distance_km=10000.):
    """A finite geometric visit; its incoming/outgoing velocity change is a burn."""
    event=candidate['events'][index];body=event['body'];date=event['julian_date_tdb']
    incoming=np.asarray(candidate['arrival_velocities_kms'][index-1],dtype=float)
    target=np.asarray(event['planet_state_km_kms'],dtype=float)
    node=small_body_node(body,date,ep,incoming-target[3:],distance_km)
    node['incoming_heliocentric_velocity_kms']=incoming
    if index<len(candidate['events'])-1:
        node['outgoing_heliocentric_velocity_kms']=np.asarray(candidate['departure_velocities_kms'][index],dtype=float)
    return node


def node_coast_boundary(node,outgoing):
    """Connect a solar coast to a hyperbola or a zero-GM geometric visit."""
    if node['pieces']:
        piece=node['pieces'][-1] if outgoing else node['pieces'][0]
        date=piece['end'] if outgoing else piece['start']
        return date,piece['state'](date)
    state=np.asarray(node['target_state'],dtype=float).copy()
    key='outgoing_heliocentric_velocity_kms' if outgoing else 'incoming_heliocentric_velocity_kms'
    if key in node:state[3:]=node[key]
    return node['date'],state


MAX_PATCH_EPOCH_SHIFT_DAYS=365.25


def validate_patch_epoch_shift(value):
    value=float(value)
    if not math.isfinite(value) or not 0<=value<=MAX_PATCH_EPOCH_SHIFT_DAYS:
        raise ValueError(f'Finite-patch flyby date adjustment must be between 0 and {MAX_PATCH_EPOCH_SHIFT_DAYS:g} days')
    return value


def export(candidate,config,output,arrival_altitude_km=None,powered_flybys=None,post_flyby_months=0.,arrival_inclination_deg=None,refine_patches=True,patch_epoch_shift_days=2.):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    def status(message):
        atomic_json(output/'integration_status.json',dict(state='running',message=message))
    q=json.loads(Path(candidate).read_text(encoding='utf-8'))
    if not supported_launch_energy(q.get('launch_c3_km2_s2')):
        raise ValueError(f'Candidate launch C3 must be finite and at least {HARD_MIN_C3:g} km²/s²; rerun the launch search.')
    original_status=q['status']
    arrival_inclination_deg=validate_inclination(arrival_inclination_deg)
    patch_epoch_shift_days=validate_patch_epoch_shift(patch_epoch_shift_days)
    if arrival_inclination_deg is not None and q['events'][-1]['body'] not in BODIES:
        raise ValueError('Arrival inclination targeting requires a supported planet with known pole and GM')
    config=dict(config)
    if powered_flybys is not None:config['powered_flybys']=powered_flybys
    c=normalize(config,Path(candidate).parent)
    post_flyby_months=validate_post_flyby_months(post_flyby_months)
    encounter_date=q['events'][-1]['julian_date_tdb']
    extended_end=encounter_date+post_flyby_months*MONTH_DAYS
    if post_flyby_months>0 and extended_end<=encounter_date:raise ValueError('Post-flyby duration is too small to represent in Julian dates')
    if arrival_altitude_km is not None:
        arrival_altitude_km=float(arrival_altitude_km)
        if not math.isfinite(arrival_altitude_km) or arrival_altitude_km<=0:
            raise ValueError('Arrival altitude must be positive and finite')
    ep=get_ephemerides(c,routes_for(c))
    if post_flyby_months>0:
        # Only the final encounter's center is needed by the post-flyby force
        # patch. Other cached planet vectors are optional clearance inputs.
        extend_planet_ephemerides(ep,c,q['events'][0]['julian_date_tdb']-2,extended_end+2,status,
                                  bodies=[q['events'][-1]['body']])
    if powered_flybys is not None or c.get('powered_flybys'):
        from dynamics import Model
        model=Model(next(r for r in routes_for(c) if r['id']==q['sequence']),c,ep)
        updated=model.evaluate(q['x'],q['branches'],enforce_c3=False);updated['id']=q['id']
        updated['status']='passes_configured_patched_conic_screen' if model.accepted(updated) else 'near_miss_not_accepted'
        q=updated
    violations=requirement_violations(q,c)
    status('Constructing finite-radius departure and flyby hyperbolas…')
    nodes=[]
    for i,e in enumerate(q['events']):
        body,date=e['body'],e['julian_date_tdb']
        if i==0:
            node=planet_pieces(body,date,ep,uout=np.array(q['launch_vinf_vector_kms']),altitude=200.,departure=True)
        elif body in BODIES:
            floor=c['minimum_altitude_km'].get(body,BODIES[body][3])
            f=next((f for f in q['flybys'] if f.get('event_index')==i),None) if i<len(q['events'])-1 else None
            if i<len(q['events'])-1 and f is None:
                raise ValueError(f'Missing planetary flyby geometry for event {i}: {body}')
            if f is None and arrival_altitude_km is not None:floor=arrival_altitude_km
            node=planet_pieces(body,date,ep,uin=np.array(f['incoming_vinf_vector_kms'] if f else q['arrival_vinf_vector_kms']),
                               uout=np.array(f['outgoing_vinf_vector_kms']) if f else None,
                               altitude=0. if f and not q['status'].startswith('passes') and not c.get('powered_flybys') else floor,
                               terminal=i==len(q['events'])-1,powered=bool(f and c.get('powered_flybys')),
                               arrival_inclination_deg=arrival_inclination_deg if i==len(q['events'])-1 else None)
            if f and node['altitude']<floor-1e-6:
                violations.append(f"{body} integrated flyby altitude {node['altitude']:.8g} km is below requested {floor:.8g} km")
        else:
            distance=arrival_altitude_km if i==len(q['events'])-1 and arrival_altitude_km is not None else 10000.
            node=minor_body_event_node(q,i,ep,distance)
        nodes.append(node)
    from finite_targeting import match_finite_patches
    try:
        if refine_patches:
            nodes,targeted_dsm_points,targeting_report=match_finite_patches(nodes,q,c,ep,status,max_epoch_shift_days=patch_epoch_shift_days)
        else:targeted_dsm_points={};targeting_report=dict(applied=False,reason='Local finite-patch refinement disabled')
    except (ValueError,RuntimeError,AssertionError,FloatingPointError) as error:
        targeted_dsm_points={};targeting_report=dict(applied=False,reason='Local match unavailable: '+str(error))
    atomic_json(output/'finite_targeting.json',targeting_report)
    pieces=list(nodes[0]['pieces'])
    segment_index=0
    for i in range(len(nodes)-1):
        left,right=nodes[i],nodes[i+1]
        begin,y0=node_coast_boundary(left,True)
        end,y1=node_coast_boundary(right,False)
        burn=next((b for b in q['dsms'] if b['leg_index']==i),None)
        reference=q['segments'][segment_index]
        if burn:
            mid=burn['julian_date_tdb'];point=targeted_dsm_points.get(i,np.array(burn['position_km']))
            pieces.append(solar_piece(begin,mid,y0[:3],point,reference,q['branches'][i][1],boundary_velocities=(y0[3:],None)))
            pieces.append(solar_piece(mid,end,point,y1[:3],q['segments'][segment_index+1],True,boundary_velocities=(None,y1[3:])))
            segment_index+=2
        else:
            pieces.append(solar_piece(begin,end,y0[:3],y1[:3],reference,q['branches'][i][1],
                                      boundary_velocities=(y0[3:],y1[3:])))
            segment_index+=1
        pieces.extend(right['pieces'])
    if post_flyby_months>0:
        status('Integrating '+str(post_flyby_months)+' months after the final flyby…')
        pieces.extend(post_flyby_pieces(nodes[-1],ep,extended_end,pieces[-1]['state'](encounter_date)))
    post_solar=next((p for p in pieces if p.get('label')=='Post-flyby heliocentric coast'),None)
    outgoing_solar_orbit=heliocentric_orbit_summary(post_solar['state'](post_solar['start']),post_solar['start']) if post_solar else None
    status('Checking state joins and recording every maneuver…')
    burns=[];jumps=[]
    mu=BODIES[nodes[0]['body']][1];r0=nodes[0]['rp']
    exported_c3=float(nodes[0]['peri_out_velocity']@nodes[0]['peri_out_velocity']-2*mu/r0)
    injection=np.sqrt(exported_c3+2*mu/r0)-np.sqrt(mu/r0)
    injection_vector=injection*unit(nodes[0]['peri_out_velocity'])
    burns.append(dict(kind='launch_injection_from_200_km',julian_date_tdb=q['dates_jd_tdb'][0],
                      magnitude_kms=float(injection),dx_kms=injection_vector[0],dy_kms=injection_vector[1],dz_kms=injection_vector[2]))
    for a,b in zip(pieces,pieces[1:]):
        if abs(a['end']-b['start'])>1e-8:
            raise ValueError('Gap between integrated pieces')
        t=b['start'];ya,yb=a['state'](t),b['state'](t)
        jumps.append(float(np.linalg.norm(ya[:3]-yb[:3])))
        dv=yb[3:]-ya[3:]
        event_burn=next((burn for burn in q.get('event_burns',[]) if burn.get('kind')=='target_turnaround' and abs(burn['julian_date_tdb']-t)<1e-8),None)
        if event_burn is not None and a['kind']=='solar' and b['kind']=='solar':kind='target_turnaround'
        elif a['kind']=='solar' and b['kind']=='solar':kind='retargeted_DSM'
        elif a['kind']=='planet' and b['kind']=='planet':kind='powered_flyby' if c.get('powered_flybys') else 'flyby_speed_match_burn'
        else:kind='finite_patch_junction'
        if np.linalg.norm(dv)>1e-8:
            record=dict(kind=kind,julian_date_tdb=t,magnitude_kms=float(np.linalg.norm(dv)),
                        dx_kms=dv[0],dy_kms=dv[1],dz_kms=dv[2])
            if event_burn is not None:
                record.update(body=event_burn['body'],event_index=event_burn['event_index'],
                              candidate_modeled_magnitude_kms=event_burn['magnitude_kms'])
            burns.append(record)
    status('Sampling integrated arcs and checking planetary clearances…')
    samples=[sample_piece(p,i<len(pieces)-1) for i,p in enumerate(pieces)]
    start,end=pieces[0]['start'],pieces[-1]['end']
    try:
        all_ep=Ephemerides(c['cache'],list(BODIES),start,end,c['max_ephemeris_step_days'])
        clearance_rows=clearances(pieces,samples,all_ep)
        checked=list(BODIES)
    except ValueError:
        # Do not download unrelated planets solely for a clearance check.
        # Exclude cached tables that do not cover an extended trajectory.
        class CoveredEphemerides:
            def __init__(self):
                a=(start-JD0)*DAY;b=(end-JD0)*DAY
                self.splines={body:curve for body,curve in ep.splines.items() if curve.x[0]<=a and curve.x[-1]>=b}
            def state(self,body,date):return ep.state(body,date)
        clearance_ep=CoveredEphemerides()
        clearance_rows=clearances(pieces,samples,clearance_ep)
        checked=[b for b in BODIES if b in clearance_ep.splines]
    flattened=[(t,y) for group in samples for t,y in group]
    for burn in burns:
        burn['date']=calendar(burn['julian_date_tdb'])
    if any(a[0]>=b[0] for a,b in zip(flattened,flattened[1:])):
        raise ValueError('Trajectory epochs are not strictly increasing')
    for extension in ('csv','xyzv'):
        temporary=output/('trajectory.'+extension+'.tmp')
        with temporary.open('w',newline='',encoding='utf-8') as stream:
            if extension=='csv':
                stream.write('julian_date_tdb,x_km,y_km,z_km,vx_kms,vy_kms,vz_kms\n')
            separator=',' if extension=='csv' else ' '
            for t,y in flattened:
                stream.write(separator.join([f'{t:.12f}']+[f'{v:.6f}' for v in y[:3]]+[f'{v:.10f}' for v in y[3:]])+'\n')
        temporary.replace(output/('trajectory.'+extension))
    for name,rows in [('burns',burns),('encounters',[dict(body=n['body'],julian_date_tdb=n['date'],
                           date=calendar(n['date']),periapsis_radius_km=n['rp'],altitude_km=n['altitude'],
                           target_center_distance_km=n.get('center_distance_km')) for n in nodes]),
                      ('planet_clearances',clearance_rows)]:
        with (output/(name+'.csv')).open('w',newline='',encoding='utf-8') as stream:
            fields=list(dict.fromkeys(key for row in rows for key in row))
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    max_error=max(p['numerical_error_km'] for p in pieces)
    last=nodes[-1]
    arrival_state=None
    if last['body'] in BODIES:
        y=last['pieces'][0]['state'](last['date']);relative=y-ep.state(last['body'],last['date'])
        arrival_state=dict(body=last['body'],epoch_jd_tdb=last['date'],epoch=calendar(last['date']),
                           frame='Planet-centered Ecliptic J2000 (not equatorial or body-fixed); geometric, km and km/s; epoch TDB',
                           position_km=relative[:3].tolist(),velocity_kms=relative[3:].tolist(),
                           heliocentric_state_km_kms=y.tolist(),planet_state_km_kms=ep.state(last['body'],last['date']).tolist(),
                           reference_radius_km=BODIES[last['body']][2],gm_km3_s2=BODIES[last['body']][1],
                           altitude_km=float(np.linalg.norm(relative[:3])-BODIES[last['body']][2]),
                           capture_assessment=last['capture_assessment'],
                           note='Incoming state at periapsis. No insertion burn or captured orbit has been applied. Transform the frame and time scale as needed before using FreeFlyer.')
    else:
        y=next(p for p in reversed(pieces) if p['start']<=last['date']<=p['end'])['state'](last['date'])
        target=ep.state(last['body'],last['date']);relative=y-target
        arrival_state=dict(body=last['body'],epoch_jd_tdb=last['date'],epoch=calendar(last['date']),
            frame='Target-centered Ecliptic J2000; geometric, km and km/s; epoch TDB',
            position_km=relative[:3].tolist(),velocity_kms=relative[3:].tolist(),
            heliocentric_state_km_kms=y.tolist(),target_state_km_kms=target.tolist(),
            center_distance_km=float(np.linalg.norm(relative[:3])),
            note='Geometric encounter state; no target gravity, surface radius, collision clearance or capture is modeled.')
    if arrival_state is not None:
        atomic_json(output/'arrival_state.json',arrival_state)
        with (output/'arrival_state.csv').open('w',newline='',encoding='utf-8') as stream:
            writer=csv.writer(stream);writer.writerow(['julian_date_tdb','x_km','y_km','z_km','vx_kms','vy_kms','vz_kms'])
            writer.writerow([last['date'],*relative.tolist()])
    exported_arrival_speed=float(np.linalg.norm(relative[3:]))
    if last['body'] in BODIES:
        exported_arrival_speed=float(np.sqrt(max(0.,exported_arrival_speed**2-2*BODIES[last['body']][1]/np.linalg.norm(relative[:3]))))
    if exported_arrival_speed>c['max_arrival_vinf_kms']+1e-8:
        violations.append('Exported arrival V-infinity exceeds the requested limit after finite targeting')
    if not c.get('effective_min_c3',c.get('min_c3',5.))-1e-8<=exported_c3<=c['max_c3']+1e-8:
        violations.append('Exported launch C3 is outside the requested bounds after finite targeting')
    patch_dv=sum(b['magnitude_kms'] for b in burns if b['kind']=='finite_patch_junction')
    onboard=sum(b['magnitude_kms'] for b in burns if not b['kind'].startswith('launch'))
    actual_dsm_peak=max((b['magnitude_kms'] for b in burns if b['kind'] in ('retargeted_DSM','finite_patch_junction','target_turnaround')),default=0.)
    actual_power_peak=max((b['magnitude_kms'] for b in burns if b['kind'] in ('powered_flyby','flyby_speed_match_burn')),default=0.)
    individual_pass=actual_dsm_peak<=c['max_single_dsm_kms']+1e-9 and actual_power_peak<=c['max_powered_flyby_kms']+1e-9
    if not individual_pass:violations.append('An integrated DSM/patch correction or flyby impulse exceeds its individual burn cap; see burns.csv')
    budget=export_budget_breakdown(q,burns)
    from app_paths import APP_VERSION
    report=dict(engine_version=APP_VERSION,model='Two-body patched conics: Sun-only coasts and one-planet-only SOI hyperbolas, translated using JPL planet states',
                propagation_model='two_body_patched_conics',nbody_propagation=False,
                force_model=dict(heliocentric_coasts='Sun point mass only, outside planned encounter SOIs',
                    planetary_patches='Encounter-planet point mass only in planet-relative coordinates, inside its Laplace SOI',
                    simultaneous_multiple_gravity_sources=False,solar_tides_inside_planet_patch=False,
                    other_planet_perturbations_outside_soi=False,
                    planet_ephemerides_usage='Geometric planet positions/velocities translate patch frames and support clearance checks; they are not perturbing force inputs.',
                    unplanned_encounters_automatically_patched=False),
                force_segments=[dict(start_jd_tdb=p['start'],end_jd_tdb=p['end'],center=p.get('force_center',p.get('body','Sun')),
                    gm_km3_s2=p.get('gm_km3_s2',MU_SUN),soi_radius_km=p.get('soi_radius_km')) for p in pieces],
                maneuver_budget_breakdown=budget,candidate_maneuver_budget_complete=budget['candidate_maneuver_budget_complete'],
                frame='Sun-centered Ecliptic J2000; km, km/s; Julian dates TDB',candidate_id=q['id'],
                arrival_altitude_option_km=arrival_altitude_km,arrival_inclination_option_deg=arrival_inclination_deg,arrival_state=arrival_state,
                post_flyby_months=post_flyby_months,month_length_days=MONTH_DAYS,post_flyby_solar_orbit=outgoing_solar_orbit,
                final_encounter_jd_tdb=encounter_date,post_flyby_end_date=calendar(end),
                passes_individual_burn_limits=individual_pass,maximum_integrated_dsm_or_patch_kms=actual_dsm_peak,
                maximum_integrated_flyby_burn_kms=actual_power_peak,
                source_candidate_status=original_status,export_evaluation_status=q['status'],powered_flybys_active=c.get('powered_flybys',False),
                candidate_powered_flyby_delta_v_kms=q.get('powered_flyby_delta_v_kms',0.),
                candidate_cruise_dsm_kms=q.get('cruise_dsm_kms',q['total_dsm_kms']-q.get('powered_flyby_delta_v_kms',0.)-q.get('turnaround_delta_v_kms',0.)),
                candidate_target_turnaround_delta_v_kms=q.get('turnaround_delta_v_kms',0.),
                candidate_event_burns=q.get('event_burns',[]),
                exported_target_turnaround_burns=[burn for burn in burns if burn['kind']=='target_turnaround'],
                powered_flyby_burns=[dict(body=f['body'],event_index=f['event_index'],julian_date_tdb=f['julian_date_tdb'],**f['powered_flyby']) for f in q['flybys'] if f.get('powered_flyby')],
                candidate_passes_requested_limits=not violations and q['status'].startswith('passes'),
                requirement_violations=violations,
                requested_limits={key:c.get(key) for key in ('effective_min_c3','min_c3','max_c3','arrival_date','arrival_tolerance_days','max_dsm_kms','max_single_dsm_kms','max_powered_flyby_kms','max_arrival_vinf_kms','max_years','vinf_tolerance_mps','minimum_altitude_km')},
                source_candidate_sha256=hashlib.sha256(Path(candidate).read_bytes()).hexdigest(),
                exported_launch_c3_km2_s2=exported_c3,exported_arrival_vinf_kms=exported_arrival_speed,finite_targeting=targeting_report,
                refine_patches_option=bool(refine_patches),patch_epoch_shift_days_option=patch_epoch_shift_days,
                ephemeris_sources=ep.manifest,
                numerical_validation_passed=max_error<1 and max(jumps,default=0)<1,
                maximum_arc_endpoint_error_km=max_error,maximum_position_join_residual_km=max(jumps,default=0),
                patch_join_delta_v_kms=patch_dv,total_onboard_delta_v_kms=onboard,
                patch_targeting=dict(finite_soi_positions_targeted=True,planet_center_endpoints_used_for_export=False,
                    adjacent_flyby_and_coast_velocities_jointly_optimized=bool(targeting_report.get('applied')),
                    original_physical_coast_winding_retained=True,
                    correction_meaning='Finite-SOI periapsis geometry, epochs and existing DSM positions are locally matched to adjacent solar coasts. All remaining velocity gaps are explicit impulses; launch injection uses the exported departure energy.'),
                launch_injection_from_200_km_kms=float(injection),candidate_dsm_kms=q['total_dsm_kms'],
                passes_original_onboard_budget=onboard<=c['max_dsm_kms'],rows=len(flattened),
                start_jd_tdb=start,end_jd_tdb=end,planet_clearances=clearance_rows,
                no_sample_bracketed_planet_or_sun_impacts=all(r['altitude_km']>0 for r in clearance_rows),
                clearance_checks_cover_all_eight_planets=len(checked)==len(BODIES),
                planets_checked=checked,planets_omitted_from_clearance_check=[body for body in BODIES if body not in checked],
                clearance_ephemerides_policy='Use existing complete-span cached vectors only for other planets; no extra downloads or perturbing gravity are added for this check.',
                continuous_nbody_validated=False,
                sampling='Adaptive Hermite midpoint position residual below 0.1 km; maximum solar step 2 days, flyby step 2 hours; impulse epochs separated by 0.02 s.',
                small_body_arrival=(f"{last['center_distance_km']:.12g} km from target center at the requested encounter epoch; target gravity, surface radius and capture are not modeled." if 'center_distance_km' in last else None),
                small_body_encounter_distance_km=last.get('center_distance_km'),
                limitations=['Finite SOI-boundary positions and times are retargeted from the planet-center Lambert design; every velocity gap is an explicit junction impulse, not an n-body correction.',
                             'Inside each planned SOI only that planet is propagated; outside planned SOIs only the Sun is propagated. Unplanned encounters are not automatically patched.',
                             'Clearance minima are sample-bracketed with continuous refinement, not exhaustive polynomial root isolation.',
                             'Moon perturbations, planetary rings and thermal constraints are not included.',
                             'Numerical validation does not establish an optimized or budget-compliant mission.'])
    if post_flyby_months>0:report['limitations'].append('Post-flyby continuation uses the target planet inside its SOI and Sun-only gravity outside; custom-body gravity and later flybys are not modeled. No new burn is applied.')
    atomic_json(output/'integration_report.json',report)
    ssc=f'''"Candidate {q['id']}" "Sol"
{{
    Class "spacecraft"
    Radius 0.005
    Color [0.7 0.9 1.0]
    Beginning {start:.12f}
    Ending {end:.12f}
    OrbitFrame {{ EclipticJ2000 {{ Center "Sol" }} }}
    SampledTrajectory {{ Source "trajectory.xyzv" DoublePrecision true Interpolation "Cubic" }}
}}
'''
    (output/'trajectory.ssc').write_text(ssc,encoding='utf-8')
    (output/'README.txt').write_text('Force model: two-body patched conics, never n-body. Sun only outside planned SOIs; the encounter planet only inside its SOI. JPL planet vectors translate reference frames and check clearances.\nCSV and XYZV contain the same integrated Sun-centered Ecliptic J2000 states, km and km/s, JD TDB.\nFor Celestia put trajectory.ssc in an addon folder and trajectory.xyzv in its data subfolder.\nAll maneuvers, including finite-patch junction corrections, are in burns.csv. Check integration_report.json before using its fuel budget.\n',encoding='utf-8')
    atomic_json(output/'integration_status.json',dict(state='finished',message='Integrated trajectory and both export formats saved.'))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--candidate',required=True);p.add_argument('--config',required=True);p.add_argument('--output',required=True);p.add_argument('--arrival-altitude-km',type=float);p.add_argument('--powered-flybys',action=argparse.BooleanOptionalAction,default=None);p.add_argument('--post-flyby-months',type=float,default=0.);p.add_argument('--arrival-inclination-deg',type=float);p.add_argument('--refine-patches',action=argparse.BooleanOptionalAction,default=True);p.add_argument('--patch-epoch-shift-days',type=float,default=2.)
    args=p.parse_args()
    try:
        export(args.candidate,json.loads(Path(args.config).read_text(encoding='utf-8')),args.output,args.arrival_altitude_km,args.powered_flybys,args.post_flyby_months,args.arrival_inclination_deg,args.refine_patches,args.patch_epoch_shift_days)
    except Exception as exc:
        Path(args.output).mkdir(parents=True,exist_ok=True)
        atomic_json(Path(args.output)/'integration_status.json',dict(state='failed',message=str(exc)))
        traceback.print_exc();raise
