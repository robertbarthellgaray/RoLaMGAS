"""Integrate the six named, screened study recreations and publish finite-radius files.

Does not turn reference-only Decadal schedules into accepted missions, or upload
executables. Source candidate scores remain separate from exported burn costs.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse,hashlib,json,os,shutil,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ephemeris import atomic_json,Ephemerides,DAY
from dynamics import kepler
import numpy as np
ROOT=Path(__file__).resolve().parents[1]

def interpolation_error(output,report,cache):
    """Independent exact two-body midpoint check of the serialized XYZV."""
    points=np.loadtxt(output/'trajectory.xyzv');segments=report['force_segments']
    bodies=sorted({s['center'] for s in segments if s['center']!='Sun'})
    ep=Ephemerides(cache,bodies,points[0,0],points[-1,0],1.) if bodies else None
    errors=[];index=0
    for a,b in zip(points,points[1:]):
        middle=(a[0]+b[0])/2;dt=(b[0]-a[0])*DAY
        while index<len(segments)-1 and middle>segments[index]['end_jd_tdb']:index+=1
        segment=segments[index];center=segment['center'];r,v=a[1:4],a[4:]
        if center!='Sun':
            origin=ep.state(center,a[0]);r=r-origin[:3];v=v-origin[3:]
        exact,_=kepler(r,v,dt/2,segment['gm_km3_s2'])
        if center!='Sun':exact+=ep.state(center,middle)[:3]
        estimate=.5*(a[1:4]+b[1:4])+dt/8*(a[4:]-b[4:])
        errors.append(float(np.linalg.norm(exact-estimate)))
    maximum=max(errors,default=0.)
    if maximum>1:raise ValueError(f'Serialized trajectory midpoint error exceeds 1 km: {maximum}')
    return maximum

def integrate(row,cache):
    identifier=row['id']
    folder=ROOT/'studies/trident_reconstruction' if identifier=='f53fc65c9329' else next(
        p.parent for p in (ROOT/'studies/mission_report_recreations').glob('*/candidate.json')
        if json.loads(p.read_text(encoding='utf-8'))['id']==identifier)
    candidate=folder/'candidates'/(identifier+'.json')
    config=json.loads((folder/'run_manifest.json').read_text(encoding='utf-8'))['config']
    config['cache']=str(cache)
    output=folder/'integrated';output.mkdir(exist_ok=True)
    config_path=output/'local_config.json';atomic_json(config_path,config)
    try:
        fit=subprocess.run([sys.executable,str(ROOT/'integrate_export.py'),'--candidate',str(candidate),
            '--config',str(config_path),'--output',str(output),'--post-flyby-months','1'],capture_output=True,text=True)
        if fit.returncode:raise RuntimeError(fit.stderr[-1800:])
    finally:config_path.unlink(missing_ok=True)
    report=json.loads((output/'integration_report.json').read_text(encoding='utf-8'))
    if not report['numerical_validation_passed'] or not report['no_sample_bracketed_planet_or_sun_impacts']:
        raise ValueError('Numerical or planet/Sun clearance check failed; not publishing')
    return row,folder,output,report

def publish(row,folder,output,report,cache=None):
    identifier=row['id'];base=identifier+'-patched';downloads=ROOT/'docs/downloads'
    for source,suffix in [('trajectory.csv','.csv'),('trajectory.xyzv','.xyzv'),
            ('integration_report.json','-integration.json'),('burns.csv','-burns.csv'),('encounters.csv','-encounters.csv')]:
        destination=downloads/(base+suffix)
        shutil.copy2(output/source,destination)
        if suffix.endswith('.csv'):destination.write_bytes(destination.read_bytes().replace(b'\r\n',b'\n'))
    note=('Finite-radius Sun/planet patched-conic integration; not n-body. Includes one month after final encounter. '
          'Original search metrics are separate from exported maneuvers: additional SOI junction burns '
          f"{report['patch_join_delta_v_kms']:.6f} km/s; total exported onboard delta-v {report['total_onboard_delta_v_kms']:.6f} km/s. "
          +('Exceeds the original configured onboard budget. ' if not report['passes_original_onboard_budget'] else '')+
          'Check the full integration/burn reports; these are modified study reconstructions, not official spacecraft ephemerides.')
    readme=row['title']+'\n\n'+note+'\n\nColumns: JD TDB, X Y Z (km), VX VY VZ (km/s). Sun-centered Ecliptic J2000.\n'
    (downloads/(base+'-README.txt')).write_text(readme,encoding='utf-8')
    path=ROOT/'docs/data/cases'/(identifier+'.json');case=json.loads(path.read_text(encoding='utf-8'))
    cache=cache or Path(json.loads((folder/'run_manifest.json').read_text(encoding='utf-8'))['config']['cache'])
    error=interpolation_error(output,report,cache)
    case['trajectory_files']=dict(csv='downloads/'+base+'.csv',xyzv='downloads/'+base+'.xyzv',
        readme='downloads/'+base+'-README.txt',integration_report='downloads/'+base+'-integration.json',
        burns='downloads/'+base+'-burns.csv',rows=report['rows'],finite_radius=True,
        units='JD(TDB), km, km/s',coordinates='Sun-centered Ecliptic J2000',
        source='Numerically propagated finite-radius patched conics',note=note,
        total_onboard_delta_v_kms=report['total_onboard_delta_v_kms'],passes_original_onboard_budget=report['passes_original_onboard_budget'],
        max_checked_hermite_position_error_km=error,
        interpolation_check='All serialized interval midpoints against exact two-body propagation in the reported force center; JPL frame translation inside planet patches.',
        csv_sha256=hashlib.sha256((downloads/(base+'.csv')).read_bytes()).hexdigest(),
        xyzv_sha256=hashlib.sha256((output/'trajectory.xyzv').read_bytes()).hexdigest())
    path.write_text(json.dumps(case,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    # Integrated artifacts live in the public downloads directory; retain a
    # small portable summary beside the source study instead of duplicating MB.
    summary=dict(id=identifier,name=row['title'],rows=report['rows'],numerical_validation_passed=True,
        clearance_passed=True,patch_join_delta_v_kms=report['patch_join_delta_v_kms'],
        total_onboard_delta_v_kms=report['total_onboard_delta_v_kms'],
        passes_original_onboard_budget=report['passes_original_onboard_budget'],
        csv=Path(os.path.relpath(downloads/(base+'.csv'),folder)).as_posix(),
        xyzv=Path(os.path.relpath(downloads/(base+'.xyzv'),folder)).as_posix())
    atomic_json(folder/'integrated_summary.json',summary)
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--cache',type=Path,required=True)
    args=parser.parse_args();rows=json.loads((ROOT/'studies/mission_report_recreations/website_links.json').read_text())
    summaries=[];failures=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(integrate,row,args.cache):row for row in rows}
        for future in as_completed(futures):
            try:summary=publish(*future.result(),cache=args.cache);summaries.append(summary);print(json.dumps(summary),flush=True)
            except Exception as exc:
                failure=dict(name=futures[future]['title'],error=str(exc));failures.append(failure);print(json.dumps(failure),flush=True)
    atomic_json(ROOT/'studies/mission_report_recreations/integrated_exports.json',dict(trajectories=summaries,failures=failures))
    if failures:raise SystemExit(1)

if __name__=='__main__':main()
