"""Independent admission checks for public Lambert examples (no saved flags).

The source solver uses NumPy. This screen deliberately recomputes flyby
geometry with standard-library arithmetic from the stored encounter vectors.
It is a patched-conic screen, not an n-body or navigation validation.
"""
import math

POLICY = dict(max_unpowered_speed_mismatch_mps=1., max_single_dsm_mps=700.,
              max_powered_flyby_mps=200., max_total_cruise_mps=1500.)

def norm(v): return math.sqrt(sum(float(x)**2 for x in v))
def sub(a,b): return [float(x)-float(y) for x,y in zip(a,b)]

def audit_powered_flyby(power,gm,radius_floor,vi,vo):
    """Recover both hyperbolic asymptotes independently from periapsis states."""
    errors=[]
    try:
        r=power['peri_position_km'];before=power['peri_in_velocity_kms'];after=power['peri_out_velocity_kms']
        if any(len(v)!=3 or not all(math.isfinite(float(x)) for x in v) for v in (r,before,after,power['delta_v_vector_kms'])):
            raise ValueError('Invalid powered state')
        rp=norm(r);uin,uout=norm(vi),norm(vo)
        if rp<radius_floor-1e-6 or abs(rp-power['periapsis_radius_km'])>1e-5:errors.append('Powered periapsis violates radius/floor')
        for speed,v,incoming,expected in ((uin,before,True,vi),(uout,after,False,vo)):
            vp=norm(v);ecc=1+rp*speed**2/gm
            if abs(vp**2-2*gm/rp-speed**2)>1e-5:errors.append('Powered hyperbola energy differs')
            if abs(sum(a*b for a,b in zip(r,v)))>1e-7*rp*vp:errors.append('Powered velocity is not tangent at periapsis')
            radial=(1 if incoming else -1)/ecc
            tangential=math.sqrt(1-1/ecc**2)
            recovered=[speed*(radial*p/rp+tangential*t/vp) for p,t in zip(r,v)]
            if norm(sub(recovered,expected))>1e-6:errors.append('Powered asymptote differs from Lambert encounter')
        delta=sub(after,before)
        if norm(sub(delta,power['delta_v_vector_kms']))>1e-8 or abs(norm(delta)-power['magnitude_kms'])>1e-8:errors.append('Powered burn vector differs from charged magnitude')
    except (KeyError,TypeError,ValueError,ZeroDivisionError,OverflowError):errors.append('Incomplete or degenerate powered flyby states')
    return errors

