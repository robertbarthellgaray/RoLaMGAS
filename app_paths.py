"""Separate bundled read-only resources from persistent user searches/cache."""
from pathlib import Path
import os,sys,zipfile

RESOURCE_ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
if os.environ.get('ROLAMGAS_DATA_DIR'):
    DATA_ROOT=Path(os.environ['ROLAMGAS_DATA_DIR']).expanduser().resolve()
elif getattr(sys,'frozen',False):
    DATA_ROOT=(Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'RoLaMGAS').resolve()
else:
    DATA_ROOT=RESOURCE_ROOT


def ensure_data():
    DATA_ROOT.mkdir(parents=True,exist_ok=True)
    archive=RESOURCE_ROOT/'baseline_ephemerides.zip'
    if not archive.exists():return
    cache=DATA_ROOT/'cache';cache.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            path=(cache/item.filename).resolve()
            if not path.is_relative_to(cache.resolve()):raise ValueError('Invalid bundled baseline path')
            if not path.exists():
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(z.read(item))


def worker_command(module,*arguments):
    if getattr(sys,'frozen',False):
        return [sys.executable,'--rolamgas-module',module,*map(str,arguments)]
    return [sys.executable,'-u',str(RESOURCE_ROOT/(module+'.py')),*map(str,arguments)]


def worker_environment(log_file):
    return dict(os.environ,ROLAMGAS_LOG_FILE=str(log_file))
