"""Local Saturn/Titan arrival targeting; no drag, landing or global mission search.

Sun-only cruise is patched at Saturn's SOI to Saturn plus Titan point-mass
gravity. The finite Titan entry-interface point is illustrative, not an EDL
corridor or landing-site solution. Ecliptic J2000 axes, TDB, km, km/s.
"""
import bootstrap  # noqa: F401
from dataclasses import dataclass
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares,brentq
from lamberthub import izzo2015
from dynamics import kepler
from ephemeris import BODIES,DAY,MU_SUN

# JPL SAT441 physical parameters: https://ssd.jpl.nasa.gov/sats/phys_par/
TITAN_GM=8978.13710
TITAN_RADIUS_KM=2574.76
SATURN_GM=BODIES['Saturn'][1]
SATURN_RADIUS_KM=BODIES['Saturn'][2]

@dataclass(frozen=True)
class MoonSystem:
    parent: str='Saturn'
    moon: str='Titan'
    parent_mu: float=SATURN_GM
    parent_radius: float=SATURN_RADIUS_KM
    moon_mu: float=TITAN_GM
    moon_radius: float=TITAN_RADIUS_KM
    cancelled: object=None

DEFAULT_SYSTEM=MoonSystem()

def position(callback,date):
    return callback.position(date) if hasattr(callback,'position') else callback(date)[:3]


def unit(vector):
    vector=np.asarray(vector,float);length=float(np.linalg.norm(vector))
    if not np.isfinite(length) or length<=1e-12:raise ValueError('Nonzero finite direction required')
    return vector/length

def point_mass_gradient(position,mu):
    r=np.asarray(position,float);d=float(np.linalg.norm(r))
    return mu*(3*np.outer(r,r)/d**5-np.eye(3)/d**3)

def relative_acceleration(position,moon_position,primary_mu=SATURN_GM,moon_mu=TITAN_GM):
    """Differential moon acceleration includes acceleration of the origin."""
    r=np.asarray(position);m=np.asarray(moon_position);delta=m-r
    return -primary_mu*r/np.linalg.norm(r)**3+moon_mu*(delta/np.linalg.norm(delta)**3-m/np.linalg.norm(m)**3)

def illustrative_entry_normal(relative_velocity,radial_hint,gamma_deg=-65.,clock_deg=0.):
    if not -89.9<=gamma_deg<=-5:raise ValueError('Illustrative inbound flight-path angle must be between -89.9 and -5 degrees')
    u=unit(relative_velocity);b=np.cross(u,radial_hint)
    if np.linalg.norm(b)<1e-10:b=np.cross(u,np.eye(3)[np.argmin(abs(u))])
    b=unit(b);c=np.cross(u,b);clock=np.radians(clock_deg)
    return -np.sin(abs(np.radians(gamma_deg)))*u+np.cos(np.radians(gamma_deg))*(np.cos(clock)*b+np.sin(clock)*c)

def solar_state(segment,date):
    r,v=kepler(np.asarray(segment['r']),np.asarray(segment['v']),(date-segment['start_jd'])*DAY)
    return np.r_[r,v]

def soi_entry(segment,arrival_jd,saturn_state,system=DEFAULT_SYSTEM):
    start=segment['start_jd'];stop=min(arrival_jd,segment['end_jd'])
    def boundary(jd):
        sat=saturn_state(jd);soi=np.linalg.norm(sat[:3])*(system.parent_mu/MU_SUN)**.4
        return float(np.linalg.norm(solar_state(segment,jd)[:3]-sat[:3])-soi)
    dates=np.linspace(max(start,stop-1000),stop,1001);values=[boundary(t) for t in dates]
    brackets=[(a,b) for a,b,fa,fb in zip(dates[:-1],dates[1:],values[:-1],values[1:]) if fa>0 and fb<=0]
    if not brackets:raise ValueError('No inbound Saturn SOI crossing on this final solar coast')
    a,b=brackets[0];epoch=brentq(boundary,a,b,xtol=1e-9)
    state=solar_state(segment,epoch)-saturn_state(epoch)
    return float(epoch),state

