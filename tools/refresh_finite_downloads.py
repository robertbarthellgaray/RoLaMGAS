"""Audit and refresh curated flyby downloads with bounded finite-SOI targeting.

No executable releases or public candidate records are changed. Original files
remain available; only validated, low-correction variants become primary downloads.
Run without --publish first to review report.json; repeat with --publish to apply.
"""
from pathlib import Path,PureWindowsPath,PurePosixPath
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse,hashlib,json,re,shutil,subprocess,sys
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
import bootstrap
from ephemeris import atomic_json


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def portable_report(value):
    """Keep input filenames and scientific provenance without workstation paths."""
    if isinstance(value,dict):return {k:portable_report(v) for k,v in value.items()}
    if isinstance(value,list):return [portable_report(v) for v in value]
    if isinstance(value,str):
        if re.match(r'^[A-Za-z]:[\\/]',value):return 'Local Horizons input: '+PureWindowsPath(value).name
        if value.startswith(('/Users/','/home/')):return 'Local Horizons input: '+PurePosixPath(value).name
    return value


def merge_cache(sources,destination):
    destination.mkdir(parents=True,exist_ok=True)
    for source in sources:
        for metadata in source.glob('*.json'):
            try:doc=read(metadata)
            except (ValueError,OSError):continue
            if not isinstance(doc,dict) or 'raw_file' not in doc or 'npz_sha256' not in doc:continue
            # Publish metadata last so another worker cannot select a table
            # before its checksummed raw and numeric files are available.
            files=[source/doc['raw_file'],metadata.with_suffix('.npz'),metadata]
            if any(not p.is_file() for p in files):continue
            for p in files:
                target=destination/p.name
                if not target.exists():shutil.copy2(p,target)


def admitted(report,threshold_mps,old=None):
    reasons=[]
    for key in ['numerical_validation_passed','no_sample_bracketed_planet_or_sun_impacts',
                'passes_individual_burn_limits','passes_original_onboard_budget','candidate_passes_requested_limits']:
        if not report.get(key):reasons.append(key+' failed')
    if report['patch_join_delta_v_kms']*1000>threshold_mps:reasons.append('Additional patch burns exceed publication threshold')
    if old and report['total_onboard_delta_v_kms']>old['total_onboard_delta_v_kms']+1e-7:
        reasons.append('Existing finite download has a lower total cruise budget')
    return reasons


def refresh(job):
    from mission_search import normalize,routes_for,get_ephemerides
    from trajectory_transfer import materialize,pin_record_epochs
    from integrate_export import export
    from integrate_named_studies import interpolation_error
    case,document,cache,folder,ranges,threshold,cache_alternatives=job
    folder=Path(folder);cache=Path(cache);folder.mkdir(parents=True,exist_ok=True)
    result=dict(id=case['id'],title=case['title'],attempts=[],accepted=False)
    try:
        import_errors=[]
        for candidate_cache in dict.fromkeys([str(cache)]+cache_alternatives):
            try:
                config=normalize(dict(pin_record_epochs(document['settings'],document['trajectory']),cache=candidate_cache));route=routes_for(config)[0]
                ep=get_ephemerides(config,[route]);candidate=materialize(document['trajectory'],config,route,ep)
                cache=Path(candidate_cache);break
            except (ValueError,KeyError) as error:import_errors.append(str(error))
        else:raise ValueError('No cached source reproduces this exact candidate: '+' | '.join(dict.fromkeys(import_errors)))
        candidate['id']=case['id']
        # This is an export comparison, not permission to buy a larger launcher.
        config['max_c3']=min(config['max_c3'],candidate['launch_c3_km2_s2']+1e-6)
        source=folder/'candidate.json';atomic_json(source,candidate)
        old_files=case.get('trajectory_files',{});old=None
        if old_files.get('finite_radius') and old_files.get('integration_report'):
            old=read(ROOT/'docs'/old_files['integration_report'])
        post=old.get('post_flyby_months',1.) if old else 1.
        accepted=[]
        for days in ranges:
            output=folder/('days_'+str(days))
            try:
                report=export(source,config,output,post_flyby_months=post,patch_epoch_shift_days=days)
                reasons=admitted(report,threshold,old)
                attempt=dict(days=days,patch_mps=report['patch_join_delta_v_kms']*1000,
                    total_cruise_mps=report['total_onboard_delta_v_kms']*1000,
                    dsm_mps=report['maneuver_budget_breakdown']['exported_cruise_dsm_kms']*1000,
                    exported_c3=report['exported_launch_c3_km2_s2'],reasons=reasons)
                if not reasons:
                    attempt['maximum_serialized_midpoint_error_km']=interpolation_error(output,report,cache)
                    accepted.append((report['total_onboard_delta_v_kms'],output,report,attempt))
                result['attempts'].append(attempt)
                # Preserve historical flyby days whenever a fixed-date export
                # already meets the publication standard.
                if accepted and days==0:break
            except Exception as error:result['attempts'].append(dict(days=days,error=str(error)))
        if accepted:
            _,output,report,attempt=min(accepted,key=lambda row:row[0])
            result.update(accepted=True,selected_output=str(output),selected_days=attempt['days'],
                patch_mps=attempt['patch_mps'],total_cruise_mps=attempt['total_cruise_mps'],
                exported_c3=attempt['exported_c3'],maximum_serialized_midpoint_error_km=attempt['maximum_serialized_midpoint_error_km'])
    except Exception as error:result['error']=str(error)
    atomic_json(folder/'review.json',result)
    return result


