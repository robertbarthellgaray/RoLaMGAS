"""Reproduce reference-entry comparisons and atmospheric sensitivity cases.

No online service is called. Density/wind changes are deterministic scenarios,
not a Monte Carlo uncertainty distribution or a landing ellipse.
"""
from pathlib import Path
import argparse,csv,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from titan_entry import Atmosphere,integrate,export,incoming,RADIUS,OMEGA
from moon_targets import titan_target_normal,titan_body_axes
from ephemeris import atomic_json

def reference_state(epoch,speed,gamma):
    normal=titan_target_normal(epoch,0.,0.);axes=titan_body_axes(epoch);r=(RADIUS+1270000)*normal
    velocity=speed*(np.sin(np.radians(gamma))*normal+np.cos(np.radians(gamma))*axes[1])+np.cross(OMEGA*axes[2],r)
    return np.r_[r,velocity]/1000

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path,default=ROOT/'docs/downloads/dragonfly-titan-entry-2035-arrival-state.json');p.add_argument('--output',type=Path,default=ROOT/'runs/titan_entry_study');p.add_argument('--summary',type=Path,default=ROOT/'studies/titan_entry/validation.json');a=p.parse_args()
    epoch,actual=incoming(a.state);atmosphere_file=ROOT/'model_assets/titan/hasi_reference.csv';summaries=[]
    cases=[('NASA_Dragonfly_reference_2024',reference_state(epoch,7300.,-48.),70.,1.,0.,9190.),('Huygens_reference',reference_state(epoch,6000.,-65.5),35.,1.,0.,4640.),('Saved_arrival_nominal',actual,70.,1.,0.,None),('Saved_arrival_density_80pct',actual,70.,.8,0.,None),('Saved_arrival_density_120pct',actual,70.,1.2,0.,None),('Saved_arrival_east_wind_50mps',actual,70.,1.,50.,None)]
    for name,state,beta,scale,wind,published in cases:
        atmosphere=Atmosphere(atmosphere_file,scale);report,times,states,diagnostics=integrate(epoch,state,atmosphere,beta=beta,zonal=wind)
        export(a.output/name,report,times,states,diagnostics)
        peak=report['peak_dynamic_pressure'];row=dict(case=name,beta_kg_m2=beta,density_multiplier=scale,zonal_wind_mps=wind,entry_air_speed_mps=report['initial_air_speed_mps'],entry_air_flight_path_angle_deg=report['initial_air_relative_flight_path_angle_deg'],handoff_seconds=report['duration_seconds'],handoff_altitude_km=diagnostics[-1]['altitude_m']/1000,peak_dynamic_pressure_pa=peak['dynamic_pressure_pa'],published_reference_peak_q_pa=published,peak_q_difference_pct=None if published is None else 100*(peak['dynamic_pressure_pa']/published-1),peak_deceleration_g0=report['peak_sensed_deceleration']['sensed_deceleration_g0'],energy_work_balance_error_j_kg=report['energy_work_balance_error_j_kg'])
        summaries.append(row);print(json.dumps(row),flush=True)
    a.summary.parent.mkdir(parents=True,exist_ok=True)
    atomic_json(a.summary,dict(cases=summaries,scope='Constant-beta 3-DOF entries into the Huygens reference column; Saturn tides omitted in these comparative runs. Not official mission state reproductions.',reference='https://ntrs.nasa.gov/citations/20240007259',interpretation='Published peak pressures come from a different complete vehicle/atmosphere simulation. Deviations measure model differences; coefficients were not tuned to match these peaks.'))
    with a.summary.with_suffix('.csv').open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(summaries[0]));w.writeheader();w.writerows(summaries)

if __name__=='__main__':main()
