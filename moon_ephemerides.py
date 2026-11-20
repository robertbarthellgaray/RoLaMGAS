"""Explicit opt-in two-body moon projections; never presented as JPL coverage."""
from pathlib import Path
import json,hashlib,math
import numpy as np
from ephemeris import DAY,JD0,Ephemerides,fetch,atomic_json
from horizons_targets import identity,register_target,cache_stem
from moon_targets import CATALOG_SYSTEMS,canonical_parent,target_options
from dynamics import kepler

MODEL='two-body projection from JPL reference state'

def project(cache,body,start,end,step,progress):
    descriptor=identity(body)
    parent=canonical_parent(descriptor.get('parent_body') or body)
    system=CATALOG_SYSTEMS.get(parent,{})
    if not system.get('gm') or not system.get('physical_id'):
        raise ValueError('No JPL reference-state projection model is available for '+body)
    moons=[m for m in target_options(parent) if m.get('reference_relative_state_km_kms')]
    selected=next((m for m in moons if str(m['id'])==str(descriptor['id'])),None)
    if not moons or (selected is None and str(descriptor['id'])!=str(system['physical_id'])):
        raise ValueError('No complete JPL reference orbit is available for '+body)
    des=str(system['designation']);bary_name=system['fullname']
    register_target(dict(name=bary_name,id=system['barycenter_id'],command=des+';',kind='small_body',designation=des))
    periods=[m.get('period_days') for m in moons if m.get('period_days')]
    cadence=min(step,min(periods)/128 if periods else step)
    cadence_seconds=max(60,int(math.floor(cadence*DAY)))
    first=math.floor((start-JD0)*DAY/cadence_seconds)-2;last=math.ceil((end-JD0)*DAY/cadence_seconds)+2
    seconds=np.arange(first,last+1,dtype=float)*cadence_seconds
    dates=JD0+seconds/DAY
    if len(dates)>500000:raise ValueError('Moon projection would exceed 500,000 samples; shorten the requested window.')
    try:ep=Ephemerides(cache,[bary_name],dates[0]-1,dates[-1]+1,max(1.,cadence))
    except ValueError:
        progress('Downloading current JPL system-barycenter motion for '+parent+'...')
        fetch(cache,bary_name,dates[0]-2,dates[-1]+2,min(1.,max(cadence,.25)))
        ep=Ephemerides(cache,[bary_name],dates[0]-1,dates[-1]+1,max(1.,cadence))
    progress('APPROXIMATE: projecting '+body+' from a JPL reference orbit. Future moon phase is uncertain.')
    total=system['gm']+sum(m['gm'] for m in moons)
    values=[]
    for date in dates:
        reference={}
        for moon in moons:
            state=np.asarray(moon['reference_relative_state_km_kms'],float)
            r,v=kepler(state[:3],state[3:],(date-moon['reference_epoch_jd_tdb'])*DAY,system['gm']+moon['gm'])
            reference[moon['id']]=np.r_[r,v]
        offset=sum((m['gm']/total*reference[m['id']] for m in moons),np.zeros(6))
        physical=ep.state(bary_name,date)-offset
        values.append(physical+(reference[selected['id']] if selected else 0.))
    states=np.asarray(values);cache=Path(cache);cache.mkdir(exist_ok=True,parents=True)
    note=dict(ephemeris_model=MODEL,body=body,parent=parent,start_jd=float(dates[0]),end_jd=float(dates[-1]),
        reference_orbits=moons,parent_model=system,system_barycenter_sources=ep.manifest[bary_name],
        warning='Approximate two-body moon phase projected outside published satellite ephemeris coverage. Numerical propagation checks do not validate future moon position. No secular perturbations or orbital covariance propagation.')
    raw=json.dumps(note,sort_keys=True,allow_nan=False);digest=hashlib.sha256(raw.encode()).hexdigest();key=cache_stem(body)+'_'+digest[:16]
    (cache/(key+'.txt')).write_text(raw,encoding='utf-8');packed=cache/(key+'.npz')
    np.savez_compressed(packed,times=seconds,states=states)
    atomic_json(cache/(key+'.json'),dict(body=body,source='JPL reference orbit + explicitly enabled two-body projection',
        ephemeris_model=MODEL,projection_warning=note['warning'],sha256=digest,raw_file=key+'.txt',target_identity=descriptor,
        npz_sha256=hashlib.sha256(packed.read_bytes()).hexdigest(),format='Sun-centered Ecliptic J2000, km, km/s, TDB; APPROXIMATE projected satellite orbit',
        start_jd=float(dates[0]),end_jd=float(dates[-1]),max_step_days=cadence_seconds/DAY,records=len(dates),
        reference_epoch_jd_tdb=moons[0]['reference_epoch_jd_tdb']))
    return Ephemerides(cache,[body],start,end,step)
