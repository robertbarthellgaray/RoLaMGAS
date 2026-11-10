"""Build source and native Windows, macOS or Debian release packages.

Run on the target operating system: PyInstaller is not a cross-compiler.
"""
import bootstrap  # noqa: F401
from pathlib import Path
import argparse,hashlib,json,os,platform,re,shutil,subprocess,sys,tempfile,zipfile

ROOT=Path(__file__).resolve().parent
MODULES=['app_paths','bootstrap','rolamgas','gui','gui_worker','mission_search','sequence_timing','dynamics','ephemeris',
         'horizons_targets','network','search_options','candidate_archive','community','candidate_status','earth_return_seeds','historical_seeds','launch_performance','trajectory_transfer','arrival_geometry','cost_refinement','powered_flyby','mercury_returns','candidate_refinement','append_flyby',
         'presentation','live_gallery','integrate_export','celestia_package','moon_screen','baseline_cache',
         'build_database','build_release','restore_diagnostics']
DOCS=['MISSION_STUDIES.md','RESONANT_TRANSFERS.md','LAUNCH_PERFORMANCE.md','WEBSITE_HANDOFF.md','GUI_GUIDE.md','ARRIVAL_AND_MOON_SCREENING.md','TITAN_ARRIVAL.md','POWERED_FLYBYS.md','SHARING.md','COMMUNITY.md','LAB_COMPUTER_REVIEW.md','ARRIVAL_INCLINATION.md','JUICE_DEPARTURE_SEEDS.md','PREVIEW_AND_RESULTS.md','HISTORICAL_SEEDS.md']
DATA_FILES=('departure_seeds','community_seed_catalog.json','community_config.json','gui.html','gui.js','mission_metrics.js','gui.css','gallery.html','sequence_database.json','examples','model_assets',
            'gui_assets','baseline_ephemerides.zip','LICENSE','THIRD_PARTY_NOTICES.md','third_party_licenses')


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
    files += [ROOT/name for name in ('gui.html','gui.js','mission_metrics.js','gui.css','gallery.html','sequence_database.json',
              'requirements.txt','requirements-build.txt','Launch RoLaMGAS.cmd','Launch Mission Search.cmd','Launch GUI.ps1',
              'Launch Command Line.cmd','Setup Python.cmd','.gitignore','.gitattributes')+tuple(DOCS)]
    # Local historical-comparison work is included when present; a clean clone
    # without that optional feature must still produce a complete solver release.
    files += [p for p in (ROOT/'compare_historical_mission.py',ROOT/'Compare Historical Mission.cmd') if p.is_file()]
    files += [ROOT/'community_config.json',ROOT/'community_seed_catalog.json']
    files += [p for p in (ROOT/'community_backend').rglob('*') if p.is_file() and p.suffix in ('.mjs','.sql','.toml','.md')]
    files += list(ROOT.glob('test_*.py'))
    files += list((ROOT/'examples').glob('*.json'))
    files += list((ROOT/'model_assets').glob('*'))
    files += [p for p in (ROOT/'.github').rglob('*') if p.is_file()]
    files += [p for folder in ('docs','tools','gui_assets','departure_seeds','third_party_licenses','mission_comparison') for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files += [ROOT/name for name in ('LICENSE','THIRD_PARTY_NOTICES.md') if (ROOT/name).is_file()]
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(set(files)):
            if not path.is_file():raise ValueError('Release file missing: '+str(path))
            z.write(path,Path('RoLaMGAS')/path.relative_to(ROOT))
        z.write(ROOT/'PUBLIC_README.md','RoLaMGAS/README.md')
        z.write(ROOT/'PUBLIC_README.md','RoLaMGAS/PUBLIC_README.md')
        z.write(baseline,'RoLaMGAS/baseline_ephemerides.zip')
    print('Source release:',destination,flush=True)
    return destination


def pyinstaller_command(system=None,windows_folder=False,output_directory=None):
    """Return arguments only; target selection follows the host, never emulation."""
    system=system or sys.platform
    if system not in ('win32','darwin','linux'):
        raise ValueError('Native releases support Windows, macOS and Linux')
    mode=['--onedir' if windows_folder else '--onefile','--windowed'] if system=='win32' else ['--onedir']
    if windows_folder and system!='win32':raise ValueError('The folder preview option is Windows-only')
    if system=='win32':
        mode+=['--icon',str(ROOT/'gui_assets/rolamgas.ico'),'--version-file',str(ROOT/'gui_assets/windows_version.txt')]
    elif system=='darwin':mode+=['--icon',str(ROOT/'gui_assets/rolamgas.icns')]
    destination=Path(output_directory) if output_directory is not None else (ROOT/'releases/testing/windows-folder' if windows_folder else ROOT/'releases')
    if system=='darwin':
        mode+=['--windowed','--osx-bundle-identifier','io.github.robertbarthellgaray.rolamgas']
    command=[sys.executable,'-m','PyInstaller','--noconfirm',*mode,'--name','RoLaMGAS',
             '--noupx','--distpath',str(destination),'--workpath',str(ROOT/'.build/pyinstaller'),
             '--specpath',str(ROOT/'.build'),'--collect-all','lamberthub','--collect-all','truststore']
    for name in ('tkinter','IPython','pytest','pandas','torch'):
        command+=['--exclude-module',name]
    for module in MODULES:
        command+=['--hidden-import',module,'--add-data',str(ROOT/(module+'.py'))+os.pathsep+'.']
    for name in DATA_FILES:
        path=ROOT/name
        if not path.exists():raise ValueError('Bundled resource missing: '+name)
        command+=['--add-data',str(path)+os.pathsep+(name if path.is_dir() else '.')]
    for path in (ROOT,ROOT/'.build_deps',ROOT.parents[1]/'deps'):
        if path.exists():command+=['--paths',str(path)]
    command.append(str(ROOT/'rolamgas.py'))
    return command


def executable(baseline,windows_folder=False,output_directory=None):
    if baseline!=ROOT/'baseline_ephemerides.zip':
        raise ValueError('Expected the baseline archive in the project root')
    command=pyinstaller_command(windows_folder=windows_folder,output_directory=output_directory)
    paths=[ROOT,ROOT/'.build_deps',ROOT.parents[1]/'deps']
    env=dict(os.environ,MPLBACKEND='Agg',PYTHONIOENCODING='utf-8',PYTHONPATH=os.pathsep.join(str(p) for p in reversed(paths) if p.exists()))
    (ROOT/'.build').mkdir(exist_ok=True)
    with (ROOT/'.build/executable_build.log').open('w',encoding='utf-8') as log:
        subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    destination=Path(command[command.index('--distpath')+1])
    output=(destination/'RoLaMGAS/RoLaMGAS.exe') if windows_folder else destination/('RoLaMGAS.exe' if sys.platform=='win32' else 'RoLaMGAS.app' if sys.platform=='darwin' else 'RoLaMGAS')
    print('Native application:',output,flush=True)
    return output


def architecture(machine=None):
    machine=(machine or platform.machine()).lower()
    if machine in ('x86_64','amd64'):return 'amd64'
    if machine in ('aarch64','arm64'):return 'arm64'
    raise ValueError('Unsupported release CPU architecture: '+machine)


def validate_version(version):
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)*(?:[+~.-][A-Za-z0-9]+)*',version):
        raise ValueError('Version must start with a number and contain only numeric release components and a simple suffix')
    return version


