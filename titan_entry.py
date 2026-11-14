"""Standalone Titan entry integrator: supplied arrival state -> drag trajectory.

Uses SI internally; input/output vectors are Titan-centered Ecliptic J2000,
km and km/s, JD TDB. Baseline atmosphere is an auditable Huygens reference,
not a 2030s weather forecast. No six-DOF attitude, heating, ablation or landing
autopilot is inferred. Default output stops at the Mach-1.5 chute handoff.
"""
import bootstrap  # noqa: F401
from pathlib import Path
import argparse,csv,hashlib,json,math,io,tempfile,os
import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import PchipInterpolator
from moon_targets import titan_body_axes,titan_geography
from ephemeris import DAY,calendar,atomic_json

ROOT=Path(__file__).resolve().parent
MU=8978.13710*1e9
RADIUS=2574.76*1000.
OMEGA=np.radians(22.5769768)/DAY
G0=9.80665
MOLAR_MASS=.98*.0280134+.02*.01604246
R_GAS=8.31446261815324
NASA_REFERENCE='https://ntrs.nasa.gov/citations/20240007259'

class Atmosphere:
    """Replaceable CSV column; GRAM outputs can be converted to these SI names."""
    def __init__(self,path,density_scale=1.):
        self.path=Path(path);self.scale=float(density_scale)
        if not np.isfinite(self.scale) or self.scale<=0:raise ValueError('Positive finite density multiplier required')
        with self.path.open(newline='',encoding='utf-8') as stream:rows=list(csv.DictReader(stream))
        required=['altitude_m','density_kg_m3','temperature_k','pressure_pa']
        data=np.array([[float(r[k]) for k in required] for r in rows])
        if data.ndim!=2 or len(data)<3 or not np.isfinite(data).all() or np.any(np.diff(data[:,0])<=0) or np.any(data[:,1:]<=0):
            raise ValueError('Atmosphere needs increasing finite SI altitudes and positive density/temperature/pressure')
        self.minimum,self.maximum=float(data[0,0]),float(data[-1,0])
        self.rho=PchipInterpolator(data[:,0],np.log(data[:,1]),extrapolate=False)
        self.temp=PchipInterpolator(data[:,0],data[:,2],extrapolate=False)
        self.press=PchipInterpolator(data[:,0],np.log(data[:,3]),extrapolate=False)
        self.wind_profiles=[]
        for field in ('zonal_wind_mps','meridional_wind_mps'):
            if any(row.get(field) for row in rows):
                values=np.array([float(row[field]) for row in rows])
                if not np.isfinite(values).all():raise ValueError('Wind profile must be finite at every altitude')
                self.wind_profiles.append(PchipInterpolator(data[:,0],values,extrapolate=False))
            else:self.wind_profiles.append(None)
        self.metadata=json.loads(self.path.with_suffix('.json').read_text()) if self.path.with_suffix('.json').exists() else {}

    def sample(self,altitude):
        if altitude>self.maximum+.1:raise ValueError('Entry left the supplied atmospheric altitude coverage')
        height=float(np.clip(altitude,self.minimum,self.maximum))
        rho=float(np.exp(self.rho(height)))*self.scale;temperature=float(self.temp(height));pressure=float(np.exp(self.press(height)))
        return rho,temperature,pressure

    def wind(self,altitude):
        height=float(np.clip(altitude,self.minimum,self.maximum))
        return tuple(float(profile(height)) if profile is not None else 0. for profile in self.wind_profiles)

def incoming(path):
    document=json.loads(Path(path).read_text(encoding='utf-8'))
    if document.get('body')=='Titan':
        if 'Ecliptic J2000' not in document.get('frame',''):raise ValueError('Supply a Titan-centered Ecliptic J2000 state')
        epoch=document['epoch_jd_tdb'];state=document['position_km']+document['velocity_kms']
    elif document.get('moon_body')=='Titan':
        epoch=document['arrival_jd_tdb'];state=document.get('moon_relative_state_km_kms',document.get('titan_relative_entry_state_km_kms'))
    else:raise ValueError('State document must explicitly identify Titan as the center')
    state=np.asarray(state,dtype=float);epoch=float(epoch)
    if state.shape!=(6,) or not np.isfinite(state).all() or not np.isfinite(epoch):raise ValueError('Finite six-component entry state and JD required')
    if np.linalg.norm(state[:3])*1000<=RADIUS or state[:3]@state[3:]>=0:raise ValueError('Initial state must be above the surface and inbound')
    return epoch,state

