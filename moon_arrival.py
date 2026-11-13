"""Local Saturn/Titan arrival targeting; no drag, landing or global mission search.

Sun-only cruise is patched at Saturn's SOI to Saturn plus Titan point-mass
gravity. The finite Titan entry-interface point is illustrative, not an EDL
corridor or landing-site solution. Ecliptic J2000 axes, TDB, km, km/s.
"""
import bootstrap  # noqa: F401
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

def soi_entry(segment,arrival_jd,saturn_state):
    start=segment['start_jd'];stop=min(arrival_jd,segment['end_jd'])
    def boundary(jd):
        sat=saturn_state(jd);soi=np.linalg.norm(sat[:3])*(SATURN_GM/MU_SUN)**.4
        return float(np.linalg.norm(solar_state(segment,jd)[:3]-sat[:3])-soi)
    dates=np.linspace(max(start,stop-1000),stop,1001);values=[boundary(t) for t in dates]
    brackets=[(a,b) for a,b,fa,fb in zip(dates[:-1],dates[1:],values[:-1],values[1:]) if fa>0 and fb<=0]
    if not brackets:raise ValueError('No inbound Saturn SOI crossing on this final solar coast')
    a,b=brackets[0];epoch=brentq(boundary,a,b,xtol=1e-9)
    state=solar_state(segment,epoch)-saturn_state(epoch)
    return float(epoch),state

def propagate(initial,seconds,moon_position,*,variational=False,rtol=2e-11,atol_position=1e-5):
    """Moon position callback takes elapsed seconds from the SOI entry epoch."""
    initial=np.asarray(initial,float)
    def rhs(t,y):
        r=y[:3];m=moon_position(t);acc=relative_acceleration(r,m)
        if not variational:return np.r_[y[3:6],acc]
        phi=y[6:].reshape(6,3);gradient=point_mass_gradient(r,SATURN_GM)+point_mass_gradient(r-m,TITAN_GM)
        return np.r_[y[3:6],acc,np.vstack([phi[3:],gradient@phi[:3]]).ravel()]
    def saturn_impact(t,y):return np.linalg.norm(y[:3])-SATURN_RADIUS_KM
    def titan_impact(t,y):return np.linalg.norm(y[:3]-moon_position(t))-TITAN_RADIUS_KM
    saturn_impact.terminal=titan_impact.terminal=True
    saturn_impact.direction=titan_impact.direction=-1
    if variational:initial=np.r_[initial,np.vstack([np.zeros((3,3)),np.eye(3)]).ravel()]
    atol=np.r_[np.full(3,atol_position),np.full(3,1e-11),np.full(18,1e-8)] if variational else np.r_[np.full(3,atol_position),np.full(3,1e-11)]
    fit=solve_ivp(rhs,(0,float(seconds)),initial,method='DOP853',rtol=rtol,atol=atol,dense_output=True,events=[saturn_impact,titan_impact],max_step=2*DAY)
    if not fit.success or fit.status==1:raise ValueError('Arrival trial intersects Saturn/Titan or integration failed')
    return fit

def shoot(entry_state,seconds,target_position,moon_position,initial_velocity):
    """Three velocity controls, three endpoint coordinates; analytic sensitivities."""
    r0=np.asarray(entry_state[:3]);target=np.asarray(target_position);evaluations={}
    def evaluate(v):
        key=tuple(v)
        if key not in evaluations:
            fit=propagate(np.r_[r0,v],seconds,moon_position,variational=True)
            evaluations[key]=(fit.y[:3,-1]-target,fit.y[6:,-1].reshape(6,3)[:3],fit)
        return evaluations[key]
    def residual(v):return evaluate(v)[0]/1e5
    def jacobian(v):return evaluate(v)[1]/1e5
    fit=least_squares(residual,np.asarray(initial_velocity),jac=jacobian,xtol=1e-12,ftol=1e-12,gtol=1e-12,max_nfev=25,x_scale='jac')
    error,jac,solution=evaluate(fit.x)
    if np.linalg.norm(error)>.1:raise ValueError('Titan endpoint did not converge within 100 m')
    return fit.x,solution,dict(iterations=fit.nfev,endpoint_error_km=float(np.linalg.norm(error)),optimizer_success=bool(fit.success))

