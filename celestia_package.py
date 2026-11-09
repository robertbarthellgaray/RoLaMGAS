"""Build a self-contained Celestia addon folder and ZIP using user spacecraft meshes."""
from pathlib import Path
import csv
import hashlib
import json
import re
import shutil
import struct
import zipfile
from ephemeris import AU,atomic_json

HERE=Path(__file__).resolve().parent
MODELS={'Panels':'LowPolySatPanels.3ds','RTG':'LowPolySatRTG.3ds'}
DWARF_NAMES=('ceres','pluto','eris','haumea','makemake')


def choose_model(candidate,config,maximum_distance_au,override='auto'):
    if override not in ('auto','Panels','RTG'):
        raise ValueError('Choose auto, Panels or RTG')
    if override!='auto':
        return override,'Selected manually in the package exporter.'
    obj=config.get('target_object') or {}
    label=str(obj.get('name') or config.get('target') or candidate['bodies'][-1]).casefold()
    if any(re.search(r'\b'+name+r'\b',label) for name in DWARF_NAMES):
        return 'RTG','Dwarf-planet destination; RTG selected by your packaging rule.'
    if any(b in ('Saturn','Uranus','Neptune') for b in candidate['bodies']):
        return 'RTG','The mission visits a planet beyond Jupiter.'
    if not obj and candidate['bodies'][-1] in ('Mercury','Venus','Earth','Mars','Jupiter'):
        return 'Panels','Planetary mission at Jupiter or closer.'
    if float(obj.get('semimajor_axis_au') or 0)>6 or maximum_distance_au>6:
        return 'RTG','The object orbit or integrated trajectory extends into the outer Solar System.'
    return 'Panels','The integrated small-body mission stays in the inner/Jupiter region.'


def texture_references(path):
    data=path.read_bytes()
    if len(data)<6 or struct.unpack_from('<H',data)[0]!=0x4d4d:
        raise ValueError('Expected a valid 3DS mesh: '+path.name)
    references=[]
    containers={0x4d4d,0x3d3d,0xafff,0xa200,0xa210,0xa220,0xa230,0xa240,0xa250,0xa252,0xa33a}
    def walk(start,end):
        cursor=start
        while cursor+6<=end:
            kind,size=struct.unpack_from('<HI',data,cursor)
            if size<6 or cursor+size>end:
                break
            if kind==0xa300:
                references.append(data[cursor+6:cursor+size].split(b'\0',1)[0].decode('latin1'))
            elif kind in containers:
                walk(cursor+6,cursor+size)
            cursor+=size
    walk(0,len(data))
    return list(dict.fromkeys(references))