def air_velocity(position,pole,zonal=0.,meridional=0.):
    r=np.asarray(position);radial=r/np.linalg.norm(r);east=np.cross(pole,radial);length=np.linalg.norm(east)
    if length<1e-12:
        if abs(zonal)+abs(meridional)>0:raise ValueError('East/north winds are undefined exactly at a pole')
        return np.cross(OMEGA*pole,r)
    east/=length;north=np.cross(radial,east)
    return np.cross(OMEGA*pole,r)+zonal*east+meridional*north

def forces(state,atmosphere,pole,beta,ld=0.,bank_deg=0.,zonal=0.,meridional=0.):
    r=state[:3];velocity=state[3:6];rho,temp,pressure=atmosphere.sample(np.linalg.norm(r)-RADIUS)
    model_zonal,model_meridional=atmosphere.wind(np.linalg.norm(r)-RADIUS)
    relative=velocity-air_velocity(r,pole,zonal+model_zonal,meridional+model_meridional);speed=float(np.linalg.norm(relative))
    drag=-rho/(2*beta)*speed*relative;lift=np.zeros(3)
    if ld and speed>1e-8:
        u=relative/speed;up=r/np.linalg.norm(r);direction=up-(up@u)*u;length=np.linalg.norm(direction)
        if length>1e-10:
            direction/=length;bank=np.radians(bank_deg);direction=direction*np.cos(bank)+np.cross(u,direction)*np.sin(bank)
            lift=ld*np.linalg.norm(drag)*direction
    sound=math.sqrt(1.4*R_GAS/MOLAR_MASS*temp)
    return drag+lift,dict(density_kg_m3=rho,temperature_k=temp,pressure_pa=pressure,air_speed_mps=speed,mach=speed/sound,
        dynamic_pressure_pa=.5*rho*speed**2,sensed_deceleration_g0=float(np.linalg.norm(drag+lift)/G0),ballistic_coefficient_kg_m2=beta,zonal_wind_mps=zonal+model_zonal,meridional_wind_mps=meridional+model_meridional)

