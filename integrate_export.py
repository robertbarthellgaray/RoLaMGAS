"""Finite-radius patched-conic visualization, explicit junction burns, CSV/XYZV."""
import bootstrap  # noqa: F401
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import traceback
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq
from dynamics import kepler,lambert
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


def integrate_relative(mu,r,v,t0,t1):
    initial = hyperbolic_state(mu,r,v,t0)
    def rhs(t,y):
        return np.r_[y[3:],-mu*y[:3]/np.linalg.norm(y[:3])**3]
    fit = solve_ivp(rhs,(t0,t1),initial,method='DOP853',rtol=2.5e-13,
                    atol=np.r_[np.full(3,1e-8),np.full(3,1e-12)],dense_output=True)
    if not fit.success:
        raise ValueError('Planet-centered integration failed: '+fit.message)
    expected = hyperbolic_state(mu,r,v,t1)
    error = float(np.linalg.norm(fit.y[:3,-1]-expected[:3]))
    return fit.sol,error


def planet_pieces(body,date,ep,uin=None,uout=None,altitude=200.,departure=False,terminal=False,powered=False):
    _,mu,radius,_ = BODIES[body]
    planet = ep.state(body,date)
    soi = np.linalg.norm(planet[:3])*(mu/MU_SUN)**.4
    if departure or terminal:
        rp = radius+altitude
        speed = float(np.linalg.norm(uout if departure else uin))
        alpha = float(np.arcsin(1/(1+rp*speed*speed/mu)))
        direction = unit(uout if departure else uin)
        h = plane_axis(planet[:3],direction)
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
                           label=body+' hyperbola',kind='planet',body=body,numerical_error_km=error))
    return dict(pieces=pieces,rp=rp,altitude=rp-radius,body=body,date=date,soi=soi,
                peri_position=relr,peri_in_velocity=vpin,peri_out_velocity=vpout)


def revolutions(segment):
    r,v = np.asarray(segment['r']),np.asarray(segment['v'])
    dt = (segment['end_jd']-segment['start_jd'])*DAY
    energy = np.dot(v,v)/2-MU_SUN/np.linalg.norm(r)
    if energy>=0:
        return 0
    a = -MU_SUN/(2*energy)
    period = 2*np.pi*np.sqrt(a**3/MU_SUN)
    h = unit(np.cross(r,v)); p=unit(r); q=np.cross(h,p)
    times = np.linspace(0,dt,min(3000,max(60,int(dt/period*60)+60)))
    points = np.asarray([kepler(r,v,float(t))[0] for t in times])
    angles = np.unwrap(np.arctan2(points@q,points@p))
    return max(0,int(np.floor((angles[-1]-angles[0])/(2*np.pi)+1e-8)))


def solar_piece(start,end,r0,r1,reference,low=True):
    if end<=start:
        raise ValueError('Finite flyby patches overlap a DSM or the next encounter')
    m = revolutions(reference)
    prograde=bool(np.cross(np.asarray(reference['r']),np.asarray(reference['v']))[2]>=0)
    choices = []
    for path in ([low,not low] if m else [True]):
        try:
            va,vb = lambert(np.asarray(r0),np.asarray(r1),end-start,(m,path,prograde))
            choices.append((np.linalg.norm(va-np.asarray(reference['v'])),va,vb))
        except (ValueError,RuntimeError,AssertionError):
            pass
    if not choices:
        raise ValueError('No finite-boundary Lambert solution on the original revolution family. This candidate needs further targeting.')
    _,va,vb = min(choices,key=lambda q:q[0])
    def rhs(t,y):
        return np.r_[y[3:],-MU_SUN*y[:3]/np.linalg.norm(y[:3])**3]
    duration = (end-start)*DAY
    fit = solve_ivp(rhs,(0,duration),np.r_[r0,va],method='DOP853',rtol=2.5e-13,
                    atol=np.r_[np.full(3,1e-6),np.full(3,1e-13)],dense_output=True)
    if not fit.success:
        raise ValueError('Heliocentric integration failed: '+fit.message)
    def state(j):
        return fit.sol((j-start)*DAY)
    error = float(np.linalg.norm(fit.y[:3,-1]-r1))
    return dict(start=start,end=end,state=state,label='Heliocentric coast',kind='solar',
                numerical_error_km=error,revolutions=m)


