"""One GUI-owned search process; numerical workers remain separate CPU processes."""
import bootstrap  # noqa: F401
from pathlib import Path
from datetime import datetime,timezone
import argparse
import json
import multiprocessing
import traceback
import threading
import time
from ephemeris import atomic_json
from mission_search import normalize,routes_for,prepare,run


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output',required=True)
    p.add_argument('--recover-from')
    args = p.parse_args()
    output = Path(args.output).resolve()
    stop_file = output/'stop.request'
    started = datetime.now(timezone.utc).isoformat()
    heartbeat_stop=threading.Event()
    clock_start=time.monotonic()
    def heartbeat():
        while not heartbeat_stop.is_set():
            atomic_json(output/'heartbeat.json',dict(updated_unix=time.time(),elapsed_seconds=time.monotonic()-clock_start))
            heartbeat_stop.wait(2)
    thread=threading.Thread(target=heartbeat,daemon=True)
    thread.start()
    def state(name,message):
        atomic_json(output/'gui_status.json',dict(state=name,message=message,started_utc=started,
                    updated_utc=datetime.now(timezone.utc).isoformat()))
    try:
        raw = json.loads((output/'request.json').read_text(encoding='utf-8'))
        c = normalize(raw,output)
        routes = routes_for(c)
        state('preparing','Checking cached vectors and downloading only missing coverage.')
        prepare(c,routes,stop_file=stop_file)
        if stop_file.exists():
            raise InterruptedError('Stopped before search')
        state('running','Searching locally; candidate images appear as workers report them.')
        run(c,routes,output,stop_file=stop_file,managed=True,checkpoint_seed=args.recover_from)
        state('stopped' if stop_file.exists() else 'finished','Search stopped; candidates saved.' if stop_file.exists() else 'Search complete. Candidates and images saved.')
    except InterruptedError as exc:
        state('stopped',str(exc))
    except Exception as exc:
        traceback.print_exc()
        state('failed',str(exc))
        raise
    finally:
        heartbeat_stop.set()
        thread.join(timeout=3)


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
