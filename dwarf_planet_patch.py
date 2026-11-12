"""Optional, encounter-year Celestia small-body ephemeris overrides.

Only orbital timeline properties are copied from Celestia's original catalog.
Textures/shape are retained with Modify, and original frames/rotation are restored
outside the sampled interval. JPL target identity is never silently substituted.
"""
from pathlib import Path
from datetime import datetime
import hashlib,json,os,re,shutil
import numpy as np
from app_paths import RESOURCE_ROOT,DATA_ROOT
from ephemeris import Ephemerides,fetch,jd,calendar,atomic_json
from horizons_targets import register_target

ASSET=RESOURCE_ROOT/'celestia_assets/dwarf_planet_orbits.json'
SMALL_BODY_ASSET=RESOURCE_ROOT/'celestia_assets/small_body_orbits.json'
CATALOG_NAMES=('dwarfplanets.ssc','asteroids.ssc','comets.ssc','interstellar.ssc','outersys.ssc','solarsys.ssc')
PROPERTIES={'EllipticalOrbit','OrbitFrame','BodyFrame','UniformRotation','FixedRotation',
            'PrecessingRotation','CustomRotation','SpiceRotation','ScriptedRotation'}
TOKENS=re.compile(r'"(?:\\.|[^"\\])*"|\#[^\r\n]*|[{}\[\]]|[^\s{}\[\]#"]+')

def catalog_from_ssc(text):
    """Read balanced blocks, ignoring braces in comments and quoted values."""
    tokens=[m for m in TOKENS.finditer(text) if not m.group().startswith('#')]
    def end_block(start):
        closing={'{':'}','[':']'};stack=[]
        for i in range(start,len(tokens)):
            token=tokens[i].group()
            if token in closing:stack.append(closing[token])
            elif token in ('}',']'):
                if not stack or token!=stack.pop():raise ValueError('Unbalanced Celestia catalog')
                if not stack:return i
        raise ValueError('Unclosed Celestia catalog block')
    result=[];i=0
    while i<len(tokens):
        kind='Body'
        if tokens[i].group()=='ReferencePoint':kind='ReferencePoint';i+=1
        if i+2>=len(tokens) or not tokens[i].group().startswith('"') or not tokens[i+1].group().startswith('"') or tokens[i+2].group()!='{':
            i+=1;continue
        label=json.loads(tokens[i].group());parent=json.loads(tokens[i+1].group());start=i+2;end=end_block(start)
        props={};classification=None;j=start+1
        while j<end:
            key=tokens[j].group()
            if key=='Class' and j+1<end:classification=tokens[j+1].group().strip('"')
            if j+1<end and tokens[j+1].group() in ('{','['):
                stop=end_block(j+1)
                if key in PROPERTIES:props[key]=text[tokens[j].start():tokens[stop].end()]
                j=stop+1
            elif key in PROPERTIES and j+1<end:
                props[key]=text[tokens[j].start():tokens[j+1].end()];j+=2
            else:j+=1
        if parent=='Sol' and (classification in ('dwarfplanet','asteroid','comet','smallbody') or kind=='ReferencePoint') and 'EllipticalOrbit' in props:
            # An unspecified spin period inherits the old orbital period. Pin it
            # before replacing that orbit by an aperiodic sampled trajectory.
            rotation=props.get('UniformRotation','')
            if rotation and not re.search(r'\bPeriod\b',re.sub(r'#[^\n]*','',rotation)):
                period=re.search(r'\bPeriod\s+([\d.eE+-]+)',props['EllipticalOrbit'])
                if period:
                    frame=props.get('OrbitFrame','');relative=bool(re.search(r'Center\s+"(?!Sol")[^"]+"',frame))
                    hours=float(period[1])*24*(1 if relative else 365.25)
                    props['UniformRotation']=rotation.replace('{','{\n    Period '+format(hours,'.15g'),1)
            result.append(dict(name=label.split(':')[0],aliases=label.split(':'),parent=parent,
                item_type=kind,classification=classification,properties=props))
        i=end+1
    if not result:raise ValueError('No supported small-body Keplerian definitions found in this Celestia catalog')
    return result

def read_catalog(source):
    source=Path(source);raw=source.read_bytes();text=raw.decode('utf-8-sig').replace('\r\n','\n')
    rows=catalog_from_ssc(text)
    attribution=[line for line in text.splitlines() if 'SPDX-FileCopyrightText:' in line]
    license_match=re.search(r'SPDX-License-Identifier:\s*([^\r\n]+)',text)
    for row in rows:
        row.update(catalog_source=str(source),source_sha256=hashlib.sha256(raw).hexdigest(),
                   attribution=attribution,license=license_match[1].strip() if license_match else 'not specified in source catalog')
    return rows


