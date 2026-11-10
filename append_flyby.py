"""Append encounters while preserving the selected cruise; point-target turns are explicit burns."""
import bootstrap  # noqa: F401
from copy import deepcopy
import math
import numpy as np
from ephemeris import BODIES


def original_target_descriptors(config):
    """Resolved identities for all nonplanet encounters already in the cruise."""
    extension=config.get('append_flyby') or {}
    values=list(extension.get('original_target_objects') or [])
    values.extend([extension.get('original_target_object'),config.get('target_object')])
    result={}
    for value in values:
        if value is None:continue
        if not isinstance(value,dict) or not value.get('name') or not value.get('id'):
            raise ValueError('The original resolved Horizons target identity is incomplete')
        name=value['name']
        if name in result and str(result[name]['id'])!=str(value['id']):
            raise ValueError('Conflicting original Horizons identities for '+name)
        result[name]=deepcopy(value)
    return list(result.values())


def extension_request(config,route,candidate,parent_run,body=None,count=1,minimum_days=80.,maximum_days=750.,dsm=False,target_object=None):
    if not isinstance(dsm,bool):raise ValueError('New-leg DSM option must be boolean')
    if isinstance(count,bool) or int(count)!=count or not 1<=count<=3:
        raise ValueError('Add one to three encounters at a time')
    count=int(count)
    if target_object is not None:
        from horizons_targets import register_target,moon_model_notice
        register_target(target_object)
        notice=moon_model_notice(target_object)
        if notice:raise ValueError(notice)
        body=target_object['name']
    else:
        body=str(body or candidate['bodies'][-1]).strip().title()
        if body not in BODIES:
            raise ValueError('Resolve a Horizons object or choose a supported planet for the next encounter')
    descriptors=original_target_descriptors(config)
    prefix_names={b for b in candidate['bodies'] if b not in BODIES}
    originals=[d for d in descriptors if d['name'] in prefix_names]
    if {d['name'] for d in originals}!=prefix_names:
        raise ValueError('A follow-on from a minor body requires a confirmed original Horizons identity for every frozen target')
    point_turn=candidate['bodies'][-1] not in BODIES
    original_target=next((d for d in originals if d['name']==candidate['bodies'][-1]),originals[0] if originals else None)
    minimum_days,maximum_days=float(minimum_days),float(maximum_days)
    if not all(math.isfinite(v) for v in (minimum_days,maximum_days)) or not 0<minimum_days<maximum_days<=10000:
        raise ValueError('New leg timing requires 0 < minimum < maximum <= 10000 days')
    codes=dict(Earth='E',Venus='V',Mars='M',Mercury='Me',Jupiter='J',Saturn='S',Uranus='U',Neptune='N')
    n0=len(candidate['bodies']);n=n0+count
    dsms=list(route.get('dsm_legs',[]))
    if dsm:dsms+=list(range(n0-1,n-1))
    sequence=candidate['sequence']+('dv' if dsm else '')+codes.get(body,'X')
    for _ in range(count-1):sequence+=('dv' if dsm else '')+codes.get(body,'X')
    branches=[[list(b)] for b in candidate['branches']]
    bodies=list(candidate['bodies'])+[body]*count
    for a,b in zip(bodies[n0-1:],bodies[n0:]):
        max_m=(4 if b=='Mercury' else 2) if a==b else (1 if a in ('Mercury','Venus') and b in ('Mercury','Venus','Earth') else 0)
        if a==b=='Mercury':
            from mercury_returns import branch_options
            branches.append(branch_options(maximum_days))
        else:branches.append([[0,True]]+[[m,low] for m in range(1,max_m+1) for low in (True,False)])
    new_route=dict(id=sequence,bodies=bodies,target=body,dsm_legs=dsms,
        leg_days=deepcopy(route['leg_days'])+[[minimum_days,maximum_days] for _ in range(count)],
        branch_options=branches,provenance='Appended encounters; selected earlier cruise and dates frozen')
    request=deepcopy(config)
    for key in ('launch_jd','event_windows_jd','event_windows','local_refinement','append_flyby','arrival_date','arrival_window_jd','arrival_tolerance_days'):
        request.pop(key,None)
    seed=list(candidate['x'][:n0])+[.5]*count+list(candidate['x'][n0:])
    if dsm:seed += [.5,.5,.5,.5]*count
    if len(seed)!=n+4*len(dsms):raise ValueError('Saved candidate DSM controls differ from its route')
    for key in ('max_single_dsm_kms','max_powered_flyby_kms'):
        request.setdefault(key,config['max_dsm_kms'])
    request.update(target=body,target_object=deepcopy(target_object),sequences=[sequence],route_overrides={},search_objective='dsm' if point_turn else 'arrival',
                   seed=int(config.get('seed',502))+1,mercury_resonant_seeds=True)
    # A full snapshot preserves even a tolerated original v-infinity mismatch;
    # no hidden rewrite of earlier Lambert legs or DSM vectors is permitted.
    request['append_flyby']=dict(parent_run=parent_run,parent_candidate=candidate['id'],
        prefix=deepcopy(candidate),prefix_count=n0,route=new_route,seed_x=seed,
        new_body=body,added_encounters=count,new_leg_dsm=dsm,
        original_target_object=original_target,original_target_objects=originals,point_target_turnaround=point_turn,
        reference_arrival_vinf_kms=candidate['arrival_vinf_kms'])
    return request


