"""Test a saved final solar coast with explicit Saturn-SOI targeting of Titan.

python tools/target_titan_arrival.py --case docs/data/cases/6ef2b7edc240.json
Outputs a separate arrival segment and burn/entry report; no source is changed.
"""
from pathlib import Path
import argparse,json,sys,csv
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bootstrap,numpy as np
from ephemeris import Ephemerides,fetch,calendar,atomic_json,DAY
from horizons_targets import register_target
from moon_arrival import target_arrival,target_upstream,solar_state
from dynamics import lambert

def cached(cache,body,start,end,step):
    try:return Ephemerides(cache,[body],start,end,step)
    except ValueError:
        print('Downloading JPL',body,calendar(start),calendar(end),'step',step,'days',flush=True)
        fetch(cache,body,start-1,end+1,step);return Ephemerides(cache,[body],start,end,step)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',type=Path,required=True);p.add_argument('--cache',type=Path,default=ROOT/'cache');p.add_argument('--output',type=Path,default=ROOT/'runs/titan_arrival');p.add_argument('--entry-altitude-km',type=float,default=1270.);p.add_argument('--illustrative-gamma-deg',type=float,default=-65.);p.add_argument('--clock-deg',type=float,default=0.);p.add_argument('--heliocentric-seed',choices=['saved','moon'],default='saved');p.add_argument('--upstream-burn-fraction',type=float,help='Jointly target a real cruise DSM instead of applying a Saturn SOI burn');a=p.parse_args()
    source=json.loads(a.case.read_text(encoding='utf-8'));segments=source.get('coasts',source.get('segments'))
    if not segments:raise ValueError('Provide a case/public science record with retained solar coast states')
    segment=dict(segments[-1]);arrival=float(source.get('end',segment['end_jd']))
    sat=cached(a.cache,'Saturn',segment['start_jd']-1,arrival+2,1.)
    register_target(dict(name='Titan',id='606',command='606',kind='natural_satellite',parent_body='Saturn'))
    moon=cached(a.cache,'Titan',max(segment['start_jd'],arrival-1002),arrival+2,1/24)
    upstream_delta=np.zeros(3)
    if a.heliocentric_seed=='moon':
        old_velocity=np.asarray(segment['v']);v,_=lambert(np.asarray(segment['r']),moon.state('Titan',arrival)[:3],arrival-segment['start_jd'],[0,True]);segment['v']=v.tolist();upstream_delta=v-old_velocity
    print('Solving Saturn-SOI velocity correction to Titan entry…',flush=True)
    report,dates,relative=target_arrival(segment,arrival,lambda t:sat.state('Saturn',t),lambda t:moon.state('Titan',t),a.entry_altitude_km,a.illustrative_gamma_deg,a.clock_deg)
    if a.upstream_burn_fraction is not None:
        if a.heliocentric_seed!='saved':raise ValueError('Upstream correction must start from the saved coast to preserve earlier flybys')
        print('Jointly targeting an earlier cruise DSM and continuous Saturn SOI passage...',flush=True)
        report,dates,relative=target_upstream(segment,arrival,lambda t:sat.state('Saturn',t),lambda t:moon.state('Titan',t),report,a.upstream_burn_fraction)
    report.update(source_candidate_id=source.get('id'),source_sequence=source.get('sequence'),heliocentric_seed=a.heliocentric_seed,
        upstream_departure_velocity_change_kms=upstream_delta.tolist(),upstream_departure_velocity_change_magnitude_kms=float(np.linalg.norm(upstream_delta)),
        upstream_note='Saved final coast preserved.' if a.heliocentric_seed=='saved' else 'Final solar Lambert endpoint changed from planet to Titan center. This departure-vector change requires upstream flyby/DSM reoptimization; it is not a free correction or a verified new mission.',
        soi_burn_date=calendar(report['entry_jd_tdb']),arrival_date=calendar(arrival),
        source_designed_cruise_delta_v_kms=source.get('burns_mps',0)/1000 if 'burns_mps' in source else source.get('metrics',{}).get('total_dsm_kms'),
        ephemeris_sources={'Saturn':sat.manifest['Saturn'],'Titan':moon.manifest['Titan']})
    if 'upstream_delta_v_kms' in report:report['upstream_note']='Preserves the saved coast through the additional cruise DSM, and preserves all earlier legs and flybys.'
    export_products(a.output,report,dates,relative,sat,moon)
    fields=['soi_burn_date','arrival_date','soi_delta_v_kms','titan_entry_altitude_km','titan_relative_inertial_entry_speed_kms','entry_flight_path_angle_deg','independent_endpoint_error_km','upstream_departure_velocity_change_magnitude_kms']
    if 'upstream_delta_v_kms' in report:fields+=['upstream_burn_jd_tdb','upstream_delta_v_kms','soi_velocity_matching_residual_kms']
    print(json.dumps({k:report[k] for k in fields},indent=2),flush=True)