def load_catalog(path=None):
    if path:
        source=Path(path).expanduser()
        if source.suffix.lower()!='.ssc' or not source.is_file():raise ValueError('Select an existing Celestia .ssc catalog file')
        return read_catalog(source),str(source)
    for root in (os.environ.get('ProgramFiles'),os.environ.get('ProgramFiles(x86)')):
        if root:
            rows=[];sources=[]
            for name in CATALOG_NAMES:
                source=Path(root)/'Celestia/data'/name
                if not source.is_file():continue
                try:rows.extend(read_catalog(source));sources.append(str(source))
                except ValueError as exc:
                    if not str(exc).startswith('No supported small-body'):raise
            if rows:return rows,'; '.join(sources)
    asset=SMALL_BODY_ASSET if SMALL_BODY_ASSET.is_file() else ASSET
    return json.loads(asset.read_text(encoding='utf-8'))['objects'],'bundled Celestia small-body orbit snapshot'


def normalized_name(value):
    return ' '.join(re.findall(r'\w+',str(value).casefold()))


def comet_designation(value):
    value=str(value).strip()
    match=re.match(r'^(\d+[PDI](?:-[A-Z]+)?)(?=[\s/:(]|$)|^([ACPDXI]/?\s*\d{4}\s+[A-Z]\d+(?:-[A-Z]+)?)',value,re.I)
    return normalized_name(match.group()) if match else None

def select_template(config,objects):
    descriptor=config.get('target_object') or {}
    name=descriptor.get('name') or config.get('target','')
    ident=str(descriptor.get('id',''))
    # A Pluto-system design is not a design aimed at the center of Pluto itself.
    if ident=='9' or name.casefold()=='pluto barycenter':
        return next((r for r in objects if r['name']=='Pluto-Charon'),None),name,descriptor
    designation=str(descriptor.get('designation','')).strip()
    number=str(int(ident)-20000000) if ident.isdigit() and 20000000<int(ident)<30000000 else (designation if designation.isdigit() else None)
    comet=comet_designation(designation) or comet_designation(name)
    target=normalized_name(name);design=normalized_name(designation);matches=[]
    for row in objects:
        if row['item_type']!='Body':continue
        aliases=row['aliases'];keys=[normalized_name(a) for a in aliases]
        numbers={m[1] for a in aliases if (m:=re.match(r'^(\d+)(?:\s|$)',a))}
        comet_keys={key for a in aliases if (key:=comet_designation(a))}
        # Never let a common name such as ATLAS override conflicting identities.
        if number and numbers and number not in numbers:continue
        if comet and comet_keys and comet not in comet_keys:continue
        score=100 if (number and number in numbers) or (comet and comet in comet_keys) else 0
        if not score and design and any(k==design or k.startswith(design+' ') for k in keys):score=90
        if not score and not comet:
            if target in keys:score=80
            elif any(len(k)>=3 and (' '+k+' ') in (' '+target+' ') for k in keys):score=60
        if score:matches.append((score,row))
    if not matches:return None,name,descriptor
    best=max(score for score,_ in matches);rows=[row for score,row in matches if score==best]
    if len(rows)!=1:raise ValueError('Ambiguous Celestia target definitions; select the original .ssc file for this small body')
    return rows[0],name,descriptor

def patch_info(config,catalog_path=None):
    objects,source=load_catalog(catalog_path);row,name,descriptor=select_template(config,objects)
    return dict(available=bool(row and descriptor.get('command')),target=name,
        celestia_object=('Sol/'+row['name'] if row else None),catalog_source=row.get('catalog_source',source) if row else source,
        barycenter=bool(row and row['item_type']=='ReferencePoint'),
        note=('Celestia Keplerian asteroid, comet, centaur, trans-Neptunian and dwarf-planet orbits can differ from JPL positions by millions of km. '
              'This option adds JPL Horizons position/velocity data for the encounter year(s), using the same target identity as the spacecraft export. '
              'A Modify timeline restores the original orbit outside that interval and keeps the existing appearance. '
              'Pluto barycenter targets patch Pluto–Charon, not the surface of Pluto. Moon ephemerides are not independently corrected. '
              'The package may download missing JPL data. It does not edit your Celestia installation. '
              'Installed asteroid, comet, interstellar, outer-system and dwarf-planet catalogs are searched. For other addons, choose their original .ssc file. '
              'A target absent from these definitions is not silently created or replaced by a different object. '
              'Avoid overlapping ephemeris patches from multiple addons; remove the optional patch SSC to undo it. '
              'Switching back to the old orbit at the year boundaries may produce a position jump away from the flyby.'))

