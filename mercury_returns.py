"""Resonance-informed guesses, not imposed resonances or certified transfers."""
import bootstrap  # noqa: F401
import numpy as np

MERCURY_YEAR_DAYS=87.9691


def seed_returns(samples,model,branches,rng):
    if not model.config.get('mercury_resonant_seeds',True) or model.config.get('event_windows_jd'):
        return 0
    affected=False
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
