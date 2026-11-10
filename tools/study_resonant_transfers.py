"""Offline resonance review and optional fixed-prefix Mercury-return search.

Run from source: python tools/study_resonant_transfers.py --output runs/resonance_review
Add a return: ... --extend-candidate path/to/candidate.json --dsm-per-return-mps 350
Uses the local JPL cache and local CPU. No AI or community API is called.
"""
from pathlib import Path
import argparse,csv,hashlib,json,math,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import differential_evolution,minimize
from dynamics import Model,kepler,lambert
from ephemeris import AU,DAY,MU_SUN,BODIES,Ephemerides,atomic_json,jd
from mission_search import normalize,routes_for
from mercury_returns import verified_resonant_seeds
ROOT=Path(__file__).resolve().parents[1]


def two_year_earth_limit():
    """Ideal circular, coplanar Earth; exact perihelion launch and 2-year return."""
    earth_speed=math.sqrt(MU_SUN/AU)
    axis=2**(2/3)*AU
    departure=math.sqrt(MU_SUN*(2/AU-1/axis))
    jupiter_departure=math.sqrt(MU_SUN*(2/AU-2/(AU+5.2*AU)))
    return dict(model='Circular Earth at 1 AU; exact prograde perihelion departure',
                semimajor_axis_au=axis/AU,aphelion_au=2*axis/AU-1,
                earth_speed_kms=earth_speed,departure_speed_kms=departure,
                launch_vinf_kms=departure-earth_speed,c3_km2_s2=(departure-earth_speed)**2,
                maximum_post_flyby_speed_kms=departure,
                jupiter_hohmann_departure_speed_kms=jupiter_departure,
                jupiter_hohmann_c3_km2_s2=(jupiter_departure-earth_speed)**2,
                explanation='Incoming excess velocity is already parallel to Earth motion. Rotating it cannot increase heliocentric speed. Nearby non-perihelion geometries require their own feasibility search.')


def outgoing_flyby(incoming,mu,periapsis,beta,hint):
    """An unpowered turn: exactly preserve speed and respect the chosen radius."""
    incoming=np.asarray(incoming,float);u=float(np.linalg.norm(incoming))
    if not math.isfinite(u) or u<=1e-10 or not math.isfinite(mu) or mu<=0 or not math.isfinite(periapsis) or periapsis<=0:raise ValueError('A finite nonzero flyby speed and positive GM/periapsis are required')
    axis=incoming/u
    transverse=np.cross(axis,hint)
    if np.linalg.norm(transverse)<1e-10:transverse=np.cross(axis,np.eye(3)[np.argmin(abs(axis))])
    transverse/=np.linalg.norm(transverse);other=np.cross(axis,transverse)
    angle=2*math.asin(1/(1+periapsis*u*u/mu))
    return incoming*math.cos(angle)+u*(transverse*math.cos(beta)+other*math.sin(beta))*math.sin(angle)


def physical_record(q,config):
    controls=[];n=len(q['bodies'])
    for j,burn in enumerate(q['dsms']):
        k=n+4*j
        controls.append(dict(leg_index=burn['leg_index'],fraction=.1+.8*q['x'][k],
                             departure_offset_kms=((np.array(q['x'][k+1:k+4])*2-1)*config['dsm_velocity_box_kms']).tolist()))
    return dict(schema_version=1,sequence=q['sequence'],body_ids=[str(BODIES[b][0]) for b in q['bodies']],
                dates_jd_tdb=q['dates_jd_tdb'],branches=q['branches'],dsm_controls=controls,
                segments=q['segments'],metrics={k:q[k] for k in ('launch_c3_km2_s2','total_dsm_kms','arrival_vinf_kms','duration_years')})


