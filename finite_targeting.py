"""Local finite-SOI matching. No force model changes, hidden impulses or downloads."""
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
from ephemeris import BODIES,DAY,MU_SUN,calendar


def retarget_node(original,ep,position,vin,vout,date,numerical=False):
    from integrate_export import hyperbolic_state,hyperbolic_time,integrate_relative
    node=dict(original);body=node['body'];mu=BODIES[body][1]
    rp=float(np.linalg.norm(position));ni=np.sqrt(vin@vin-2*mu/rp);no=np.sqrt(vout@vout-2*mu/rp)
    soi=float(np.linalg.norm(ep.state(body,date)[:3])*(mu/MU_SUN)**.4)
    if rp>=.8*soi:raise ValueError('Periapsis outside finite patch')
    inbound=original['pieces'][0]['start']<original['date']
    outbound=original['pieces'][-1]['end']>original['date']
    pieces=[]
    for begin,end,velocity in ([(-hyperbolic_time(mu,rp,ni,soi),0.,vin)] if inbound else [])+([(0.,hyperbolic_time(mu,rp,no,soi),vout)] if outbound else []):
        if numerical:solution,error=integrate_relative(mu,position,velocity,begin,end)
        else:
            solution=lambda seconds,velocity=velocity:hyperbolic_state(mu,position,velocity,seconds)
            error=0.
        def state(j,solution=solution,date=date,body=body):return ep.state(body,j)+solution((j-date)*DAY)
        pieces.append(dict(start=date+begin/DAY,end=date+end/DAY,state=state,label=body+' hyperbola',
            kind='planet',body=body,numerical_error_km=error,force_center=body,gm_km3_s2=mu,soi_radius_km=soi))
    node.update(pieces=pieces,rp=rp,altitude=rp-BODIES[body][2],date=date,soi=soi,
                peri_position=position,peri_in_velocity=vin,peri_out_velocity=vout)
    return node