def integrate(epoch,state_km,atmosphere,beta=70.,scenario='ballistic',ld=0.,bank_deg=0.,zonal=0.,meridional=0.,max_seconds=6*3600.,saturn_position=None):
    """Continuous inertial state; event-driven coefficient changes have no impulses.

    Illustrative descent uses the published 2025 8.25-m drogue and 16.7-m main,
    with assumed CD=0.7. Subsonic capsule CD=1.0 and constant reference mass
    are analyst assumptions, not the official multibody aerodynamic database.
    """
    beta=float(beta);values=[beta,ld,bank_deg,zonal,meridional,max_seconds]
    if not all(np.isfinite(values)) or beta<=0 or not 0<=ld<=2 or not 0<max_seconds<=2*DAY:raise ValueError('Invalid entry parameters')
    if scenario not in ('ballistic','illustrative-descent'):raise ValueError('Unknown entry scenario')
    state=np.asarray(state_km)*1000.
    if state.shape!=(6,) or not np.isfinite(state).all() or state[:3]@state[3:]>=0:raise ValueError('Finite inbound entry state required')
    if not 0<np.linalg.norm(state[:3])-RADIUS<=atmosphere.maximum:raise ValueError('Initial altitude must be within the atmospheric table')
    pole=titan_body_axes(epoch)[2];start_height=float(np.linalg.norm(state[:3])-RADIUS)
    phases=[dict(name='Aeroshell',beta=beta,trigger='mach',value=1.5)]
    assumptions=['Constant aeroshell ballistic coefficient; gamma=1.4 and constant 98% N2 / 2% CH4 gas constant for Mach estimates.','Zero lift by default. No six-DOF attitude, reefing, heating, ablation or terrain.']
    if scenario=='illustrative-descent':
        mass=2309.;capsule_cda=1.0*np.pi*4.5**2/4;drogue_cda=.7*np.pi*8.25**2/4
        drogue_beta=mass/(capsule_cda+drogue_cda)
        main_beta=mass/(.7*np.pi*16.7**2/4)
        phases.extend([dict(name='Illustrative 8.25 m drogue',beta=float(drogue_beta),trigger='altitude',value=5000.),dict(name='Illustrative 16.7 m main',beta=float(main_beta),trigger='altitude',value=800.)])
        assumptions+=['Drogue diameter 8.25 m and main diameter 16.7 m from NASA 2025; each CD=0.7 is an analyst assumption. Mass is held at the published CBE 2309 kg.',
            'During drogue descent, assumed subsonic capsule CD=1.0 is retained. At 5 km main-chute drag replaces the combined model. No inflation, official drag database or mass-jettison model is included; release speed is computed, not fitted.',
            'Stops at illustrative 800 m lander release; powered flight and touchdown are not propagated.']
    phases_out=[];events=[];current=np.r_[state,0.,0.];clock=0.;outcome='time_limit'
    for phase in phases:
        def rhs(t,y):
            r=y[:3];aero,_=forces(y,atmosphere,pole,phase['beta'],ld,bank_deg,zonal,meridional)
            tide=np.zeros(3)
            if saturn_position is not None:
                parent=np.asarray(saturn_position(t));delta=parent-r;tide=37931206.234e9*(delta/np.linalg.norm(delta)**3-parent/np.linalg.norm(parent)**3)
            acceleration=-MU*r/np.linalg.norm(r)**3+aero+tide
            return np.r_[y[3:6],acceleration,aero@y[3:6],tide@y[3:6]]
        def surface(t,y):return np.linalg.norm(y[:3])-RADIUS
        def escape(t,y):return np.linalg.norm(y[:3])-RADIUS-min(start_height+1.,atmosphere.maximum)
        def handoff(t,y):
            return forces(y,atmosphere,pole,phase['beta'],ld,bank_deg,zonal,meridional)[1]['mach']-phase['value'] if phase['trigger']=='mach' else np.linalg.norm(y[:3])-RADIUS-phase['value']
        surface.terminal=escape.terminal=handoff.terminal=True
        surface.direction=handoff.direction=-1;escape.direction=1
        solution=solve_ivp(rhs,(clock,max_seconds),current,method='DOP853',rtol=2e-10,atol=np.r_[np.full(3,.001),np.full(3,1e-6),.001,.001],max_step=2. if phase['trigger']=='mach' else 5.,dense_output=True,events=[surface,escape,handoff])
        if not solution.success:raise ValueError('Entry integration failed: '+solution.message)
        phases_out.append(dict(phase,solution=solution,start=clock,end=float(solution.t[-1])))
        clock=float(solution.t[-1]);current=solution.y[:,-1]
        if len(solution.t_events[0]):outcome='vacuum_surface_intersection';break
        if len(solution.t_events[1]):outcome='atmospheric_skip_out';break
        if not len(solution.t_events[2]):outcome='time_limit';break
        event=dict(name=phase['name']+' handoff',seconds=clock,epoch_jd_tdb=epoch+clock/DAY,altitude_m=float(np.linalg.norm(current[:3])-RADIUS),state_km_kms=(current[:6]/1000).tolist())
        events.append(event);outcome='mach_1_5_handoff' if scenario=='ballistic' else 'illustrative_lander_release'
    grid=np.unique(np.r_[np.arange(0,min(clock,900),1.),np.arange(900,clock,10.),[p['end'] for p in phases_out],clock])
    states=[];diagnostics=[]
    for second in grid:
        phase=next((p for p in reversed(phases_out) if second>=p['start']),phases_out[0]);y=phase['solution'].sol(second)
        _,d=forces(y,atmosphere,pole,phase['beta'],ld,bank_deg,zonal,meridional)
        location=titan_geography(epoch+second/DAY,y[:6]/1000)
        r=y[:3];relative=y[3:6]-air_velocity(r,pole,d['zonal_wind_mps'],d['meridional_wind_mps'])
        gamma=float(np.degrees(np.arcsin(np.clip((r@relative)/(np.linalg.norm(r)*max(np.linalg.norm(relative),1e-12)),-1,1))))
        diagnostics.append(dict(seconds=float(second),julian_date_tdb=float(epoch+second/DAY),phase=phase['name'],altitude_m=float(np.linalg.norm(r)-RADIUS),latitude_deg=location['latitude_deg'],longitude_east_deg=location['longitude_east_deg'],air_relative_flight_path_angle_deg=gamma,**d));states.append(y)
    states=np.array(states);energy=lambda y:.5*(y[3:6]@y[3:6])-MU/np.linalg.norm(y[:3])
    balance=float(energy(states[-1])-energy(states[0])-states[-1,6]-states[-1,7])
    peak_q=max(diagnostics,key=lambda row:row['dynamic_pressure_pa']);peak_g=max(diagnostics,key=lambda row:row['sensed_deceleration_g0'])
    report=dict(model='Titan 3-DOF reference-column entry; not an official Dragonfly EDL prediction',scenario=scenario,outcome=outcome,completed=outcome in ('mach_1_5_handoff','illustrative_lander_release'),epoch_jd_tdb=epoch,entry_date=calendar(epoch),duration_seconds=clock,rows=len(grid),initial_state_km_kms=np.asarray(state_km).tolist(),final_state_km_kms=(states[-1,:6]/1000).tolist(),
        initial_location=titan_geography(epoch,state_km),final_location=titan_geography(epoch+clock/DAY,states[-1,:6]/1000),initial_air_speed_mps=diagnostics[0]['air_speed_mps'],initial_air_relative_flight_path_angle_deg=diagnostics[0]['air_relative_flight_path_angle_deg'],peak_dynamic_pressure=peak_q,peak_sensed_deceleration=peak_g,
        events=events,phases=[{k:v for k,v in p.items() if k!='solution'} for p in phases_out],energy_work_balance_error_j_kg=balance,
        force_model='Spherical Titan gravity; aerodynamic force relative to rigidly rotating atmosphere plus specified winds; '+('JPL-prescribed differential Saturn gravity.' if saturn_position else 'Saturn tide omitted.'),
        atmosphere=dict(file=atmosphere.path.name,sha256=hashlib.sha256(atmosphere.path.read_bytes()).hexdigest(),density_multiplier=atmosphere.scale,metadata=atmosphere.metadata),
        parameters=dict(beta_kg_m2=beta,lift_to_drag=ld,bank_deg=bank_deg,zonal_wind_mps=zonal,meridional_wind_mps=meridional),assumptions=assumptions,descent_geometry_source='https://ntrs.nasa.gov/citations/20240014477' if scenario=='illustrative-descent' else None,
        reference_load_check=dict(limit_g0=12.,predicted_peak_g0=peak_g['sensed_deceleration_g0'],exceeds_reference_limit=bool(peak_g['sensed_deceleration_g0']>12.),source='https://ntrs.nasa.gov/citations/20240014477',note='Published Dragonfly study constraint, compared against this simplified model; not a vehicle certification or survivability test.'),
        limitations=['HASI is a single 2005 atmospheric column, not 2034/2035 weather.','No heat flux or thermal survivability prediction. Titan radiative heating cannot be replaced by an Earth heating formula.','No validated parachute/attitude/navigation database; full-descent mode is an illustrative scenario.','No powered flight, touchdown or landing ellipse prediction.'],reference=NASA_REFERENCE)
    return report,grid,states[:,:6]/1000,diagnostics

