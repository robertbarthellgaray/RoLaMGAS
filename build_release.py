"""Build a clean source ZIP and optionally a single Windows executable."""
import bootstrap  # noqa: F401
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,zipfile

ROOT=Path(__file__).resolve().parent
MODULES=['app_paths','bootstrap','rolamgas','gui','gui_worker','mission_search','dynamics','ephemeris',
         'horizons_targets','cost_refinement','powered_flyby','mercury_returns','candidate_refinement','append_flyby',
         'presentation','live_gallery','integrate_export','celestia_package','moon_screen','baseline_cache',
         'build_database','build_release','restore_diagnostics']
DOCS=['GUI_GUIDE.md','ARRIVAL_AND_MOON_SCREENING.md','TITAN_ARRIVAL.md','POWERED_FLYBYS.md','SHARING.md']


def baseline_archive():
    destination=ROOT/'baseline_ephemerides.zip'
    manifest=ROOT/'cache/baseline_manifest.json'
    if not manifest.exists():
        if destination.exists():return destination
        raise ValueError('Download the eight-planet baseline before building a release')
    doc=json.loads(manifest.read_text(encoding='utf-8'))
    if not doc.get('completed'):raise ValueError('Baseline download is incomplete')
    names={'baseline_manifest.json'}
    for entry in doc['entries']:
        for item in entry['files']:
            names.add(item['metadata_file']);names.add(item['raw_file'])
            names.add(str(Path(item['raw_file']).with_suffix('.npz')))
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name in sorted(names):
            path=ROOT/'cache'/name
            if Path(name).name!=name or not path.is_file():raise ValueError('Invalid baseline member '+name)
            archive.write(path,name)
    return destination


def source_release(baseline):
    release=ROOT/'releases';release.mkdir(exist_ok=True)
    destination=release/'RoLaMGAS-source.zip'
    files=[ROOT/(name+'.py') for name in MODULES]
    files += [ROOT/name for name in ('gui.html','gui.js','gui.css','gallery.html','sequence_database.json',
              'requirements.txt','requirements-build.txt','Launch RoLaMGAS.cmd','Launch Mission Search.cmd','Launch GUI.ps1',
              'Launch Command Line.cmd','Setup Python.cmd','.gitignore','.gitattributes')+tuple(DOCS)]
    files += list(ROOT.glob('test_*.py'))
    files += list((ROOT/'examples').glob('*.json'))
    files += list((ROOT/'model_assets').glob('*'))
    files += [p for p in (ROOT/'.github').rglob('*') if p.is_file()]
    files += [p for folder in ('docs','tools','third_party_licenses') for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files += [ROOT/name for name in ('LICENSE','THIRD_PARTY_NOTICES.md') if (ROOT/name).is_file()]
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in files:
            if not path.is_file():raise ValueError('Release file missing: '+str(path))
            z.write(path,Path('RoLaMGAS')/path.relative_to(ROOT))
        z.write(ROOT/'PUBLIC_README.md','RoLaMGAS/README.md')
        z.write(ROOT/'PUBLIC_README.md','RoLaMGAS/PUBLIC_README.md')
        z.write(baseline,'RoLaMGAS/baseline_ephemerides.zip')
    print('Source release:',destination,flush=True)


def executable(baseline):
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--onefile','--windowed','--name','RoLaMGAS',
             '--distpath',str(ROOT/'releases'),'--workpath',str(ROOT/'.build/pyinstaller'),
             '--specpath',str(ROOT/'.build'),'--collect-all','lamberthub']
    for name in ('tkinter','IPython','pytest','pandas','torch'):
        command+=['--exclude-module',name]
    for module in MODULES:
        command+=['--hidden-import',module,'--add-data',str(ROOT/(module+'.py'))+os.pathsep+'.']
    for name in ('gui.html','gui.js','gui.css','gallery.html','sequence_database.json','examples','model_assets','baseline_ephemerides.zip','LICENSE','THIRD_PARTY_NOTICES.md','third_party_licenses'):
        command+=['--add-data',str(ROOT/name)+os.pathsep+name if (ROOT/name).is_dir() else str(ROOT/name)+os.pathsep+'.']
    paths=[ROOT,ROOT/'.build_deps',ROOT.parents[1]/'deps']
    for path in paths:
        if path.exists():command+=['--paths',str(path)]
    command.append(str(ROOT/'rolamgas.py'))
    env=dict(os.environ,MPLBACKEND='Agg',PYTHONIOENCODING='utf-8',PYTHONPATH=os.pathsep.join(str(p) for p in reversed(paths) if p.exists()))
    (ROOT/'.build').mkdir(exist_ok=True)
    with (ROOT/'.build/executable_build.log').open('w',encoding='utf-8') as log:
        subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    print('Executable:',ROOT/'releases/RoLaMGAS.exe',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--exe',action='store_true')
    args=parser.parse_args();baseline=baseline_archive();source_release(baseline)
    if args.exe:executable(baseline)
    files=[p for p in (ROOT/'releases').iterdir() if p.is_file()]
    manifest={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files if p.name!='release_manifest.json'}
    (ROOT/'releases/release_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')


if __name__=='__main__':main()
