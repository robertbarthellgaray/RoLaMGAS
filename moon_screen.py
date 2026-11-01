"""Rank nominal Saturn arrivals by Titan distance; a seed screen, not targeting."""
import bootstrap  # noqa: F401
from pathlib import Path
import argparse
import csv
import json
import math
import re
import traceback
import numpy as np
from scipy.optimize import minimize_scalar
from ephemeris import BODIES,DAY,JD0,Ephemerides,fetch,atomic_json,calendar
from horizons_targets import register_target
from integrate_export import planet_pieces,integrate_relative,hyperbolic_time,unit

TITAN_RADIUS=2574.76  # km; https://ssd.jpl.nasa.gov/sats/phys_par/ (SAT441)


def rotation(axis,angle):
    x,y,z=unit(axis);cross=np.array([[0.,-z,y],[z,0.,-x],[-y,x,0.]])
    return np.eye(3)*np.cos(angle)+(1-np.cos(angle))*np.outer([x,y,z],[x,y,z])+np.sin(angle)*cross


def refined_minimum(function,grid,values):
    """Refine every bracketed minimum, in relative seconds rather than large JD."""
    candidates=[(float(values[0]),float(grid[0])),(float(values[-1]),float(grid[-1]))]
    for i in np.flatnonzero((values[1:-1]<=values[:-2])&(values[1:-1]<=values[2:]))+1:
        fit=minimize_scalar(function,bounds=(grid[i-1],grid[i+1]),method='bounded',options={'xatol':.005})
        candidates.append((float(fit.fun),float(fit.x)))
    return min(candidates)


def cached(cache,body,start,end,step):
    try:return Ephemerides(cache,[body],start,end,step)
    except ValueError:
        # Each interval is a single SOI transit, not a multi-decade hourly download.
        fetch(cache,body,start-1,end+1,step)
        return Ephemerides(cache,[body],start,end,step)


def screen_candidate(q,cache,altitude,clocks):
    epoch=q['events'][-1]['julian_date_tdb'];uin=np.array(q['arrival_vinf_vector_kms'])
    sat=cached(cache,'Saturn',epoch-800,epoch+800,1.)
    node=planet_pieces('Saturn',epoch,sat,uin=uin,altitude=altitude,terminal=True)
    duration=hyperbolic_time(BODIES['Saturn'][1],node['rp'],np.linalg.norm(uin),node['soi'])
    start,end=epoch-duration/DAY,epoch+duration/DAY
    moon=cached(cache,'Titan',start,end,1/24)
    solution,error=integrate_relative(BODIES['Saturn'][1],node['peri_position'],node['peri_in_velocity'],-duration,duration)
    grid=np.linspace(-duration,duration,max(3,int(math.ceil(2*duration/3600))+1))
    dates=epoch+grid/DAY;t=(dates-JD0)*DAY
    moon_states=np.c_[moon.splines['Titan'](t)-sat.splines['Saturn'](t),moon.splines['Titan'](t,1)-sat.splines['Saturn'](t,1)]
    probe=solution(grid).T;best=None
    for clock in np.arange(clocks)*360/clocks:
        rotate=rotation(uin,math.radians(float(clock)))
        xyz=probe[:,:3]@rotate.T
        distances=np.linalg.norm(xyz-moon_states[:,:3],axis=1)
        def distance(seconds):
            date=epoch+seconds/DAY
            relative_moon=moon.state('Titan',date)-sat.state('Saturn',date)
            return float(np.linalg.norm(rotate@solution(seconds)[:3]-relative_moon[:3]))
        value,seconds=refined_minimum(distance,grid,distances)
        if best is None or value<best[0]:best=(value,seconds,float(clock),rotate)
    distance,seconds,clock,rotate=best;date=epoch+seconds/DAY
    state=solution(seconds);state=np.r_[rotate@state[:3],rotate@state[3:]]
    titan=moon.state('Titan',date)-sat.state('Saturn',date)
    row=dict(candidate_id=q['id'],sequence=q['sequence'],source_status=q['status'],
             closest_jd_tdb=date,closest_date=calendar(date),distance_km=distance,altitude_km=distance-TITAN_RADIUS,
             relative_speed_kms=float(np.linalg.norm(state[3:]-titan[3:])),
             saturn_periapsis_altitude_km=altitude,b_plane_clock_deg=clock,
             saturn_periapsis_jd_tdb=epoch,launch_c3_km2_s2=q['launch_c3_km2_s2'],
             probe_state_saturn_relative_km_kms=state.tolist(),titan_state_saturn_relative_km_kms=titan.tolist(),
             probe_state_titan_relative_km_kms=(state-titan).tolist(),
             saturn_integration_endpoint_error_km=error,
             window_start_jd_tdb=start,window_end_jd_tdb=end,
             ephemeris_sources=dict(Saturn=sat.manifest['Saturn'],Titan=moon.manifest['Titan']))
    # Include distance-history data near closest approach for manual review.
    selection=np.abs(grid-seconds)<2*DAY
    return row,dict(hours=(grid[selection]-seconds)/3600,
                    distance=np.linalg.norm(probe[selection,:3]@rotate.T-moon_states[selection,:3],axis=1))