MONTH_DAYS=365.25/12


def validate_post_flyby_months(value):
    value=float(value)
    if not math.isfinite(value) or value<0:raise ValueError('Months after flyby must be nonnegative and finite')
    return value


def extend_planet_ephemerides(ep,c,start,end,status):
    """Load cached coverage first; download only a missing future interval."""
    for body in list(ep.splines):
        if body not in BODIES:continue
        old_end=JD0+ep.splines[body].x[-1]/DAY
        if old_end>=end:continue
        status('Checking post-flyby ephemeris coverage for '+body+'…')
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


def solar_continuation(start,end,initial):
    initial=np.array(initial,dtype=float);seconds=(end-start)*DAY
    expected,_=kepler(initial[:3],initial[3:],seconds)
    def rhs(t,y):return np.r_[y[3:],-MU_SUN*y[:3]/np.linalg.norm(y[:3])**3]
    fit=solve_ivp(rhs,(0,seconds),initial,method='DOP853',rtol=2.5e-13,
                  atol=np.r_[np.full(3,1e-6),np.full(3,1e-13)],dense_output=True,max_step=2*DAY)
    if not fit.success:raise ValueError('Post-flyby heliocentric integration failed: '+fit.message)
    def state(date):return fit.sol((date-start)*DAY)
    return dict(start=start,end=end,state=state,label='Post-flyby heliocentric coast',kind='solar',
                numerical_error_km=float(np.linalg.norm(fit.y[:3,-1]-expected)))


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
    outgoing=dict(start=date,end=stop,state=state,label=body+' outbound flyby',kind='planet',body=body,numerical_error_km=error)
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
    if q['launch_c3_km2_s2']<c.get('min_c3',0)-1e-8:
        failures.append(f"Launch C3 is below requested minimum {c['min_c3']:.8g}")
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
    return failures


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


