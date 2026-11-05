"""RoLaMGAS desktop entry point, including frozen multiprocessing dispatch."""
import multiprocessing
import sys,os,json,importlib



def self_check():
    """Offline native smoke check, including actual compiled scientific kernels."""
    import bootstrap,numpy,scipy,numba,lamberthub,ssl,zipfile
    from pathlib import Path
    from app_paths import DATA_ROOT,RESOURCE_ROOT
    from dynamics import lambert,kepler
    from ephemeris import AU,DAY,BODIES
    from network import tls_context
    r0=numpy.array([AU,0.,0.]);r1=numpy.array([.5*AU,numpy.sqrt(.75)*AU,0.])
    va,_=lambert(r0,r1,60.,(0,True))
    propagated,_=kepler(r0,va,60.*DAY)
    error=float(numpy.linalg.norm(propagated-r1))
    compiled=bool(kepler.signatures) and bool(lamberthub.izzo2015.signatures)
    if not numpy.isfinite(error) or error>=1. or not compiled:
        raise RuntimeError('Compiled Lambert/Kepler self-check failed: '+str(error)+' km')
    required=('gui.html','gui.js','mission_metrics.js','gui.css','sequence_database.json','gui_assets/launch_mass_c3.png','gui_assets/rolamgas-icon.png','departure_seeds/juice_departure.json','departure_seeds/eevee_chain.json','departure_seeds/historical_missions.json',
              'model_assets/LowPolySatPanels.3ds','model_assets/LowPolySatRTG.3ds','LICENSE')
    missing=[name for name in required if not (RESOURCE_ROOT/name).is_file()]
    if missing:raise RuntimeError('Bundled resources missing: '+', '.join(missing))
    with zipfile.ZipFile(RESOURCE_ROOT/'baseline_ephemerides.zip') as archive:
        manifest=json.loads(archive.read('baseline_manifest.json'))
        if not manifest.get('completed') or {item['body'] for item in manifest['entries']}!=set(BODIES):
            raise RuntimeError('Bundled eight-planet baseline is incomplete')
        members=set(archive.namelist())
        for entry in manifest['entries']:
            for item in entry['files']:
                for name in (item['metadata_file'],item['raw_file'],str(Path(item['raw_file']).with_suffix('.npz'))):
                    if name not in members:raise RuntimeError('Bundled baseline member missing: '+name)
    context=tls_context()
    if context.verify_mode!=ssl.CERT_REQUIRED or not context.check_hostname:
        raise RuntimeError('Verified TLS context self-check failed')
    return dict(name='RoLaMGAS',numpy=numpy.__version__,scipy=scipy.__version__,numba=numba.__version__,
        data_root=str(DATA_ROOT),scientific_self_check=dict(endpoint_error_km=error,
        numba_kernels_compiled=compiled),bundled_resource_count=len(required),baseline_planets=len(BODIES),
        certificate_verification=True,certificate_context=type(context).__module__+'.'+type(context).__name__)


def main():
    from app_paths import DATA_ROOT,ensure_data
    ensure_data()
    os.environ.setdefault('NUMBA_CACHE_DIR',str(DATA_ROOT/'numba_cache'))
    if sys.stdout is None:
        log=DATA_ROOT/'logs'/('runtime_'+str(os.getpid())+'.log')
        from pathlib import Path
        log=Path(os.environ.get('ROLAMGAS_LOG_FILE',log));log.parent.mkdir(parents=True,exist_ok=True)
        sys.stdout=log.open('a',encoding='utf-8',buffering=1)
        sys.stderr=sys.stdout
    if len(sys.argv)>2 and sys.argv[1]=='--rolamgas-module':
        module=sys.argv[2]
        if module not in ('gui_worker','integrate_export','moon_screen','mission_search','baseline_cache'):
            raise ValueError('Unsupported worker module')
        sys.argv=[module+'.py',*sys.argv[3:]]
        import runpy
        return runpy.run_module(module,run_name='__main__')
    if len(sys.argv)>2 and sys.argv[1]=='--self-check-file':
        from pathlib import Path
        output=Path(sys.argv[2]);output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(self_check(),indent=2),encoding='utf-8')
        return
    from gui import main as launch
    launch()


if __name__=='__main__':
    multiprocessing.freeze_support()
    main()
