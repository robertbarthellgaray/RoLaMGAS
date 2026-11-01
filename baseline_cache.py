"""Download a durable planetary baseline, independently of any mission search."""
import bootstrap  # noqa: F401
from pathlib import Path
import argparse
from datetime import datetime,timezone
from ephemeris import BODIES,Ephemerides,atomic_json,calendar,fetch,jd


def baseline(cache,start='2027-01-01',end='2100-01-01',mercury_fine=True,stop_file=None):
    cache = Path(cache).resolve()
    cache.mkdir(parents=True,exist_ok=True)
    a,b = jd(start),jd(end)
    if b <= a:
        raise ValueError('Baseline end must follow start')
    entries = []
    for body in BODIES:
        # Mercury gets its requested daily baseline plus an optional finer set.
        for step in ([1.,.25] if body == 'Mercury' and mercury_fine else [1.]):
            cursor = a
            while cursor < b:
                if stop_file and Path(stop_file).exists():
                    raise InterruptedError('Baseline download stopped; completed chunks are preserved')
                stop = min(b,cursor+20000*step)
                matches = []
                for p in cache.glob(body+'_*.json'):
                    import json
                    m = json.loads(p.read_text(encoding='utf-8'))
                    if m['start_jd'] <= cursor and m['end_jd'] >= stop and abs(m['max_step_days']-step)<1e-8:
                        matches.append(m)
                if matches:
                    print(f'Baseline {body} {step:g} d: cached chunk {calendar(cursor)}',flush=True)
                else:
                    fetch(cache,body,cursor,stop,step)
                cursor = stop
            selected = []
            for p in cache.glob(body+'_*.json'):
                import json
                m = json.loads(p.read_text(encoding='utf-8'))
                if abs(m['max_step_days']-step)<1e-8 and m['start_jd'] < b and m['end_jd'] > a:
                    selected.append(dict(metadata_file=p.name,**m))
            entries.append(dict(body=body,step_days=step,files=selected))
            atomic_json(cache/'baseline_manifest.json',dict(start=start,end=end,entries=entries,
                        completed=False,updated_utc=datetime.now(timezone.utc).isoformat()))
    # Prove that the cache can serve every body with no HTTP requests.
    Ephemerides(cache,list(BODIES),a,b,1.,mercury_fine=mercury_fine)
    atomic_json(cache/'baseline_manifest.json',dict(start=start,end=end,entries=entries,completed=True,
                updated_utc=datetime.now(timezone.utc).isoformat(),
                note='Public JPL geometric Sun-centered planet-center Ecliptic J2000 vectors, TDB. Original responses and checksums retained.'))
    print('All eight planetary baselines verified offline.',flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache',default=str(Path(__file__).parent/'cache'))
    p.add_argument('--start',default='2027-01-01')
    p.add_argument('--end',default='2100-01-01')
    p.add_argument('--daily-only',action='store_true')
    args = p.parse_args()
    baseline(args.cache,args.start,args.end,not args.daily_only)