def validate_extension(value,config):
    if not isinstance(value,dict):raise ValueError('Invalid append-flyby configuration')
    prefix=value.get('prefix',{});route=value.get('route',{})
    n0=len(prefix.get('bodies',[]));n=len(route.get('bodies',[]))
    if n0<2 or not 1<=n-n0<=3 or value.get('prefix_count')!=n0:
        raise ValueError('Invalid frozen prefix size')
    next_object=config.get('target_object')
    allowed_new=set(BODIES)|({next_object['name']} if next_object else set())
    if route['bodies'][:n0]!=prefix['bodies'] or any(b not in allowed_new for b in route['bodies'][n0:]):
        raise ValueError('Appended route changes the original bodies or adds an unsupported target')
    unsupported={b for b in route['bodies'][:n0] if b not in BODIES}
    originals=original_target_descriptors(config)
    by_name={d['name']:d for d in originals}
    if not unsupported.issubset(by_name):
        raise ValueError('The frozen nonplanet encounters need their original resolved Horizons identities')
    from horizons_targets import register_target,moon_model_notice
    for body in unsupported:
        descriptor=by_name[body]
        notice=moon_model_notice(descriptor)
        if notice:raise ValueError(notice)
        register_target(descriptor)
    if config['sequences']!=[route['id']] or route['target']!=config['target']:
        raise ValueError('Appended route and destination differ')
    dates=prefix.get('dates_jd_tdb',[])
    if len(dates)!=n0 or not all(math.isfinite(t) for t in dates) or min(np.diff(dates))<=0:
        raise ValueError('Invalid frozen encounter dates')
    seed=value.get('seed_x',[])
    if len(seed)!=n+4*len(route.get('dsm_legs',[])) or not all(math.isfinite(v) and 0<=v<=1 for v in seed):
        raise ValueError('Invalid appended search seed')
    for options,branch in zip(route['branch_options'][:n0-1],prefix['branches']):
        if options!=[branch]:raise ValueError('Original Lambert branches must remain fixed')


def return_root_seeds(model,branches):
    """Bracket narrow one-leg speed matches that ordinary random starts miss."""
    if not model.extension:return []
    # A zero-GM point encounter has no natural speed-matching flyby resonance.
    if model.bodies[model.prefix_count-1] not in BODIES:return []
    if len(model.free_indices)!=1:
        # A zero-DSM resonant return is also a useful starting point for the
        # optional burn search. Put the burn late enough that its remaining
        # Lambert subarc has zero complete revolutions, as that model requires.
        if model.n-model.prefix_count!=1:return []
        new_dsms=[i for i,leg in enumerate(model.dsm_legs) if leg>=model.prefix_count-1]
        if not new_dsms:return []
        from dynamics import Model
        config=deepcopy(model.config);route=deepcopy(model.route)
        old_indices=[i for i,leg in enumerate(model.dsm_legs) if leg<model.prefix_count-1]
        route['dsm_legs']=[model.dsm_legs[i] for i in old_indices]
        seed=config['append_flyby']['seed_x']
        seed=seed[:model.n]+[seed[model.n+4*i+j] for i in old_indices for j in range(4)]
        config['append_flyby']['route']=route;config['append_flyby']['seed_x']=seed
        coast=Model(route,config,model.ep);result=[]
        for root in return_root_seeds(coast,branches):
            x=np.asarray(model.extension['seed_x'],dtype=float)
            x[model.n-1]=root[model.n-1]
            for i in new_dsms:x[model.n+4*i:model.n+4*i+4]=[.99,.5,.5,.5]
            try:
                q=model.evaluate(x,branches)
                if model.accepted(q,allow_arrival_overrun=True):result.append(q['x'])
            except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError):pass
        return result
    from scipy.optimize import brentq
    from functools import lru_cache
    index=int(model.free_indices[0]);lo,hi=model.route['leg_days'][-1]
    days=list(np.linspace(lo+1e-7,hi-1e-7,385))
    if model.bodies[-2:]==['Mercury','Mercury']:
        from mercury_returns import MERCURY_YEAR_DAYS
        # Planet-center Lambert geometry is exceptionally narrow near an exact
        # return. Resolve seconds/minutes about integer Mercury years as well.
        offsets=np.r_[0.,*[sign*10.**power for power in range(-6,1) for sign in (-1,1)]]
        for k in range(1,int(hi/MERCURY_YEAR_DAYS)+1):
            days.extend(k*MERCURY_YEAR_DAYS+offsets)
    grid=np.unique([(t-lo)/(hi-lo) for t in days if lo<t<hi])
    @lru_cache(maxsize=128)
    def evaluate(z):
        x=model.expand_variables([z]);q=model.evaluate(x,branches)
        f=q['flybys'][-1]
        return f['vinf_out_kms']-f['vinf_in_kms'],q
    seeds=[];previous=None
    for z in grid:
        try:error,q=evaluate(float(z))
        except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError):previous=None;continue
        if previous and error*previous[1]<=0:
            try:
                root=brentq(lambda x:evaluate(float(x))[0],previous[0],float(z),xtol=1e-13)
                mismatch,q=evaluate(float(root))
                if abs(mismatch)<.0001 and all(abs(root-p[index])>1e-8 for p in seeds):seeds.append(q['x'])
            except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError):pass
        previous=float(z),error
    seeds.sort(key=lambda x:float(np.linalg.norm(model.residual(x,branches))))
    return seeds