def publish(result,threshold_mps=100.):
    identifier=result['id'];folder=Path(result['selected_output']);report=read(folder/'integration_report.json')
    casepath=ROOT/'docs/data/cases'/(identifier+'.json');case=read(casepath)
    previous=case['trajectory_files'];base=identifier+'-targeted-025';downloads=ROOT/'docs/downloads'
    if admitted(report,threshold_mps):raise ValueError('Export no longer passes publication checks: '+identifier)
    if (folder/'integration_status.json').is_file() and read(folder/'integration_status.json')['state']!='finished':
        raise ValueError('Export is not finished: '+identifier)
    if 'patch_mps' in result and abs(report['patch_join_delta_v_kms']*1000-result['patch_mps'])>1e-5:
        raise ValueError('Reviewed export changed before publication: '+identifier)
    mapping={'trajectory.csv':'.csv','trajectory.xyzv':'.xyzv','integration_report.json':'-integration.json',
        'burns.csv':'-burns.csv','encounters.csv':'-encounters.csv','finite_targeting.json':'-targeting.json'}
    for source,suffix in mapping.items():
        target=downloads/(base+suffix)
        if source=='integration_report.json':target.write_text(json.dumps(portable_report(report),ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
        else:target.write_bytes((folder/source).read_bytes().replace(b'\r\n',b'\n'))
    changes=report.get('finite_targeting',{}).get('changes',[])
    shift=max((abs(n['epoch_shift_days']) for n in changes),default=0.)
    note=(f"Refined finite-radius patched-conic variant. Exported onboard delta-v {report['total_onboard_delta_v_kms']*1000:.2f} m/s, "
          f"including {report['patch_join_delta_v_kms']*1000:.2f} m/s of additional patch corrections; "
          f"exported C3 {report['exported_launch_c3_km2_s2']:.5f} km2/s2. "
          f"Intermediate flyby dates differ by up to {shift:.5f} days from the saved preview. "
          f"Launch/final encounter dates are fixed; includes {report.get('post_flyby_months',0):g} months after the encounter. "
          "Preview metrics describe the original candidate. Download encounter and burn tables for this variant. "
          "Sun/planet two-body patches, not n-body or official mission ephemerides.")
    (downloads/(base+'-README.txt')).write_text(case['title']+'\n\n'+note+'\n\nColumns: JD TDB, X Y Z (km), VX VY VZ (km/s), Sun-centered Ecliptic J2000.\n',encoding='utf-8')
    case.setdefault('original_trajectory_files',previous)
    case['trajectory_files']=dict(csv='downloads/'+base+'.csv',xyzv='downloads/'+base+'.xyzv',
        readme='downloads/'+base+'-README.txt',integration_report='downloads/'+base+'-integration.json',
        burns='downloads/'+base+'-burns.csv',encounters='downloads/'+base+'-encounters.csv',targeting='downloads/'+base+'-targeting.json',
        rows=report['rows'],finite_radius=True,units='JD(TDB), km, km/s',coordinates='Sun-centered Ecliptic J2000',
        source='Jointly targeted, numerically integrated finite-SOI export variant',note=note,
        total_onboard_delta_v_kms=report['total_onboard_delta_v_kms'],exported_c3=report['exported_launch_c3_km2_s2'],
        patch_join_delta_v_kms=report['patch_join_delta_v_kms'],maximum_epoch_shift_days=shift,
        passes_original_onboard_budget=report['passes_original_onboard_budget'],
        max_checked_hermite_position_error_km=result['maximum_serialized_midpoint_error_km'],
        csv_sha256=hashlib.sha256((downloads/(base+'.csv')).read_bytes()).hexdigest(),
        xyzv_sha256=hashlib.sha256((downloads/(base+'.xyzv')).read_bytes()).hexdigest())
    casepath.write_text(json.dumps(case,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--cache-source',type=Path,action='append',default=[]);p.add_argument('--output',type=Path,default=ROOT/'.build/finite_downloads')
    p.add_argument('--ids',nargs='*');p.add_argument('--ranges',type=float,nargs='+',default=[0.,30.]);p.add_argument('--workers',type=int,default=3)
    p.add_argument('--max-patch-mps',type=float,default=100.);p.add_argument('--publish',action='store_true');p.add_argument('--resume',action='store_true');p.add_argument('--retry-failed',action='store_true')
    a=p.parse_args();a.cache=a.cache.resolve();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
    if a.cache_source:merge_cache(a.cache_source,a.cache)
    cases=[];retained=[]
    for row in read(ROOT/'docs/data/index.json')['cases']:
        if a.ids and row['id'] not in a.ids:continue
        case=read(ROOT/'docs/data/cases'/(row['id']+'.json'))
        if not case.get('desktop_record_url'):
            retained.append(dict(id=case['id'],reason='Original integrated file retained; no Lambert handoff record'));continue
        case['desktop_record']=read(ROOT/'docs'/case['desktop_record_url']);cases.append(case)
    # Use the exact same portable handoff builder as the website download button.
    js="import fs from 'node:fs';import {transferDocument} from './docs/desktop_transfer.js';const cases=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(cases.map(c=>transferDocument(c))));"
    docs=json.loads(subprocess.run(['node','--input-type=module','-e',js],input=json.dumps(cases),text=True,capture_output=True,check=True,cwd=ROOT).stdout)
    results=[];jobs=[]
    for case,document in zip(cases,docs):
        folder=a.output/case['id'];saved=folder/'review.json'
        if a.resume and saved.is_file() and (not a.retry_failed or read(saved)['accepted']):results.append(read(saved));continue
        jobs.append((case,document,str(a.cache),str(folder),a.ranges,a.max_patch_mps,[str(p.resolve()) for p in a.cache_source]))
    with ProcessPoolExecutor(max_workers=max(1,a.workers)) as pool:
        futures=[pool.submit(refresh,job) for job in jobs]
        for future in as_completed(futures):
            result=future.result();results.append(result)
            print(json.dumps({k:result.get(k) for k in ['id','accepted','patch_mps','total_cruise_mps','error']})+f' [{len(results)}/{len(cases)}]',flush=True)
    if a.publish:
        for result in results:
            if result['accepted']:publish(result,a.max_patch_mps)
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),publication_threshold_mps=a.max_patch_mps,
        attempted=len(results),accepted=sum(r['accepted'] for r in results),published=bool(a.publish),
        retained_originals=retained,trajectories=sorted(results,key=lambda r:r['id']))
    atomic_json(a.output/'report.json',report)
    if a.publish:
        def clean_error(value):
            return 'Original cached source data could not be reproduced; original download retained.' if ':\\' in value or '/Users/' in value else value
        public=dict(generated_at=report['generated_at'],publication_threshold_mps=a.max_patch_mps,
            reviewed=report['attempted'],upgraded=report['accepted'],original_integrations_retained=retained,
            note='Numerical, clearance, burn-cap, budget and serialized midpoint checks required. Larger date windows are explicit variants; source candidate previews and original files are retained.',
            trajectories=[])
        for result in sorted(results,key=lambda r:r['id']):
            row={k:result[k] for k in ['id','title','accepted','selected_days','patch_mps','total_cruise_mps','exported_c3','maximum_serialized_midpoint_error_km'] if k in result}
            if not result['accepted']:
                if result.get('error'):row['reason']=clean_error(result['error'])
                row['attempts']=[{k:(clean_error(v) if k=='error' else v) for k,v in trial.items()} for trial in result.get('attempts',[])]
            public['trajectories'].append(row)
        atomic_json(ROOT/'docs/data/finite_download_review.json',public)
    print(json.dumps({k:report[k] for k in ['attempted','accepted','published','retained_originals']}),flush=True)


if __name__=='__main__':main()
