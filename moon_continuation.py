"""Unpowered continuation of a validated moon encounter; source stays immutable."""
import bootstrap  # noqa: F401
from pathlib import Path
import argparse,hashlib,json,shutil,time,traceback
import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import CubicHermiteSpline
from ephemeris import BODIES,DAY,JD0,MU_SUN,AU,Ephemerides,fetch,atomic_json,calendar
from horizons_targets import register_target
from moon_targets import target_options,parent_parameters,register_parent
from moon_arrival import relative_acceleration
from integrate_export import MONTH_DAYS,validate_post_flyby_months,solar_continuation,sample_piece,heliocentric_orbit_summary
from planet_moon_patch import spline_states,source_tables


def continuation_path(source,months):
    source=Path(source);months=validate_post_flyby_months(months)
    digest=hashlib.sha256((source/'trajectory.xyzv').read_bytes()).hexdigest()
    key=hashlib.sha256(f'{digest}:{months:.17g}:moon-coast-1'.encode()).hexdigest()[:12]
    return source/'continuations'/key


def load_vectors(cache,body,sources,start,end,step,progress):
    """Preserve original interpolation through the encounter; add guarded coverage."""
    chunks=[]
    for source in source_tables(sources):
        path=Path(cache)/Path(source['raw_file']).with_suffix('.npz').name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=source['npz_sha256']:
            raise ValueError('Original JPL table checksum differs: '+body)
        with np.load(path,allow_pickle=False) as z:chunks.append((z['times'],z['states']))
    times=np.concatenate([x[0] for x in chunks]);values=np.concatenate([x[1] for x in chunks])
    times,indices=np.unique(times,return_index=True);values=values[indices]
    provenance=sources
    if (start-JD0)*DAY<times[0] or (end-JD0)*DAY>times[-1]:
        # Request only the required local SOI window, never decades of moon data.
        if any(m.get('ephemeris_model') for m in source_tables(sources)):
            from moon_targeting import cached
            extra=cached(cache,body,start-1,end+1,step,progress,allow_projection=True)
        else:
            try:extra=Ephemerides(cache,[body],start-1,end+1,step,mercury_fine=False)
            except ValueError:
                progress('Downloading '+body+' vectors for the outgoing SOI arc...')
                fetch(cache,body,start-1,end+1,step)
                extra=Ephemerides(cache,[body],start-1,end+1,step,mercury_fine=False)
        curve=extra.splines[body];outside=curve.x[(curve.x<times[0])|(curve.x>times[-1])]
        times=np.r_[times,outside];values=np.r_[values,spline_states(curve,outside)]
        order=np.argsort(times);times=times[order];values=values[order]
        provenance=dict(original_tables=sources,extension_tables=extra.manifest[body])
    return CubicHermiteSpline(times,values[:,:3],values[:,3:],extrapolate=False),provenance


