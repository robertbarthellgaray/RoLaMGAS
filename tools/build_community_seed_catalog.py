"""Create a public, nonidentifying starter catalog from local passing history."""
from pathlib import Path
import sys,json,argparse,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mission_search import normalize,routes_for,get_ephemerides
from community import public_record
from dynamics import Model
from ephemeris import atomic_json

def build(history,cache,output):
    records={};checked=skipped=0
    for folder in sorted(Path(history).iterdir()):
        if not (folder/'results.json').is_file() or not (folder/'run_manifest.json').is_file():continue
        try:
            manifest=json.loads((folder/'run_manifest.json').read_text(encoding='utf-8'))
            rows=json.loads((folder/'results.json').read_text(encoding='utf-8')).get('candidates',[])
            if not rows:continue
            config=normalize(dict(manifest['config'],cache=str(cache)));routes=routes_for(config);ep=get_ephemerides(config,routes)
            models={route['id']:Model(route,config,ep) for route in routes}
            for old in rows:
                try:
                    model=models[old['sequence']];q=model.evaluate(old['x'],old['branches']);checked+=1
                    if not model.accepted(q):skipped+=1;continue
                    q.update(status='passes_configured_patched_conic_screen',discovered_unix=old.get('discovered_unix',time.time()))
                    record=public_record(q,config,model.route)
                    if record:records.setdefault(record['id'],record)
                except (ValueError,KeyError,TypeError,RuntimeError,AssertionError,OverflowError):skipped+=1
        except (ValueError,KeyError,TypeError,OSError):skipped+=1
    doc=dict(schema_version=1,description='Public passing trajectory starter seeds; locally revalidated before reuse.',candidates=list(records.values()))
    atomic_json(output,doc);print(json.dumps(dict(candidates=len(records),checked=checked,skipped=skipped,bytes=Path(output).stat().st_size)),flush=True)
    return doc

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--history',required=True);p.add_argument('--cache',required=True);p.add_argument('--output',required=True);args=p.parse_args();build(args.history,args.cache,args.output)
