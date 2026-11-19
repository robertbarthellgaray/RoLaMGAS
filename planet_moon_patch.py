"""Optional encounter-window JPL overrides for Celestia planets and moons."""
from pathlib import Path
import hashlib,json,math,os,re,shutil
import numpy as np
from app_paths import RESOURCE_ROOT
from ephemeris import Ephemerides,DAY,JD0,atomic_json,calendar,fetch
from horizons_targets import register_target
from moon_targets import target_options
from dwarf_planet_patch import catalog_from_ssc


def templates():
    source=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Celestia/data/solarsys.ssc'
    if source.is_file():
        text=source.read_text(encoding='utf-8-sig')
        return dict(objects=catalog_from_ssc(text,include_major=True),source=str(source),
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            license=(re.search(r'SPDX-License-Identifier:\s*([^\r\n]+)',text)[1]),
            attribution=[s for s in text.splitlines() if 'SPDX-FileCopyrightText:' in s])
    return json.loads((RESOURCE_ROOT/'celestia_assets/planet_moon_orbits.json').read_text(encoding='utf-8'))


def validate_patch_days(value):
    if value is None:return 14.
    value=float(value)
    if not math.isfinite(value) or not 0<value<=3652.5:raise ValueError('JPL patch duration must be positive and at most 3652.5 days')
    return value


def orbital_period_days(parent_state,moon_state,parent_gm,moon_gm):
    relative=np.asarray(moon_state)-np.asarray(parent_state)
    radius=np.linalg.norm(relative[:3]);mu=parent_gm+moon_gm
    inverse_a=2/radius-np.dot(relative[3:],relative[3:])/mu
    if not np.isfinite(inverse_a) or inverse_a<=0:raise ValueError('JPL moon state does not define a bound orbit around its parent')
    return 2*math.pi/math.sqrt(mu*inverse_a**3)/DAY


def spline_states(spline,seconds):
    """Allow only the sub-millisecond roundoff from JD/seconds conversion."""
    seconds=np.asarray(seconds)
    if np.any(seconds<spline.x[0]-.001) or np.any(seconds>spline.x[-1]+.001):
        raise ValueError('JPL patch requested outside verified vector coverage')
    seconds=np.clip(seconds,spline.x[0],spline.x[-1])
    return np.concatenate([spline(seconds),spline(seconds,1)],axis=-1)


def compact_vectors(dates,values,encounter,position_tolerance_km=.05,velocity_tolerance_kms=1e-6,max_step_days=.25):
    """Thin playback only; test Hermite error at knots and within every source interval."""
    from scipy.interpolate import CubicHermiteSpline
    seconds=(np.asarray(dates)-JD0)*DAY;values=np.asarray(values)
    reference=CubicHermiteSpline(seconds,values[:,:3],values[:,3:],extrapolate=False)
    checks=np.unique(np.r_[seconds,*[seconds[:-1]+f*np.diff(seconds) for f in (.25,.5,.75)]])
    truth=spline_states(reference,checks);kept={0,len(seconds)-1,int(np.argmin(abs(dates-encounter)))}
    max_position=max_velocity=0.
    def refine(left,right):
        nonlocal max_position,max_velocity
        if right-left<=1:return
        a,b=seconds[left],seconds[right];mask=(checks>a)&(checks<b);t=checks[mask]
        trial=CubicHermiteSpline([a,b],values[[left,right],:3],values[[left,right],3:])
        predicted=spline_states(trial,t);actual=truth[mask]
        pe=float(np.max(np.linalg.norm(predicted[:,:3]-actual[:,:3],axis=1),initial=0))
        ve=float(np.max(np.linalg.norm(predicted[:,3:]-actual[:,3:],axis=1),initial=0))
        if b-a>max_step_days*DAY or pe>position_tolerance_km or ve>velocity_tolerance_kms:
            middle=(left+right)//2;kept.add(middle);refine(left,middle);refine(middle,right)
        else:max_position=max(max_position,pe);max_velocity=max(max_velocity,ve)
    boundaries=sorted(kept)
    for left,right in zip(boundaries,boundaries[1:]):refine(left,right)
    indices=sorted(kept)
    return np.asarray(dates)[indices],values[indices],dict(original_rows=len(dates),retained_rows=len(indices),
        position_tolerance_km=position_tolerance_km,velocity_tolerance_kms=velocity_tolerance_kms,
        maximum_checked_position_error_km=max_position,maximum_checked_velocity_error_kms=max_velocity,
        maximum_sample_step_minutes=float(np.max(np.diff(np.asarray(dates)[indices]))*1440),
        method='Cubic Hermite checked at original source knots and quarter points; encounter and endpoints retained. Solver ephemerides unchanged.')