def outgoing_pieces(epoch,end,initial,parent,moon,parent_name,moon_data,extra_bodies=()):
    """Planet+differential moon until outbound SOI; Sun-only after, no impulse."""
    mu=parent_parameters(parent_name)[1];radius=parent_parameters(parent_name)[2]
    origin=(epoch-JD0)*DAY
    def at(curve,t):return spline_states(curve,origin+t)
    def rhs(t,y):
        m=at(moon,t)[:3]-at(parent,t)[:3]
        acceleration=relative_acceleration(y[:3],m,mu,moon_data['gm'])
        for body,curve in extra_bodies:
            p=at(curve,t)[:3]-at(parent,t)[:3];r=y[:3]
            acceleration+=body['gm']*((p-r)/np.linalg.norm(p-r)**3-p/np.linalg.norm(p)**3)
        return np.r_[y[3:],acceleration]
    def escape(t,y):return np.linalg.norm(y[:3])-np.linalg.norm(at(parent,t)[:3])*(mu/MU_SUN)**.4
    def impact_parent(t,y):return np.linalg.norm(y[:3])-radius
    def impact_moon(t,y):return np.linalg.norm(y[:3]-(at(moon,t)-at(parent,t))[:3])-moon_data['radius_km']
    escape.terminal=impact_parent.terminal=impact_moon.terminal=True
    escape.direction=1;impact_parent.direction=impact_moon.direction=-1
    seconds=(end-epoch)*DAY
    local=np.asarray(initial)-at(parent,0.)
    events=[escape,impact_parent,impact_moon]
    for body,curve in extra_bodies:
        def impact(t,y,body=body,curve=curve):return np.linalg.norm(y[:3]-(at(curve,t)-at(parent,t))[:3])-body['radius_km']
        impact.terminal=True;impact.direction=-1;events.append(impact)
    def solve(tolerance):return solve_ivp(rhs,(0,seconds),local,method='DOP853',rtol=tolerance,
        atol=np.r_[np.full(3,1e-7),np.full(3,1e-12)],dense_output=True,
        max_step=DAY,events=events)
    fit=solve(3e-13)
    if not fit.success:raise ValueError('Outgoing moon propagation failed: '+fit.message)
    if any(len(x) for x in fit.t_events[1:]):raise ValueError('Outgoing trajectory intersects the parent or targeted moon')
    stop=epoch+fit.t[-1]/DAY
    def state(date):
        seconds=(date-epoch)*DAY
        return fit.sol(seconds)+at(parent,seconds)
    # Independent tolerance rerun at a common epoch, avoiding event-time error.
    check=solve(1e-12);common=min(fit.t[-1],check.t[-1])
    error=float(np.linalg.norm(fit.sol(common)[:3]-check.sol(common)[:3]))
    if error>.1:raise ValueError(f'Outgoing moon propagation disagrees by {error:.6g} km')
    pieces=[dict(start=epoch,end=stop,state=state,kind='planet',label=parent_name+' and '+moon_data['name']+' outgoing',
        numerical_error_km=error,force_center=parent_name,perturbers=[moon_data['name']]+[b['name'] for b,c in extra_bodies],gm_km3_s2=mu)]
    if len(fit.t_events[0]) and end>stop:pieces.append(solar_continuation(stop,end,state(stop)))
    return pieces