def export(candidate,config,output,arrival_altitude_km=None,powered_flybys=None,post_flyby_months=0.):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    def status(message):
        atomic_json(output/'integration_status.json',dict(state='running',message=message))
    q=json.loads(Path(candidate).read_text(encoding='utf-8'))
    original_status=q['status']
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
    if post_flyby_months>0:extend_planet_ephemerides(ep,c,q['events'][0]['julian_date_tdb']-2,extended_end+2,status)
    if powered_flybys is not None or c.get('powered_flybys'):
        from dynamics import Model
        model=Model(next(r for r in routes_for(c) if r['id']==q['sequence']),c,ep)
        updated=model.evaluate(q['x'],q['branches']);updated['id']=q['id']
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
            f=q['flybys'][i-1] if i<len(q['events'])-1 else None
            if f is None and arrival_altitude_km is not None:floor=arrival_altitude_km
            node=planet_pieces(body,date,ep,uin=np.array(f['incoming_vinf_vector_kms'] if f else q['arrival_vinf_vector_kms']),
                               uout=np.array(f['outgoing_vinf_vector_kms']) if f else None,
                               altitude=0. if f and not q['status'].startswith('passes') and not c.get('powered_flybys') else floor,
                               terminal=i==len(q['events'])-1,powered=bool(f and c.get('powered_flybys')))
            if f and node['altitude']<floor-1e-6:
                violations.append(f"{body} integrated flyby altitude {node['altitude']:.8g} km is below requested {floor:.8g} km")
        else:
            node=small_body_node(body,date,ep,q['arrival_vinf_vector_kms'],
                                 10000. if arrival_altitude_km is None else arrival_altitude_km)
        nodes.append(node)
    pieces=list(nodes[0]['pieces'])
    segment_index=0
    for i in range(len(nodes)-1):
        left,right=nodes[i],nodes[i+1]
        begin=left['pieces'][-1]['end']
        y0=left['pieces'][-1]['state'](begin)
        end=right['pieces'][0]['start'] if right['pieces'] else right['date']
        y1=right['pieces'][0]['state'](end) if right['pieces'] else right['target_state']
        burn=next((b for b in q['dsms'] if b['leg_index']==i),None)
        reference=q['segments'][segment_index]
        if burn:
            mid=burn['julian_date_tdb'];point=np.array(burn['position_km'])
            pieces.append(solar_piece(begin,mid,y0[:3],point,reference,q['branches'][i][1]))
            pieces.append(solar_piece(mid,end,point,y1[:3],q['segments'][segment_index+1],True))
            segment_index+=2
        else:
            pieces.append(solar_piece(begin,end,y0[:3],y1[:3],reference,q['branches'][i][1]))
            segment_index+=1
        pieces.extend(right['pieces'])
    if post_flyby_months>0:
        status('Integrating '+str(post_flyby_months)+' months after the final flyby…')
        pieces.extend(post_flyby_pieces(nodes[-1],ep,extended_end,pieces[-1]['state'](encounter_date)))
    status('Checking state joins and recording every maneuver…')
    burns=[];jumps=[]
    mu=BODIES['Earth'][1];r0=BODIES['Earth'][2]+200
    injection=np.sqrt(q['launch_c3_km2_s2']+2*mu/r0)-np.sqrt(mu/r0)
    injection_vector=injection*unit(nodes[0]['peri_out_velocity'])
    burns.append(dict(kind='launch_injection_from_200_km',julian_date_tdb=q['dates_jd_tdb'][0],
                      magnitude_kms=float(injection),dx_kms=injection_vector[0],dy_kms=injection_vector[1],dz_kms=injection_vector[2]))
    for a,b in zip(pieces,pieces[1:]):
        if abs(a['end']-b['start'])>1e-8:
            raise ValueError('Gap between integrated pieces')
        t=b['start'];ya,yb=a['state'](t),b['state'](t)
        jumps.append(float(np.linalg.norm(ya[:3]-yb[:3])))
        dv=yb[3:]-ya[3:]
        if a['kind']=='solar' and b['kind']=='solar':kind='retargeted_DSM'
        elif a['kind']=='planet' and b['kind']=='planet':kind='powered_flyby' if c.get('powered_flybys') else 'flyby_speed_match_burn'
        else:kind='finite_patch_junction'
        if np.linalg.norm(dv)>1e-8:
            burns.append(dict(kind=kind,julian_date_tdb=t,magnitude_kms=float(np.linalg.norm(dv)),
                              dx_kms=dv[0],dy_kms=dv[1],dz_kms=dv[2]))
    status('Sampling integrated arcs and checking planetary clearances…')
    samples=[sample_piece(p,i<len(pieces)-1) for i,p in enumerate(pieces)]
    start,end=pieces[0]['start'],pieces[-1]['end']
    try:
        all_ep=Ephemerides(c['cache'],list(BODIES),start,end,c['max_ephemeris_step_days'])
        clearance_rows=clearances(pieces,samples,all_ep)
        checked=list(BODIES)
    except ValueError:
        clearance_rows=clearances(pieces,samples,ep)
        checked=[b for b in BODIES if b in ep.splines]
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
                           date=calendar(n['date']),periapsis_radius_km=n['rp'],altitude_km=n['altitude']) for n in nodes]),
                      ('planet_clearances',clearance_rows)]:
        with (output/(name+'.csv')).open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
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
    patch_dv=sum(b['magnitude_kms'] for b in burns if b['kind']=='finite_patch_junction')
    onboard=sum(b['magnitude_kms'] for b in burns if not b['kind'].startswith('launch'))
    actual_dsm_peak=max((b['magnitude_kms'] for b in burns if b['kind'] in ('retargeted_DSM','finite_patch_junction')),default=0.)
    actual_power_peak=max((b['magnitude_kms'] for b in burns if b['kind'] in ('powered_flyby','flyby_speed_match_burn')),default=0.)
    individual_pass=actual_dsm_peak<=c['max_single_dsm_kms']+1e-9 and actual_power_peak<=c['max_powered_flyby_kms']+1e-9
    if not individual_pass:violations.append('An integrated DSM/patch correction or flyby impulse exceeds its individual burn cap; see burns.csv')
    report=dict(model='Numerically integrated Sun-only coasts and planet-centered hyperbolas, translated using JPL planet states',
                frame='Sun-centered Ecliptic J2000; km, km/s; Julian dates TDB',candidate_id=q['id'],
                arrival_altitude_option_km=arrival_altitude_km,arrival_state=arrival_state,
                post_flyby_months=post_flyby_months,month_length_days=MONTH_DAYS,
                final_encounter_jd_tdb=encounter_date,post_flyby_end_date=calendar(end),
                passes_individual_burn_limits=individual_pass,maximum_integrated_dsm_or_patch_kms=actual_dsm_peak,
                maximum_integrated_flyby_burn_kms=actual_power_peak,
                source_candidate_status=original_status,export_evaluation_status=q['status'],powered_flybys_active=c.get('powered_flybys',False),
                candidate_powered_flyby_delta_v_kms=q.get('powered_flyby_delta_v_kms',0.),
                candidate_cruise_dsm_kms=q.get('cruise_dsm_kms',q['total_dsm_kms']-q.get('powered_flyby_delta_v_kms',0.)),
                powered_flyby_burns=[dict(body=f['body'],event_index=f['event_index'],julian_date_tdb=f['julian_date_tdb'],**f['powered_flyby']) for f in q['flybys'] if f.get('powered_flyby')],
                candidate_passes_requested_limits=not violations and q['status'].startswith('passes'),
                requirement_violations=violations,
                requested_limits={key:c[key] for key in ('min_c3','max_c3','arrival_date','arrival_tolerance_days','max_dsm_kms','max_single_dsm_kms','max_powered_flyby_kms','max_arrival_vinf_kms','max_years','vinf_tolerance_mps','minimum_altitude_km')},
                source_candidate_sha256=hashlib.sha256(Path(candidate).read_bytes()).hexdigest(),
                ephemeris_sources=ep.manifest,
                numerical_validation_passed=max_error<1 and max(jumps,default=0)<1,
                maximum_arc_endpoint_error_km=max_error,maximum_position_join_residual_km=max(jumps,default=0),
                patch_join_delta_v_kms=patch_dv,total_onboard_delta_v_kms=onboard,
                launch_injection_from_200_km_kms=float(injection),candidate_dsm_kms=q['total_dsm_kms'],
                passes_original_onboard_budget=onboard<=c['max_dsm_kms'],rows=len(flattened),
                start_jd_tdb=start,end_jd_tdb=end,planet_clearances=clearance_rows,
                no_sample_bracketed_planet_or_sun_impacts=all(r['altitude_km']>0 for r in clearance_rows),
                planets_checked=checked,continuous_nbody_validated=False,
                sampling='Adaptive Hermite midpoint position residual below 0.1 km; maximum solar step 2 days, flyby step 2 hours; impulse epochs separated by 0.02 s.',
                small_body_arrival=(f"{last['center_distance_km']:.12g} km from target center at the requested encounter epoch; target gravity, surface radius and capture are not modeled." if 'center_distance_km' in last else None),
                small_body_encounter_distance_km=last.get('center_distance_km'),
                limitations=['Boundary velocities are retargeted; every resulting impulse is explicit in burns.csv.',
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
    (output/'README.txt').write_text('CSV and XYZV contain the same integrated Sun-centered Ecliptic J2000 states, km and km/s, JD TDB.\nFor Celestia put trajectory.ssc in an addon folder and trajectory.xyzv in its data subfolder.\nAll maneuvers, including finite-patch junction corrections, are in burns.csv. Check integration_report.json before using its fuel budget.\n',encoding='utf-8')
    atomic_json(output/'integration_status.json',dict(state='finished',message='Integrated trajectory and both export formats saved.'))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--candidate',required=True);p.add_argument('--config',required=True);p.add_argument('--output',required=True);p.add_argument('--arrival-altitude-km',type=float);p.add_argument('--powered-flybys',action=argparse.BooleanOptionalAction,default=None);p.add_argument('--post-flyby-months',type=float,default=0.)
    args=p.parse_args()
    try:
        export(args.candidate,json.loads(Path(args.config).read_text(encoding='utf-8')),args.output,args.arrival_altitude_km,args.powered_flybys,args.post_flyby_months)
    except Exception as exc:
        Path(args.output).mkdir(parents=True,exist_ok=True)
        atomic_json(Path(args.output)/'integration_status.json',dict(state='failed',message=str(exc)))
        traceback.print_exc();raise