def propagate(initial,seconds,moon_position,*,variational=False,rtol=2e-11,atol_position=1e-5,system=DEFAULT_SYSTEM,moon_surface_stop=True):
    """Moon position callback takes elapsed seconds from the SOI entry epoch."""
    initial=np.asarray(initial,float)
    def rhs(t,y):
        if system.cancelled and system.cancelled():raise InterruptedError('Moon targeting stopped')
        r=y[:3];m=moon_position(t);acc=relative_acceleration(r,m,system.parent_mu,system.moon_mu)
        if not variational:return np.r_[y[3:6],acc]
        phi=y[6:].reshape(6,3);gradient=point_mass_gradient(r,system.parent_mu)+point_mass_gradient(r-m,system.moon_mu)
        return np.r_[y[3:6],acc,np.vstack([phi[3:],gradient@phi[:3]]).ravel()]
    def saturn_impact(t,y):return np.linalg.norm(y[:3])-system.parent_radius
    def titan_impact(t,y):return np.linalg.norm(y[:3]-moon_position(t))-system.moon_radius
    saturn_impact.terminal=True
    titan_impact.terminal=moon_surface_stop
    saturn_impact.direction=titan_impact.direction=-1
    if variational:initial=np.r_[initial,np.vstack([np.zeros((3,3)),np.eye(3)]).ravel()]
    atol=np.r_[np.full(3,atol_position),np.full(3,1e-11),np.full(18,1e-8)] if variational else np.r_[np.full(3,atol_position),np.full(3,1e-11)]
    fit=solve_ivp(rhs,(0,float(seconds)),initial,method='DOP853',rtol=rtol,atol=atol,dense_output=True,events=[saturn_impact,titan_impact],max_step=2*DAY)
    if not fit.success or fit.status==1:raise ValueError('Arrival trial intersects Saturn/Titan or integration failed')
    return fit

def shoot(entry_state,seconds,target_position,moon_position,initial_velocity,system=DEFAULT_SYSTEM,moon_surface_stop=True):
    """Three velocity controls, three endpoint coordinates; analytic sensitivities."""
    r0=np.asarray(entry_state[:3]);target=np.asarray(target_position);evaluations={}
    def evaluate(v):
        key=tuple(v)
        if key not in evaluations:
            fit=propagate(np.r_[r0,v],seconds,moon_position,variational=True,system=system,moon_surface_stop=moon_surface_stop)
            evaluations[key]=(fit.y[:3,-1]-target,fit.y[6:,-1].reshape(6,3)[:3],fit)
        return evaluations[key]
    def residual(v):return evaluate(v)[0]/1e5
    def jacobian(v):return evaluate(v)[1]/1e5
    fit=least_squares(residual,np.asarray(initial_velocity),jac=jacobian,xtol=1e-12,ftol=1e-12,gtol=1e-12,max_nfev=25,x_scale='jac')
    error,jac,solution=evaluate(fit.x)
    if np.linalg.norm(error)>.1:raise ValueError('Titan endpoint did not converge within 100 m')
    return fit.x,solution,dict(iterations=fit.nfev,endpoint_error_km=float(np.linalg.norm(error)),optimizer_success=bool(fit.success))

def local_velocity(entry_state,seconds,target,moon,system=DEFAULT_SYSTEM,moon_surface_stop=True):
    guesses=[]
    for prograde in [True,False]:
        try:
            v,_=izzo2015(system.parent_mu,entry_state[:3],target,seconds,M=0,prograde=prograde,low_path=True)
            guesses.append((float(np.linalg.norm(v-entry_state[3:])),v))
        except (ValueError,RuntimeError,AssertionError):continue
    for _,v in sorted(guesses,key=lambda row:row[0]):
        try:return shoot(entry_state,seconds,target,moon,v,system,moon_surface_stop)
        except (ValueError,RuntimeError,AssertionError):continue
    raise ValueError('No collision-free parent/moon arrival initial guess')


