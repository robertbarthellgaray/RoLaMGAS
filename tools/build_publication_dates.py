"""Record real publication evidence, never a mission epoch or a guessed solve time."""
from pathlib import Path
from datetime import datetime,timezone
import json,subprocess
ROOT=Path(__file__).resolve().parents[1]

def build():
    target=ROOT/'docs/data/publication_dates.json'
    prior=json.loads(target.read_text(encoding='utf-8')).get('candidates',{}) if target.exists() else {}
    history=dict(prior)
    log=subprocess.check_output(['git','log','--reverse','--format=@@%cI','--name-only','--diff-filter=A','--','docs/data/cases'],cwd=ROOT,text=True,encoding='utf-8')
    stamp=None
    for line in log.splitlines():
        if line.startswith('@@'):stamp=line[2:]
        elif line.startswith('docs/data/cases/') and line.endswith('.json'):
            history.setdefault(Path(line).stem,dict(added_at=stamp,basis='first Git commit containing this candidate'))
    now=datetime.now(timezone.utc).isoformat()
    index=json.loads((ROOT/'docs/data/index.json').read_text(encoding='utf-8'))
    for row in index['cases']:history.setdefault(row['id'],dict(added_at=now,basis='publication batch time'))
    archive=json.loads((ROOT/'docs/data/community_seed_catalog.json').read_text(encoding='utf-8'))
    for row in archive['candidates']:
        stamp=row.get('added_at') or row.get('received_at')
        if stamp:
            entry=dict(added_at=stamp,basis=row.get('added_at_basis','earliest retained receipt'))
            history.setdefault(row['id'],entry)
            alias=archive.get('curated_aliases',{}).get(row['id'])
            if alias:
                previous=history.get(alias)
                if previous is None or previous['basis']=='publication batch time' or datetime.fromisoformat(stamp)<datetime.fromisoformat(previous['added_at']):history[alias]=entry
    target.write_text(json.dumps(dict(schema_version=1,candidates=history),separators=(',',':'))+'\n',encoding='utf-8')
    print(f'Publication evidence: {len(history)} candidates')

if __name__=='__main__':build()