def build_package(output,candidate,config,override='auto'):
    output=Path(output)
    report=json.loads((output/'integration_report.json').read_text(encoding='utf-8'))
    if not report.get('numerical_validation_passed'):
        raise ValueError('The integrated trajectory did not pass its numerical check. Inspect the report first.')
    if not report.get('no_sample_bracketed_planet_or_sun_impacts'):
        raise ValueError('The integrated clearance screen found a planet/Sun impact. Inspect the report before packaging.')
    maximum=0.
    with (output/'trajectory.csv').open(newline='',encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            maximum=max(maximum,(sum(float(row[k])**2 for k in ('x_km','y_km','z_km')))**.5/AU)
    selected,reason=choose_model(candidate,config,maximum,override)
    filename=MODELS[selected]
    source=next((p for p in (HERE.parent/filename,HERE/'model_assets'/filename) if p.is_file()),None)
    if source is None:
        raise ValueError(f'Model missing: put {filename} in mission_designer or explorer/model_assets')
    references=texture_references(source)
    identifier=candidate['id']
    if not re.fullmatch(r'[a-f0-9]{12}',identifier):
        raise ValueError('Invalid candidate ID')
    addon_name=f'Trajectory_{identifier}_{selected}'
    root=output/'celestia_package'/addon_name
    for sub in ('data','models','reports'):
        (root/sub).mkdir(parents=True,exist_ok=True)
    trajectory_name='trajectory_'+identifier+'.xyzv'
    shutil.copy2(output/'trajectory.xyzv',root/'data'/trajectory_name)
    shutil.copy2(source,root/'models'/filename)
    for reference in references:
        basename=Path(reference.replace('\\','/')).name
        if not basename or basename!=reference:
            raise ValueError('Use a relative texture filename in the model before packaging: '+reference)
        choices=[source.parent/basename,source.parent/'textures'/'medres'/basename,source.parent/'textures'/basename]
        texture=next((p for p in choices if p.is_file()),None)
        if texture is None:
            raise ValueError('Referenced texture not found: '+reference)
        destination=root/'textures'/'medres'/basename
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(texture,destination)
    object_name=f'Trajectory {identifier} {selected}'
    ssc=f'''"{object_name}" "Sol"
{{
    Class "spacecraft"
    Mesh "{filename}"
    NormalizeMesh true
    Radius 0.005
    Albedo 0.7
    Beginning {report['start_jd_tdb']:.12f}
    Ending {report['end_jd_tdb']:.12f}
    OrbitFrame {{ EclipticJ2000 {{ Center "Sol" }} }}
    FixedRotation {{ }}
    SampledTrajectory {{ Source "{trajectory_name}" DoublePrecision true Interpolation "Cubic" }}
}}
'''
    (root/(addon_name+'.ssc')).write_text(ssc,encoding='utf-8')
    for name in ('integration_report.json','burns.csv','encounters.csv','planet_clearances.csv','trajectory.csv','arrival_state.json','arrival_state.csv'):
        if (output/name).is_file():shutil.copy2(output/name,root/'reports'/name)
    from app_paths import APP_VERSION
    manifest=dict(engine_version=APP_VERSION,candidate_id=identifier,model=selected,model_filename=filename,model_selection_reason=reason,
                  source_model_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  trajectory_sha256=hashlib.sha256((output/'trajectory.xyzv').read_bytes()).hexdigest(),
                  maximum_heliocentric_distance_au=maximum,celestia_object='Sol/'+object_name,
                  normalized_model_radius_km=.005,start_jd_tdb=report['start_jd_tdb'],end_jd_tdb=report['end_jd_tdb'],
                  additional_patch_burns_kms=report['patch_join_delta_v_kms'],
                  post_flyby_months=report.get('post_flyby_months',0.),
                  powered_flybys_active=report.get('powered_flybys_active',False),
                  candidate_powered_flyby_delta_v_kms=report.get('candidate_powered_flyby_delta_v_kms',0.),
                  source_candidate_status=report.get('source_candidate_status',candidate.get('status')),
                  candidate_passes_requested_limits=report.get('candidate_passes_requested_limits'),
                  requirement_violations=report.get('requirement_violations',[]),
                  passes_original_onboard_budget=report['passes_original_onboard_budget'])
    atomic_json(root/'package_manifest.json',manifest)
    (root/'README.txt').write_text(
        f'CELESTIA TRAJECTORY PACKAGE\n\nExtract the ZIP and copy this entire {addon_name} folder into Celestia/extras.\n'
        f'In Celestia select: {object_name}\nFull object path: Sol/{object_name}\n'
        f'Mission dates: {candidate["launch_date"]} to {candidate["arrival_date"]}\n'
        f'Included model: {filename}\nSelection: {reason}\n'
        'The mesh is normalized to a 5 m reference radius; edit Radius in the SSC to change the displayed scale.\n'
        'The data file is Sun-centered Ecliptic J2000, JD TDB, km and km/s.\n\n'
        f'Additional finite-patch junction burns: {report["patch_join_delta_v_kms"]:.6f} km/s.\n'
        f'Source candidate status: {candidate.get("status","unknown")}.\n'
        f'Requested-limit violations: {"; ".join(report.get("requirement_violations",[])) or "See integration report and source search."}\n'
        'Numerical conic validation is not an optimized fuel budget or continuous n-body validation.\n'
        'See reports/integration_report.json and reports/burns.csv for all maneuvers and limitations.\n',encoding='utf-8')
    zip_name=addon_name+'.zip'
    temporary=output/(zip_name+'.tmp')
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob('*')):
            if path.is_file():archive.write(path,path.relative_to(root.parent))
    temporary.replace(output/zip_name)
    result=dict(state='finished',filename=zip_name,folder=str(root.parent),addon_folder=str(root),**manifest)
    atomic_json(output/('package_'+selected+'.json'),result)
    return result
