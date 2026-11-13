"""Search defaults and public-library policy, not physical feasibility limits."""
DEFAULT_VENUS_OUTER_C3=30.
OUTER_PLANETS={'Jupiter','Saturn','Uranus','Neptune','599','699','799','899'}
SMALL_BODY_MAX_YEARS=40.
SMALL_BODY_HIGH_C3=170.
SMALL_BODY_HIGH_C3_MAX_YEARS=25.


def public_small_body_reason(record):
    ids=record.get('body_ids',[]);dates=record.get('dates_jd_tdb',[])
    if len(ids)<2 or len(dates)!=len(ids):return None
    target=int(ids[-1]);years=(dates[-1]-dates[0])/365.25
    if target not in (9,999) and target<1000:return None
    if years>=SMALL_BODY_MAX_YEARS:return 'Small-body flight time must be below 40 years.'
    if record['metrics']['launch_c3_km2_s2']>SMALL_BODY_HIGH_C3 and years>=SMALL_BODY_HIGH_C3_MAX_YEARS:
        return 'Small-body flights above C3 170 must take less than 25 years.'
    return None

def venus_outer_route(bodies):
    values=list(map(str,bodies))
    return any(body in ('Venus','299') for body in values[1:-1]) and any(body in OUTER_PLANETS for body in values[1:])

def c3_ceiling(bodies,config):
    ceiling=float(config['max_c3']);venus=config.get('max_venus_c3',DEFAULT_VENUS_OUTER_C3)
    return min(ceiling,float(venus)) if venus is not None and venus_outer_route(bodies) else ceiling

def public_energy_reason(record):
    energy=record.get('metrics',{}).get('launch_c3_km2_s2',record.get('c3'))
    if energy is not None and energy>DEFAULT_VENUS_OUTER_C3+1e-8 and venus_outer_route(record.get('body_ids',record.get('bodies',[]))):
        return 'Venus-assisted outer-planet example exceeds the public C3 ceiling of 30 km2/s2.'
    return None