def local_velocity(entry_state,seconds,target,moon):
    guesses=[]
    for prograde in [True,False]:
        try:
            v,_=izzo2015(SATURN_GM,entry_state[:3],target,seconds,M=0,prograde=prograde,low_path=True)
            propagate(np.r_[entry_state[:3],v],seconds,moon)
            guesses.append((float(np.linalg.norm(v-entry_state[3:])),v))
        except (ValueError,RuntimeError,AssertionError):continue
    if not guesses:raise ValueError('No collision-free Saturn Lambert initial guess')
    return shoot(entry_state,seconds,target,moon,min(guesses,key=lambda g:g[0])[1])

def target_arrival(segment,arrival_jd,saturn_state,titan_state,entry_altitude_km=1270.,gamma_deg=-65.,clock_deg=0.):
    if not np.isfinite(entry_altitude_km) or entry_altitude_km<=0:raise ValueError('Positive finite Titan entry altitude required')
    entry_jd,incoming=soi_entry(segment,arrival_jd,saturn_state);seconds=(arrival_jd-entry_jd)*DAY
    titan=titan_state(arrival_jd)-saturn_state(arrival_jd)
    nominal=solar_state(segment,arrival_jd)-titan_state(arrival_jd)
    normal=illustrative_entry_normal(nominal[3:],titan[:3],gamma_deg,clock_deg)
    target=titan[:3]+normal*(TITAN_RADIUS_KM+entry_altitude_km)
    moon=lambda t:(titan_state(entry_jd+t/DAY)-saturn_state(entry_jd+t/DAY))[:3]
    velocity,solution,convergence=local_velocity(incoming,seconds,target,moon)
    delta=velocity-incoming[3:];end=solution.y[:6,-1];relative=end-titan
    gamma=float(np.degrees(np.arcsin(np.clip(np.dot(unit(relative[:3]),unit(relative[3:])),-1,1))))
    # Independent state-only propagation, at tighter tolerances than the solve.
    independent=propagate(np.r_[incoming[:3],velocity],seconds,moon,rtol=3e-13,atol_position=1e-7)
    independent_error=float(np.linalg.norm(independent.y[:3,-1]-target))
    if independent_error>.1 or gamma>=0:raise ValueError('Independent entry validation failed or trajectory is outbound at entry')
    grid=np.unique(np.r_[np.arange(0,max(0,seconds-2*DAY),6*3600.),np.arange(max(0,seconds-2*DAY),seconds,60.),seconds])
    states=independent.sol(grid).T
    relative_moon=np.array([moon(t) for t in grid]);distances=np.linalg.norm(states[:,:3]-relative_moon,axis=1)
    radii=np.linalg.norm(states[:,:3],axis=1)
    earlier=grid<seconds-1
    if np.any(distances[earlier]<TITAN_RADIUS_KM+entry_altitude_km-.1):raise ValueError('An earlier sampled Titan entry precedes the target epoch')
    report=dict(entry_jd_tdb=entry_jd,arrival_jd_tdb=arrival_jd,saturn_soi_radius_km=float(np.linalg.norm(incoming[:3])),
        soi_delta_v_vector_ecliptic_j2000_kms=delta.tolist(),soi_delta_v_kms=float(np.linalg.norm(delta)),
        state_before_soi_burn_saturn_relative_km_kms=incoming.tolist(),state_after_soi_burn_saturn_relative_km_kms=np.r_[incoming[:3],velocity].tolist(),
        titan_relative_entry_state_km_kms=relative.tolist(),requested_entry_altitude_km=float(entry_altitude_km),titan_entry_altitude_km=float(np.linalg.norm(relative[:3])-TITAN_RADIUS_KM),
        titan_relative_inertial_entry_speed_kms=float(np.linalg.norm(relative[3:])),entry_flight_path_angle_deg=gamma,
        independent_endpoint_error_km=independent_error,minimum_sampled_saturn_altitude_km=float(np.min(radii)-SATURN_RADIUS_KM),
        coast_days=seconds/DAY,**convergence,
        model='Sun-only upstream coast; Saturn plus differential Titan point-mass gravity inside Saturn SOI. No solar tide, other moons, Saturn J2/rings, atmosphere or spacecraft navigation uncertainty.',
        entry_geometry='Illustrative inbound shell point, not an optimized entry corridor or landing site. Entry speed is Titan-relative inertial, not atmosphere-relative.')
    return report,entry_jd+grid/DAY,states

