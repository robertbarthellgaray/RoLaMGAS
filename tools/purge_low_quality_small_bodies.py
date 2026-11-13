"""Audit or purge public catalog entries; private local runs are never touched.

Use --apply to update bundled/website archives, with originals in backups/.
Apply the corresponding D1 migration separately to clean the live service.
"""
import argparse,csv,json,shutil,sys
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).resolve().parent))
from trajectory_policy import public_small_body_reason
from review_early2030s import save_catalog

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');args=p.parse_args()
    backup=ROOT/'backups'/('small_body_quality_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    report=dict(policy=dict(max_flight_years_exclusive=40,high_c3_above=170,high_c3_max_flight_years_exclusive=25),catalogs=[])
    def preserve(path):
        destination=backup/path.relative_to(ROOT);destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)
    for path in (ROOT/'community_seed_catalog.json',ROOT/'docs/data/community_seed_catalog.json'):
        doc=json.loads(path.read_text(encoding='utf-8'));bad=[r for r in doc['candidates'] if public_small_body_reason(r)]
        removed={r['id'] for r in bad};kept=[r for r in doc['candidates'] if r['id'] not in removed]
        report['catalogs'].append(dict(path=str(path.relative_to(ROOT)),before=len(doc['candidates']),after=len(kept),purged=len(bad),by_target=dict(Counter(r['body_ids'][-1] for r in bad))))
        if not args.apply:continue
        preserve(path);doc['candidates']=kept;doc['small_body_max_flight_years_exclusive']=40
        doc['small_body_high_c3_policy']=dict(c3_above=170,max_flight_years_exclusive=25)
        # Leave aliases only when their destination is still present or a curated case.
        for key in ('curated_aliases','duplicate_aliases'):
            doc[key]={a:b for a,b in doc.get(key,{}).items() if a not in removed and b not in removed}
        save_catalog(path,doc)
        report_path=path.parent/'community_history_report.json';csv_path=path.parent/'community_history_index.csv'
        if report_path.is_file():
            preserve(report_path);summary=json.loads(report_path.read_text(encoding='utf-8'))
            summary.update(published_candidates=len(kept),by_target=dict(Counter(r['body_ids'][-1] for r in kept)),archive_bytes=path.stat().st_size,small_body_quality_purged=len(bad))
            report_path.write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
        if csv_path.is_file():
            preserve(csv_path)
            with csv_path.open(newline='',encoding='utf-8') as stream:reader=csv.DictReader(stream);fields=reader.fieldnames;rows=[r for r in reader if r['id'] not in removed]
            with csv_path.open('w',newline='',encoding='utf-8') as stream:writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    index_path=ROOT/'docs/data/index.json';index=json.loads(index_path.read_text(encoding='utf-8'));bad_cases=[]
    for c in index['cases']:
        target=c.get('target_id')
        if not target:
            target=next((str(k) for k,v in json.loads((ROOT/'docs/data/body_names.json').read_text(encoding='utf-8'))['bodies'].items() if v['name']==c['target']),None)
        if target and public_small_body_reason(dict(body_ids=['399',str(target)],dates_jd_tdb=[c['start'],c['end']],metrics=dict(launch_c3_km2_s2=c['c3']))):bad_cases.append(c)
    report['curated_cases_removed']=[dict(id=c['id'],title=c['title']) for c in bad_cases]
    if args.apply and bad_cases:
        preserve(index_path);ids={c['id'] for c in bad_cases};index['cases']=[c for c in index['cases'] if c['id'] not in ids]
        index_path.write_text(json.dumps(index,separators=(',',':'),ensure_ascii=False)+'\n',encoding='utf-8')
        for c in bad_cases:
            case=ROOT/'docs/data/cases'/(c['id']+'.json')
            if case.is_file():preserve(case);case.unlink()
    report['backup_dir']=str(backup) if args.apply else None
    if args.apply:
        backup.mkdir(parents=True,exist_ok=True);(backup/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        (ROOT/'docs/data/small_body_quality_report.json').write_text(json.dumps({k:v for k,v in report.items() if k!='backup_dir'},indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
