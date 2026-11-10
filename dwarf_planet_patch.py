"""Optional, encounter-year Celestia dwarf-planet ephemeris overrides.

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
        if parent=='Sol' and (classification=='dwarfplanet' or kind=='ReferencePoint') and 'EllipticalOrbit' in props:
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
                item_type=kind,properties=props))
        i=end+1
    if not result:raise ValueError('No supported dwarf-planet Keplerian definitions found')
    return result

def load_catalog(path=None):
    if path:
        source=Path(path).expanduser()
        if source.suffix.lower()!='.ssc' or not source.is_file():raise ValueError('Select an existing dwarfplanets.ssc file')
        return catalog_from_ssc(source.read_text(encoding='utf-8-sig')),str(source)
    for root in (os.environ.get('ProgramFiles'),os.environ.get('ProgramFiles(x86)')):
        if root:
            source=Path(root)/'Celestia/data/dwarfplanets.ssc'
            if source.is_file():return catalog_from_ssc(source.read_text(encoding='utf-8-sig')),str(source)
    return json.loads(ASSET.read_text(encoding='utf-8'))['objects'],'bundled Celestia dwarf-planet orbit snapshot'

def select_template(config,objects):
    descriptor=config.get('target_object') or {}
    name=descriptor.get('name') or config.get('target','')
    ident=str(descriptor.get('id',''))
    # A Pluto-system design is not a design aimed at the center of Pluto itself.
    if ident=='9' or name.casefold()=='pluto barycenter':
        return next((r for r in objects if r['name']=='Pluto-Charon'),None),name,descriptor
    designation=str(descriptor.get('designation',''))
    if ident.isdigit() and 20000000<int(ident)<30000000:designation=designation or str(int(ident)-20000000)
    for row in objects:
        if row['item_type']!='Body':continue
        aliases=row['aliases'];words=[re.escape(row['name'])]
        named=any(re.search(r'(?<!\w)'+word+r'(?!\w)',name,re.I) for word in words)
        numbered=bool(designation and any(re.match(re.escape(designation)+r'\b',a) for a in aliases))
        if named or numbered:return row,name,descriptor
    return None,name,descriptor

def patch_info(config,catalog_path=None):
    objects,source=load_catalog(catalog_path);row,name,descriptor=select_template(config,objects)
    return dict(available=bool(row and descriptor.get('command')),target=name,
        celestia_object=('Sol/'+row['name'] if row else None),catalog_source=source,
        barycenter=bool(row and row['item_type']=='ReferencePoint'),
        note=('Celestia Keplerian dwarf-planet orbits can differ from JPL positions by millions of km. '
              'This option adds JPL Horizons position/velocity data for the encounter year(s), using the same target identity as the spacecraft export. '
              'A Modify timeline restores the original orbit outside that interval and keeps the existing appearance. '
              'Pluto barycenter targets patch Pluto–Charon, not the surface of Pluto. Moon ephemerides are not independently corrected. '
              'The package may download missing JPL data. It does not edit your Celestia installation. '
              'Avoid overlapping ephemeris patches from multiple addons; remove the optional patch SSC to undo it. '
              'Switching back to the old orbit at the year boundaries may produce a position jump away from the flyby.'))

def create_patch(root,candidate,config,report,catalog_path=None):
    root=Path(root);objects,source=load_catalog(catalog_path);row,name,descriptor=select_template(config,objects)
    if row is None or not descriptor.get('command'):raise ValueError('No original Celestia dwarf-planet orbit matched this resolved target')
    register_target(descriptor)
    dates=[d for b,d in zip(candidate['bodies'],candidate['dates_jd_tdb']) if b==name]
    if not dates:raise ValueError('No encounter epoch found for the resolved dwarf planet')
    years=[datetime.fromisoformat(calendar(d).split(' TDB')[0]).year for d in dates]
    first,last=min(years),max(years)+1;start,end=jd(f'{first:04d}-01-01'),jd(f'{last:04d}-01-01')
    # Physical Pluto has 6.4-day binary motion, unlike its slowly moving barycenter.
    step=.125 if row['name']=='Pluto' else 1.
    cache=Path(config.get('cache') or DATA_ROOT/'cache')
    try:ep=Ephemerides(cache,[name],start,end,step,mercury_fine=False)
    except ValueError:
        fetch(cache,name,start,end,step);ep=Ephemerides(cache,[name],start,end,step,mercury_fine=False)
    stem='jpl_'+re.sub(r'[^a-z0-9]+','_',row['name'].casefold()).strip('_')+f'_{first}_{last}'
    (root/'data').mkdir(parents=True,exist_ok=True)
    xyzv=root/'data'/(stem+'.xyzv')
    times=np.unique(np.r_[np.arange(start,end,step),dates,end])
    with xyzv.open('w',encoding='utf-8') as stream:
        for t in times:
            state=ep.state(name,t)
            if not np.all(np.isfinite(state)):raise ValueError('Nonfinite JPL dwarf-planet state')
            stream.write(f'{t:.12f} '+' '.join(f'{v:.15e}' for v in state)+'\n')
    props=row['properties'];old='\n'.join(props.values())
    spin='\n'.join(value for key,value in props.items() if key not in ('OrbitFrame','EllipticalOrbit'))
    item='ReferencePoint ' if row['item_type']=='ReferencePoint' else ''
    ssc=(f'# RoLaMGAS optional JPL override: {name}; Sun-centered Ecliptic J2000, JD TDB.\n'
         '# Original orbit fields derived from Celestia dwarfplanets.ssc, GPL-2.0-or-later; see provenance.\n'
         f'Modify {item}{json.dumps(row["name"])} "Sol"\n{{\n Timeline\n [\n'
         f'  {{\n Ending {start:.12f}\n{old}\n  }}\n'
         f'  {{\n Ending {end:.12f}\n OrbitFrame {{ EclipticJ2000 {{ Center "Sol" }} }}\n'
         f' SampledTrajectory {{ Source "{xyzv.name}" DoublePrecision true Interpolation "cubic" }}\n{spin}\n  }}\n'
         f'  {{\n{old}\n  }}\n ]\n}}\n')
    filename='jpl_dwarf_planet_patch.ssc';(root/filename).write_text(ssc,encoding='utf-8')
    source_text=Path(source).read_text(encoding='utf-8-sig') if Path(source).is_file() else ''
    attribution=([line for line in source_text.splitlines() if 'SPDX-FileCopyrightText:' in line]
                 or json.loads(ASSET.read_text(encoding='utf-8'))['attribution'])
    shutil.copy2(RESOURCE_ROOT/'LICENSE',root/'reports/Celestia_orbit_LICENSE.txt')
    metadata=dict(target_identity=descriptor,celestia_object='Sol/'+row['name'],catalog_source=source,
        license='GPL-3.0-or-later (derived from GPL-2.0-or-later Celestia orbit fields)',attribution=attribution,
        start_jd_tdb=start,end_jd_tdb=end,start_date=f'{first}-01-01',end_date=f'{last}-01-01',
        step_days=step,rows=len(times),frame='Sun-centered Ecliptic J2000, JD TDB, km, km/s',
        barycenter=row['item_type']=='ReferencePoint',original_properties=props,
        ephemeris_sources=ep.manifest,trajectory_sha256=hashlib.sha256(xyzv.read_bytes()).hexdigest(),
        files=[filename,'data/'+xyzv.name,'reports/dwarf_planet_patch.json','reports/Celestia_orbit_LICENSE.txt'],
        limitations=patch_info(config,catalog_path)['note'])
    atomic_json(root/'reports/dwarf_planet_patch.json',metadata)
    return metadata
