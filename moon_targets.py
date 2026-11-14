"""Supported local arrival models; JPL SAT441 GM and mean radii.

Source: https://ssd.jpl.nasa.gov/sats/phys_par/ . No spacecraft, drag or
non-spherical surface model is inferred from a Horizons name resolution.
"""
SATURN_MOONS=[
    dict(id='606',name='Titan',gm=8978.13710,radius_km=2574.76,step_days=1/24),
    dict(id='602',name='Enceladus',gm=7.21037,radius_km=252.10,step_days=1/288),
    dict(id='605',name='Rhea',gm=153.94175,radius_km=763.50,step_days=1/96),
    dict(id='604',name='Dione',gm=73.11607,radius_km=561.40,step_days=1/144),
    dict(id='603',name='Tethys',gm=41.21353,radius_km=531.10,step_days=1/288),
    dict(id='608',name='Iapetus',gm=120.51511,radius_km=734.30,step_days=1/24),
    dict(id='601',name='Mimas',gm=2.50349,radius_km=198.20,step_days=1/288),
    dict(id='607',name='Hyperion',gm=.37049,radius_km=135.,step_days=1/24),
    dict(id='609',name='Phoebe',gm=.55479,radius_km=106.50,step_days=1/24),
]

def target_options(parent):
    return [dict(m,parent_body=parent,source='JPL SAT441') for m in SATURN_MOONS] if parent=='Saturn' else []

def validate_options(parent,moon_id,mode,altitude,max_added_mps=700.,effort='standard',inclination_deg=None,target_latitude_deg=None,target_longitude_deg=None):
    import math
    moon=next((m for m in target_options(parent) if m['id']==str(moon_id)),None)
    if moon is None:raise ValueError('Select a supported moon of the final target planet')
    if mode not in ('impact','approach','entry'):raise ValueError('Select impact, closest approach or entry interface')
    if mode=='entry' and moon['name']!='Titan':raise ValueError('Atmospheric entry interface is supported for Titan only')
    altitude=0. if mode=='impact' else float(altitude)
    if not math.isfinite(altitude) or altitude<0 or (mode!='impact' and altitude<=0) or altitude>1e6:
        raise ValueError('Moon approach/entry altitude must be positive and at most 1,000,000 km')
    cap=float(max_added_mps)
    if not math.isfinite(cap) or not 0<cap<=10000:raise ValueError('Added-burn limit must be between 0 and 10,000 m/s')
    if effort not in ('quick','standard'):raise ValueError('Unknown moon targeting effort')
    from arrival_geometry import validate_inclination
    inclination_deg=validate_inclination(inclination_deg)
    if inclination_deg is not None and moon['name']!='Titan':raise ValueError('Equatorial moon-arrival inclination is currently supported for Titan only')
    point=None
    if target_latitude_deg is not None or target_longitude_deg is not None:
        if target_latitude_deg is None or target_longitude_deg is None:raise ValueError('Specify both target latitude and east longitude')
        latitude,longitude=float(target_latitude_deg),float(target_longitude_deg)
        if not math.isfinite(latitude) or not -90<=latitude<=90 or not math.isfinite(longitude):raise ValueError('Target latitude must be -90 to 90 degrees and longitude must be finite')
        if moon['name']!='Titan' or mode=='approach':raise ValueError('Body-fixed point targeting is supported for Titan entry or vacuum impact only')
        if inclination_deg is not None:raise ValueError('Choose a body-fixed target point or an inclination constraint, not both')
        point=dict(latitude_deg=latitude,longitude_east_deg=longitude%360.)
    return dict(parent=parent,moon=moon,mode=mode,altitude_km=altitude,max_added_mps=cap,effort=effort,
                burn_fractions=[.35] if effort=='quick' else [.15,.35,.55],inclination_deg=inclination_deg,target_point=point)

def titan_body_axes(epoch_jd_tdb):
    """ICRF->IAU_TITAN matrix, expressed against Ecliptic J2000 vectors.

    JPL NAIF pck00011.tpc BODY606: pole RA=39.4827, DEC=83.4279;
    prime meridian W=186.5855+22.5769768*d degrees from J2000 noon.
    Rows are the rotating prime-meridian, east and north axes.
    """
    import numpy as np
    epoch=float(epoch_jd_tdb)
    if not np.isfinite(epoch):raise ValueError('Titan rotation epoch must be finite')
    ra,dec=np.radians([39.4827,83.4279]);w=np.radians((186.5855+22.5769768*(epoch-2451545.))%360.)
    pole=np.array([np.cos(dec)*np.cos(ra),np.cos(dec)*np.sin(ra),np.sin(dec)])
    node=np.array([-np.sin(ra),np.cos(ra),0.]);across=np.cross(pole,node)
    axes=np.array([np.cos(w)*node+np.sin(w)*across,-np.sin(w)*node+np.cos(w)*across,pole])
    epsilon=np.radians(84381.448/3600.);c,s=np.cos(epsilon),np.sin(epsilon)
    return axes@np.array([[1.,0.,0.],[0.,c,-s],[0.,s,c]])

def titan_target_normal(epoch,latitude_deg,longitude_east_deg):
    import numpy as np
    lat,lon=np.radians([latitude_deg,longitude_east_deg])
    return titan_body_axes(epoch).T@np.array([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)])

def titan_geography(epoch,relative_state):
    import numpy as np
    state=np.asarray(relative_state);axes=titan_body_axes(epoch);r=axes@state[:3];radius=np.linalg.norm(r)
    omega=np.radians(22.5769768)/86400.*axes[2]
    return dict(latitude_deg=float(np.degrees(np.arcsin(np.clip(r[2]/radius,-1,1)))),longitude_east_deg=float(np.degrees(np.arctan2(r[1],r[0]))%360.),
        rotating_frame_speed_kms=float(np.linalg.norm(state[3:]-np.cross(omega,state[:3]))),
        frame='IAU_TITAN text-PCK; planetocentric latitude, east-positive longitude',
        source='https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/pck00011.tpc',
        note='Entry-interface subpoint or vacuum impact site, not a landing prediction. Rotating-frame speed omits winds.')