def run(folder,cache,count=10,altitude=10000.,clocks=12):
    folder=Path(folder);output=folder/'moon_screen';output.mkdir(exist_ok=True)
    if not 1<=count<=1000 or not 1<=clocks<=72 or not math.isfinite(altitude) or altitude<=0:raise ValueError('Invalid screening count, clock count or Saturn periapsis altitude')
    register_target(dict(name='Titan',id='606',command='606',kind='natural_satellite',parent_body='Saturn'))
    candidates=[]
    for path in (folder/'candidates').glob('*.json'):
        if not re.fullmatch('[a-f0-9]{12}',path.stem):continue
        q=json.loads(path.read_text())
        if q['events'][-1]['body']=='Saturn':candidates.append(q)
    candidates.sort(key=lambda q:(not q['status'].startswith('passes'),q['launch_c3_km2_s2'],q['total_dsm_kms']))
    selected=candidates[:count]
    if not selected:raise ValueError('Open a saved search whose final destination is Saturn; no Saturn-arrival candidates found.')
    rows=[];errors=[]
    def status(state,message):
        fields=['candidate_id','sequence','closest_date','closest_jd_tdb','distance_km','altitude_km','relative_speed_kms','b_plane_clock_deg','saturn_periapsis_altitude_km','source_status']
        temporary=output/'ranked.csv.tmp'
        with temporary.open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(sorted(rows,key=lambda r:r['distance_km']))
        temporary.replace(output/'ranked.csv')
        atomic_json(output/'status.json',dict(state=state,message=message,completed=len(rows)+len(errors),total=len(selected),
                    available=len(candidates),rows=sorted(rows,key=lambda r:r['distance_km']),errors=errors,
                    model='Saturn-only gravity, full inbound/outbound SOI transit; hourly JPL Titan vectors; sampled B-plane clock angles. No Titan gravity, Sun perturbations, atmosphere, rings, JOI or upstream retargeting validation. Closest-approach seeds only.',
                    selection='Passing candidates first, then lowest C3 and DSM; screen count limits this subset.'))
    status('running','Preparing Saturn/Titan screening…')
    for i,q in enumerate(selected):
        status('running',f"Candidate {i+1}/{len(selected)}: {q['id']} — hourly Titan cache/download, Saturn integration, {clocks} clock angles")
        try:
            row,history=screen_candidate(q,cache,altitude,clocks)
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig,ax=plt.subplots(figsize=(8,4));ax.plot(history['hours'],history['distance']/1000)
            ax.set(xlabel='Hours from refined closest approach',ylabel='Titan center distance (thousand km)',
                   title=f"{q['id']} · altitude {row['altitude_km']:,.0f} km · clock {row['b_plane_clock_deg']:.0f}°")
            ax.grid(alpha=.3);fig.tight_layout();fig.savefig(output/(q['id']+'.png'),dpi=130);plt.close(fig)
            row['picture']=q['id']+'.png';rows.append(row)
        except Exception as exc:errors.append(dict(candidate_id=q['id'],error=str(exc)))
        status('running',f'Completed {i+1}/{len(selected)} candidates')
    rows.sort(key=lambda r:r['distance_km'])
    fields=['candidate_id','sequence','closest_date','closest_jd_tdb','distance_km','altitude_km','relative_speed_kms','b_plane_clock_deg','saturn_periapsis_altitude_km','source_status']
    with (output/'ranked.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    status('finished',f'Screened {len(rows)} candidates; {len(errors)} errors. Sorted by Titan center distance.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--cache',required=True);p.add_argument('--count',type=int,default=10);p.add_argument('--altitude',type=float,default=10000);p.add_argument('--clocks',type=int,default=12);a=p.parse_args()
    try:run(a.run,a.cache,a.count,a.altitude,a.clocks)
    except Exception as exc:
        atomic_json(Path(a.run)/'moon_screen/status.json',dict(state='failed',message=str(exc)));traceback.print_exc();raise