def create_patch(root,candidate,config,report,catalog_path=None):
    root=Path(root);objects,source=load_catalog(catalog_path);row,name,descriptor=select_template(config,objects)
    if row is None or not descriptor.get('command'):raise ValueError('No original Celestia small-body orbit matched this resolved target; select its original .ssc file')
    register_target(descriptor)
    dates=[d for b,d in zip(candidate['bodies'],candidate['dates_jd_tdb']) if b==name]
    if not dates:raise ValueError('No encounter epoch found for the resolved small body')
    years=[datetime.fromisoformat(calendar(d).split(' TDB')[0]).year for d in dates]
    first,last=min(years),max(years)+1;start,end=jd(f'{first:04d}-01-01'),jd(f'{last:04d}-01-01')
    # Physical Pluto has 6.4-day binary motion, unlike its slowly moving barycenter.
    from horizons_targets import is_comet
    step=1/24 if is_comet(descriptor) or row.get('classification')=='comet' else (.125 if row['name']=='Pluto' or 0<float(descriptor.get('perihelion_au',1.) or 1.)<.5 else 1.)
    cache=Path(config.get('cache') or DATA_ROOT/'cache')
    try:ep=Ephemerides(cache,[name],start,end,step,mercury_fine=False)
    except ValueError:
        fetch(cache,name,start,end,step);ep=Ephemerides(cache,[name],start,end,step,mercury_fine=False)
    stem='jpl_'+re.sub(r'[^a-z0-9]+','_',row['name'].casefold()).strip('_')+f'_{first}_{last}'
    (root/'data').mkdir(parents=True,exist_ok=True)
    (root/'reports').mkdir(parents=True,exist_ok=True)
    xyzv=root/'data'/(stem+'.xyzv')
    times=np.unique(np.r_[np.arange(start,end,step),dates,end])
    with xyzv.open('w',encoding='utf-8') as stream:
        for t in times:
            state=ep.state(name,t)
            if not np.all(np.isfinite(state)):raise ValueError('Nonfinite JPL small-body state')
            stream.write(f'{t:.12f} '+' '.join(f'{v:.15e}' for v in state)+'\n')
    props=row['properties'];old='\n'.join(props.values())
    spin='\n'.join(value for key,value in props.items() if key not in ('OrbitFrame','EllipticalOrbit'))
    item='ReferencePoint ' if row['item_type']=='ReferencePoint' else ''
    ssc=(f'# RoLaMGAS optional JPL override: {name}; Sun-centered Ecliptic J2000, JD TDB.\n'
         '# Original orbit/rotation fields copied from the source catalog; see provenance for attribution and license.\n'
         f'Modify {item}{json.dumps(row["name"])} "Sol"\n{{\n Timeline\n [\n'
         f'  {{\n Ending {start:.12f}\n{old}\n  }}\n'
         f'  {{\n Ending {end:.12f}\n OrbitFrame {{ EclipticJ2000 {{ Center "Sol" }} }}\n'
         f' SampledTrajectory {{ Source "{xyzv.name}" DoublePrecision true Interpolation "cubic" }}\n{spin}\n  }}\n'
         f'  {{\n{old}\n  }}\n ]\n}}\n')
    legacy=row.get('classification','dwarfplanet')=='dwarfplanet' or row['item_type']=='ReferencePoint'
    filename='jpl_dwarf_planet_patch.ssc' if legacy else 'jpl_small_body_patch.ssc'
    report_file='reports/dwarf_planet_patch.json' if legacy else 'reports/small_body_patch.json'
    (root/filename).write_text(ssc,encoding='utf-8')
    attribution=row.get('attribution',[])
    shutil.copy2(RESOURCE_ROOT/'LICENSE',root/'reports/Celestia_orbit_LICENSE.txt')
    metadata=dict(target_identity=descriptor,celestia_object='Sol/'+row['name'],catalog_source=row.get('catalog_source',source),
        source_catalog_sha256=row.get('source_sha256'),object_class=row.get('classification'),report_file=report_file,
        license='GPL-3.0-or-later (generated RoLaMGAS patch code)',source_license=row.get('license','not specified in source catalog'),attribution=attribution,
        start_jd_tdb=start,end_jd_tdb=end,start_date=f'{first}-01-01',end_date=f'{last}-01-01',
        step_days=step,rows=len(times),frame='Sun-centered Ecliptic J2000, JD TDB, km, km/s',
        barycenter=row['item_type']=='ReferencePoint',original_properties=props,
        ephemeris_sources=ep.manifest,trajectory_sha256=hashlib.sha256(xyzv.read_bytes()).hexdigest(),
        files=[filename,'data/'+xyzv.name,report_file,'reports/Celestia_orbit_LICENSE.txt'],
        limitations=patch_info(config,catalog_path)['note'])
    atomic_json(root/report_file,metadata)
    return metadata
