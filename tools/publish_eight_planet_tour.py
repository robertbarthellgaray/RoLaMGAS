"""Publish the owner-approved ReachStar research recreation, not a standard seed.

Keeps the usual public-library altitude policy unchanged. No backend or binary
upload is performed. All underlying JPL vectors must already be cached.
"""
from pathlib import Path
import hashlib,json,shutil,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bootstrap,numpy as np
from ephemeris import Ephemerides,BODIES,AU,DAY
from dynamics import kepler
from catalog_validation import audit_candidate
from study_resonant_transfers import audit_coasts,physical_record
from trajectory_transfer import materialize
from mission_search import normalize,routes_for
from live_gallery import card_data
from build_trajectory_downloads import sample_coasts

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'studies/eight_planet_tour/verified_source_recreation'
TITLE='ReachStar’s Eight-Planet Grand Tour'
CREDIT='Original RSS/Principia trajectory design by ReachStar on Bilibili; date-adjusted JPL patched-conic recreation in RoLaMGAS.'
NOTE=(CREDIT+' This is not an exact Principia replay. Inner encounters differ by up to about one day; outer encounters shift by approximately 5–19 days. '
      'C3 is 13.43529 km²/s²; ideal injection from 200 km LEO is 3.81853 km/s. '
      'The two modeled solar corrections total 0.02727 m/s, not an n-body navigation budget; the source table lists 4.54 m/s of TCMs. '
      'Research altitude exceptions: Earth 130 km and Venus 250 km minimum, below standard gallery floors. Atmosphere, moons, heating and navigation uncertainty are excluded. '
      'Solar coasts meet at ideal planet centers; flyby altitudes are inferred asymptotic turns, not resolved finite-radius flybys. Desktop finite-radius export can add corrections.')

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')