def audit_coasts(q):
    """Independent DOP853 integration of every declared Sun-only arc."""
    maximum=0.;velocity=0.
    for i,segment in enumerate(q['segments']):
        y=np.r_[segment['r'],segment['v']];seconds=(segment['end_jd']-segment['start_jd'])*DAY
        def rhs(t,state):return np.r_[state[3:],-MU_SUN*state[:3]/np.linalg.norm(state[:3])**3]
        fit=solve_ivp(rhs,(0,seconds),y,method='DOP853',rtol=2e-12,atol=np.r_[np.full(3,1e-5),np.full(3,1e-12)])
        if not fit.success:raise ValueError(fit.message)
        event=next((e for e in q['events'] if abs(e['julian_date_tdb']-segment['end_jd'])<1e-8),None)
        expected=event['planet_state_km_kms'][:3] if event else q['segments'][i+1]['r']
        maximum=max(maximum,float(np.linalg.norm(fit.y[:3,-1]-expected)))
        _,analytic_velocity=kepler(y[:3],y[3:],seconds)
        velocity=max(velocity,float(np.linalg.norm(fit.y[3:,-1]-analytic_velocity)))
    return dict(maximum_dop853_endpoint_error_km=maximum,maximum_velocity_difference_kms=velocity,
                passed=maximum<1. and velocity<1e-6,nbody_validated=False)


def configuration(target,sequences):
    return normalize(dict(target=target,sequences=sequences,launch_start='2030-01-01',launch_end='2036-01-01',
                          min_c3=6.25,max_c3=50.,max_dsm_kms=1.5,max_single_dsm_kms=.7,
                          max_arrival_vinf_kms=8.,max_years=18.,vinf_tolerance_mps=.1,cache=str(ROOT/'cache')))


def extend_mercury(parent,parent_config,ep,budget_mps=350.,iterations=300,seed=502):
    """Search one flyby/DSM return with speed conservation built into the variables.

    The earlier cruise stays fixed. The current app DSM model has a zero-revolution
    post-burn Lambert arc; the search obeys that model and charges the full burn.
    This greedy extension is a starter, not a globally optimal resonance ladder.
    """
    from community import record_variables
    if parent['bodies'][-1]!='Mercury':raise ValueError('The selected trajectory must end at Mercury')
    if not math.isfinite(budget_mps) or not 0<budget_mps<=700:raise ValueError('The individual DSM cap must be in (0,700] m/s')
    if not 1<=iterations<=10000:raise ValueError('Iterations must be in [1,10000]')
    budget=budget_mps/1000;interior=max(budget*.99,budget-1e-5)
    t=parent['dates_jd_tdb'][-1];planet=ep.state('Mercury',t);incoming=np.array(parent['arrival_vinf_vector_kms'])
    _,mu,radius,floor=BODIES['Mercury'];floor=max(floor,parent_config.get('minimum_altitude_km',{}).get('Mercury',floor));rmin=radius+floor
    def construct(z):
        days,fraction,logradius,beta=z
        vo=outgoing_flyby(incoming,mu,rmin*math.exp(logradius),beta,planet[3:])
        r,before=kepler(planet[:3],planet[3:]+vo,days*fraction*DAY)
        target=ep.state('Mercury',t+days);after,vf=lambert(r,target[:3],days*(1-fraction),(0,True))
        return float(np.linalg.norm(after-before)),float(np.linalg.norm(vf-target[3:])),vo
    def safe(z):
        try:return construct(z)
        except (ValueError,RuntimeError,AssertionError,ZeroDivisionError,OverflowError):return 1e5,1e5,np.zeros(3)
    best=None
    for years in (3,4,5,6,7):
        bounds=[(years*87.9691-25,years*87.9691+25),(.1,.8999),(0.,math.log(50.)),(-math.pi,math.pi)]
        fit=differential_evolution(lambda z:safe(z)[1]+500*max(safe(z)[0]-interior,0.)**2,bounds,
                                   maxiter=iterations,popsize=16,tol=1e-7,seed=seed+years,polish=False)
        local=minimize(lambda z:safe(z)[1],fit.x,method='SLSQP',bounds=bounds,
                       constraints=[dict(type='ineq',fun=lambda z:interior-safe(z)[0])],options=dict(maxiter=200,ftol=1e-10,eps=1e-6))
        for z in (fit.x,local.x):
            dv,vinf,vo=safe(z)
            if dv<=budget and (best is None or vinf<best[1]):best=(dv,vinf,np.array(z),vo)
        print(f'Return near {years} Mercury years: best feasible arrival {best[1]:.4f} km/s' if best else f'Return near {years} Mercury years: no in-budget match',flush=True)
    if best is None:return None
    dv,vinf,z,vo=best;days,fraction,_,_=z;target=ep.state('Mercury',t+days);choices=[]
    for m in range(9):
        for low in ((True,) if m==0 else (True,False)):
            try:
                va,_=lambert(planet[:3],target[:3],days,[m,low]);choices.append((np.linalg.norm(va-planet[3:]-vo),[m,low],va))
            except (ValueError,RuntimeError,AssertionError,ZeroDivisionError):continue
    if not choices:raise ValueError('No whole-leg Lambert parameterization for the selected return')
    _,branch,va=min(choices,key=lambda item:item[0]);seq=parent['sequence']+'dvMe'
    branches=parent['branches']+[branch];dates=parent['dates_jd_tdb']+[t+days]
    record=physical_record(parent,parent_config);record.update(sequence=seq,body_ids=record['body_ids']+['199'],dates_jd_tdb=dates,branches=branches)
    record['dsm_controls'].append(dict(leg_index=len(parent['bodies'])-1,fraction=float(fraction),departure_offset_kms=(planet[3:]+vo-va).tolist()))
    c=dict(parent_config);c.pop('append_flyby',None);c.pop('local_refinement',None)
    for key in ('event_windows','event_windows_jd','arrival_date','arrival_window_jd','arrival_tolerance_days'):c.pop(key,None)
    c.update(sequences=[seq],target='Mercury',target_object=None,max_dsm_kms=parent['total_dsm_kms']+budget+.001,
             max_years=max(18.,parent['duration_years']+3),max_arrival_vinf_kms=max(15.,parent['arrival_vinf_kms']+.1),
             route_overrides={seq:dict(branch_options=[[b] for b in branches],leg_days=[[max(1,d*.5),d*1.5+1] for d in np.diff(dates)])})
    c=normalize(c);model=Model(routes_for(c)[0],c,ep);x,bb=record_variables(record,model);q=model.evaluate(x,bb)
    if not model.accepted(q):raise ValueError('Forward result did not pass the full-chain model')
    if q['dates_jd_tdb'][:-1]!=parent['dates_jd_tdb']:raise ValueError('Earlier encounter dates changed')
    for before,after in zip(parent['segments'],q['segments']):
        if np.linalg.norm(np.array(before['r'])-after['r'])>.01 or np.linalg.norm(np.array(before['v'])-after['v'])>1e-8:raise ValueError('Earlier coast changed')
    q['id']=hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:12]
    q['status']='passes_configured_patched_conic_screen'
    return q,c