def target_upstream(segment,arrival_jd,saturn_state,titan_state,base_report,burn_fraction=.5):
    """Move the correction to a real cruise DSM; jointly match the SOI boundary.

    Three controls: two SOI direction coordinates and its epoch. Each evaluation
    solves Sun and Saturn/Titan arcs, then matches all three velocity components.
    Earlier spacecraft states and flybys are preserved through the new DSM.
    """
    if not .05<=burn_fraction<=.9:raise ValueError('Cruise burn fraction must be between .05 and .9')
    burn_jd=segment['start_jd']+burn_fraction*(arrival_jd-segment['start_jd'])
    burn_state=solar_state(segment,burn_jd);entry0=base_report['entry_jd_tdb']
    if burn_jd>=entry0-1:raise ValueError('Place the cruise DSM before Saturn SOI entry')
    n=unit(base_report['state_before_soi_burn_saturn_relative_km_kms'][:3])
    e1=unit(np.cross(n,np.eye(3)[np.argmin(abs(n))]));e2=np.cross(n,e1)
    titan=titan_state(arrival_jd)-saturn_state(arrival_jd)
    target=titan[:3]+np.array(base_report['titan_relative_entry_state_km_kms'][:3])
    memo={}
    def evaluate(z):
        key=tuple(z)
        if key not in memo:
            epoch=entry0+z[2];sat=saturn_state(epoch);soi=np.linalg.norm(sat[:3])*(SATURN_GM/MU_SUN)**.4
            r=soi*unit(n+z[0]*e1+z[1]*e2)
            departure,vin=izzo2015(MU_SUN,burn_state[:3],sat[:3]+r,(epoch-burn_jd)*DAY,M=0,prograde=True,low_path=True)
            moon=lambda t:(titan_state(epoch+t/DAY)-saturn_state(epoch+t/DAY))[:3]
            needed,solution,convergence=local_velocity(np.r_[r,vin-sat[3:]],(arrival_jd-epoch)*DAY,target,moon)
            memo[key]=dict(epoch=epoch,r=r,departure=departure,vin=vin,needed=needed,solution=solution,gap=needed-(vin-sat[3:]),moon=moon)
        return memo[key]
    def residual(z):return evaluate(z)['gap']/.1
    def jacobian(z):
        steps=[2e-6,2e-6,.0002];columns=[]
        for i,h in enumerate(steps):
            d=np.zeros(3);d[i]=h;columns.append((residual(z+d)-residual(z-d))/(2*h))
        return np.column_stack(columns)
    fit=least_squares(residual,np.zeros(3),jac=jacobian,bounds=([-.15,-.15,-14.],[.15,.15,14.]),x_scale=[.02,.02,1.],max_nfev=20,gtol=1e-11,ftol=1e-12,xtol=1e-12)
    best=evaluate(fit.x);epoch=best['epoch'];seconds=(arrival_jd-epoch)*DAY
    actual_incoming=best['vin']-saturn_state(epoch)[3:]
    independent=propagate(np.r_[best['r'],actual_incoming],seconds,best['moon'],rtol=3e-13,atol_position=1e-7)
    error=float(np.linalg.norm(independent.y[:3,-1]-target))
    if error>.1:raise ValueError(f'Continuous upstream targeting missed the entry point by {error:.6f} km')
    relative=independent.y[:6,-1]-titan;delta=best['departure']-burn_state[3:]
    gamma=float(np.degrees(np.arcsin(np.clip(unit(relative[:3])@unit(relative[3:]),-1,1))))
    if gamma>=0:raise ValueError('Upstream-targeted entry is outbound')
    grid=np.unique(np.r_[np.arange(0,max(0,seconds-2*DAY),6*3600.),np.arange(max(0,seconds-2*DAY),seconds,60.),seconds])
    states=independent.sol(grid).T
    report=dict(base_report,entry_jd_tdb=epoch,soi_delta_v_kms=0.,soi_delta_v_vector_ecliptic_j2000_kms=[0.,0.,0.],
        upstream_burn_jd_tdb=float(burn_jd),upstream_delta_v_kms=float(np.linalg.norm(delta)),upstream_delta_v_vector_kms=delta.tolist(),
        upstream_burn_fraction=burn_fraction,upstream_burn_position_heliocentric_km=burn_state[:3].tolist(),upstream_post_burn_velocity_heliocentric_kms=best['departure'].tolist(),
        soi_velocity_matching_residual_kms=float(np.linalg.norm(best['gap'])),independent_endpoint_error_km=error,
        titan_relative_entry_state_km_kms=relative.tolist(),titan_entry_altitude_km=float(np.linalg.norm(relative[:3])-TITAN_RADIUS_KM),
        titan_relative_inertial_entry_speed_kms=float(np.linalg.norm(relative[3:])),entry_flight_path_angle_deg=gamma,
        state_before_soi_burn_saturn_relative_km_kms=np.r_[best['r'],actual_incoming].tolist(),state_after_soi_burn_saturn_relative_km_kms=np.r_[best['r'],actual_incoming].tolist(),
        coast_days=seconds/DAY,iterations=fit.nfev,optimizer_success=bool(fit.success),endpoint_error_km=error,
        minimum_sampled_saturn_altitude_km=float(np.min(np.linalg.norm(states[:,:3],axis=1))-SATURN_RADIUS_KM),
        correction_model='One real upstream cruise DSM; continuous velocity at Saturn SOI. Entry position/epoch jointly targeted; no SOI burn applied during independent propagation.')
    report['target_entry_position_saturn_relative_km']=target.tolist()
    report['saturn_soi_radius_km']=float(np.linalg.norm(best['r']))
    return verify_upstream_coasts(report,saturn_state,titan_state)

