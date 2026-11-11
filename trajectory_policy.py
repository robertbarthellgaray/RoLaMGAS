"""Search defaults and public-library policy, not physical feasibility limits."""
DEFAULT_VENUS_OUTER_C3=30.
OUTER_PLANETS={'Jupiter','Saturn','Uranus','Neptune','599','699','799','899'}

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