def main():
    docs=ROOT/'docs';q=read(RUN/'candidate.json');cfg=normalize(read(RUN/'run_manifest.json')['config'])
    ep=Ephemerides(ROOT/'cache',q['bodies'],q['dates_jd_tdb'][0]-1,q['dates_jd_tdb'][-1]+1,1.)
    research_bodies={b:(d[0],d[1],d[2],cfg['minimum_altitude_km'].get(b,d[3])) for b,d in BODIES.items()}
    audit=audit_candidate(q,cfg,research_bodies);standard=audit_candidate(q,cfg,BODIES);coasts=audit_coasts(q)
    if not audit['passed'] or not coasts['passed']:raise ValueError((audit,coasts))
    delta=np.array([ep.state(e['body'],e['julian_date_tdb'])-e['planet_state_km_kms'] for e in q['events']])
    pos=float(np.max(np.linalg.norm(delta[:,:3],axis=1)));vel=float(np.max(np.linalg.norm(delta[:,3:],axis=1))*1000)
    if pos>.1 or vel>.001:raise ValueError('JPL state mismatch')
    endpoint=0.
    for i,s in enumerate(q['segments']):
        r,v=kepler(np.array(s['r']),np.array(s['v']),(s['end_jd']-s['start_jd'])*DAY)
        e=next((e for e in q['events'] if abs(e['julian_date_tdb']-s['end_jd'])<1e-8),None)
        expected=e['planet_state_km_kms'][:3] if e else q['segments'][i+1]['r']
        endpoint=max(endpoint,float(np.linalg.norm(r-expected)))
    if endpoint>1.:raise ValueError('Coast endpoint discrepancy')
    audit.update(max_reference_ephemeris_position_error_km=pos,max_reference_ephemeris_velocity_error_mps=vel,
                 max_coast_endpoint_error_km=endpoint,scope='Research altitude exceptions only; independent solar coasts and vector checks, not atmosphere or n-body validation')
    record=physical_record(q,cfg);loaded=materialize(record,cfg,routes_for(cfg)[0],ep)
    if loaded['status']!='passes_configured_patched_conic_screen':raise ValueError('Desktop import failed')
    card=card_data(q,ep);ident=q['id']
    events=[dict(body=e['body'],jd=e['julian_date_tdb'],date=e['date'],position_au=(np.array(e['planet_state_km_kms'][:3])/AU).tolist(),kind='Departure' if i==0 else 'Arrival' if i==len(q['events'])-1 else 'Flyby') for i,e in enumerate(q['events'])]
    burns=[dict(kind='DSM',jd=b['julian_date_tdb'],date=b['date'],magnitude_mps=b['magnitude_kms']*1000,position_au=(np.array(b['position_km'])/AU).tolist()) for b in q['dsms']]
    flybys=[dict(body=f['body'],jd=f['julian_date_tdb'],date=f['date'],mismatch_mps=f['speed_mismatch_mps'],altitude_km=f['conservative_equal_speed_altitude_km'],altitude_floor_km=f['minimum_altitude_km']) for f in q['flybys']]
    paths=[dict(start=s['start_jd'],end=s['end_jd'],points=points) for s,points in zip(q['segments'],card['paths'])]
    c=dict(id=ident,title=TITLE,target='Neptune',target_id='899',sequence=q['sequence'],bodies=q['bodies'],
           model='Research patched-conic recreation',spotlight=False,featured_priority=12,
           start=q['dates_jd_tdb'][0],end=q['dates_jd_tdb'][-1],launch_date=q['launch_date'][:10],arrival_date=q['arrival_date'][:10],
           years=q['duration_years'],c3=q['launch_c3_km2_s2'],vinf=q['arrival_vinf_kms'],burns_mps=q['total_dsm_kms']*1000,
           paths=paths,coasts=q['segments'],planet_paths=card['planet_paths'],events=events,burns=burns,flybys=flybys,
           powered_flybys=False,validation=audit,standard_catalog_audit=standard,independent_solar_audit=coasts,
           research_altitude_exception='Owner-approved research recreation: Earth minimum 130 km and Venus minimum 250 km. Standard public-library floors remain unchanged. Atmospheric survival is not validated.',
           note=NOTE,provenance=dict(source=CREDIT,credit='ReachStar on Bilibili',candidate_id=ident,coordinates='Heliocentric Ecliptic J2000',time_scale='TDB',plot_units='AU',ephemerides='JPL Horizons geometric vectors',target_horizons_id='899'))
    data,error=sample_coasts(q['segments']);csvpath=docs/'downloads'/f'{ident}.csv';xyzvpath=docs/'downloads'/f'{ident}-analysis.xyzv';readmepath=docs/'downloads'/f'{ident}-README.txt'
    np.savetxt(csvpath,data,delimiter=',',fmt=['%.12f']+['%.9f']*6,header='jd_tdb,x_km,y_km,z_km,vx_km_s,vy_km_s,vz_km_s',comments='')
    np.savetxt(xyzvpath,data,fmt=['%.12f']+['%.9f']*6,header=TITLE+' | ANALYSIS ONLY: ideal planet-center joins, not finite-radius flybys\n'+NOTE+'\nJD(TDB) x_km y_km z_km vx_km_s vy_km_s vz_km_s; heliocentric Ecliptic J2000')
    for p in (csvpath,xyzvpath):p.write_bytes(p.read_bytes().replace(b'\r\n',b'\n'))
    readmepath.write_text(TITLE+'\n'+NOTE+'\n\nAnalysis CSV: JD(TDB), x/y/z km, vx/vy/vz km/s, heliocentric Ecliptic J2000. Ideal center-node solar coasts, not a collision-free Celestia export.\n',encoding='utf-8')
    c['trajectory_files']=dict(csv='downloads/'+csvpath.name,xyzv='downloads/'+xyzvpath.name,readme='downloads/'+readmepath.name,rows=len(data),units='JD(TDB), km, km/s',coordinates='Sun-centered Ecliptic J2000',note=NOTE,csv_sha256=hashlib.sha256(csvpath.read_bytes()).hexdigest(),xyzv_sha256=hashlib.sha256(xyzvpath.read_bytes()).hexdigest(),max_checked_hermite_position_error_km=error)
    save(docs/'data/desktop'/f'{ident}.json',record);c['desktop_record_url']=f'data/desktop/{ident}.json'
    save(docs/'data/cases'/f'{ident}.json',c)
    index=read(docs/'data/index.json');summary={k:c[k] for k in ['id','title','target','target_id','sequence','bodies','model','spotlight','featured_priority','start','end','launch_date','arrival_date','years','c3','vinf','burns_mps']}
    index['cases']=[row for row in index['cases'] if row['id']!=ident]+[summary];save(docs/'data/index.json',index)
    annotations=read(docs/'data/mission_annotations.json');annotations['missions'][ident]=dict(label=TITLE,featured_priority=12,note=CREDIT);(docs/'data/mission_annotations.json').write_text(json.dumps(annotations,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    points=np.array([p for path in paths for p in path['points']]);extent=max(float(np.max(abs(points[:,:2]))),1)*1.1
    def poly(points):return ' '.join(f'{160+p[0]/extent*140:.2f},{110-p[1]/extent*90:.2f}' for p in points)
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 220"><rect width="320" height="220" fill="#08121e"/>'
    for i,path in enumerate(paths):svg+=f'<polyline points="{poly(path["points"])}" fill="none" stroke="{["#79d8f1","#ffd08a","#8ae3bd"][i%3]}" stroke-width="1.5"/>'
    svg+='<circle cx="160" cy="110" r="3" fill="#ffd08a"/></svg>';(docs/'images'/f'{ident}.svg').write_text(svg,encoding='utf-8')
    for name in ['trajectory.png','encounter_comparison.png']:shutil.copyfile(RUN/name,docs/'images'/f'{ident}-{name}')
    document=read(RUN/'selected-trajectory.json');document['display_name']=TITLE;document['attribution']=CREDIT
    (RUN/'selected-trajectory.json').write_text(json.dumps(document,indent=2)+'\n',encoding='utf-8')
    (RUN/'run_manifest.json').write_text(json.dumps(dict(config=dict(cfg,cache='cache')),indent=2)+'\n',encoding='utf-8')
    save(docs/'downloads'/f'{ident}-selected-trajectory.json',document)
    report=read(docs/'data/catalog_audit.json');report.setdefault('research_recreations',{})[ident]=dict(research_checks_passed=True,standard_altitude_floors_met=standard['passed'],credit='ReachStar on Bilibili')
    routes=report.setdefault('routes_by_target',{}).setdefault('Neptune',[])
    if q['sequence'] not in routes:routes.append(q['sequence']);routes.sort()
    save(docs/'data/catalog_audit.json',report)
    print('Published local research case',ident,'states',len(data),'credit ReachStar on Bilibili',flush=True)

if __name__=='__main__':main()