def verify_upstream_coasts(report,saturn_state,titan_state):
    """Propagate Sun then Saturn/Titan, carrying the numerical state across SOI."""
    report=dict(report);burn_jd=report['upstream_burn_jd_tdb'];entry=report['entry_jd_tdb'];arrival=report['arrival_jd_tdb']
    initial=np.r_[report['upstream_burn_position_heliocentric_km'],report['upstream_post_burn_velocity_heliocentric_kms']]
    def sun_rhs(t,y):return np.r_[y[3:],-MU_SUN*y[:3]/np.linalg.norm(y[:3])**3]
    solar=solve_ivp(sun_rhs,(0,(entry-burn_jd)*DAY),initial,method='DOP853',rtol=3e-13,atol=np.r_[np.full(3,1e-7),np.full(3,1e-12)])
    if not solar.success:raise ValueError('Independent solar propagation failed')
    at_entry=solar.y[:,-1]-saturn_state(entry)
    target=np.array(report.get('target_entry_position_saturn_relative_km',np.array(report['titan_relative_entry_state_km_kms'][:3])+(titan_state(arrival)-saturn_state(arrival))[:3]))
    moon=lambda t:(titan_state(entry+t/DAY)-saturn_state(entry+t/DAY))[:3]
    seconds=(arrival-entry)*DAY
    local=propagate(at_entry,seconds,moon,rtol=3e-13,atol_position=1e-7)
    error=float(np.linalg.norm(local.y[:3,-1]-target))
    if error>.1:raise ValueError('Independent Sun-to-Saturn/Titan propagation missed the entry point by '+str(error)+' km')
    expected=np.array(report['state_before_soi_burn_saturn_relative_km_kms'])
    relative=local.y[:6,-1]-(titan_state(arrival)-saturn_state(arrival))
    grid=np.unique(np.r_[np.arange(0,max(0,seconds-2*DAY),6*3600.),np.arange(max(0,seconds-2*DAY),seconds,60.),seconds]);states=local.sol(grid).T
    earlier=grid<seconds-1;distance=np.array([np.linalg.norm(state[:3]-moon(t)) for t,state in zip(grid,states)])
    shell=report.get('requested_entry_altitude_km',report['titan_entry_altitude_km'])
    if np.any(distance[earlier]<TITAN_RADIUS_KM+shell-.1):
        raise ValueError('An earlier sampled Titan entry precedes the requested epoch')
    report.update(independent_solar_endpoint_error_km=float(np.linalg.norm(at_entry[:3]-expected[:3])),
        independent_solar_velocity_error_kms=float(np.linalg.norm(at_entry[3:]-expected[3:])),
        independent_endpoint_error_km=error,independent_sun_and_saturn_titan_propagation_passed=True,
        state_before_soi_burn_saturn_relative_km_kms=at_entry.tolist(),state_after_soi_burn_saturn_relative_km_kms=at_entry.tolist(),
        titan_relative_entry_state_km_kms=relative.tolist(),titan_entry_altitude_km=float(np.linalg.norm(relative[:3])-TITAN_RADIUS_KM),
        titan_relative_inertial_entry_speed_kms=float(np.linalg.norm(relative[3:])),
        entry_flight_path_angle_deg=float(np.degrees(np.arcsin(np.clip(unit(relative[:3])@unit(relative[3:]),-1,1)))))
    return report,entry+grid/DAY,states