def macos_dmg(app,version):
    if sys.platform!='darwin':raise ValueError('Build a DMG on macOS')
    destination=ROOT/'releases'/f'RoLaMGAS-{version}-macos-{architecture()}.dmg'
    # TemporaryDirectory only owns the staging tree it creates. No user directory
    # or previous release is recursively removed by this script.
    with tempfile.TemporaryDirectory(prefix='rolamgas-dmg-') as temp:
        staging=Path(temp)
        shutil.copytree(app,staging/app.name,symlinks=True)
        (staging/'Applications').symlink_to('/Applications',target_is_directory=True)
        (staging/'Read me first.txt').write_text(
            'Drag RoLaMGAS.app to Applications, then open it.\n'
            'This preview is unsigned and not notarized. macOS may ask you to approve opening it.\n'
            'Only open a download whose source and checksum you trust.\n'
            'The browser interface runs locally and uses your Mac CPU.\n',encoding='utf-8')
        subprocess.run(['hdiutil','create','-ov','-format','UDZO','-volname','RoLaMGAS',
                        '-srcfolder',str(staging),str(destination)],check=True)
    return destination


def debian_control(version,arch):
    return (f'Package: rolamgas\nVersion: {validate_version(version)}\nSection: science\nPriority: optional\n'
            f'Architecture: {arch}\nMaintainer: Robert Barthell Garay <robertbarthellgaray@users.noreply.github.com>\n'
            'Depends: libc6 (>= 2.35), libstdc++6, libglib2.0-0, libx11-6, libxext6, libxrender1, libfontconfig1, xdg-utils\n'
            'Homepage: https://github.com/robertbarthellgaray/RoLaMGAS\n'
            'Description: Local Lambert multi-gravity-assist mission explorer\n'
            ' Browse and search interplanetary trajectories using your CPU.\n'
            ' Includes Python scientific dependencies and an offline eight-planet baseline.\n')