def audit_candidate(q, config, bodies):
    errors=[];joins=[]
    events=q['events'];n=len(events);dates=q['dates_jd_tdb']
    if len(dates)!=n or any(b<=a for a,b in zip(dates,dates[1:])):errors.append('Non-increasing encounter epochs')
    if len(q['departure_velocities_kms'])!=n-1 or len(q['arrival_velocities_kms'])!=n-1:
        return dict(passed=False,reasons=['Incomplete leg velocities'],joins=[])
    launch=sub(q['departure_velocities_kms'][0],events[0]['planet_state_km_kms'][3:])
    terminal=sub(q['arrival_velocities_kms'][-1],events[-1]['planet_state_km_kms'][3:])
    if abs(norm(launch)**2-q['launch_c3_km2_s2'])>1e-6:errors.append('C3 differs from departure vectors')
    if abs(norm(terminal)-q['arrival_vinf_kms'])>1e-7:errors.append('Arrival Vinf differs from terminal vectors')
    for i in range(1,n-1):
        body=events[i]['body'];gm,radius,floor=bodies[body][1:]
        stored=next((f for f in q['flybys'] if f['event_index']==i),None)
        if stored is None:errors.append('Missing flyby record');continue
        floor=max(floor,config.get('minimum_altitude_km',{}).get(body,floor),stored.get('minimum_altitude_km',floor))
        planet_v=events[i]['planet_state_km_kms'][3:]
        vi=sub(q['arrival_velocities_kms'][i-1],planet_v);vo=sub(q['departure_velocities_kms'][i],planet_v)
        a,b=norm(vi),norm(vo);mismatch=1000*abs(a-b)
        cross=[vi[1]*vo[2]-vi[2]*vo[1],vi[2]*vo[0]-vi[0]*vo[2],vi[0]*vo[1]-vi[1]*vo[0]]
        angle=math.atan2(norm(cross),sum(x*y for x,y in zip(vi,vo)))
        if min(a,b)<=1e-8:errors.append('Degenerate flyby speed');continue
        periapsis=gm/max(a,b)**2*(1/math.sin(angle/2)-1) if angle>1e-12 else None
        max_turn=2*math.asin(1/(1+(radius+floor)*max(a,b)**2/gm))
        # Public examples must meet both the current strict gallery rule and
        # the original requested tolerance. No discrepancy is silently a burn.
        tolerance=min(POLICY['max_unpowered_speed_mismatch_mps'],config.get('vinf_tolerance_mps',1.))
        power=stored.get('powered_flyby') if config.get('powered_flybys') else None
        if power is not None:
            errors.extend(f'{body}: {reason}' for reason in audit_powered_flyby(power,gm,radius+floor,vi,vo))
            soi=norm(events[i]['planet_state_km_kms'][:3])*(gm/132712440041.27942)**.4
            if soi and power['periapsis_radius_km']>=.8*soi:errors.append(f'{body}: powered periapsis lies outside the modeled sphere of influence')
        else:
            if mismatch>tolerance+1e-6:errors.append(f'{body}: speed mismatch exceeds {tolerance:g} m/s')
            if angle>max_turn+1e-9:errors.append(f'{body}: required turn exceeds the altitude-floor limit')
        altitude=power['periapsis_radius_km']-radius if power else (None if periapsis is None else periapsis-radius)
        joins.append(dict(body=body,event_index=i,jd=dates[i],mismatch_mps=mismatch,vinf_in_kms=a,vinf_out_kms=b,
                          turn_deg=math.degrees(angle),max_turn_deg=math.degrees(max_turn),
                          inferred_altitude_km=altitude,minimum_altitude_km=floor,
                          powered_mps=1000*power['magnitude_kms'] if power else 0.,
                          powered_geometry_audited=power is not None,
                          clearance_above_floor_km=None if altitude is None else altitude-floor))
    for burn in q.get('dsms',[]):
        vector=burn.get('delta_v_ecliptic_j2000_kms')
        if vector is None or abs(norm(vector)-burn['magnitude_kms'])>1e-8:errors.append('DSM magnitude differs from its vector')
    max_dsm=max([1000*b['magnitude_kms'] for b in q.get('dsms',[])]+[0])
    powers=[1000*f.get('powered_flyby',{}).get('magnitude_kms',0.) for f in q.get('flybys',[])]
    peak_power=max(powers+[0])
    if max_dsm>min(POLICY['max_single_dsm_mps'],1000*config.get('max_single_dsm_kms',.7))+1e-6:errors.append('Individual DSM exceeds cap')
    if peak_power>min(POLICY['max_powered_flyby_mps'],1000*config.get('max_powered_flyby_kms',.2))+1e-6:errors.append('Powered flyby exceeds cap')
    total=1000*sum(b['magnitude_kms'] for b in q.get('dsms',[]))+sum(powers)
    if total>POLICY['max_total_cruise_mps']+1e-6:errors.append('Cruise maneuver total exceeds catalog limit')
    if total>1000*config.get('max_dsm_kms',float('inf'))+1e-6:errors.append('Cruise maneuver total exceeds saved budget')
    if abs(total-1000*q['total_dsm_kms'])>.001:errors.append('Cruise total differs from explicit burns')
    for key,limit in [('launch_c3_km2_s2','max_c3'),('arrival_vinf_kms','max_arrival_vinf_kms'),('duration_years','max_years')]:
        if q[key]>config.get(limit,float('inf'))+1e-7:errors.append(f'{key} exceeds saved mission limit')
    return dict(passed=not errors,reasons=errors,method='Independent stored-vector patched-conic screen',
                joins=joins,max_vinf_mismatch_mps=max([j['mismatch_mps'] for j in joins]+[0]),
                max_unpowered_vinf_mismatch_mps=max([j['mismatch_mps'] for j in joins if not j['powered_geometry_audited']]+[0]),
                max_single_dsm_mps=max_dsm,max_powered_flyby_mps=peak_power,cruise_total_mps=total,policy=POLICY)
