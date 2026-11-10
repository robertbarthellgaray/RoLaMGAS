"""Resonance-informed guesses, not imposed resonances or certified transfers."""
import bootstrap  # noqa: F401
import numpy as np

MERCURY_YEAR_DAYS=87.9691


def branch_options(maximum_days=750.):
    """Outer resonant returns need more than two complete solar revolutions."""
    maximum=min(8,max(0,int(float(maximum_days)/MERCURY_YEAR_DAYS)))
    return [[0,True]]+[[m,low] for m in range(1,maximum+1) for low in (True,False)]


def coherent_families(route):
    """Prioritize MESSENGER-like 2/3, 3/4, 5/6 revolution ladders.

    Lambert M is the number of complete solar revolutions, not the number of
    Mercury years. Both neighboring M values and both paths are tried because
    an encounter can lie just before or just after an exact orbital return.
    Explicit user branch restrictions are respected.
    """
    legs=[i for i,(a,b) in enumerate(zip(route["bodies"],route["bodies"][1:])) if a==b=="Mercury"]
    if not legs:return []
    families=[]
    for decrement,low in ((0,True),(1,True),(0,False),(1,False)):
        family=[list(opts[0]) for opts in route["branch_options"]]
        for index,leg in enumerate(legs):
            years=(3,4,6)[index] if index<3 else min(8,index+4)
            m=years-1-decrement
            options=route["branch_options"][leg]
            preferred=next((list(b) for b in options if b[0]==m and b[1]==low),None)
            if preferred is None:
                preferred=list(min(options,key=lambda b:(abs(b[0]-m),b[1]!=low)))
            family[leg]=preferred
        if family not in families:families.append(family)
    return families


def seed_returns(samples,model,branches,rng):
    if not model.config.get('mercury_resonant_seeds',True) or model.config.get('event_windows_jd'):
        return 0
    affected=False
    return_index=0
    count=max(1,len(samples)//2)
    for i,(a,b) in enumerate(zip(model.bodies,model.bodies[1:])):
        if a!=b or a!='Mercury':continue
        lo,hi=model.route['leg_days'][i]
        m=int(branches[i][0])
        # For M complete revolutions, favor returns after M+1 or M+2 Mercury
        # years, admitting an orbit with a period longer than Mercury's.
        choices=[k*MERCURY_YEAR_DAYS for k in (m+1,m+2,m+3) if lo+2<k*MERCURY_YEAR_DAYS<hi-2]
        if not choices:continue
        duration=rng.choice(choices,count)+rng.normal(0.,1.5,count)
        years=(3,4,6)[return_index] if return_index<3 else min(8,return_index+4)
        preferred=years*MERCURY_YEAR_DAYS
        if any(abs(preferred-v)<1e-6 for v in choices):
            coherent=max(1,count//2)
            duration[:coherent]=preferred+rng.normal(0.,.35,coherent)
        return_index+=1
        samples[:count,i+1]=np.clip((duration-lo)/(hi-lo),1e-6,1-1e-6)
        affected=True
    return count if affected else 0


def return_diagnostics(bodies,dates,branches):
    rows=[]
    for i,(a,b) in enumerate(zip(bodies,bodies[1:])):
        if a==b=='Mercury':
            days=dates[i+1]-dates[i];years=days/MERCURY_YEAR_DAYS
            rows.append(dict(leg_index=i,duration_days=float(days),mercury_years=float(years),
                             nearest_integer_return=int(round(years)),lambert_revolutions=int(branches[i][0]),
                             note='Diagnostic only; a resonant seed does not establish flyby feasibility or capture'))
    return rows


def verified_resonant_seeds(config,routes,ephemerides):
    """Rebuild stored physical starters; never reuse a stale pass flag."""
    import json,time
    from app_paths import RESOURCE_ROOT
    from community import record_variables
    from dynamics import Model
    path=RESOURCE_ROOT/'departure_seeds/resonant_chains.json'
    stats=dict(mapped=0,rejected=0,accepted=0);accepted=[]
    if not config.get('historical_mission_seeds',True) or not path.exists():
        return dict(accepted=accepted,stats=stats)
    records=json.loads(path.read_text(encoding='utf-8'))['records']
    for route in routes:
        model=Model(route,config,ephemerides)
        for record in records:
            if record['sequence']!=route['id']:continue
            if 'Mercury' in model.bodies and not config.get('mercury_resonant_seeds',True):continue
            if 'Mercury' not in model.bodies and not config.get('earth_return_seeds',True):continue
            stats['mapped']+=1
            try:
                x,branches=record_variables(record,model)
                # Only the launch leg is evaluated outside the allowed energy.
                if not model.c3_in_bounds(model.launch_c3(x,branches)):
                    stats['rejected']+=1;continue
                q=model.evaluate(x,branches)
                if not model.accepted(q):stats['rejected']+=1;continue
            except (ValueError,KeyError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):
                stats['rejected']+=1;continue
            q.update(status='passes_configured_patched_conic_screen',discovered_unix=time.time(),
                     screening_residual_norm=float(np.linalg.norm(model.residual(x,branches))),
                     reused_from=dict(library='bundled_resonant_chains',candidate=record['id'],revalidated=True))
            accepted.append(q);stats['accepted']+=1
    return dict(accepted=accepted,stats=stats)


def preferred_resonant_branch(config,route):
    """Schedule a compatible stored branch even with one branch-family slot."""
    import json
    from app_paths import RESOURCE_ROOT
    from community import record_variables
    from dynamics import Model
    if not config.get('historical_mission_seeds',True) or config.get('local_refinement'):return None
    if 'Mercury' in route['bodies'] and not config.get('mercury_resonant_seeds',True):return None
    if 'Mercury' not in route['bodies'] and not config.get('earth_return_seeds',True):return None
    path=RESOURCE_ROOT/'departure_seeds/resonant_chains.json'
    if not path.exists():return None
    model=Model(route,config,None)
    for record in json.loads(path.read_text(encoding='utf-8'))['records']:
        if record['sequence']!=route['id']:continue
        if not model.c3_in_bounds(record['metrics']['launch_c3_km2_s2']):continue
        try:_,branches=record_variables(record,model)
        except (ValueError,KeyError):continue
        return [list(b) for b in branches]
    return None