def match_finite_patches(nodes,candidate,config,ep,status=lambda text:None,max_nfev=100,max_epoch_shift_days=2.):
    """Adjust periapsis geometry, dates and the existing DSM; retain best real budget.

    Intermediate periapsis epochs can move by at most two days. Launch epoch,
    final encounter epoch/aimpoint, node order, DSM epoch and coast winding stay
    fixed. Launch speed stays inside the user's C3 bounds and within 10.6% C3.
    Every remaining velocity gap is still exported as an actual impulse.
    """
    from integrate_export import node_coast_boundary,solar_velocities
    descriptors=[];lower=[];upper=[];size=0
    for i,node in enumerate(nodes[:-1]):
        if node['body'] not in BODIES:continue
        count=4 if i==0 else (6 if max_epoch_shift_days else 5)
        descriptors.append((i,size,count));size+=count
        lower.extend([-.25]*3+[-.05] if i==0 else [-.25]*3+[-3.,-.05]+([-1.] if max_epoch_shift_days else []))
        upper.extend([.25]*3+[.05] if i==0 else [.25]*3+[3.,.05]+([1.] if max_epoch_shift_days else []))
        if i==0:
            mu=BODIES[node['body']][1];speed2=float(node['peri_out_velocity']@node['peri_out_velocity']-2*mu/node['rp'])
            floor=max(5.,config.get('effective_min_c3',config.get('min_c3',5.)))
            lower[-1]=max(lower[-1],.5*np.log(floor/speed2))
            upper[-1]=min(upper[-1],.5*np.log(min(config['max_c3'],candidate.get('effective_max_c3',config['max_c3']))/speed2))
            if not lower[-1]<=0<=upper[-1]:return nodes,{},dict(applied=False,reason='Source launch energy is outside requested bounds')
    dsms={b['leg_index']:b for b in candidate['dsms']};dsm_indices={}
    for leg in dsms:dsm_indices[leg]=size;size+=3;lower.extend([-3.]*3);upper.extend([3.]*3)
    if not descriptors:return nodes,{},dict(applied=False,reason='No planetary patches')
    if any(n['body'] not in BODIES for n in nodes[1:-1]):
        return nodes,{},dict(applied=False,reason='Geometric intermediate-body turnaround retained without local matching')
    references=[];index=0
    for leg in range(len(nodes)-1):
        references.append(candidate['segments'][index:index+(2 if leg in dsms else 1)])
        index+=len(references[-1])

    def decode(x,numerical=False):
        result=list(nodes)
        for i,offset,count in descriptors:
            old=nodes[i];values=x[offset:offset+count];rotation=Rotation.from_rotvec(values[:3]);mu=BODIES[old['body']][1]
            if i==0:rp=old['rp'];speed_factor=np.exp(values[3]);date=old['date']
            else:
                minimum=BODIES[old['body']][2]+config['minimum_altitude_km'].get(old['body'],BODIES[old['body']][3])
                if old['rp']<minimum-1e-6:raise ValueError('Original periapsis is below the requested floor')
                # A positive clearance parameter prevents an optimizer step below the floor.
                rp=minimum+max(1e-3,old['rp']-minimum)*np.exp(values[3]);speed_factor=np.exp(values[4]);date=old['date']+(max_epoch_shift_days*values[5] if count==6 else 0.)
            position=rotation.apply(old['peri_position'])*rp/old['rp'];velocities=[]
            for key in ['peri_in_velocity','peri_out_velocity']:
                velocity=old[key];energy=float(velocity@velocity-2*mu/old['rp'])
                velocities.append(rotation.apply(velocity)/np.linalg.norm(velocity)*np.sqrt(energy*speed_factor**2+2*mu/rp))
            result[i]=retarget_node(old,ep,position,*velocities,date,numerical)
        points={leg:np.asarray(dsms[leg]['position_km'])+1e6*x[offset:offset+3] for leg,offset in dsm_indices.items()}
        return result,points

    def evaluate(x):
        trial,points=decode(x);gaps=[];burns=[]
        for leg in range(len(nodes)-1):
            start,a=node_coast_boundary(trial[leg],True);end,b=node_coast_boundary(trial[leg+1],False)
            last_has_patch=bool(trial[leg+1]['pieces']) or leg+1<len(nodes)-1
            if leg in dsms:
                mid=dsms[leg]['julian_date_tdb'];point=points[leg]
                va,vm,_,_=solar_velocities(start,mid,a[:3],point,references[leg][0],candidate['branches'][leg][1],(a[3:],None))
                vn,vb,_,_=solar_velocities(mid,end,point,b[:3],references[leg][1],True,(None,b[3:] if last_has_patch else None))
                burns.append(vn-vm)
            else:
                va,vb,_,_=solar_velocities(start,end,a[:3],b[:3],references[leg][0],candidate['branches'][leg][1],(a[3:],b[3:] if last_has_patch else None))
            gaps.append(va-a[3:])
            if last_has_patch:gaps.append(b[3:]-vb)
        peri=sum(np.linalg.norm(n['peri_out_velocity']-n['peri_in_velocity']) for n in trial[1:-1] if n['pieces'])
        return gaps,burns,float(peri)

    initial=np.zeros(size);g0,b0,p0=evaluate(initial)
    baseline=sum(np.linalg.norm(v) for v in g0+b0)+p0
    # The stored DSM vector field differs between old candidates; use its actual
    # retargeted vector as the local reference rather than assume a missing zero.
    wanted=b0
    best=[baseline,initial.copy()];calls=[0]
    length=3*(len(g0)+len(b0))+size
    def residual(x):
        try:
            gaps,burns,peri=evaluate(x);cost=sum(np.linalg.norm(v) for v in gaps+burns)+peri
            if cost<best[0]:best[:]=[cost,x.copy()]
            calls[0]+=1
            if calls[0]%250==0:status(f'Matching finite flyby patches: {best[0]*1000:.1f} m/s total cruise impulses so far…')
            return np.r_[np.concatenate(gaps)/.001,np.concatenate([v-w for v,w in zip(burns,wanted)])/.1 if burns else [],x*.001]
        except (ValueError,RuntimeError,AssertionError,FloatingPointError):return np.full(length,1e6)+np.linalg.norm(x)
    status('Matching finite flyby geometry and preceding coasts; no new DSM epochs…')
    fit=least_squares(residual,initial,bounds=(lower,upper),max_nfev=max_nfev,diff_step=1e-5,ftol=1e-9,xtol=1e-9,gtol=1e-9)
    # Include the final optimizer point; only adopt a demonstrably cheaper variant.
    residual(fit.x);final_gaps,final_burns,final_peri=evaluate(fit.x)
    chosen=best[1];applied=bool(best[0]<baseline-1e-6)
    result,points=decode(chosen,numerical=True) if applied else (nodes,{})
    gaps,burns,peri=evaluate(chosen)
    report=dict(applied=applied,reason='Lower explicit cruise budget' if applied else 'No lower-budget local match found',
        baseline_cruise_delta_v_kms=baseline,matched_cruise_delta_v_kms=best[0],evaluations=calls[0],
        remaining_patch_delta_v_kms=float(sum(np.linalg.norm(v) for v in gaps)),
        maximum_patch_burn_kms=float(max((np.linalg.norm(v) for v in gaps),default=0.)),
        matched_dsm_delta_v_kms=float(sum(np.linalg.norm(v) for v in burns)),
        final_solver_patch_delta_v_kms=float(sum(np.linalg.norm(v) for v in final_gaps)),
        final_solver_cruise_delta_v_kms=float(sum(np.linalg.norm(v) for v in final_gaps+final_burns)+final_peri),
        scipy_success=bool(fit.success),scipy_message=str(fit.message),maximum_periapsis_epoch_shift_days=float(max_epoch_shift_days),
        changes=[dict(body=n['body'],source_jd_tdb=o['date'],exported_jd_tdb=n['date'],date=calendar(n['date']),
                      epoch_shift_days=n['date']-o['date'],source_altitude_km=o['altitude'],exported_altitude_km=n['altitude'])
                 for o,n in zip(nodes,result)],
        note='Local finite-SOI matching, not a global minimum. Source candidate is unchanged. Remaining velocity gaps are explicit burns, not hidden or erased.')
    return result,points,report