def linux_deb(app,version):
    if sys.platform!='linux':raise ValueError('Build a Debian package on Linux')
    if not shutil.which('dpkg-deb'):raise ValueError('Install dpkg-deb before building a .deb')
    arch=architecture()
    destination=ROOT/'releases'/f'rolamgas_{version}_{arch}.deb'
    with tempfile.TemporaryDirectory(prefix='rolamgas-deb-') as temp:
        staging=Path(temp)
        (staging/'DEBIAN').mkdir()
        (staging/'DEBIAN/control').write_text(debian_control(version,arch),encoding='utf-8')
        shutil.copytree(app,staging/'opt/rolamgas',symlinks=True)
        binary=staging/'usr/bin/rolamgas';binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\nexec /opt/rolamgas/RoLaMGAS "$@"\n',encoding='utf-8');binary.chmod(0o755)
        desktop=staging/'usr/share/applications/rolamgas.desktop';desktop.parent.mkdir(parents=True)
        desktop.write_text('[Desktop Entry]\nType=Application\nName=RoLaMGAS\n'
            'Comment=Robert\'s Lambert Multi Gravity Assist Solver\nExec=rolamgas\n'
            'Terminal=false\nIcon=rolamgas\nCategories=Education;Science;Astronomy;\n',encoding='utf-8')
        icon=staging/'usr/share/icons/hicolor/256x256/apps/rolamgas.png';icon.parent.mkdir(parents=True);shutil.copy2(ROOT/'gui_assets/rolamgas-icon.png',icon)
        legal=staging/'usr/share/doc/rolamgas';legal.mkdir(parents=True)
        shutil.copy2(ROOT/'LICENSE',legal/'copyright')
        for directory in (staging,*[p for p in staging.rglob('*') if p.is_dir()]):directory.chmod(0o755)
        subprocess.run(['dpkg-deb','--build','--root-owner-group',str(staging),str(destination)],check=True)
    return destination


def native_package(app,version):
    validate_version(version)
    if sys.platform=='darwin':return macos_dmg(app,version)
    if sys.platform=='linux':return linux_deb(app,version)
    return app


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',action='store_true',help='Build the native application on this operating system')
    parser.add_argument('--native',action='store_true',help='Also wrap it in a macOS DMG or Linux DEB; Windows outputs EXE')
    parser.add_argument('--version',default='0.2.3',help='Package version, for example 0.2.0')
    args=parser.parse_args();validate_version(args.version)
    baseline=baseline_archive();source_release(baseline)
    if args.exe or args.native:
        app=executable(baseline)
        if args.native:print('Native package:',native_package(app,args.version),flush=True)
    files=[p for p in (ROOT/'releases').iterdir() if p.is_file()]
    manifest={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files if p.name!='release_manifest.json'}
    (ROOT/'releases/release_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')


if __name__=='__main__':main()
