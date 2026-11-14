"""GUI worker: finite interplanetary source -> separate moon arrival branch."""
import bootstrap  # noqa: F401
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,json,math,os,threading,time,traceback,subprocess,shutil
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from ephemeris import BODIES,DAY,JD0,MU_SUN,Ephemerides,atomic_json,calendar,fetch
from horizons_targets import register_target
from app_paths import worker_command,worker_environment
from moon_targets import validate_options,titan_target_normal
from moon_arrival import MoonSystem,target_arrival,target_upstream,solar_state,soi_entry

class BodyVectors:
    def __init__(self,ep,body):self.ep,self.body=ep,body
    def __call__(self,date):return self.ep.state(self.body,date)
    def position(self,date):return self.ep.splines[self.body]((date-JD0)*DAY)

def cached(cache,body,start,end,step,progress):
    try:return Ephemerides(cache,[body],start,end,step)
    except ValueError:
        progress('Downloading and caching JPL '+body+' vectors...')
        fetch(cache,body,start-1,end+1,step);return Ephemerides(cache,[body],start,end,step)

def finite_source(xyzv,report):
    """Select a state strictly inside the last Sun-only coast of the real export."""
    rows=np.loadtxt(xyzv,comments='#')
    if rows.ndim!=2 or rows.shape[1]!=7 or len(rows)<3 or not np.isfinite(rows).all() or np.any(np.diff(rows[:,0])<=0):
        raise ValueError('Source XYZV must contain finite, strictly increasing seven-column states')
    if not report.get('numerical_validation_passed'):raise ValueError('Source finite-radius export has not passed numerical checks')
    spans=[s for s in report['force_segments'] if s['center']=='Sun']
    if not spans:raise ValueError('No Sun-only final coast exists in this export')
    span=spans[-1];start,end=span['start_jd_tdb'],span['end_jd_tdb']
    indices=np.flatnonzero((rows[:,0]>start+2/DAY)&(rows[:,0]<end-2/DAY))
    if not len(indices):raise ValueError('No source samples inside final solar coast')
    row=rows[indices[0]];arrival=float(report['final_encounter_jd_tdb'])
    return dict(start_jd=float(row[0]),end_jd=arrival,r=row[1:4].tolist(),v=row[4:7].tolist()),rows,span

def stitch_source(source,report,dates,local,parent):
    """Use the old finite path up to the new DSM; bracket only its velocity jump."""
    epoch=report['upstream_burn_jd_tdb'];r=np.array(report['upstream_burn_position_heliocentric_km']);v=np.array(report['upstream_post_burn_velocity_heliocentric_kms']);delta=np.array(report['upstream_delta_v_vector_kms'])
    before=epoch-.5/DAY;after=epoch+.5/DAY
    # Source interpolation is used only at the left side of the impulse. The
    # solver initial state is checked against it before producing a full file.
    times=(source[:,0]-JD0)*DAY;spline=CubicHermiteSpline(times,source[:,1:4],source[:,4:7])
    join=np.r_[spline((epoch-JD0)*DAY),spline((epoch-JD0)*DAY,1)]
    position_error=float(np.linalg.norm(join[:3]-r));velocity_error=float(np.linalg.norm(join[3:]-(v-delta)))
    if position_error>1. or velocity_error>1e-5:raise ValueError('New cruise arc does not join the finite source continuously')
    left=np.r_[before,spline((before-JD0)*DAY),spline((before-JD0)*DAY,1)]
    seg=dict(start_jd=epoch,r=r.tolist(),v=v.tolist())
    solar_dates=np.unique(np.r_[after,np.arange(after,dates[0],.25)])
    solar=np.array([np.r_[t,solar_state(seg,t)] for t in solar_dates])
    heliocentric=np.array([np.r_[t,y+parent(t)] for t,y in zip(dates,local)])
    full=np.vstack([source[source[:,0]<before],left,solar,heliocentric])
    if not np.isfinite(full).all() or np.any(np.diff(full[:,0])<=0):raise ValueError('Joined trajectory dates are not strictly increasing')
    report.update(source_join_position_error_km=position_error,source_join_velocity_error_kms=velocity_error,
                  added_burn_bracket_seconds=1.,source_path_preserved_until_jd_tdb=float(before))
    return full

