"""Publish the independently checked finite Dragonfly-style Titan branch.

Run after moon_targeting.py has produced runs/dragonfly_titan_full. This only
prepares tracked gallery files; it never uploads a native build or edits a seed.
"""
from pathlib import Path
import sys,json,csv,hashlib,shutil
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bootstrap,numpy as np
from scipy.interpolate import CubicHermiteSpline
from ephemeris import AU,DAY,JD0,calendar

def main():
    folder=ROOT/'runs/dragonfly_titan_full';report=json.loads((folder/'moon_report.json').read_text())
    assert report['independent_sun_and_saturn_titan_propagation_passed']
    assert report['independent_endpoint_error_km']<.1 and report['soi_delta_v_kms']==0
    rows=np.loadtxt(folder/'trajectory.xyzv');assert np.all(np.diff(rows[:,0])>0)
    source=json.loads((ROOT/'docs/data/cases/6ef2b7edc240.json').read_text())
    identifier='dragonfly-titan-entry-2035';base='downloads/'+identifier
    for origin,suffix in [('trajectory.xyzv','.xyzv'),('trajectory.csv','.csv'),('moon_report.json','-integration.json'),('burns.csv','-burns.csv'),('README.txt','-README.txt'),('arrival_state.json','-arrival-state.json'),('moon_approach_parent_relative.xyzv','-saturn-relative.xyzv'),('trajectory.png','-arrival.png')]:
        shutil.copy2(folder/origin,ROOT/'docs'/(base+suffix))
    # Include the preserved prefix's audit, referenced by the moon report.
    shutil.copy2(folder/'source_export/integration_report.json',ROOT/'docs'/(base+'-source-integration.json'))
    public_report=json.loads((ROOT/'docs'/(base+'-integration.json')).read_text())
    public_report.update(source_parent_report=identifier+'-source-integration.json',achieved_altitude_km=report['titan_entry_altitude_km'],moon_relative_state_km_kms=report['titan_relative_entry_state_km_kms'],moon_relative_speed_kms=report['titan_relative_inertial_entry_speed_kms'])
    (ROOT/'docs'/(base+'-integration.json')).write_text(json.dumps(public_report,indent=2),encoding='utf-8')
    spline=CubicHermiteSpline((rows[:,0]-JD0)*DAY,rows[:,1:4],rows[:,4:7])
    point=lambda jd:np.round(spline((jd-JD0)*DAY)/AU,10).tolist()
    start,end=rows[0,0],rows[-1,0]
    events=[dict(e,position_au=point(e['jd'])) for e in source['events'][:-1]]
    events[0].update(jd=float(start),date=calendar(start))
    events.append(dict(body='Titan',kind='Entry interface · 1,270 km; no landing model',altitude_km=1270.,jd=float(end),date=calendar(end),position_au=point(end)))
    burns=[]
    with (folder/'burns.csv').open(newline='',encoding='utf-8') as f:
        for b in csv.DictReader(f):
            if b['kind'].startswith('launch_injection'):continue
            jd=float(b['julian_date_tdb']);burns.append(dict(body='DSM',kind='Titan targeting cruise DSM' if b['kind']=='Moon targeting cruise DSM' else b['kind'],jd=jd,date=calendar(jd),magnitude_mps=float(b['magnitude_kms'])*1000,vector_kms=[float(b[k]) for k in ['dx_kms','dy_kms','dz_kms']],position_au=point(jd)))
    assert abs(sum(b['magnitude_mps'] for b in burns)-report['total_onboard_delta_v_kms']*1000)<1e-7
    cuts=sorted(set([float(start),float(end)]+[e['jd'] for e in events[1:-1]]+[b['jd'] for b in burns if b['magnitude_mps']>.1]))
    paths=[]
    for a,b in zip(cuts[:-1],cuts[1:]):
        indices=np.flatnonzero((rows[:,0]>=a)&(rows[:,0]<=b));indices=indices[np.unique(np.linspace(0,len(indices)-1,min(350,len(indices))).astype(int))]
        times=np.unique(np.r_[a,rows[indices,0],b]);paths.append(dict(start=a,end=b,times=times.tolist(),points=[point(t) for t in times]))
    local=np.array(report['state_before_soi_burn_saturn_relative_km_kms']);sat_mu=37931206.234
    vinf=float(np.sqrt(max(0,local[3:]@local[3:]-2*sat_mu/np.linalg.norm(local[:3]))))
    note=(f"Dragonfly-inspired EdvES transfer with a separately targeted Titan arrival on {calendar(end)}. "
          "NASA's current Dragonfly plan reaches Titan in late 2034; this November 2035 case is not its operational trajectory or a date match. "
          f"Retains the finite 2028 launch and 2031 Earth flyby; adds a {report['upstream_delta_v_kms']*1000:.3f} m/s cruise DSM on {calendar(report['upstream_burn_jd_tdb'])}. "
          f"Total onboard cruise delta-v {report['total_onboard_delta_v_kms']*1000:.3f} m/s; launcher injection excluded. No Saturn SOI burn. "
          f"Titan entry at 1,270 km altitude, {report['titan_relative_inertial_entry_speed_kms']:.4f} km/s moon-relative inertial speed, flight-path angle {report['entry_flight_path_angle_deg']:.3f} degrees. "
          "The Arrival V-infinity metric is Saturn-relative at SOI entry, not Titan entry speed. Sun-only cruise, Saturn plus differential Titan gravity locally; no other moons, solar tides inside SOI, J2, rings, atmosphere, descent or landing. No landing-site targeting. Lowest added burn of three tested timings; not a global optimum.")
    files=dict(csv=base+'.csv',xyzv=base+'.xyzv',integration_report=base+'-integration.json',burns=base+'-burns.csv',readme=base+'-README.txt',rows=len(rows),finite_radius=True,coordinates='Sun-centered Ecliptic J2000',units='JD(TDB), km, km/s',note='Complete launch-to-Titan entry path. '+note)
    for ext in ['xyzv','csv']:files[ext+'_sha256']=hashlib.sha256((ROOT/'docs'/files[ext]).read_bytes()).hexdigest()
    case=dict(id=identifier,title='Dragonfly-style Titan entry · 2035',target='Saturn',destination_moon='Titan',sequence='EdvES',bodies=source['bodies'],model='Integrated concept',spotlight=True,start=float(start),end=float(end),launch_date=calendar(start)[:10],arrival_date=calendar(end)[:10],years=float((end-start)/365.25),c3=report['exported_launch_c3_km2_s2'],vinf=vinf,burns_mps=report['total_onboard_delta_v_kms']*1000,
        events=events,burns=burns,flybys=[dict(f,altitude_km=230.1684512113943) for f in source['flybys']],paths=paths,planet_paths=source['planet_paths'],note=note,trajectory_files=files,desktop_handoff_source='6ef2b7edc240',
        provenance=dict(source='Finite EdvES source export plus independently propagated Saturn/Titan arrival',candidate_id=identifier,sha256=files['xyzv_sha256'],coordinates='Heliocentric Ecliptic J2000',time_scale='TDB',plot_units='AU',ephemerides='JPL Horizons planet-center and Titan geometric vectors',export_units='JD TDB, km, km/s; complete launch-to-entry XYZV'),
        moon_arrival=dict(parent='Saturn',moon='Titan',mode='entry',altitude_km=report['titan_entry_altitude_km'],speed_kms=report['titan_relative_inertial_entry_speed_kms'],flight_path_angle_deg=report['entry_flight_path_angle_deg'],independent_endpoint_error_km=report['independent_endpoint_error_km'],atmosphere_modeled=False,landing_site_targeted=False),
        additional_downloads=[dict(label='Saturn-relative Titan approach XYZV ↓',url=base+'-saturn-relative.xyzv'),dict(label='Titan-relative entry state ↓',url=base+'-arrival-state.json'),dict(label='Arrival diagram',url=base+'-arrival.png')])
    case['download']=files['xyzv']
    pathfile=ROOT/'docs/data/cases'/(identifier+'.json')
    if pathfile.exists():
        old=json.loads(pathfile.read_text())
        if old.get('integration_validation'):case['integration_validation']=old['integration_validation']
    pathfile.write_text(json.dumps(case,separators=(',',':')),encoding='utf-8')
    scale=90/max(1.,float(np.max(np.linalg.norm(rows[:,1:3]/AU,axis=1))))
    poly=lambda points:' '.join(f'{160+scale*p[0]:.2f},{105-scale*p[1]:.2f}' for p in points)
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 220"><rect width="320" height="220" fill="#08121e"/>'
    for index,path in enumerate(paths):svg+=f'<polyline points="{poly(path["points"])}" fill="none" stroke="{["#79d8f1","#ffd08a","#8ae3bd"][index%3]}" stroke-width="1.5"/>'
    svg+='<circle cx="160" cy="105" r="3" fill="#ffd08a"/><text x="12" y="207" fill="#b1c5d9" font-family="monospace" font-size="10">EdvES / Titan entry / 2035</text></svg>'
    (ROOT/'docs/images'/(identifier+'.svg')).write_text(svg,encoding='utf-8')
    index_path=ROOT/'docs/data/index.json';index=json.loads(index_path.read_text());summary={k:case[k] for k in ['id','title','target','sequence','bodies','model','spotlight','start','end','launch_date','arrival_date','years','c3','vinf','burns_mps']}
    index['cases']=[c for c in index['cases'] if c['id']!=identifier]+[summary];index['updated']=datetime.now(timezone.utc).isoformat();index_path.write_text(json.dumps(index,separators=(',',':')),encoding='utf-8')
    annotations=ROOT/'docs/data/mission_annotations.json';data=json.loads(annotations.read_text());data['missions'][identifier]=dict(label=case['title'],mission_kind='reconstruction',featured_priority=17,note='Dragonfly-inspired Titan entry; arrives November 2035 rather than the planned late 2034. Atmospheric entry and landing are not propagated.');annotations.write_text(json.dumps(data,indent=2),encoding='utf-8')
    publications=ROOT/'docs/data/publication_dates.json';data=json.loads(publications.read_text());data['candidates'].setdefault(identifier,dict(added_at=datetime.now(timezone.utc).isoformat(),basis='First publication of finite Dragonfly-style Titan arrival'));publications.write_text(json.dumps(data,separators=(',',':')),encoding='utf-8')
    print(identifier,case['years'],files['rows'],report['upstream_delta_v_kms']*1000)

if __name__=='__main__':main()