def target_arrival(segment,arrival_jd,saturn_state,titan_state,entry_altitude_km=1270.,gamma_deg=-65.,clock_deg=0.,system=DEFAULT_SYSTEM,mode='entry',target_normal=None):
    if mode not in ('entry','approach','impact'):raise ValueError('Unknown moon targeting mode')
    if mode=='impact':entry_altitude_km=0.
    if not np.isfinite(entry_altitude_km) or entry_altitude_km<0 or (mode!='impact' and entry_altitude_km==0):raise ValueError('Positive finite moon altitude required for a non-impact arrival')
    entry_jd,incoming=soi_entry(segment,arrival_jd,saturn_state,system);seconds=(arrival_jd-entry_jd)*DAY
    titan=titan_state(arrival_jd)-saturn_state(arrival_jd)
    nominal=solar_state(segment,arrival_jd)-titan_state(arrival_jd)
    if target_normal is not None and mode=='approach':raise ValueError('A fixed surface point and tangent-periapsis mode cannot be combined')
    normal=unit(target_normal) if target_normal is not None else illustrative_entry_normal(nominal[3:],titan[:3],gamma_deg,clock_deg)
    target=titan[:3]+normal*(system.moon_radius+entry_altitude_km)
    moon=lambda t:position(titan_state,entry_jd+t/DAY)-position(saturn_state,entry_jd+t/DAY)
    velocity,solution,convergence=local_velocity(incoming,seconds,target,moon,system,mode!='impact')
    if mode=='approach':
        # Rotate the target point within the chosen encounter plane until the
        # relative velocity is tangent: altitude means true periapsis here.
        u=unit(nominal[3:]);b=unit(normal+np.sin(abs(np.radians(gamma_deg)))*u)
        beta=abs(np.radians(gamma_deg))
        for _ in range(8):
            rel=solution.y[:6,-1]-titan
            angle=float(np.arcsin(np.clip(unit(rel[:3])@unit(rel[3:]),-1,1)))
            if abs(angle)<1e-8:break
            beta+=angle;normal=-np.sin(beta)*u+np.cos(beta)*b
            target=titan[:3]+normal*(system.moon_radius+entry_altitude_km)
            velocity,solution,convergence=local_velocity(incoming,seconds,target,moon,system)
        rel=solution.y[:6,-1]-titan
        angle=float(np.arcsin(np.clip(unit(rel[:3])@unit(rel[3:]),-1,1)))
        if abs(angle)>1e-6:raise ValueError('Moon closest-approach tangency did not converge')
    delta=velocity-incoming[3:];end=solution.y[:6,-1];relative=end-titan
    gamma=float(np.degrees(np.arcsin(np.clip(np.dot(unit(relative[:3]),unit(relative[3:])),-1,1))))
    # Independent state-only propagation, at tighter tolerances than the solve.
    independent=propagate(np.r_[incoming[:3],velocity],seconds,moon,rtol=3e-13,atol_position=1e-7,system=system,moon_surface_stop=mode!='impact')
    independent_error=float(np.linalg.norm(independent.y[:3,-1]-target))
    if independent_error>.1 or (mode!='approach' and gamma>=0):raise ValueError('Independent entry validation failed or trajectory is outbound at entry')
    grid=np.unique(np.r_[np.arange(0,max(0,seconds-2*DAY),6*3600.),np.arange(max(0,seconds-2*DAY),seconds,60.),seconds])
    states=independent.sol(grid).T
    relative_moon=np.array([moon(t) for t in grid]);distances=np.linalg.norm(states[:,:3]-relative_moon,axis=1)
    radii=np.linalg.norm(states[:,:3],axis=1)
    earlier=grid<seconds-1
    if np.any(distances[earlier]<system.moon_radius+entry_altitude_km-.1):raise ValueError('An earlier sampled Titan entry precedes the target epoch')
    report=dict(entry_jd_tdb=entry_jd,arrival_jd_tdb=arrival_jd,saturn_soi_radius_km=float(np.linalg.norm(incoming[:3])),
        soi_delta_v_vector_ecliptic_j2000_kms=delta.tolist(),soi_delta_v_kms=float(np.linalg.norm(delta)),
        state_before_soi_burn_saturn_relative_km_kms=incoming.tolist(),state_after_soi_burn_saturn_relative_km_kms=np.r_[incoming[:3],velocity].tolist(),
        titan_relative_entry_state_km_kms=relative.tolist(),requested_entry_altitude_km=float(entry_altitude_km),titan_entry_altitude_km=float(np.linalg.norm(relative[:3])-system.moon_radius),
        titan_relative_inertial_entry_speed_kms=float(np.linalg.norm(relative[3:])),entry_flight_path_angle_deg=gamma,
        independent_endpoint_error_km=independent_error,minimum_sampled_saturn_altitude_km=float(np.min(radii)-system.parent_radius),
        coast_days=seconds/DAY,**convergence,
        model='Sun-only upstream coast; Saturn plus differential Titan point-mass gravity inside Saturn SOI. No solar tide, other moons, Saturn J2/rings, atmosphere or spacecraft navigation uncertainty.',
        entry_geometry='Illustrative geometry, not an optimized entry corridor or landing site. Speed is moon-relative inertial, not atmosphere-relative.',
        target_mode=mode,parent_body=system.parent,moon_body=system.moon)
    return report,entry_jd+grid/DAY,states

