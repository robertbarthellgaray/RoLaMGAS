"""Recover saved diagnostics omitted by older top-three/top-ten summaries."""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import hashlib
import json
import os
import re
import shutil
from ephemeris import atomic_json


def restore(folder):
    folder=Path(folder)
    result=folder/'results.json'
    if not result.is_file():return None
    status=json.loads((folder/'gui_status.json').read_text()) if (folder/'gui_status.json').is_file() else {}
    if status.get('state') in ('starting','preparing','running'):return None
    summary=json.loads(result.read_text());before=len(summary.get('near_misses',[]))
    records=list(summary.get('near_misses',[]))
    for path in (folder/'checkpoints').glob('*.json'):
        records.extend(json.loads(path.read_text()).get('near_misses',[]))
    for path in (folder/'candidates').glob('*.json'):
        if re.fullmatch('[a-f0-9]{12}',path.stem):
            q=json.loads(path.read_text())
            if not q.get('status','').startswith('passes'):records.append(q)
    distinct={}
    for q in records:
        if not all(k in q for k in ('sequence','branches','dates_jd_tdb','x')):continue
        key=json.dumps([q['sequence'],q['branches'],q['dates_jd_tdb'],q['x']],sort_keys=True)
        identifier=q.get('id') or hashlib.sha256(key.encode()).hexdigest()[:12]
        q['id']=identifier;distinct[identifier]=q
    if len(distinct)<=before:return None
    old_stat=folder.stat()
    backup=folder/'diagnostic_history'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True)
    shutil.copy2(result,backup/'results.json')
    summary['near_misses']=sorted(distinct.values(),key=lambda q:q.get('screening_residual_norm',float('inf')))
    summary['diagnostics_restored_from_saved_records']=True
    atomic_json(result,summary)
    # A fresh gallery is built in the GUI's archive-rendering thread on opening.
    live=folder/'live.json'
    if live.is_file():live.replace(backup/'live.json')
    os.utime(folder,(old_stat.st_atime,old_stat.st_mtime))
    return dict(run=folder.name,before=before,after=len(distinct),backup=str(backup))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('runs');a=p.parse_args()
    restored=[]
    for folder in Path(a.runs).iterdir():
        if folder.is_dir():
            result=restore(folder)
            if result:restored.append(result)
    print(json.dumps(restored,indent=2))