def create_patches(root,config,report,patch_planet=False,patch_moon=False,patch_days=None):
    """Use the solver's exact source table for a moon branch; never extrapolate.

    The parent is Sun-relative; the satellite is parent-relative, with BOTH
    position and velocity subtracted. Playback samples are thinned with checked
    interpolation error; source solver tables and encounter epoch are retained.
    """
    from ephemeris import BODIES
    if not isinstance(patch_planet,bool) or not isinstance(patch_moon,bool):raise ValueError('JPL patch options must be boolean')
    parent=report.get('parent_body') or config.get('target')
    if parent not in BODIES:raise ValueError('Select a major-planet arrival for the planet/moon JPL patches')
    moon=next((m for m in target_options(parent) if m['id']==str(report.get('moon_id'))),None)
    if patch_moon and moon is None:raise ValueError('Select a completed moon-targeting branch before patching its moon')
    if moon:register_target(dict(name=moon['name'],id=moon['id'],command=moon['id'],kind='natural_satellite',parent_body=parent))
    epoch=float(report.get('target_epoch_jd_tdb',report.get('final_encounter_jd_tdb',report['end_jd_tdb'])))
    requested_days=validate_patch_days(patch_days)
    start=epoch-requested_days/2;end=epoch+requested_days/2;cache=Path(config['cache']);sources=report.get('ephemeris_sources',{})
    stock=templates();root=Path(root);patches=[];loaded={}

    def vectors(body,step):
        if body in loaded:return loaded[body]
        provenance=sources.get(body)
        if provenance:
            # Construct an isolated view of the original cached table. This
            # prevents a newer, slightly different JPL solution being chosen.
            from scipy.interpolate import CubicHermiteSpline
            chunks=[]
            for source in provenance if isinstance(provenance,list) else [provenance]:
                name=Path(source['raw_file']).with_suffix('.npz').name;table=cache/name
                if not table.is_file():raise ValueError('Original moon-targeting JPL table is missing: '+name+'. Restore the cache before patching.')
                if source.get('npz_sha256')!=hashlib.sha256(table.read_bytes()).hexdigest():raise ValueError('Original JPL table checksum differs: '+body)
                with np.load(table,allow_pickle=False) as data:chunks.append((data['times'],data['states']))
            times=np.concatenate([c[0] for c in chunks]);states=np.concatenate([c[1] for c in chunks])
            times,indices=np.unique(times,return_index=True);states=states[indices]
            spline=CubicHermiteSpline(times,states[:,:3],states[:,3:],extrapolate=False)
            manifest=provenance
        else:
            try:ep=Ephemerides(cache,[body],start,end,step,mercury_fine=False)
            except ValueError:
                fetch(cache,body,start,end,step);ep=Ephemerides(cache,[body],start,end,step,mercury_fine=False)
            spline=ep.splines[body];manifest=ep.manifest[body]
        loaded[body]=(spline,manifest);return loaded[body]

    parent_spline,parent_source=vectors(parent,1/24)
    period=None
    if patch_moon:
        moon_spline,moon_source=vectors(moon['name'],moon['step_days'])
        period=orbital_period_days(spline_states(parent_spline,(epoch-JD0)*DAY),spline_states(moon_spline,(epoch-JD0)*DAY),BODIES[parent][1],moon['gm'])
    effective_days=max(requested_days,period or 0.)
    start=epoch-effective_days/2;end=epoch+effective_days/2
    start_seconds=(start-JD0)*DAY;end_seconds=(end-JD0)*DAY

    def extend(body,spline,manifest,step):
        if start_seconds>=spline.x[0]-.001 and end_seconds<=spline.x[-1]+.001:return spline,manifest
        # Obtain guarded coverage for the FULL requested interval. Preserve all
        # original knots and derivatives inside its domain, even if a new JPL
        # table or a different cadence is needed outside that interval.
        try:ep=Ephemerides(cache,[body],start-1,end+1,step,mercury_fine=False)
        except ValueError:
            fetch(cache,body,start-1,end+1,step);ep=Ephemerides(cache,[body],start-1,end+1,step,mercury_fine=False)
        other=ep.splines[body];outside=other.x[(other.x<spline.x[0])|(other.x>spline.x[-1])]
        times=np.r_[outside,spline.x];values=np.r_[spline_states(other,outside),spline_states(spline,spline.x)]
        order=np.argsort(times);times=times[order];values=values[order]
        from scipy.interpolate import CubicHermiteSpline
        combined=CubicHermiteSpline(times,values[:,:3],values[:,3:],extrapolate=False)
        return combined,dict(original_tables=manifest,extension_tables=ep.manifest[body],original_interval_seconds_j2000=[float(spline.x[0]),float(spline.x[-1])])

    parent_spline,parent_source=extend(parent,parent_spline,parent_source,1/24)
    if patch_moon:moon_spline,moon_source=extend(moon['name'],moon_spline,moon_source,moon['step_days'])
    used=[parent_spline]+([moon_spline] if patch_moon else [])
    # Five-minute or finer output; retain source knots so cubic Hermite
    # interpolation is exactly the same interpolant as the arrival solver.
    cadence=min(1/288,moon['step_days']) if patch_moon else 1/288
    knots=np.r_[np.arange(start_seconds,end_seconds,cadence*DAY),start_seconds,(epoch-JD0)*DAY,end_seconds,*[s.x[(s.x>=start_seconds)&(s.x<=end_seconds)] for s in used]]
    dates=np.unique(JD0+knots/DAY)
    seconds=(dates-JD0)*DAY
    def states(spline):return spline_states(spline,seconds)
    parent_states=states(parent_spline)
    for name,center,values,manifest in ([(parent,'Sol',parent_states,{parent:parent_source})] if patch_planet else [])+([(moon['name'],'Sol/'+parent,states(moon_spline)-parent_states,{parent:parent_source,moon['name']:moon_source})] if patch_moon else []):
        output_dates,values,compression=compact_vectors(dates,values,epoch,max_step_days=min(.25,(period or 8)/32) if name!=parent else .25)
        row=next((r for r in stock['objects'] if r['name']==name and r['parent']==center),None)
        if row is None:raise ValueError('No original Celestia orbital definition available for '+name)
        props=row['properties'];old='\n'.join(props.values());spin='\n'.join(v for k,v in props.items() if k not in ('OrbitFrame','EllipticalOrbit','CustomOrbit'))
        # Stock Titan inherits its rotation period from CustomOrbit. A sampled
        # orbit is aperiodic, so explicitly retain the stock synchronous period.
        if name=='Titan' and 'UniformRotation' in props and not re.search(r'\bPeriod\b',re.sub(r'#[^\n]*','',props['UniformRotation'])):
            spin=spin.replace(props['UniformRotation'],props['UniformRotation'].replace('{','{\n Period 382.690104',1))
        stem='jpl_'+name.casefold();filename=stem+'.xyzv';ssc_name=stem+'_patch.ssc'
        (root/'data').mkdir(parents=True,exist_ok=True);(root/'reports').mkdir(parents=True,exist_ok=True)
        if not np.all(np.isfinite(values)):raise ValueError('Nonfinite JPL patch vectors for '+name)
        np.savetxt(root/'data'/filename,np.c_[output_dates,values],fmt=['%.12f']+['%.8f']*3+['%.12f']*3)
        ssc=(f'# JPL encounter override; original orbit/rotation attribution in reports/planet_moon_patches.json\n'
             f'Modify "{name}" "{center}"\n{{\n Timeline [\n'
             f' {{ Ending {start:.12f}\n{old}\n }}\n'
             f' {{ Ending {end:.12f}\n OrbitFrame {{ EclipticJ2000 {{ Center "{center}" }} }}\n'
             f' SampledTrajectory {{ Source "{filename}" DoublePrecision true Interpolation "cubic" }}\n{spin}\n }}\n'
             f' {{\n{old}\n }}\n ]\n}}\n')
        (root/ssc_name).write_text(ssc,encoding='utf-8')
        patches.append(dict(body=name,celestia_object=center+'/'+name,center=center,files=[ssc_name,'data/'+filename],
            start_jd_tdb=start,end_jd_tdb=end,start_date=calendar(start),end_date=calendar(end),rows=len(output_dates),compression=compression,
            requested_duration_days=requested_days,effective_duration_days=effective_days,moon_orbital_period_days=period,
            trajectory_sha256=hashlib.sha256((root/'data'/filename).read_bytes()).hexdigest(),
            ephemeris_sources=manifest,original_properties=props))
    metadata=dict(patches=patches,source_catalog={k:v for k,v in stock.items() if k!='objects'},
        encounter_jd_tdb=epoch,requested_duration_days=requested_days,effective_duration_days=effective_days,
        moon_orbital_period_days=period,period_method='Two-body osculating period from the original JPL parent-relative state at encounter; parent GM + moon GM.',
        frame='Ecliptic J2000; JD TDB, km, km/s',
        limitations='Position and velocity override only; existing shapes and rotations retained. Original orbits restored outside the window. Disable other addons that override the same bodies during this encounter.')
    atomic_json(root/'reports/planet_moon_patches.json',metadata)
    shutil.copy2(RESOURCE_ROOT/'LICENSE',root/'reports/Celestia_orbit_LICENSE.txt')
    return metadata