def plot_review(candidates,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    ideal=two_year_earth_limit();fig,ax=plt.subplots(figsize=(8,6))
    theta=np.linspace(0,2*np.pi,800)
    for radius,label in [(1.,'Earth'),(5.2,'Jupiter')]:ax.plot(radius*np.cos(theta),radius*np.sin(theta),'--',label=label,alpha=.6)
    a=ideal['semimajor_axis_au'];ecc=1-1/a;r=a*(1-ecc**2)/(1+ecc*np.cos(theta))
    ax.plot(r*np.cos(theta),r*np.sin(theta),label='2-year ellipse: C3 = 25.79');ax.scatter([0,1],[0,0],c=['gold','dodgerblue'])
    ax.set(xlabel='Ecliptic x (AU)',ylabel='Ecliptic y (AU)',title='Exact perihelion Earth return cannot add energy');ax.axis('equal');ax.legend();fig.tight_layout();fig.savefig(output/'eej_energy_limit.png',dpi=180);plt.close(fig)
    for target in ['Uranus','Mercury']:
        rows=[q for q in candidates if q['bodies'][-1]==target]
        if not rows:continue
        chosen=min(rows,key=lambda q:q['duration_years'] if target=='Uranus' else q['arrival_vinf_kms'])
        fig,axes=plt.subplots(1,2,figsize=(13,5))
        for i,segment in enumerate(chosen['segments']):
            positions=np.array([kepler(np.array(segment['r']),np.array(segment['v']),t)[0]/AU for t in np.linspace(0,(segment['end_jd']-segment['start_jd'])*DAY,700)])
            axes[0].plot(positions[:,0],positions[:,1],linewidth=.9,label='Solar coasts' if i==0 else None)
        axes[0].scatter([0],[0],color='gold',label='Sun');axes[0].axis('equal');axes[0].set(xlabel='Ecliptic x (AU)',ylabel='Ecliptic y (AU)',title=chosen['sequence'])
        for event in chosen['events']:
            x,y=np.array(event['planet_state_km_kms'][:2])/AU;axes[0].scatter([x],[y],s=15)
        axes[0].legend()
        if target=='Uranus':
            rows.sort(key=lambda q:q['duration_years']);axes[1].plot([q['duration_years'] for q in rows],[q['total_dsm_kms']*1000 for q in rows],'o-')
            axes[1].set(xlabel='Flight time (years)',ylabel='Modeled DSM (m/s)',title='Same launch: 27 May 2034; C3 = 23.1')
        else:
            rows.sort(key=lambda q:len(q['events']));axes[1].plot([len(q['events'])-4 for q in rows],[q['arrival_vinf_kms'] for q in rows],'o-')
            for q in rows:axes[1].annotate(f"{q['total_dsm_kms']*1000:.0f} m/s DSM",(len(q['events'])-4,q['arrival_vinf_kms']),xytext=(5,6),textcoords='offset points',fontsize=8)
            axes[1].set(xlabel='Additional Mercury returns',ylabel='Arrival V-infinity (km/s)',title='Original Mercury ladder; capture burn excluded')
        axes[1].grid(alpha=.25);fig.tight_layout();fig.savefig(output/(target.lower()+'_resonant_review.png'),dpi=180);plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'runs/resonance_review');p.add_argument('--cache',type=Path,default=ROOT/'cache')
    p.add_argument('--extend-candidate',type=Path);p.add_argument('--parent-config',type=Path);p.add_argument('--dsm-per-return-mps',type=float,default=350.);p.add_argument('--iterations',type=int,default=300)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    data=json.loads((ROOT/'departure_seeds/resonant_chains.json').read_text(encoding='utf-8'));records=data['records'];candidates=[]
    bodies=['Earth','Venus','Mercury','Uranus'];start=min(r['dates_jd_tdb'][0] for r in records);end=max(r['dates_jd_tdb'][-1] for r in records)+760
    parent=None
    if a.extend_candidate:
        parent=json.loads(a.extend_candidate.read_text(encoding='utf-8'))
        start=min(start,parent['dates_jd_tdb'][0]);end=max(end,parent['dates_jd_tdb'][-1]+760)
        bodies=list(set(bodies+parent['bodies']))
        if any(b not in BODIES for b in bodies):raise ValueError('This study supports planet-only Mercury extensions')
    ep=Ephemerides(a.cache,bodies,start-2,end+2,1.)
    for target in ['Uranus','Mercury']:
        config=configuration(target,list(dict.fromkeys(r['sequence'] for r in records if r['body_ids'][-1]==str(BODIES[target][0]))))
        result=verified_resonant_seeds(config,routes_for(config),ep)
        for q in result['accepted']:
            q['id']=q['reused_from']['candidate'];audit=audit_coasts(q)
            if not audit['passed']:raise ValueError(f"Independent coast audit failed for {q['id']}: {audit}")
            q['coast_audit']=audit;atomic_json(a.output/(q['id']+'.json'),q)
            from search_options import export_options
            document=export_options(config)['document'];document['settings']['sequences']=[q['sequence']];document['trajectory']=physical_record(q,config)
            atomic_json(a.output/(q['id']+'.options.json'),document);candidates.append(q)
            print(q['id'],q['sequence'],f"C3 {q['launch_c3_km2_s2']:.3f}; DSM {1000*q['total_dsm_kms']:.2f} m/s; arrival {q['arrival_vinf_kms']:.4f} km/s; {q['duration_years']:.3f} years",flush=True)
    if a.extend_candidate:
        config=json.loads(a.parent_config.read_text(encoding='utf-8')) if a.parent_config else configuration('Mercury',[parent['sequence']])
        result=extend_mercury(parent,config,ep,a.dsm_per_return_mps,a.iterations)
        if result:
            q,c=result;atomic_json(a.output/(q['id']+'.json'),q);atomic_json(a.output/(q['id']+'.config.json'),c);candidates.append(q)
        else:print('No in-budget Mercury return found. Earlier trajectory is unchanged.',flush=True)
    atomic_json(a.output/'eej_limit.json',two_year_earth_limit());atomic_json(a.output/'verified_candidates.json',candidates)
    plot_review(candidates,a.output)
    keys=['id','sequence','launch_date','arrival_date','duration_years','launch_c3_km2_s2','total_dsm_kms','arrival_vinf_kms']
    with (a.output/'comparison.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');writer.writeheader();writer.writerows(candidates)
    print('Review saved to',a.output.resolve(),flush=True)

if __name__=='__main__':main()