def append_prefix(prefix,entry_rows,cache,output):
    """Translate local entry states with JPL Titan states and join without a reset."""
    from horizons_targets import register_target
    from ephemeris import Ephemerides
    from moon_targeting import write_states
    source=np.loadtxt(prefix,comments='#')
    entry_rows=np.asarray(entry_rows)
    if source.ndim!=2 or source.shape[1]!=7 or not np.isfinite(source).all() or np.any(np.diff(source[:,0])<=0):raise ValueError('Prefix must be a finite, strictly increasing seven-column heliocentric XYZV')
    if entry_rows.ndim!=2 or entry_rows.shape[1]!=7 or len(entry_rows)<2 or not np.isfinite(entry_rows).all() or np.any(np.diff(entry_rows[:,0])<=0):raise ValueError('Entry states must be finite and strictly increasing')
    if abs(source[-1,0]-entry_rows[0,0])*DAY>.001:raise ValueError('Cruise must end at the supplied entry state epoch')
    register_target(dict(name='Titan',id='606',command='606',kind='natural_satellite',parent_body='Saturn'))
    ep=Ephemerides(cache,['Titan'],float(entry_rows[0,0])-.001,float(entry_rows[-1,0])+.001,1/24)
    helio=np.array([np.r_[row[0],row[1:]+ep.state('Titan',row[0])] for row in entry_rows])
    position_error=float(np.linalg.norm(helio[0,1:4]-source[-1,1:4]));velocity_error=float(np.linalg.norm(helio[0,4:]-source[-1,4:]))
    if position_error>.01 or velocity_error>1e-6:raise ValueError('Cruise-to-entry position/velocity mismatch; no trajectory has been spliced')
    full=np.vstack([source,helio[1:]])
    write_states(output/'full_trajectory.xyzv',full);write_states(output/'full_trajectory.csv',full,True)
    return dict(rows=len(full),position_join_error_km=position_error,velocity_join_error_kms=velocity_error,coordinates='Heliocentric Ecliptic J2000; JD TDB, km, km/s',prefix_sha256=hashlib.sha256(Path(prefix).read_bytes()).hexdigest())

