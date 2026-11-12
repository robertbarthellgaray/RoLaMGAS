"""Soft outer-planet approach preferences, separate from feasibility and fuel."""
import math
import numpy as np
from ephemeris import MU_SUN,DAY

OUTER_PLANETS=frozenset(('Jupiter','Saturn','Uranus','Neptune'))


def first_outward_crossing_seconds(r,v,radius,duration):
    """First outward crossing of a fixed solar radius on an elliptic coast.

    This is a radius crossing, not an earlier encounter with the moving planet.
    Unbound/circular coasts return None; their endpoint radial motion still works.
    """
    r=np.asarray(r,float);v=np.asarray(v,float);r0=float(np.linalg.norm(r))
    energy=float(v@v/2-MU_SUN/r0)
    if energy>=0:return None
    a=-MU_SUN/(2*energy);evec=np.cross(v,np.cross(r,v))/MU_SUN-r/r0
    e=float(np.linalg.norm(evec))
    if e<1e-9 or e>=1:return None
    cosine=(1-radius/a)/e
    if not -1-1e-9<=cosine<=1+1e-9:return None
    crossing=math.acos(float(np.clip(cosine,-1,1)))
    start=math.atan2(float(r@v)/(e*math.sqrt(MU_SUN*a)),(1-r0/a)/e)
    mean_start=start-e*math.sin(start);mean_cross=crossing-e*math.sin(crossing)
    rate=math.sqrt(MU_SUN/a**3);phase=(mean_cross-mean_start)%(2*math.pi)
    # A tiny negative roundoff at an outward starting point must not add a lap.
    if abs(radius-r0)<1e-5 and r@v>=0:phase=0.
    seconds=phase/rate
    return seconds if seconds<=duration+1e-2 else None


def outer_approaches(bodies,dates,states,arrivals,segments,frozen_encounters=1):
    rows=[]
    for i,body in enumerate(bodies[1:],1):
        if body not in OUTER_PLANETS:continue
        r=np.asarray(states[i][:3]);v=np.asarray(arrivals[i-1]);radius=float(np.linalg.norm(r))
        # Deliberate inward transfers (e.g. Neptune -> Jupiter) are not detours.
        outward_transfer=radius>float(np.linalg.norm(states[i-1][:3]))+1.
        radial=float(r@v/radius)
        direction='outward' if radial>1e-6 else 'inward' if radial< -1e-6 else 'near apsis'
        first=None
        if outward_transfer:
            for s in segments:
                if s['start_jd']<dates[i-1]-1e-7 or s['end_jd']>dates[i]+1e-7:continue
                elapsed=first_outward_crossing_seconds(s['r'],s['v'],radius,(s['end_jd']-s['start_jd'])*DAY)
                if elapsed is not None:
                    first=s['start_jd']+elapsed/DAY;break
        delay=max(0.,dates[i]-first) if first is not None else 0.
        if delay<1e-4:delay=0.
        eligible=outward_transfer and i>=frozen_encounters
        rows.append(dict(body=body,event_index=i,julian_date_tdb=float(dates[i]),
            heliocentric_radial_velocity_kms=radial,direction=direction,
            first_outward_radius_crossing_jd=first,days_after_first_outward_radius_crossing=delay,
            outward_transfer=outward_transfer,preference_eligible=eligible,
            normalized_detour_penalty=(delay/365.25+max(0.,-radial)/5.) if eligible else 0.))
    return rows


def preference_penalty(q,config):
    if not config.get('prefer_outbound_encounters',True):return 0.
    return float(sum(row['normalized_detour_penalty'] for row in q.get('outer_approaches',[])))


def first_outer_years(q):
    dates=q.get('dates_jd_tdb',[])
    for row in q.get('outer_approaches',[]):
        if row.get('preference_eligible') and dates:return (row['julian_date_tdb']-dates[0])/365.25
    return q['duration_years']
