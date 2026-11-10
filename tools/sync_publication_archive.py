"""Refresh public candidate science and retained publication dates for offline browsing."""
from pathlib import Path
import sys,json,urllib.parse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from community import exchange,unique_encounters
from ephemeris import atomic_json
ROOT=Path(__file__).resolve().parents[1]

def main():
    records=[];cursor=None;cursors=set()
    while True:
        params=dict(target='all',limit=100,since='1970-01-01T00:00:00.000Z',publication_dates=1)
        if cursor:params['cursor']=cursor
        page=exchange('https://rolamgas-community.corigarayv.workers.dev/v1/candidates?'+urllib.parse.urlencode(params))
        records.extend(page['candidates']);cursor=page['next_cursor']
        if not cursor:break
        if cursor in cursors:raise ValueError('Repeated page cursor')
        cursors.add(cursor)
    for file in (ROOT/'community_seed_catalog.json',ROOT/'docs/data/community_seed_catalog.json'):
        archive=json.loads(file.read_text())
        by_id={r['id']:r for r in archive['candidates']};by_id.update({r['id']:r for r in records})
        winners,aliases=unique_encounters(list(by_id.values()));archive['candidates']=winners
        archive.setdefault('duplicate_aliases',{}).update(aliases)
        archive['received_through']=max(r['received_at'] for r in records)
        # Keep one candidate per line, as in the existing public archive.
        header={k:v for k,v in archive.items() if k!='candidates'}
        text=json.dumps(header,ensure_ascii=False,indent=2)[:-2]+',\n  "candidates": [\n'
        text+=',\n'.join('    '+json.dumps(r,ensure_ascii=False,separators=(',',':')) for r in archive['candidates'])
        file.write_text(text+'\n  ]\n}\n',encoding='utf-8')
    print(f'Refreshed {len(records)} published candidates with receipt metadata')

if __name__=='__main__':main()