def write_states(path,rows,comma=False):
    with Path(path).open('w',encoding='utf-8',newline='') as f:
        if comma:f.write('julian_date_tdb,x_km,y_km,z_km,vx_kms,vy_kms,vz_kms\n')
        sep=',' if comma else ' '
        for row in rows:f.write(sep.join([f'{row[0]:.12f}']+[f'{x:.8f}' for x in row[1:4]]+[f'{x:.12f}' for x in row[4:]])+'\n')

def retained_burns(baseline,burn_epoch):
    """Separate launcher injection from cruise impulses, dropping replaced burns."""
    with (Path(baseline)/'burns.csv').open(newline='',encoding='utf-8') as f:
        rows=list(csv.DictReader(f))
    rows=[b for b in rows if float(b['julian_date_tdb'])<burn_epoch]
    onboard=sum(float(b['magnitude_kms']) for b in rows if not b['kind'].startswith('launch_injection'))
    return rows,onboard

def run(request,output,progress,cancel):
    options=validate_options(**request['options']);q=json.loads(Path(request['candidate_file']).read_text(encoding='utf-8'))
    if q['bodies'][-1]!=options['parent']:raise ValueError('Moon parent differs from the selected final planet')
    baseline=Path(request.get('baseline_folder') or output/'source_export')
    if not (baseline/'integration_report.json').is_file():
        progress('Preparing a finite-radius interplanetary export before moon targeting...')
        baseline.mkdir(parents=True,exist_ok=True)
        with (baseline/'integration.log').open('w',encoding='utf-8') as log:
            p=subprocess.Popen(worker_command('integrate_export','--candidate',request['candidate_file'],'--config',request['config_file'],'--output',str(baseline),'--refine-patches','--patch-epoch-shift-days','2'),stdout=log,stderr=subprocess.STDOUT,env=worker_environment(baseline/'integration.log'),creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            while p.poll() is None:
                if cancel():p.terminate();p.wait();raise InterruptedError('Moon targeting stopped')
                time.sleep(.3)
            if p.returncode:raise ValueError('Interplanetary export failed; see source_export/integration.log')
    source_report=json.loads((baseline/'integration_report.json').read_text());segment,source,span=finite_source(baseline/'trajectory.xyzv',source_report)
    archive=output/'source_export';archive.mkdir(exist_ok=True)
    for filename in ('integration_report.json','burns.csv','encounters.csv'):
        origin=baseline/filename;destination=archive/filename
        if origin.is_file() and origin.resolve()!=destination.resolve():shutil.copy2(origin,destination)
    arrival=source_report['final_encounter_jd_tdb'];cache=Path(request['cache']);parent_name=options['parent'];moon=options['moon']
    register_target(dict(name=moon['name'],id=moon['id'],command=moon['id'],kind='natural_satellite',parent_body=parent_name))
    coarse=cached(cache,parent_name,segment['start_jd']-2,arrival+2,1.,progress);entry,_=soi_entry(segment,arrival,BodyVectors(coarse,parent_name))
    fine_start=entry-32;fine_end=arrival+2
    ep_parent=cached(cache,parent_name,fine_start,fine_end,1/24,progress)
    ep_moon=cached(cache,moon['name'],fine_start,fine_end,moon['step_days'],progress)
    fine=BodyVectors(ep_parent,parent_name);coarse_view=BodyVectors(coarse,parent_name)
    class Parent:
        def __call__(self,t):return fine(t) if fine_start<=t<=fine_end else coarse_view(t)
        def position(self,t):return fine.position(t) if fine_start<=t<=fine_end else coarse_view.position(t)
    parent=Parent();satellite=BodyVectors(ep_moon,moon['name'])
    system=MoonSystem(parent_name,moon['name'],BODIES[parent_name][1],BODIES[parent_name][2],moon['gm'],moon['radius_km'],cancel)
    progress('Constructing '+moon['name']+' '+options['mode']+' arrival at the selected date...')
    point=options['target_point'];normal=None if point is None else titan_target_normal(arrival,point['latitude_deg'],point['longitude_east_deg'])
    base,_,_=target_arrival(segment,arrival,parent,satellite,options['altitude_km'],system=system,mode=options['mode'],target_normal=normal)
    attempts=[];best=None
    for index,fraction in enumerate(options['burn_fractions']):
        if cancel():raise InterruptedError('Moon targeting stopped')
        def update(message):
            if cancel():raise InterruptedError('Moon targeting stopped')
            progress(f'Correction timing {index+1}/{len(options["burn_fractions"])}: '+message,attempts=attempts)
        try:
            report,dates,states=target_upstream(segment,arrival,parent,satellite,base,fraction,system,update,inclination_deg=options['inclination_deg'])
            delta=report['upstream_delta_v_kms'];attempts.append(dict(fraction=fraction,passed=True,delta_v_mps=delta*1000,burn_date=calendar(report['upstream_burn_jd_tdb'])))
            if best is None or delta<best[0]:best=(delta,report,dates,states)
        except InterruptedError:raise
        except (ValueError,RuntimeError,AssertionError,OverflowError) as error:attempts.append(dict(fraction=fraction,passed=False,error=str(error)))
        atomic_json(output/'attempts.json',attempts)
    if best is None:raise ValueError('No moon-targeted branch passed. See attempts.json for each correction timing.')
    delta,report,dates,states=best
    burns,retained_onboard=retained_burns(baseline,report['upstream_burn_jd_tdb'])
    report.update(parent_body=parent_name,moon_body=moon['name'],moon_id=moon['id'],target_mode=options['mode'],target_altitude_km=options['altitude_km'],
        target_epoch_jd_tdb=float(arrival),target_date=calendar(arrival),added_correction_delta_v_kms=delta,
        requested_body_fixed_point=point,
        parent_export_onboard_delta_v_kms=source_report['total_onboard_delta_v_kms'],retained_parent_onboard_delta_v_kms=retained_onboard,total_onboard_delta_v_kms=retained_onboard+delta,
        source_candidate_id=q['id'],source_sequence=q['sequence'],exported_launch_c3_km2_s2=source_report['exported_launch_c3_km2_s2'],
        minimum_found_note='Lowest added burn among the tested correction epochs; not a global minimum.',attempts=attempts,
        added_burn_limit_mps=options['max_added_mps'],passes_added_burn_limit=bool(delta*1000<=options['max_added_mps']),
        ephemeris_sources={parent_name:ep_parent.manifest[parent_name],moon['name']:ep_moon.manifest[moon['name']]},
        source_parent_report='source_export/integration_report.json',
        force_model=f'Sun outside {parent_name} SOI; {parent_name} and differential {moon["name"]} point-mass gravity inside. No atmosphere, landing, rings, J2 or other moons.')
    report.update(achieved_altitude_km=report['titan_entry_altitude_km'],moon_relative_state_km_kms=report['titan_relative_entry_state_km_kms'],
        moon_relative_speed_kms=report['titan_relative_inertial_entry_speed_kms'],numerical_validation_passed=True,
        budget_note='Onboard budget excludes launcher injection and source burns replaced by the new terminal arc.')
    report['model']=report['force_model']
    report['requested_limits']=source_report.get('requested_limits',{})
    limit=report['requested_limits'].get('max_dsm_kms')
    report['passes_original_onboard_budget']=None if limit is None else report['total_onboard_delta_v_kms']<=limit
    report['force_segments']=[dict(s,end_jd_tdb=min(s['end_jd_tdb'],report['upstream_burn_jd_tdb'])) for s in source_report['force_segments'] if s['start_jd_tdb']<report['upstream_burn_jd_tdb']]
    report['force_segments']+=[dict(center='Sun',start_jd_tdb=report['upstream_burn_jd_tdb'],end_jd_tdb=report['entry_jd_tdb']),dict(center=parent_name,perturbers=[moon['name']],start_jd_tdb=report['entry_jd_tdb'],end_jd_tdb=arrival)]
    full=stitch_source(source,report,dates,states,parent)
    write_states(output/'trajectory.xyzv',full);write_states(output/'trajectory.csv',full,True)
    write_states(output/'moon_approach_parent_relative.xyzv',np.c_[dates,states])
    atomic_json(output/'arrival_state.json',dict(body=moon['name'],epoch_jd_tdb=arrival,position_km=report['titan_relative_entry_state_km_kms'][:3],velocity_kms=report['titan_relative_entry_state_km_kms'][3:],frame='Moon-centered Ecliptic J2000; km, km/s; no capture burn'))
    plot(output,dates,states,parent,satellite,report)
    report['rows']=len(full);report['start_jd_tdb']=float(full[0,0]);report['end_jd_tdb']=float(full[-1,0])
    # Keep the source's explicit finite-planet burns and add the new real DSM.
    burns.append(dict(kind='Moon targeting cruise DSM',julian_date_tdb=report['upstream_burn_jd_tdb'],date=calendar(report['upstream_burn_jd_tdb']),magnitude_kms=delta,dx_kms=report['upstream_delta_v_vector_kms'][0],dy_kms=report['upstream_delta_v_vector_kms'][1],dz_kms=report['upstream_delta_v_vector_kms'][2]))
    fields=list(dict.fromkeys(k for b in burns for k in b))
    with (output/'burns.csv').open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(burns)
    atomic_json(output/'moon_report.json',report)
    (output/'README.txt').write_text(f'{moon["name"]} {options["mode"]} branch. Full finite-radius launch-to-moon trajectory.\nEcliptic J2000, Sun-centered km and km/s, JD TDB.\nAdded cruise correction: {delta*1000:.3f} m/s. No SOI burn.\n'+report['force_model']+'\nClosest-approach mode targets a tangent periapsis. Impact is a vacuum geometric surface intersection, not a landing simulation. Entry mode stops at an illustrative atmospheric interface.\n',encoding='utf-8')
    return report

def plot(output,dates,states,parent,moon,report):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    satellite=np.array([moon(t)-parent(t) for t in dates]);close=np.linalg.norm(states[:,:3],axis=1)<3e6
    fig,ax=plt.subplots(figsize=(7,6));ax.plot(states[close,0]/1e6,states[close,1]/1e6,label='Probe');ax.plot(satellite[:,0]/1e6,satellite[:,1]/1e6,lw=.6,label=report['moon_body']);ax.scatter(0,0,color='orange',label=report['parent_body']);ax.scatter(*satellite[-1,:2]/1e6,marker='*',s=80);ax.set_aspect('equal',adjustable='datalim');ax.set(xlabel='Parent-relative x (million km)',ylabel='y (million km)',title=f"{report['moon_body']} {report['target_mode']} · {report['added_correction_delta_v_kms']*1000:.1f} m/s added\n{report['target_date'][:19]} TDB");ax.legend();fig.tight_layout();fig.savefig(output/'trajectory.png',dpi=140);plt.close(fig)

def main():
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);a=p.parse_args();request_file=Path(a.request);output=request_file.parent
    request=json.loads(request_file.read_text());started=time.time();stop=threading.Event();status={'state':'running','message':'Starting moon targeting...','started_unix':started}
    def progress(message,**extra):status.update(message=message,**extra);atomic_json(output/'status.json',dict(status,elapsed_seconds=time.time()-started,updated_unix=time.time()))
    def heartbeat():
        while not stop.wait(1.):progress(status['message'])
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    try:
        report=run(request,output,progress,lambda:(output/'stop.request').exists());status.update(state='finished',message='Moon branch saved; '+('within added-burn limit.' if report['passes_added_burn_limit'] else 'added burn exceeds the requested limit.'),report=report);progress(status['message'])
    except InterruptedError as error:status.update(state='stopped');progress(str(error))
    except Exception as error:traceback.print_exc();status.update(state='failed');progress(str(error));raise
    finally:stop.set();thread.join(timeout=3)
if __name__=='__main__':main()