def target_upstream(segment,arrival_jd,saturn_state,titan_state,base_report,burn_fraction=.5,system=DEFAULT_SYSTEM,progress=None,inclination_deg=None):
    """Move the correction to a real cruise DSM; jointly match the SOI boundary.

    Three controls: two SOI direction coordinates and its epoch. Each evaluation
    solves Sun and Saturn/Titan arcs, then matches all three velocity components.
    Earlier spacecraft states and flybys are preserved through the new DSM.
    """
    if not .05<=burn_fraction<=.9:raise ValueError('Cruise burn fraction must be between .05 and .9')
    mode=base_report.get('target_mode','entry')
    burn_jd=segment['start_jd']+burn_fraction*(arrival_jd-segment['start_jd'])
    burn_state=solar_state(segment,burn_jd);entry0=base_report['entry_jd_tdb']
    if burn_jd>=entry0-1:raise ValueError('Place the cruise DSM before Saturn SOI entry')
    n=unit(base_report['state_before_soi_burn_saturn_relative_km_kms'][:3])
    e1=unit(np.cross(n,np.eye(3)[np.argmin(abs(n))]));e2=np.cross(n,e1)
    titan=titan_state(arrival_jd)-saturn_state(arrival_jd)
    target=titan[:3]+np.array(base_report['titan_relative_entry_state_km_kms'][:3])
    target_normal=unit(target-titan[:3]);target_tangent=unit(base_report['titan_relative_entry_state_km_kms'][3:])
    target_radius=float(np.linalg.norm(target-titan[:3]))
    from arrival_geometry import validate_inclination,planet_pole,target_plane_axis
    inclination_deg=validate_inclination(inclination_deg)
    pole=planet_pole(system.moon,arrival_jd) if inclination_deg is not None else None
    clock_axis=target_tangent
    initial_clock=0.
    if inclination_deg is not None:
        initial_h=unit(np.cross(target_normal,target_tangent))
        wanted=target_plane_axis(clock_axis,pole,initial_h,inclination_deg)
        initial_clock=float(np.arctan2(clock_axis@np.cross(initial_h,wanted),initial_h@wanted))
    memo={}
    def evaluate(z):
        key=tuple(z)
        if key not in memo:
            if progress:progress('Matching solar and moon arcs; boundary trial '+str(len(memo)+1))
            epoch=entry0+z[2];sat=saturn_state(epoch);soi=np.linalg.norm(sat[:3])*(system.parent_mu/MU_SUN)**.4
            r=soi*unit(n+z[0]*e1+z[1]*e2)
            departure,vin=izzo2015(MU_SUN,burn_state[:3],sat[:3]+r,(epoch-burn_jd)*DAY,M=0,prograde=True,low_path=True)
            moon=lambda t:position(titan_state,epoch+t/DAY)-position(saturn_state,epoch+t/DAY)
            aim=titan[:3]+target_radius*unit(target_normal*np.cos(z[3])+target_tangent*np.sin(z[3])) if mode=='approach' else target
            if inclination_deg is not None:
                normal=unit(aim-titan[:3]);clock=z[-1]
                normal=normal*np.cos(clock)+np.cross(clock_axis,normal)*np.sin(clock)+clock_axis*(clock_axis@normal)*(1-np.cos(clock))
                aim=titan[:3]+target_radius*normal
            needed,solution,convergence=local_velocity(np.r_[r,vin-sat[3:]],(arrival_jd-epoch)*DAY,aim,moon,system,mode!='impact')
            rel=solution.y[:6,-1]-titan;radial=float(unit(rel[:3])@rel[3:])
            inclination_residual=0. if pole is None else float(np.arccos(np.clip(unit(np.cross(rel[:3],rel[3:]))@pole,-1.,1.))-np.radians(inclination_deg))
            memo[key]=dict(epoch=epoch,r=r,departure=departure,vin=vin,needed=needed,solution=solution,gap=needed-(vin-sat[3:]),moon=moon,target=aim,radial=radial,inclination_residual=inclination_residual)
        return memo[key]
    def residual(z):
        q=evaluate(z)
        value=list(q['gap'])+([q['radial']] if mode=='approach' else [])
        if pole is not None:value.append(q['inclination_residual'])
        return np.array(value)/.1
    def jacobian(z):
        steps=[2e-6,2e-6,.0002]+([2e-5] if mode=='approach' else [])+([2e-5] if pole is not None else []);columns=[];base=residual(z)
        for i,h in enumerate(steps):
            d=np.zeros(len(z));d[i]=h;columns.append((residual(z+d)-base)/h)
        return np.column_stack(columns)
    lower=[-.15,-.15,-14.]+([-1.3] if mode=='approach' else [])+([-np.pi-.01] if pole is not None else []);upper=[.15,.15,14.]+([1.3] if mode=='approach' else [])+([np.pi+.01] if pole is not None else [])
    guess=np.zeros(len(lower))
    if pole is not None:guess[-1]=initial_clock
    fit=least_squares(residual,guess,jac=jacobian,bounds=(lower,upper),x_scale=[.02,.02,1.]+([.2] if mode=='approach' else [])+([.5] if pole is not None else []),max_nfev=20,gtol=1e-11,ftol=1e-12,xtol=1e-12)
    best=evaluate(fit.x);epoch=best['epoch'];seconds=(arrival_jd-epoch)*DAY
    target=best['target']
    actual_incoming=best['vin']-saturn_state(epoch)[3:]
    independent=propagate(np.r_[best['r'],actual_incoming],seconds,best['moon'],rtol=3e-13,atol_position=1e-7,system=system,moon_surface_stop=mode!='impact')
    error=float(np.linalg.norm(independent.y[:3,-1]-target))
    if error>.1:raise ValueError(f'Continuous upstream targeting missed the entry point by {error:.6f} km')
    relative=independent.y[:6,-1]-titan;delta=best['departure']-burn_state[3:]
    gamma=float(np.degrees(np.arcsin(np.clip(unit(relative[:3])@unit(relative[3:]),-1,1))))
    if (mode!='approach' and gamma>=0):raise ValueError('Upstream-targeted entry is outbound')
    grid=np.unique(np.r_[np.arange(0,max(0,seconds-2*DAY),6*3600.),np.arange(max(0,seconds-2*DAY),seconds,60.),seconds])
    states=independent.sol(grid).T
    report=dict(base_report,entry_jd_tdb=epoch,soi_delta_v_kms=0.,soi_delta_v_vector_ecliptic_j2000_kms=[0.,0.,0.],
        upstream_burn_jd_tdb=float(burn_jd),upstream_delta_v_kms=float(np.linalg.norm(delta)),upstream_delta_v_vector_kms=delta.tolist(),
        upstream_burn_fraction=burn_fraction,upstream_burn_position_heliocentric_km=burn_state[:3].tolist(),upstream_post_burn_velocity_heliocentric_kms=best['departure'].tolist(),
        soi_velocity_matching_residual_kms=float(np.linalg.norm(best['gap'])),independent_endpoint_error_km=error,
        titan_relative_entry_state_km_kms=relative.tolist(),titan_entry_altitude_km=float(np.linalg.norm(relative[:3])-system.moon_radius),
        titan_relative_inertial_entry_speed_kms=float(np.linalg.norm(relative[3:])),entry_flight_path_angle_deg=gamma,
        state_before_soi_burn_saturn_relative_km_kms=np.r_[best['r'],actual_incoming].tolist(),state_after_soi_burn_saturn_relative_km_kms=np.r_[best['r'],actual_incoming].tolist(),
        coast_days=seconds/DAY,iterations=fit.nfev,optimizer_success=bool(fit.success),endpoint_error_km=error,
        minimum_sampled_saturn_altitude_km=float(np.min(np.linalg.norm(states[:,:3],axis=1))-system.parent_radius),
        correction_model='One real upstream cruise DSM; continuous velocity at Saturn SOI. Entry position/epoch jointly targeted; no SOI burn applied during independent propagation.')
    report['target_entry_position_saturn_relative_km']=target.tolist()
    report['saturn_soi_radius_km']=float(np.linalg.norm(best['r']))
    report['requested_inclination_deg']=inclination_deg
    return verify_upstream_coasts(report,saturn_state,titan_state,system)