def export(output,report,times,states,diagnostics):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    from moon_targeting import write_states
    rows=np.c_[report['epoch_jd_tdb']+times/DAY,states];write_states(output/'titan_entry.xyzv',rows)
    write_states(output/'titan_entry_states.csv',rows,True)
    with (output/'entry_profile.csv').open('w',newline='',encoding='utf-8') as stream:
        w=csv.DictWriter(stream,fieldnames=list(diagnostics[0]));w.writeheader();w.writerows(diagnostics)
    atomic_json(output/'entry_report.json',report)
    (output/'README.txt').write_text('Titan-centered Ecliptic J2000; JD TDB, km, km/s. The XYZV starts with the supplied entry state without a position/velocity reset.\n'+report['model']+'\nOutcome: '+report['outcome']+'\n'+report['force_model']+'\n'+ '\n'.join(report['assumptions']+report['limitations'])+'\n',encoding='utf-8')
    plot(output,report,diagnostics)

def plot(output,report,diagnostics):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    t=np.array([d['seconds'] for d in diagnostics])/60;alt=np.array([d['altitude_m'] for d in diagnostics])/1000
    fig,axes=plt.subplots(2,2,figsize=(12,8));axes=axes.ravel()
    axes[0].plot(t,alt);axes[0].set(xlabel='Minutes from interface',ylabel='Altitude (km)',yscale='log')
    axes[1].plot(t,[d['air_speed_mps']/1000 for d in diagnostics]);axes[1].set(xlabel='Minutes from interface',ylabel='Air-relative speed (km/s)',yscale='log')
    axes[2].plot(alt,[d['dynamic_pressure_pa']/1000 for d in diagnostics]);axes[2].set(xlabel='Altitude (km)',ylabel='Dynamic pressure (kPa)');axes[2].invert_xaxis()
    axes[3].plot(t,[d['sensed_deceleration_g0'] for d in diagnostics]);axes[3].set(xlabel='Minutes from interface',ylabel='Aerodynamic deceleration (Earth g)')
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('Titan entry · '+report['scenario']+'\nHuygens reference atmosphere; simplified vehicle model; no validated landing prediction');fig.tight_layout();save_figure(fig,output/'entry_profile.png');plt.close(fig)
    longitudes=np.degrees(np.unwrap(np.radians([d['longitude_east_deg'] for d in diagnostics])))
    latitude=np.array([d['latitude_deg'] for d in diagnostics]);reference=162.5+360*round((longitudes[0]-162.5)/360)
    fig,ax=plt.subplots(figsize=(9,5));ax.plot(longitudes,latitude,label='Atmospheric ground track');ax.scatter(longitudes[0],latitude[0],s=55,label='Entry interface');ax.scatter(longitudes[-1],latitude[-1],s=75,marker='*',label='Modeled handoff/release');ax.scatter(reference,4.,marker='x',s=70,color='red',label='Selk study reference · 4° N, 162.5° E')
    ax.set(xlabel='Longitude east (degrees, unwrapped)',ylabel='Planetocentric latitude (degrees N)',title='Titan rotating-frame ground track\nReference atmosphere; not a validated landing ellipse');ax.grid(alpha=.2);ax.legend();fig.tight_layout();save_figure(fig,output/'ground_track.png');plt.close(fig)

