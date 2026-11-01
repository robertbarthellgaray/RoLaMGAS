"""RoLaMGAS desktop entry point, including frozen multiprocessing dispatch."""
import multiprocessing
import sys,os,json,importlib


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
        import bootstrap,numpy,scipy,numba,lamberthub
        from pathlib import Path
        Path(sys.argv[2]).write_text(json.dumps(dict(name='RoLaMGAS',numpy=numpy.__version__,scipy=scipy.__version__,
            numba=numba.__version__,data_root=str(DATA_ROOT)),indent=2))
        return
    from gui import main as launch
    launch()


if __name__=='__main__':
    multiprocessing.freeze_support()
    main()