def extend(source,output,cache,months,progress=print):
    source=Path(source);output=Path(output);months=validate_post_flyby_months(months)
    report=json.loads((source/'moon_report.json').read_text(encoding='utf-8'))
    if report['target_mode']!='approach':raise ValueError('Post-moon continuation requires closest-approach mode; impact/entry stops at its interface')
    if not report.get('independent_sun_and_parent_moon_propagation_passed'):raise ValueError('Moon source has not passed independent propagation')
    if months<=0:raise ValueError('Select a positive duration for a moon continuation')
    if report.get('post_flyby_months',0):raise ValueError('Continue the original moon branch, not a previously extended copy')
    rows=np.loadtxt(source/'trajectory.xyzv');epoch=float(rows[-1,0]);end=epoch+months*MONTH_DAYS
    if not np.isfinite(rows).all() or np.any(np.diff(rows[:,0])<=0):raise ValueError('Invalid source trajectory')
    if abs(epoch-report['target_epoch_jd_tdb'])*DAY>.001:raise ValueError('Source endpoint differs from the moon encounter epoch')
    digest=hashlib.sha256((source/'trajectory.xyzv').read_bytes()).hexdigest()
    if report.get('trajectory_sha256')!=digest:raise ValueError('Moon source trajectory checksum changed')
    parent_name=report['parent_body'];moon_data=next(m for m in target_options(parent_name) if m['id']==report['moon_id'])
    register_parent(parent_name)
    register_target(dict(name=moon_data['name'],id=moon_data['id'],command=moon_data['id'],kind='natural_satellite',parent_body=parent_name))
    # Grow the local window only if the craft has not yet escaped it.
    horizon=min(end,epoch+90.)
    while True:
        parent,parent_sources=load_vectors(cache,parent_name,report['ephemeris_sources'][parent_name],epoch,horizon,1/24,progress)
        moon,moon_sources=load_vectors(cache,moon_data['name'],report['ephemeris_sources'][moon_data['name']],epoch,horizon,moon_data['step_days'],progress)
        progress('Propagating past '+moon_data['name']+' with parent/moon gravity...')
        extra_bodies=[];extra_sources={}
        for body_name in report.get('additional_gravity_bodies',[]):
            body=next(m for m in target_options(parent_name) if m['name']==body_name)
            register_target(dict(name=body['name'],id=body['id'],command=body['id'],kind='natural_satellite',parent_body=parent_name))
            curve,provenance=load_vectors(cache,body_name,report['ephemeris_sources'][body_name],epoch,horizon,body['step_days'],progress)
            extra_bodies.append((body,curve));extra_sources[body_name]=provenance
        pieces=outgoing_pieces(epoch,horizon,rows[-1,1:],parent,moon,parent_name,moon_data,extra_bodies)
        if pieces[-1]['kind']=='solar':
            if end>horizon:pieces[-1]=solar_continuation(pieces[-1]['start'],end,pieces[-1]['state'](pieces[-1]['start']))
            break
        if horizon>=end:break
        if horizon-epoch>=3652.5:raise ValueError('Still bound to the parent after ten years; no solar escape assumed')
        horizon=min(end,epoch+min(3652.5,2*(horizon-epoch)))
    progress('Sampling the outgoing trajectory for cubic XYZV playback...')
    extra=[]
    for piece in pieces:
        for date,y in sample_piece(piece,solar_max_step_days=30.):
            if date>(extra[-1][0] if extra else epoch):extra.append(np.r_[date,y])
    full=np.vstack([rows,extra])
    if not np.isfinite(full).all() or np.any(np.diff(full[:,0])<=0):raise ValueError('Invalid continuation samples')
    from moon_targeting import write_states
    output.mkdir(parents=True,exist_ok=True)
    # Copy the original prefix byte-for-byte; only the new rows are formatted.
    tail=output/'tail.xyzv';write_states(tail,np.asarray(extra))
    with (output/'trajectory.xyzv').open('wb') as f:
        prefix=(source/'trajectory.xyzv').read_bytes();f.write(prefix)
        if not prefix.endswith(b'\n'):f.write(b'\n')
        f.write(tail.read_bytes())
    tail.unlink();write_states(output/'trajectory.csv',full,True)
    for filename in ('burns.csv','arrival_state.json','trajectory.png','moon_approach_parent_relative.xyzv','README.txt'):
        if (source/filename).is_file():shutil.copy2(source/filename,output/filename)
    shutil.copytree(source/'source_export',output/'source_export',dirs_exist_ok=True)
    solar=next((p for p in pieces if p['kind']=='solar'),None)
    orbit=heliocentric_orbit_summary(solar['state'](solar['start']),solar['start']) if solar else None
    report.update(post_flyby_months=months,month_length_days=MONTH_DAYS,post_flyby_end_date=calendar(end),end_jd_tdb=float(full[-1,0]),rows=len(full),
        final_encounter_jd_tdb=epoch,post_flyby_solar_orbit=orbit,
        continuation_source_trajectory_sha256=digest,trajectory_sha256=hashlib.sha256((output/'trajectory.xyzv').read_bytes()).hexdigest(),
        continuation_added_burn_kms=0.,continuation_join_position_error_km=float(np.linalg.norm(pieces[0]['state'](epoch)[:3]-rows[-1,1:4])),
        continuation_join_velocity_error_kms=float(np.linalg.norm(pieces[0]['state'](epoch)[3:]-rows[-1,4:])),
        continuation_numerical_error_km=max(p['numerical_error_km'] for p in pieces),
        continuation_ephemeris_sources={parent_name:parent_sources,moon_data['name']:moon_sources,**extra_sources},
        continuation_final_heliocentric_distance_au=float(np.linalg.norm(full[-1,1:4])/AU),
        continuation_limitation='Parent and targeted moon checked through outgoing SOI; Sun-only after escape. Other moons, later encounters and interstellar forces are not modeled.')
    report['force_segments']+= [dict(center=p['force_center'],start_jd_tdb=p['start'],end_jd_tdb=p['end'],perturbers=p.get('perturbers',[])) for p in pieces]
    report['force_model']+=' Unpowered continuation: parent + targeted moon to outbound parent SOI, then Sun-only.'
    atomic_json(output/'moon_report.json',report)
    with (output/'README.txt').open('a',encoding='utf-8') as f:
        f.write(f'\nUnpowered continuation: {months:g} months after moon encounter, ending {calendar(end)}. No added burn. Original prefix preserved.\n'+report['continuation_limitation']+'\n')
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--cache',required=True);p.add_argument('--months',required=True,type=float);a=p.parse_args()
    output=Path(a.output);output.mkdir(parents=True,exist_ok=True);started=time.time()
    def progress(message):atomic_json(output/'integration_status.json',dict(state='running',message=message,started_unix=started,updated_unix=time.time()))
    try:
        report=extend(a.source,output,a.cache,a.months,progress)
        atomic_json(output/'integration_status.json',dict(state='finished',message='Moon flyby continuation ready.',report=report))
    except Exception as error:
        traceback.print_exc();atomic_json(output/'integration_status.json',dict(state='failed',message=str(error)));raise

if __name__=='__main__':main()