def save_figure(figure,path):
    """Render before replacing an existing PNG, avoiding partial plot files."""
    buffer=io.BytesIO();figure.savefig(buffer,format='png',dpi=145)
    with tempfile.NamedTemporaryFile(dir=path.parent,suffix='.png',delete=False) as f:
        f.write(buffer.getvalue());temporary=Path(f.name)
    try:os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path,required=True);p.add_argument('--atmosphere',type=Path,default=ROOT/'model_assets/titan/hasi_reference.csv');p.add_argument('--output',type=Path,default=ROOT/'runs/titan_entry');p.add_argument('--beta',type=float,default=70.);p.add_argument('--scenario',choices=['ballistic','illustrative-descent'],default='ballistic');p.add_argument('--density-scale',type=float,default=1.);p.add_argument('--zonal-wind-mps',type=float,default=0.);p.add_argument('--meridional-wind-mps',type=float,default=0.);p.add_argument('--lift-to-drag',type=float,default=0.);p.add_argument('--bank-deg',type=float,default=0.);p.add_argument('--cache',type=Path,help='Optional existing JPL cache for Saturn tides; no data are fetched');p.add_argument('--prefix',type=Path,help='Optional heliocentric cruise XYZV to append to; requires --cache');a=p.parse_args()
    if a.prefix and not a.cache:p.error('--prefix requires an existing Titan JPL cache (--cache)')
    epoch,state=incoming(a.state);atmosphere=Atmosphere(a.atmosphere,a.density_scale);parent=None
    if a.cache:
        from horizons_targets import register_target
        from ephemeris import Ephemerides
        from moon_targeting import BodyVectors
        register_target(dict(name='Titan',id='606',command='606',kind='natural_satellite',parent_body='Saturn'))
        ep=Ephemerides(a.cache,['Saturn','Titan'],epoch-.01,epoch+.26,1/24);sat=BodyVectors(ep,'Saturn');moon=BodyVectors(ep,'Titan')
        parent=lambda t:(sat.position(epoch+t/DAY)-moon.position(epoch+t/DAY))*1000
    report,times,states,diagnostics=integrate(epoch,state,atmosphere,a.beta,a.scenario,a.lift_to_drag,a.bank_deg,a.zonal_wind_mps,a.meridional_wind_mps,saturn_position=parent)
    report['input_state_sha256']=hashlib.sha256(a.state.read_bytes()).hexdigest();export(a.output,report,times,states,diagnostics)
    if a.prefix:
        report['full_trajectory_join']=append_prefix(a.prefix,np.c_[epoch+times/DAY,states],a.cache,a.output)
        atomic_json(a.output/'entry_report.json',report)
    print(json.dumps({k:report[k] for k in ['scenario','outcome','duration_seconds','rows','energy_work_balance_error_j_kg','final_location']},indent=2))
if __name__=='__main__':main()