def verify_upstream_coasts(report,saturn_state,titan_state,system=DEFAULT_SYSTEM):
    """Propagate Sun then Saturn/Titan, carrying the numerical state across SOI."""
    report=dict(report);mode=report.get('target_mode','entry');burn_jd=report['upstream_burn_jd_tdb'];entry=report['entry_jd_tdb'];arrival=report['arrival_jd_tdb']
    initial=np.r_[report['upstream_burn_position_heliocentric_km'],report['upstream_post_burn_velocity_heliocentric_kms']]
    def sun_rhs(t,y):return np.r_[y[3:],-MU_SUN*y[:3]/np.linalg.norm(y[:3])**3]
    solar=solve_ivp(sun_rhs,(0,(entry-burn_jd)*DAY),initial,method='DOP853',rtol=3e-13,atol=np.r_[np.full(3,1e-7),np.full(3,1e-12)])
    if not solar.success:raise ValueError('Independent solar propagation failed')
    at_entry=solar.y[:,-1]-saturn_state(entry)
    target=np.array(report.get('target_entry_position_saturn_relative_km',np.array(report['titan_relative_entry_state_km_kms'][:3])+(titan_state(arrival)-saturn_state(arrival))[:3]))
    moon=lambda t:position(titan_state,entry+t/DAY)-position(saturn_state,entry+t/DAY)
    seconds=(arrival-entry)*DAY
    local=propagate(at_entry,seconds,moon,rtol=3e-13,atol_position=1e-7,system=system,moon_surface_stop=mode!='impact')
    if len(local.t_events[1]) and local.t_events[1][0]<seconds-.1:raise ValueError('Moon surface intersects the path before the target epoch')
    error=float(np.linalg.norm(local.y[:3,-1]-target))
    if error>.1:raise ValueError('Independent Sun-to-Saturn/Titan propagation missed the entry point by '+str(error)+' km')
    expected=np.array(report['state_before_soi_burn_saturn_relative_km_kms'])
    relative=local.y[:6,-1]-(titan_state(arrival)-saturn_state(arrival))
    if system.moon=='Titan':
        from arrival_geometry import planet_pole,POLE_URL
        pole=planet_pole('Titan',arrival);achieved=float(np.degrees(np.arccos(np.clip(unit(np.cross(relative[:3],relative[3:]))@pole,-1.,1.))))
        requested=report.get('requested_inclination_deg')
        if requested is not None and abs(achieved-requested)>.001:raise ValueError('Titan-equatorial approach inclination did not converge within 0.001 degree')
        report.update(achieved_inclination_deg=achieved,inclination_reference='Titan equator; IAU north pole',pole_source_url=POLE_URL,
            entry_planetocentric_latitude_deg=float(np.degrees(np.arcsin(np.clip(unit(relative[:3])@pole,-1.,1.)))))
        from moon_targets import titan_geography
        report['body_fixed_endpoint']=titan_geography(arrival,relative)
    if mode=='approach' and abs(float(unit(relative[:3])@relative[3:]))>1e-5:raise ValueError('Moon approach endpoint is not periapsis')
    grid=np.unique(np.r_[np.arange(0,max(0,seconds-2*DAY),6*3600.),np.arange(max(0,seconds-2*DAY),seconds,60.),seconds]);states=local.sol(grid).T
    earlier=grid<seconds-1;distance=np.array([np.linalg.norm(state[:3]-moon(t)) for t,state in zip(grid,states)])
    shell=report.get('requested_entry_altitude_km',report['titan_entry_altitude_km'])
    if np.any(distance[earlier]<system.moon_radius+shell-.1):
        raise ValueError('An earlier sampled Titan entry precedes the requested epoch')
    report.update(independent_solar_endpoint_error_km=float(np.linalg.norm(at_entry[:3]-expected[:3])),
        independent_solar_velocity_error_kms=float(np.linalg.norm(at_entry[3:]-expected[3:])),
        independent_endpoint_error_km=error,independent_sun_and_saturn_titan_propagation_passed=True,
        state_before_soi_burn_saturn_relative_km_kms=at_entry.tolist(),state_after_soi_burn_saturn_relative_km_kms=at_entry.tolist(),
        titan_relative_entry_state_km_kms=relative.tolist(),titan_entry_altitude_km=float(np.linalg.norm(relative[:3])-system.moon_radius),
        titan_relative_inertial_entry_speed_kms=float(np.linalg.norm(relative[3:])),
        entry_flight_path_angle_deg=float(np.degrees(np.arcsin(np.clip(unit(relative[:3])@unit(relative[3:]),-1,1)))))
    return report,entry+grid/DAY,states
