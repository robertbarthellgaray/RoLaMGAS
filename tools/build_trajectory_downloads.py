"""Precompute public CSV/XYZV states without running a search or using a network.

Use saved coast initial conditions, not velocity differences of preview points.
The offline Mars grid has zero-revolution Lambert arcs; reconstruct those from
its rounded public endpoints if its original raw solver records are unavailable.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
import argparse,hashlib,json,math
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from dynamics import kepler
from ephemeris import AU,DAY,MU_SUN,BODIES,Ephemerides
from lamberthub import izzo2015

ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,v):p.write_text(json.dumps(v,separators=(',',':'),ensure_ascii=False,allow_nan=False),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def sample_coasts(coasts,tolerance_km=10.,max_days=10.):
    """Adapt to the actual Kepler motion and keep both sides of each impulse."""
    rows=[];probe_error=0.
    for index,s in enumerate(coasts):
        start,end=s['start_jd'],s['end_jd'];r0=np.array(s['r']);v0=np.array(s['v'])
        # Bracket a velocity discontinuity with distinct times, one second apart.
        finish=end-(1/DAY if index<len(coasts)-1 else 0.)
        def state(t):
            r,v=kepler(r0,v0,float((t-start)*DAY));return np.r_[r,v]
        def subdivide(a,b,sa,sb,depth=0):
            nonlocal probe_error
            dt=(b-a)*DAY;local=np.array([.25,.5,.75])*dt
            exact=np.array([state(a+x/DAY) for x in local])
            fit=CubicHermiteSpline([0.,dt],np.array([sa[:3],sb[:3]]),np.array([sa[3:],sb[3:]]))
            error=float(np.max(np.linalg.norm(fit(local)-exact[:,:3],axis=1)))
            if error>tolerance_km:
                if depth>=30:raise ValueError('Could not meet the requested interpolation tolerance')
                middle=(a+b)/2;sm=state(middle)
                subdivide(a,middle,sa,sm,depth+1);subdivide(middle,b,sm,sb,depth+1)
            else:
                probe_error=max(probe_error,error);rows.append(np.r_[a,sa])
        boundaries=np.linspace(start,finish,max(1,math.ceil((finish-start)/max_days))+1)
        for a,b in zip(boundaries[:-1],boundaries[1:]):subdivide(a,b,state(a),state(b))
        rows.append(np.r_[finish,state(finish)])
    data=np.array(rows)
    if not np.isfinite(data).all() or np.any(np.diff(data[:,0])<=0):raise ValueError('Nonfinite or non-increasing export samples')
    return data,probe_error

def reconstruct_mars(c):
    coasts=[]
    for p in c['paths']:
        r0=np.array(p['points'][0])*AU;r1=np.array(p['points'][-1])*AU
        v0,_=izzo2015(MU_SUN,r0,r1,(p['end']-p['start'])*DAY,M=0,prograde=True,low_path=True)
        coasts.append(dict(start_jd=p['start'],end_jd=p['end'],r=r0.tolist(),v=v0.tolist()))
    return coasts

def add_case(file,docs,cache):
    from catalog_validation import audit_candidate
    q=read(file);cfg=read(file.parent.parent/'run_manifest.json')['config']
    audit=audit_candidate(q,cfg,BODIES)
    if not audit['passed']:raise ValueError('Candidate fails public admission: '+str(audit['reasons']))
    ep=Ephemerides(cache,q['bodies'],q['dates_jd_tdb'][0],q['dates_jd_tdb'][-1],1.)
    residual=np.array([ep.state(e['body'],e['julian_date_tdb'])-e['planet_state_km_kms'] for e in q['events']])
    pos=float(np.max(np.linalg.norm(residual[:,:3],axis=1)));vel=float(np.max(np.linalg.norm(residual[:,3:],axis=1))*1000)
    if pos>.1 or vel>.001:raise ValueError('Independent cached JPL states do not match candidate')
    coast_error=0.;coast_v_error=0.;minimum_solar=1e99
    paths=[]
    for i,s in enumerate(q['segments']):
        end=s['end_jd'];r,v=kepler(np.array(s['r']),np.array(s['v']),(end-s['start_jd'])*DAY)
        expected=next((np.array(e['planet_state_km_kms'][:3]) for e in q['events'] if abs(e['julian_date_tdb']-end)<1e-8),None)
        if expected is None:expected=np.array(q['segments'][i+1]['r'])
        coast_error=max(coast_error,float(np.linalg.norm(r-expected)))
        event=next((j for j,e in enumerate(q['events']) if abs(e['julian_date_tdb']-end)<1e-8),None)
        if event is not None:coast_v_error=max(coast_v_error,float(np.linalg.norm(v-q['arrival_velocities_kms'][event-1]))*1000)
        samples=np.array([kepler(np.array(s['r']),np.array(s['v']),float(t))[0] for t in np.linspace(0,(end-s['start_jd'])*DAY,320)])
        minimum_solar=min(minimum_solar,float(np.min(np.linalg.norm(samples,axis=1))))
        paths.append(dict(start=s['start_jd'],end=end,points=np.round(samples/AU,8).tolist()))
    if coast_error>1. or minimum_solar<695700.:raise ValueError('Coast endpoint or solar-clearance check failed')
    audit.update(max_reference_ephemeris_position_error_km=pos,max_reference_ephemeris_velocity_error_mps=vel,max_coast_endpoint_error_km=coast_error,max_coast_velocity_error_mps=coast_v_error,minimum_solar_radius_km=minimum_solar)
    events=[dict(body=e['body'],jd=e['julian_date_tdb'],date=e['date'],position_au=(np.array(e['planet_state_km_kms'][:3])/AU).tolist(),kind='Departure' if i==0 else 'Arrival' if i==len(q['events'])-1 else 'Encounter') for i,e in enumerate(q['events'])]
    burns=[dict(body='DSM',kind='DSM',jd=b['julian_date_tdb'],date=b['date'],magnitude_mps=b['magnitude_kms']*1000,vector_kms=b['delta_v_ecliptic_j2000_kms'],position_au=(np.array(b['position_km'])/AU).tolist()) for b in q['dsms']]
    flybys=[dict(body=f['body'],jd=f['julian_date_tdb'],date=f['date'],vinf_in_kms=f['vinf_in_kms'],vinf_out_kms=f['vinf_out_kms'],mismatch_mps=f['speed_mismatch_mps'],turn_deg=f['turn_angle_deg'],altitude_km=f['conservative_equal_speed_altitude_km'],altitude_floor_km=f['minimum_altitude_km'],powered_mps=0.) for f in q['flybys']]
    dates=np.linspace(q['dates_jd_tdb'][0],q['dates_jd_tdb'][-1],320)
    planets=[dict(body=b,points=np.round([ep.state(b,t)[:3]/AU for t in dates],8).tolist()) for b in dict.fromkeys(q['bodies'])]
    c=dict(id=q['id'],title='Rebuilding Cassini · Saturn',target='Saturn',sequence=q['sequence'],bodies=q['bodies'],model='Lambert candidate',spotlight=False,start=q['dates_jd_tdb'][0],end=q['dates_jd_tdb'][-1],launch_date=q['launch_date'][:10],arrival_date=q['arrival_date'][:10],years=q['duration_years'],c3=q['launch_c3_km2_s2'],vinf=q['arrival_vinf_kms'],burns_mps=q['total_dsm_kms']*1000,events=events,burns=burns,flybys=flybys,paths=paths,planet_paths=planets,validation=audit,
           note='An independent Lambert recreation of the Cassini assist sequence, not the flown mission. Arrival is about 479 days later. These solar coasts join at planet centers; the displayed 412.4 m/s is the ideal DSM. Its separate finite-radius exporter adds 1647.3 m/s in junction burns and totals 2060.5 m/s before Saturn capture. The downloads here contain the ideal Lambert coasts, not that finite-radius export.',
           provenance=dict(source='Saved RoLaMGAS result; Cassini comparison',candidate_id=q['id'],coordinates='Heliocentric Ecliptic J2000',time_scale='TDB',plot_units='AU',ephemerides='JPL Horizons geometric vectors',speed_tolerance_mps=cfg['vinf_tolerance_mps']))
    p=docs/'data/cases'/(c['id']+'.json');save(p,c)
    # A small static thumbnail; no rendering service is required.
    all_points=np.vstack([p['points'] for p in paths]);extent=max(float(np.max(abs(all_points[:,:2]))),1)*1.15
    def poly(points):return ' '.join(f'{160+p[0]/extent*140:.2f},{110-p[1]/extent*90:.2f}' for p in points)
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 220"><rect width="320" height="220" fill="#0b1520"/>'
    for p in paths:svg+=f'<polyline points="{poly(p["points"])}" fill="none" stroke="#79d8f1" stroke-width="1.6"/>'
    svg+='<circle cx="160" cy="110" r="3" fill="#ffd08a"/><text x="15" y="205" fill="#96a9bb" font-family="monospace" font-size="10">EVdvVEJS · Cassini recreation</text></svg>'
    (docs/'images'/(c['id']+'.svg')).write_text(svg,encoding='utf-8')
    return c,q

def build(args):
    docs=args.docs;index=read(docs/'data/index.json');ids={c['id'] for c in index['cases']};sources={}
    for root in args.runs_root:
        for file in root.rglob('candidates/*.json'):
            ident=file.name.split('.')[0]
            if ident in ids and ident not in sources:sources[ident]=file
    for file in args.include_candidate:
        c,q=add_case(file,docs,args.cache);sources[c['id']]=file
        summary={k:c[k] for k in ['id','title','target','sequence','bodies','model','spotlight','start','end','launch_date','arrival_date','years','c3','vinf','burns_mps']}
        index['cases']=[r for r in index['cases'] if r['id']!=c['id']]+[summary]
    total_rows=0;total_bytes=0;downloads=docs/'downloads';downloads.mkdir(exist_ok=True)
    for summary in index['cases']:
        file=docs/'data/cases'/(summary['id']+'.json');c=read(file);ident=c['id']
        if c['model']=='Lambert candidate':
            if ident in sources:coasts=read(sources[ident])['segments'];source='Saved full-precision solar coast initial conditions'
            elif c.get('coasts'):coasts=c['coasts'];source=c.get('trajectory_files',{}).get('source','Saved full-precision solar coast initial conditions')
            elif ident.startswith('mars-'):coasts=reconstruct_mars(c);source='Zero-revolution Lambert reconstruction from rounded public Mars encounter positions'
            else:raise ValueError('Missing raw coast states for '+ident+'; provide its --runs-root')
            data,error=sample_coasts(coasts);c['coasts']=coasts
            xyzv=downloads/(ident+'-lambert.xyzv')
            note='Solar Kepler coasts with planet-center joins; not a resolved planetary flyby. Velocities jump at ideal encounters/DSMs. Samples bracket joins one second apart. Do not use planet-center passages for flyby close-up renders; use a finite-radius desktop export and check its additional burns.'
            np.savetxt(xyzv,data,fmt=['%.12f']+['%.6f']*3+['%.9f']*3,header=f'RoLaMGAS {ident} | IDEAL LAMBERT COASTS\nJD(TDB) x_km y_km z_km vx_km_s vy_km_s vz_km_s | Sun-centered Ecliptic J2000\n{note}\nBegin {data[0,0]:.12f} End {data[-1,0]:.12f}')
            xyzv.write_bytes(xyzv.read_bytes().replace(b'\r\n',b'\n'))
        else:
            xyzv=docs/c['download'];data=np.loadtxt(xyzv,comments='#');error=None;source='Unchanged original integrated XYZV'
            if sha(xyzv)!=c['provenance']['sha256']:raise ValueError('Original integration checksum differs')
            note='Original integrated concept. See Model & data for its force model, targeting burns and limitations. CSV preserves every numeric XYZV row, including any repeated impulse epochs.'
        csvfile=downloads/(ident+'.csv');np.savetxt(csvfile,data,delimiter=',',fmt=['%.12f']+['%.9f']*6,header='jd_tdb,x_km,y_km,z_km,vx_km_s,vy_km_s,vz_km_s',comments='')
        csvfile.write_bytes(csvfile.read_bytes().replace(b'\r\n',b'\n'))
        # Verify the downloadable formats agree within their declared precision.
        csvdata=np.loadtxt(csvfile,delimiter=',',skiprows=1);xyzdata=np.loadtxt(xyzv,comments='#')
        if not np.allclose(csvdata,xyzdata,rtol=0.,atol=1e-5):raise ValueError('CSV/XYZV mismatch for '+ident)
        metadata=dict(csv='downloads/'+csvfile.name,xyzv='downloads/'+xyzv.name,rows=len(data),source=source,note=note,coordinates='Sun-centered Ecliptic J2000',units='JD(TDB), km, km/s',csv_sha256=sha(csvfile),xyzv_sha256=sha(xyzv),max_checked_hermite_position_error_km=error)
        metadata['readme']='downloads/'+ident+'-README.txt'
        (docs/metadata['readme']).write_text(f'RoLaMGAS {ident} / {c["sequence"]}\n{source}\n{note}\n\nColumns: JD(TDB), x, y, z, vx, vy, vz\nOrigin: Sun. Frame: Ecliptic J2000. Position: km. Velocity: km/s.\nTime labels are TDB, not UTC.\nRows: {len(data)}\nCSV SHA256: {metadata["csv_sha256"]}\nXYZV SHA256: {metadata["xyzv_sha256"]}\n\n'+c['note']+'\n',encoding='utf-8')
        c['trajectory_files']=metadata;save(file,c);total_rows+=len(data);total_bytes+=csvfile.stat().st_size+xyzv.stat().st_size
        print(ident,len(data),'samples',flush=True)
    save(docs/'data/index.json',index)
    audit=read(docs/'data/catalog_audit.json');cases=[read(docs/'data/cases'/(c['id']+'.json')) for c in index['cases']];lambert=[c for c in cases if c['model']=='Lambert candidate']
    audit.update(lambert_candidates=len(lambert),all_published_lambert_candidates_pass=all(c['validation']['passed'] for c in lambert),routes_by_target={t:sorted({c['sequence'] for c in cases if c['target']==t}) for t in sorted({c['target'] for c in cases})})
    save(docs/'data/catalog_audit.json',audit)
    print(json.dumps(dict(cases=len(cases),rows=total_rows,download_megabytes=total_bytes/1e6)))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--docs',type=Path,default=ROOT/'docs');p.add_argument('--runs-root',type=Path,action='append',default=[]);p.add_argument('--include-candidate',type=Path,action='append',default=[]);p.add_argument('--cache',type=Path,default=Path.home()/'AppData/Local/RoLaMGAS/cache');build(p.parse_args())