def export_products(output,report,dates,relative,sat,moon):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    report['soi_transition_date']=calendar(report['entry_jd_tdb'])
    if 'upstream_burn_jd_tdb' in report:report['cruise_correction_date']=calendar(report['upstream_burn_jd_tdb'])
    atomic_json(output/'arrival_report.json',report)
    heliocentric=relative+np.array([sat.state('Saturn',t) for t in dates])
    products=[('saturn_relative',dates,relative),('heliocentric',dates,heliocentric)]
    if 'upstream_burn_jd_tdb' in report:
        segment=dict(start_jd=report['upstream_burn_jd_tdb'],r=report['upstream_burn_position_heliocentric_km'],v=report['upstream_post_burn_velocity_heliocentric_kms'])
        before=np.arange(segment['start_jd'],dates[0],.25)
        products.append(('cruise_and_arrival_heliocentric',np.r_[before,dates],np.vstack([[solar_state(segment,t) for t in before],heliocentric])))
    for name,epochs,states in products:
        rows=np.c_[epochs,states]
        with (output/(name+'.csv')).open('w',newline='',encoding='utf-8') as stream:
            w=csv.writer(stream);w.writerow(['jd_tdb','x_km','y_km','z_km','vx_kms','vy_kms','vz_kms']);w.writerows(rows)
        with (output/(name+'.xyzv')).open('w',encoding='utf-8') as stream:
            stream.write('# Separate approach segment only; '+name+' Ecliptic J2000; TDB JD, km, km/s\n')
            for row in rows:stream.write(f'{row[0]:.10f} '+' '.join(f'{v:.10f}' for v in row[1:])+'\n')
    plot(output,dates,relative,report,sat,moon)

def plot(folder,dates,states,report,sat,moon):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,5));m=np.array([moon.state('Titan',t)-sat.state('Saturn',t) for t in dates]);days=dates-dates[-1]
    close=np.linalg.norm(states[:,:3],axis=1)<3e6
    axes[0].plot(states[close,0]/1e6,states[close,1]/1e6,label='Probe');axes[0].plot(m[:,0]/1e6,m[:,1]/1e6,lw=.7,alpha=.5,label='Titan');axes[0].scatter(0,0,color='orange',label='Saturn');axes[0].scatter(m[-1,0]/1e6,m[-1,1]/1e6,marker='*',s=80,label='Titan at entry');axes[0].set_aspect('equal',adjustable='datalim');axes[0].set(xlabel='Saturn-relative x (million km)',ylabel='y (million km)');axes[0].legend()
    near=days>=-2;distance=np.linalg.norm(states[:,:3]-m[:,:3],axis=1)-2574.76
    axes[1].plot(days[near]*24,distance[near]);axes[1].axhline(report['titan_entry_altitude_km'],ls='--',color='orange');axes[1].set(xlabel='Hours before entry',ylabel='Titan altitude (km)',yscale='log');axes[1].grid(alpha=.2)
    burn=f"Cruise DSM {report['upstream_delta_v_kms']*1000:.1f} m/s; no SOI burn" if 'upstream_delta_v_kms' in report else f"SOI correction {report['soi_delta_v_kms']*1000:.1f} m/s"
    fig.suptitle(f"Titan arrival test — {burn}; entry {report['titan_relative_inertial_entry_speed_kms']:.2f} km/s\nIllustrative entry geometry; no atmosphere or landing model");fig.tight_layout();fig.savefig(folder/'arrival.png',dpi=145);plt.close(fig)
if __name__=='__main__':main()
