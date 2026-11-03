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


def database_decision(output,report,stop_file,state):
    count=report['passing_matches']
    if count<3:
        state('running',f'Database check found {count} verified matches; starting a local CPU search automatically.')
        return True
    state('awaiting_database_decision',f'{count} database trajectories fit all your requirements. Review them below, then choose whether to search locally too.')
    choice=Path(output)/'database_decision.json'
    while True:
        if Path(stop_file).exists():raise InterruptedError('Stopped while awaiting database-search decision; saved matches retained.')
        if choice.exists():
            decision=json.loads(choice.read_text(encoding='utf-8')).get('run_local')
            if not isinstance(decision,bool):raise ValueError('Invalid database-search decision')
            if decision:state('running','Keeping verified database matches and starting the local CPU search you requested.')
            return decision
        time.sleep(.25)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output',required=True)
    p.add_argument('--recover-from')
    p.add_argument('--local-search',action='store_true',help='Explicitly run local optimization without the database confirmation.')
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
        state('checking_database','Checking the shared trajectory database and independently verifying matches before starting optimizer workers.')
        gate=None if args.local_search or args.recover_from else lambda report:database_decision(output,report,stop_file,state)
        run(c,routes,output,stop_file=stop_file,managed=True,checkpoint_seed=args.recover_from,database_gate=gate)
        database=json.loads((output/'database_first.json').read_text(encoding='utf-8')) if (output/'database_first.json').exists() else {}
        message=(f"Using {database.get('passing_matches',0)} verified database matches; local optimization was not run." if database.get('cpu_search_started') is False else 'Search complete. Candidates and images saved.')
        state('stopped' if stop_file.exists() else 'finished','Search stopped; candidates saved.' if stop_file.exists() else message)
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
