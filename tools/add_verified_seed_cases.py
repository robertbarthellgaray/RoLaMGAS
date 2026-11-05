"""Publish independently audited full-chain seed cases with CSV / XYZV downloads.
No search, network or finite-radius flyby claims. Existing catalog cases remain.
"""
from pathlib import Path
import argparse,json,sys,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
import numpy as np
from dynamics import kepler
from ephemeris import BODIES,Ephemerides,AU,DAY
from catalog_validation import audit_candidate
from build_trajectory_downloads import sample_coasts
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,value):p.write_text(json.dumps(value,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
def add(run,cache,docs):
    cfg=read(run/'run_manifest.json')['config'];index=read(docs/'data/index.json')
    # One representative per identical encounter-day string, as in the shared library.
    for seed in [min(read(run/'results.json')['candidates'],key=lambda q:q['launch_c3_km2_s2'])]:
        ident=seed['id'];q=read(run/'candidates'/(ident+'.json'));card=read(run/'candidates'/(ident+'.card.json'))
        audit=audit_candidate(q,cfg,BODIES)
        if not audit['passed']:raise ValueError(audit['reasons'])
        ep=Ephemerides(cache,q['bodies'],q['dates_jd_tdb'][0],q['dates_jd_tdb'][-1],1.)
        residual=np.array([ep.state(e['body'],e['julian_date_tdb'])-e['planet_state_km_kms'] for e in q['events']])
        pos=float(np.max(np.linalg.norm(residual[:,:3],axis=1)));vel=float(np.max(np.linalg.norm(residual[:,3:],axis=1))*1000)
        endpoint=0.;speed=0.
        for k,s in enumerate(q['segments']):
            r,v=kepler(np.array(s['r']),np.array(s['v']),(s['end_jd']-s['start_jd'])*DAY)
            event=next((j for j,e in enumerate(q['events']) if abs(e['julian_date_tdb']-s['end_jd'])<1e-8),None)
            expected=np.array(q['events'][event]['planet_state_km_kms'][:3]) if event is not None else np.array(q['segments'][k+1]['r'])
            endpoint=max(endpoint,float(np.linalg.norm(r-expected)))
            if event is not None:speed=max(speed,float(np.linalg.norm(v-np.array(q['arrival_velocities_kms'][event-1]))*1000))
        if pos>.1 or vel>.001 or endpoint>1 or speed>.01:raise ValueError('Independent JPL / coast-state discrepancy')
        audit.update(max_reference_ephemeris_position_error_km=pos,max_reference_ephemeris_velocity_error_mps=vel,max_coast_endpoint_error_km=endpoint,max_coast_velocity_error_mps=speed)
        events=[dict(body=e['body'],jd=e['julian_date_tdb'],date=e['date'],position_au=(np.array(e['planet_state_km_kms'][:3])/AU).tolist(),kind='Departure' if i==0 else 'Arrival' if i==len(q['events'])-1 else 'Flyby') for i,e in enumerate(q['events'])]
        burns=[dict(kind='DSM',jd=b['julian_date_tdb'],date=b['date'],magnitude_mps=b['magnitude_kms']*1000,position_au=(np.array(b['position_km'])/AU).tolist()) for b in q['dsms']]
        flybys=[dict(body=f['body'],jd=f['julian_date_tdb'],date=f['date'],mismatch_mps=f['speed_mismatch_mps'],altitude_km=f['conservative_equal_speed_altitude_km'],altitude_floor_km=f['minimum_altitude_km']) for f in q['flybys']]
        paths=[dict(start=s['start_jd'],end=s['end_jd'],points=points) for s,points in zip(q['segments'],card['paths'])]
        note='Solver-built low-launch-energy EdvEVEEJ family, not the flown JUICE mission. Sun-only Lambert/Kepler arcs join at planet centers. Flyby altitudes are inferred from asymptotic turns, not resolved closest approaches. The first-leg DSM trades against C3. Finite-radius flyby targeting, lunar assists, launch injection and Jupiter capture are excluded.'
        c=dict(id=ident,title='Low-energy Jupiter · '+q['sequence'],target='Jupiter',target_id='599',sequence=q['sequence'],bodies=q['bodies'],model='Lambert candidate',spotlight=False,featured_priority=2 if ident=='4d76acaf1f6f' else 0,start=q['dates_jd_tdb'][0],end=q['dates_jd_tdb'][-1],launch_date=q['launch_date'][:10],arrival_date=q['arrival_date'][:10],years=q['duration_years'],c3=q['launch_c3_km2_s2'],vinf=q['arrival_vinf_kms'],burns_mps=q['total_dsm_kms']*1000,paths=paths,coasts=q['segments'],planet_paths=card['planet_paths'],events=events,burns=burns,flybys=flybys,validation=audit,note=note,provenance=dict(source='Recomputed complete RoLaMGAS seed family',candidate_id=ident,coordinates='Heliocentric Ecliptic J2000',time_scale='TDB',plot_units='AU',ephemerides='JPL Horizons geometric vectors',target_horizons_id='599'))
        data,error=sample_coasts(q['segments']);stem=docs/'downloads'/ident;csvpath=stem.with_suffix('.csv');xyzvpath=stem.with_suffix('.xyzv');readmepath=docs/'downloads'/(ident+'-README.txt')
        np.savetxt(csvpath,data,delimiter=',',fmt=['%.12f']+['%.9f']*6,header='jd_tdb,x_km,y_km,z_km,vx_km_s,vy_km_s,vz_km_s',comments='')
        np.savetxt(xyzvpath,data,fmt=['%.12f']+['%.9f']*6,header=f'RoLaMGAS {ident} | IDEAL LAMBERT COASTS\nJD(TDB) x_km y_km z_km vx_km_s vy_km_s vz_km_s | Sun-centered Ecliptic J2000\n{note}\nBegin {data[0,0]:.12f} End {data[-1,0]:.12f}')
        for p in [csvpath,xyzvpath]:p.write_bytes(p.read_bytes().replace(b'\r\n',b'\n'))
        readmepath.write_text(note+'\nColumns: JD(TDB), x_km, y_km, z_km, vx_km_s, vy_km_s, vz_km_s. Sun-centered Ecliptic J2000.\n',encoding='utf-8')
        c['trajectory_files']=dict(csv='downloads/'+csvpath.name,xyzv='downloads/'+xyzvpath.name,readme='downloads/'+readmepath.name,rows=len(data),units='JD(TDB), km, km/s',coordinates='Sun-centered Ecliptic J2000',source='Saved full-precision solar coast initial conditions',note=note,csv_sha256=hashlib.sha256(csvpath.read_bytes()).hexdigest(),xyzv_sha256=hashlib.sha256(xyzvpath.read_bytes()).hexdigest(),max_checked_hermite_position_error_km=error)
        save(docs/'data/cases'/(ident+'.json'),c)
        summary={key:c[key] for key in ['id','title','target','target_id','sequence','bodies','model','spotlight','featured_priority','start','end','launch_date','arrival_date','years','c3','vinf','burns_mps']};index['cases']=[r for r in index['cases'] if r['id']!=ident]+[summary]
        points=np.array([p for path in paths for p in path['points']]);extent=max(float(np.max(abs(points[:,:2]))),1)*1.15
        def poly(points):return ' '.join(f'{160+p[0]/extent*140:.2f},{110-p[1]/extent*90:.2f}' for p in points)
        svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 220"><rect width="320" height="220" fill="#08121e"/>'
        for k,path in enumerate(paths):svg+=f'<polyline points="{poly(path["points"])}" fill="none" stroke="{["#79d8f1","#ffd08a","#8ae3bd"][k%3]}" stroke-width="1.5"/>'
        svg+='<circle cx="160" cy="110" r="3" fill="#ffd08a"/></svg>';(docs/'images'/(ident+'.svg')).write_text(svg,encoding='utf-8');print(ident,'audited, CSV/XYZV',len(data),'rows',flush=True)
    save(docs/'data/index.json',index)
    path=docs/'data/catalog_audit.json';audit=read(path);cases=[read(docs/'data/cases'/(r['id']+'.json')) for r in index['cases']];lambert=[c for c in cases if c['model']=='Lambert candidate'];audit.update(lambert_candidates=len(lambert),all_published_lambert_candidates_pass=all(c['validation']['passed'] for c in lambert),routes_by_target={t:sorted({c['sequence'] for c in cases if c['target']==t}) for t in sorted({c['target'] for c in cases})});save(path,audit)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);a=p.parse_args();add(a.run,a.cache,ROOT/'docs')
