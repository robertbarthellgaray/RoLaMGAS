"""Local finite-SOI matching. No force model changes, hidden impulses or downloads."""
import numpy as np
from scipy.optimize import least_squares,minimize
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
    if original.get('capture_assessment') is not None:
        from arrival_geometry import capture_assessment
        sine=1/(1+rp*ni*ni/mu)
        incoming=ni*(sine*position/rp+np.sqrt(1-sine*sine)*vin/np.linalg.norm(vin))
        node['capture_assessment']=capture_assessment(body,date,mu,incoming,position,vin,
            original['capture_assessment'].get('requested_inclination_deg'))
    return node


def match_finite_patches(nodes,candidate,config,ep,status=lambda text:None,max_nfev=100,max_epoch_shift_days=2.):
    """Adjust periapsis geometry, dates and the existing DSM; retain best real budget.

    Intermediate periapsis epochs can move within the user-selected range. Launch epoch,
    final encounter epoch/altitude, node order, DSM epoch and coast winding stay
    fixed. Launch speed stays inside the user's C3 bounds and within 10.6% C3.
    Every remaining velocity gap is still exported as an actual impulse.
    """
    from integrate_export import node_coast_boundary,solar_velocities
    descriptors=[];lower=[];upper=[];size=0
    for i,node in enumerate(nodes):
        if node['body'] not in BODIES:continue
        terminal=i==len(nodes)-1
        if terminal and node.get('capture_assessment',{}).get('requested_inclination_deg') is not None:continue
        count=4 if i==0 or terminal else (6 if max_epoch_shift_days else 5)
        descriptors.append((i,size,count));size+=count
        speed_box=.05 if i==0 else .2
        lower.extend([-.5]*3+[-speed_box] if count==4 else [-.5]*3+[-3.,-speed_box]+([-max_epoch_shift_days] if max_epoch_shift_days else []))
        upper.extend([.5]*3+[speed_box] if count==4 else [.5]*3+[3.,speed_box]+([max_epoch_shift_days] if max_epoch_shift_days else []))
        if i==0:
            mu=BODIES[node['body']][1];speed2=float(node['peri_out_velocity']@node['peri_out_velocity']-2*mu/node['rp'])
            floor=max(5.,config.get('effective_min_c3',config.get('min_c3',5.)))
            lower[-1]=max(lower[-1],.5*np.log(floor/speed2))
            upper[-1]=min(upper[-1],.5*np.log(min(config['max_c3'],candidate.get('effective_max_c3',config['max_c3']))/speed2))
            if not lower[-1]<=0<=upper[-1]:return nodes,{},dict(applied=False,reason='Source launch energy is outside requested bounds')
        elif terminal:
            mu=BODIES[node['body']][1];speed=np.sqrt(node['peri_in_velocity']@node['peri_in_velocity']-2*mu/node['rp'])
            upper[-1]=min(upper[-1],np.log(config.get('max_arrival_vinf_kms',float('inf'))/speed))
    dsms={b['leg_index']:b for b in candidate['dsms']};dsm_indices={}
    for leg in dsms:dsm_indices[leg]=size;size+=3;lower.extend([-10.]*3);upper.extend([10.]*3)
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
            if count==4:rp=old['rp'];speed_factor=np.exp(values[3]);date=old['date']
            else:
                minimum=BODIES[old['body']][2]+config['minimum_altitude_km'].get(old['body'],BODIES[old['body']][3])
                if old['rp']<minimum-1e-6:raise ValueError('Original periapsis is below the requested floor')
                # A positive clearance parameter prevents an optimizer step below the floor.
                rp=minimum+max(1e-3,old['rp']-minimum)*np.exp(values[3]);speed_factor=np.exp(values[4]);date=old['date']+(values[5] if count==6 else 0.)
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
    best=[baseline,initial.copy()];best_feasible=[float('inf'),None];calls=[0]
    single_cap=config.get('max_single_dsm_kms',float('inf'));total_cap=config.get('max_dsm_kms',float('inf'))
    def remember(x,gaps,burns,peri):
        cost=float(sum(np.linalg.norm(v) for v in gaps+burns)+peri)
        if cost<best[0]:best[:]=[cost,x.copy()]
        peak=max((np.linalg.norm(v) for v in gaps+burns),default=0.)
        if peak<=single_cap+1e-9 and cost<=total_cap+1e-9 and cost<best_feasible[0]:best_feasible[:]=[cost,x.copy()]
        calls[0]+=1
        if calls[0]%250==0:status(f'Matching finite flyby patches: {min(best_feasible[0],best[0])*1000:.1f} m/s total cruise impulses so far…')
        return cost
    remember(initial,g0,b0,p0)
    length=3*(len(g0)+len(b0))+size
    def residual(x):
        try:
            gaps,burns,peri=evaluate(x);remember(x,gaps,burns,peri)
            return np.r_[np.concatenate(gaps)/.001,np.concatenate([v-w for v,w in zip(burns,wanted)])/.1 if burns else [],x*.001]
        except (ValueError,RuntimeError,AssertionError,FloatingPointError):return np.full(length,1e6)+np.linalg.norm(x)
    status('Matching finite flyby geometry and preceding coasts; no new DSM epochs…')
    # Start inside the proven two-day neighborhood. Enlarging a window must not
    # discard a cheaper narrow-window solution just because the local fit moved.
    narrow_lower=np.array(lower,float);narrow_upper=np.array(upper,float)
    if max_epoch_shift_days>2:
        for i,offset,count in descriptors:
            if count==6:narrow_lower[offset+5]=-2.;narrow_upper[offset+5]=2.
    fit=least_squares(residual,initial,bounds=(narrow_lower,narrow_upper),max_nfev=max_nfev,diff_step=1e-5,ftol=1e-9,xtol=1e-9,gtol=1e-9)
    residual(fit.x)
    # Match-only least squares can reduce gaps by making the DSM more expensive.
    # Follow it with explicit sum-of-impulses minimization and physical burn caps.
    def objective(x):
        try:
            gaps,burns,peri=evaluate(x);remember(x,gaps,burns,peri)
            return float(sum(np.sqrt(v@v+1e-10) for v in gaps+burns)+peri+1e-10*(x@x))
        except (ValueError,RuntimeError,AssertionError,FloatingPointError):return 1e6+float(x@x)
    def margins(x):
        try:
            gaps,burns,peri=evaluate(x);cost=sum(np.linalg.norm(v) for v in gaps+burns)+peri
            return np.array([cap-value for cap,value in [(single_cap,max((np.linalg.norm(v) for v in gaps+burns),default=0.)),(total_cap,cost)] if np.isfinite(cap)])
        except (ValueError,RuntimeError,AssertionError,FloatingPointError):return np.full(sum(np.isfinite(v) for v in [single_cap,total_cap]),-1e3)
    cost_stages=[]
    for lo,hi in [(narrow_lower,narrow_upper)]+([(lower,upper)] if max_epoch_shift_days>2 else []):
        start=best_feasible[1] if best_feasible[1] is not None else best[1]
        scale=np.ones(size)
        for i,offset,count in descriptors:
            if count==6:scale[offset+5]=max(1.,min(30.,hi[offset+5]))
        cost_fit=minimize(lambda z:objective(z*scale),start/scale,method='SLSQP',bounds=list(zip(np.asarray(lo)/scale,np.asarray(hi)/scale)),
            constraints=[dict(type='ineq',fun=lambda z:margins(z*scale))] if np.isfinite(single_cap) or np.isfinite(total_cap) else [],
            options=dict(maxiter=max_nfev,ftol=1e-8,eps=1e-4))
        objective(cost_fit.x*scale);cost_stages.append(dict(success=bool(cost_fit.success),message=str(cost_fit.message),best_feasible_kms=best_feasible[0] if best_feasible[1] is not None else None))
    # Include the final optimizer point; only adopt a demonstrably cheaper variant.
    residual(fit.x);final_gaps,final_burns,final_peri=evaluate(fit.x)
    winner=best_feasible if best_feasible[1] is not None and best_feasible[0]<baseline else best
    polish_report=None
    if best_feasible[1] is not None:
        pg,pb,pp=evaluate(winner[1]);patch_cost=float(sum(np.linalg.norm(v) for v in pg))
        if patch_cost>.01:
            # Improve continuity only inside the already achieved total budget.
            # This avoids trading a cosmetic patch reduction for an expensive DSM.
            polish_budget=float(winner[0]);total_cap=min(total_cap,polish_budget+1e-7)
            polished=[patch_cost,float(winner[0]),winner[1].copy()]
            def patch_objective(z):
                x=z*scale
                try:
                    gaps,burns,peri=evaluate(x);cost=float(sum(np.linalg.norm(v) for v in gaps+burns)+peri)
                    patch=float(sum(np.linalg.norm(v) for v in gaps));peak=max((np.linalg.norm(v) for v in gaps+burns),default=0.)
                    if cost<=polish_budget+1e-7 and peak<=single_cap+1e-9 and patch<polished[0]:polished[:]=[patch,cost,x.copy()]
                    calls[0]+=1
                    if calls[0]%250==0:status(f'Polishing patch continuity within {polish_budget*1000:.1f} m/s cruise budget: {polished[0]*1000:.1f} m/s corrections…')
                    return float(sum(np.sqrt(v@v+1e-10) for v in gaps)+.001*sum(np.sqrt(v@v+1e-10) for v in burns))
                except (ValueError,RuntimeError,AssertionError,FloatingPointError):return 1e6+float(x@x)
            polish=minimize(patch_objective,winner[1]/scale,method='SLSQP',bounds=list(zip(np.asarray(lower)/scale,np.asarray(upper)/scale)),
                constraints=[dict(type='ineq',fun=lambda z:margins(z*scale))],options=dict(maxiter=max_nfev,ftol=1e-8,eps=1e-4))
            patch_objective(polish.x)
            winner=[polished[1],polished[2]]
            polish_report=dict(success=bool(polish.success),message=str(polish.message),total_budget_ceiling_kms=polish_budget,
                               patch_before_kms=patch_cost,patch_after_kms=polished[0])
    chosen=winner[1];applied=bool(winner[0]<baseline-1e-6)
    result,points=decode(chosen,numerical=True) if applied else (nodes,{})
    gaps,burns,peri=evaluate(chosen)
    report=dict(applied=applied,reason='Lower explicit cruise budget' if applied else 'No lower-budget local match found',
        baseline_cruise_delta_v_kms=baseline,matched_cruise_delta_v_kms=winner[0],evaluations=calls[0],
        remaining_patch_delta_v_kms=float(sum(np.linalg.norm(v) for v in gaps)),
        maximum_patch_burn_kms=float(max((np.linalg.norm(v) for v in gaps),default=0.)),
        matched_dsm_delta_v_kms=float(sum(np.linalg.norm(v) for v in burns)),
        final_solver_patch_delta_v_kms=float(sum(np.linalg.norm(v) for v in final_gaps)),
        final_solver_cruise_delta_v_kms=float(sum(np.linalg.norm(v) for v in final_gaps+final_burns)+final_peri),
        scipy_success=bool(fit.success),scipy_message=str(fit.message),maximum_periapsis_epoch_shift_days=float(max_epoch_shift_days),
        cost_optimizer_success=bool(cost_fit.success),cost_optimizer_message=str(cost_fit.message),
        cost_optimizer_stages=cost_stages,
        continuity_polish=polish_report,
        cost_objective='Sum of actual DSM, periapsis and finite-patch vector impulse magnitudes; individual DSM/patch and total cruise caps constrained',
        parameter_schema=[dict(node_index=i,offset=offset,count=count) for i,offset,count in descriptors],
        parameter_values=chosen.tolist(),
        changes=[dict(body=n['body'],source_jd_tdb=o['date'],exported_jd_tdb=n['date'],date=calendar(n['date']),
                      epoch_shift_days=n['date']-o['date'],source_altitude_km=o['altitude'],exported_altitude_km=n['altitude'])
                 for o,n in zip(nodes,result)],
        note='Local finite-SOI matching, not a global minimum. Source candidate is unchanged. Remaining velocity gaps are explicit burns, not hidden or erased.')
    return result,points,report
