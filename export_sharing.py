"""Share numeric integrated exports under the existing community opt-out setting.

No arbitrary local files, cache paths, model assets, logs or device identifiers.
"""
import bootstrap
import csv,gzip,json,math,re,urllib.request
from pathlib import Path
from community import settings,exchange,public_record
from network import tls_context

SUMMARY_FIELDS=('exported_launch_c3_km2_s2','total_onboard_delta_v_kms','patch_join_delta_v_kms',
    'passes_original_onboard_budget','passes_individual_burn_limits','post_flyby_months',
    'arrival_altitude_option_km','arrival_inclination_option_deg')
BURN_FIELDS=('julian_date_tdb','magnitude_kms','dx_kms','dy_kms','dz_kms')

def bundle(output,candidate,config,route,moon_branch=None):
    from celestia_package import export_report
    output=Path(output);report=export_report(output,moon_branch)
    record=public_record(candidate,config,route)
    if not record:raise ValueError('Only eligible pass/yellow source trajectories can be shared')
    states=[]
    if (output/'trajectory.xyzv').stat().st_size>16_000_000:raise ValueError('Trajectory exceeds shared export size limit')
    with (output/'trajectory.xyzv').open(encoding='utf-8') as stream:
        for line in stream:
            if not line.strip() or line.lstrip().startswith('#'):continue
            row=list(map(float,line.split()))
            if len(row)!=7 or not all(math.isfinite(v) for v in row) or (states and row[0]<=states[-1][0]):raise ValueError('Shared states must be finite ordered seven-column vectors')
            states.append(row)
            if len(states)>100000:raise ValueError('Shared export exceeds 100000 samples')
    if len(states)<2:raise ValueError('No integrated trajectory to share')
    summary={k:report[k] for k in SUMMARY_FIELDS if report.get(k) is not None}
    summary.update(numerical_validation_passed=True,clearance_screen_passed=True,export_kind='moon' if moon_branch else 'planet',
        force_model='Sun-only outside planned SOIs; encounter-body gravity inside. See local validation report for limits.')
    if moon_branch:
        summary.update(moon_body=report['moon_body'],target_mode=report['target_mode'])
    burns=[]
    with (output/'burns.csv').open(newline='',encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            kind=row.get('kind','')
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _+().-]{0,99}',kind):raise ValueError('Unsupported maneuver label')
            item={'kind':kind}
            for key in BURN_FIELDS:
                if row.get(key):item[key]=float(row[key])
            if not all(math.isfinite(v) for k,v in item.items() if k!='kind'):raise ValueError('Nonfinite shared maneuver')
            burns.append(item)
    result=dict(schema_version=1,source=record,validation=summary,states=states,burns=burns)
    raw=json.dumps(result,separators=(',',':'),allow_nan=False).encode()
    if len(raw)>12_000_000:raise ValueError('Shared export exceeds 12 MB uncompressed')
    payload=gzip.compress(raw,mtime=0)
    if len(payload)>6_000_000:raise ValueError('Shared export exceeds 6 MB compressed')
    return result,payload

def publish(output,candidate,config,route,moon_branch=None,prepared=None):
    pref=settings()
    if not pref['share_candidates'] or not pref['endpoint']:return dict(state='disabled',message='Export sharing is off.')
    document,payload=prepared if prepared is not None else bundle(output,candidate,config,route,moon_branch)
    exchange(pref['endpoint']+'/v1/candidates',dict(candidates=[document['source']]))
    # Recheck opt-out immediately before uploading files, including queued jobs.
    if not settings()['share_candidates']:return dict(state='disabled',message='Export sharing is off.')
    request=urllib.request.Request(pref['endpoint']+'/v1/exports',data=payload,headers={'Content-Type':'application/gzip','User-Agent':'RoLaMGAS-export/1'})
    with urllib.request.urlopen(request,timeout=60,context=tls_context() if pref['endpoint'].startswith('https:') else None) as response:
        result=json.loads(response.read(100000))
    return dict(state='shared',message='Integrated XYZV, CSV, maneuvers and validation summary shared.',**result)
