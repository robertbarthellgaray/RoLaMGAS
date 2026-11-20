"""Supported local arrival models; JPL satellite GMs and mean radii.

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

MOON_SYSTEMS={
    'Pluto':('JPL PLU060',[
        dict(id='901',name='Charon',gm=106.1,radius_km=606.,step_days=1/288),
        dict(id='902',name='Nix',gm=.0015,radius_km=18.,step_days=1/288),
        dict(id='903',name='Hydra',gm=.0020,radius_km=18.5,step_days=1/288),
        dict(id='904',name='Kerberos',gm=0.,radius_km=6.,step_days=1/288,gm_note='Massless target approximation; JPL gives only GM <0.0002 km3/s2.'),
        dict(id='905',name='Styx',gm=0.,radius_km=5.2,step_days=1/288,gm_note='Massless target approximation; JPL gives only GM <0.0003 km3/s2.'),
    ]),
    'Mars':('JPL MAR097',[
        dict(id='401',name='Phobos',gm=.0007087,radius_km=11.08,step_days=1/1440),
        dict(id='402',name='Deimos',gm=.0000962,radius_km=6.2,step_days=1/288),
    ]),
    'Jupiter':('JPL JUP365',[
        dict(id='502',name='Europa',gm=3202.71210,radius_km=1560.80,step_days=1/288),
        dict(id='501',name='Io',gm=5959.91547,radius_km=1821.49,step_days=1/288),
        dict(id='503',name='Ganymede',gm=9887.83275,radius_km=2631.20,step_days=1/144),
        dict(id='504',name='Callisto',gm=7179.28340,radius_km=2410.30,step_days=1/96),
    ]),
    'Saturn':('JPL SAT441',SATURN_MOONS),
    'Uranus':('JPL URA111',[
        dict(id='701',name='Ariel',gm=83.5,radius_km=578.9,step_days=1/288),
        dict(id='702',name='Umbriel',gm=85.1,radius_km=584.7,step_days=1/288),
        dict(id='703',name='Titania',gm=226.9,radius_km=788.9,step_days=1/144),
        dict(id='704',name='Oberon',gm=205.3,radius_km=761.4,step_days=1/96),
        dict(id='705',name='Miranda',gm=4.3,radius_km=235.8,step_days=1/288),
    ]),
    'Neptune':('JPL NEP097',[
        dict(id='801',name='Triton',gm=1428.49546,radius_km=1352.60,step_days=1/288),
    ]),
}

def canonical_parent(parent):
    import re
    return 'Pluto' if re.fullmatch(r'(?:134340\s+)?Pluto(?:\s*\(1930\s*BM\))?',str(parent),re.I) else parent

def parent_parameters(parent):
    from ephemeris import BODIES
    parent=canonical_parent(parent)
    if parent=='Pluto':return 999,869.3,1188.3,100.
    if parent not in BODIES:raise ValueError('No validated parent gravity/radius model is available for '+str(parent))
    return BODIES[parent]

def register_parent(parent):
    from horizons_targets import register_target,pluto_identity
    if canonical_parent(parent)=='Pluto':register_target(pluto_identity())

def target_options(parent):
    parent=canonical_parent(parent)
    source,moons=MOON_SYSTEMS.get(parent,('',[]))
    return [dict(m,parent_body=parent,source=source) for m in moons]

def moon_intent(value,parent):
    """Canonical, portable moon selection; no untrusted physical constants."""
    if value is None:return None
    if not isinstance(value,dict) or canonical_parent(value.get('parent'))!=canonical_parent(parent):
        raise ValueError('Moon selection must match the destination planet')
    moon=next((m for m in target_options(parent) if m['id']==str(value.get('moon_id'))),None)
    if moon is None:raise ValueError('This moon has no supported parent-centered targeting model')
    return dict(parent=canonical_parent(parent),moon_id=moon['id'],moon_name=moon['name'])

def named_moon(query):
    """Known JPL identities also resolve offline; other Horizons names still use JPL."""
    import re
    text=re.sub(r'\s*\([JSUNM]\s*[IVX]+\)\s*$','',str(query),flags=re.I).strip().casefold()
    text=re.sub(r'^spk\s*=\s*','',text)
    for parent in MOON_SYSTEMS:
        for moon in target_options(parent):
            if text in (moon['name'].casefold(),moon['id']):
                return dict(name=moon['name'],id=moon['id'],command=moon['id'],kind='natural_satellite',parent_body=parent,
                    source='https://ssd.jpl.nasa.gov/sats/phys_par/',query=str(query),identity_note='Known JPL satellite ID; encounter vectors are fetched when targeting.')
    return None

def validate_options(parent,moon_id,mode,altitude,max_added_mps=700.,effort='standard',inclination_deg=None,target_latitude_deg=None,target_longitude_deg=None):
    import math
    parent=canonical_parent(parent)
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
                burn_fractions=[.35] if effort=='quick' else [.1,.3,.5,.7,.85],inclination_deg=inclination_deg,target_point=point)

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
        note='Body-fixed state subpoint, not a landing prediction. Rotating-frame speed omits winds.')
