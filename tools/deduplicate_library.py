"""Compact bundled public archives by encounter calendar day, with private backups.

Never writes to the remote API or database. Run after a private remote D1 export
and apply community_backend/migrations/0001_same_day_encounters.sql separately.
The SQL migration computes exactly the same key and representative ranking.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from community import unique_encounters


def compact(catalog_path, report_path, csv_path, backup_dir):
    catalog_path,report_path,csv_path,backup_dir=map(Path,(catalog_path,report_path,csv_path,backup_dir))
    backup_dir.mkdir(parents=True,exist_ok=False)
    for source in (catalog_path,report_path,csv_path):
        if source.exists():shutil.copy2(source,backup_dir/source.name)
    doc=json.loads(catalog_path.read_text(encoding='utf-8'))
    records=doc['candidates'];winners,aliases=unique_encounters(records)
    winners.sort(key=lambda r:(r['body_ids'][-1],r['solved_at'],r['id']))
    kept={r['id'] for r in winners}
    previous=doc.get('duplicate_aliases',{})
    doc['duplicate_aliases']={old:aliases.get(new,new) for old,new in {**previous,**aliases}.items()}
    doc['candidates']=winners
    doc['description']='Historical passing searches, deduplicated by ordered bodies and TDB encounter calendar days. Original search limits and solver versions differ; submitted classifications must be revalidated before reuse.'
    doc['deduplication']='ordered_body_ids_and_tdb_calendar_days'
    doc['deduplication_selection']='pass before yellow, then C3/100 + cruise delta-v (km/s) + arrival Vinf/20 + flight-years/100; ID breaks exact ties'
    catalog_path.write_text(json.dumps(doc,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    report=json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {}
    report.update(published_candidates=len(winners),purged_same_day_duplicates=len(aliases),deduplication=doc['deduplication'],by_target=dict(Counter(r['body_ids'][-1] for r in winners)),archive_bytes=catalog_path.stat().st_size)
    report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if csv_path.exists():
        with csv_path.open(newline='',encoding='utf-8') as f:
            reader=csv.DictReader(f);fields=reader.fieldnames;rows=[r for r in reader if r['id'] in kept]
        with csv_path.open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    summary=dict(before=len(records),after=len(winners),purged=len(aliases),aliases_preserved=len(doc['duplicate_aliases']),by_target=report['by_target'])
    (backup_dir/'deduplication_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',required=True);parser.add_argument('--report',required=True);parser.add_argument('--csv',required=True);parser.add_argument('--backup-dir',required=True)
    a=parser.parse_args();print(json.dumps(compact(a.catalog,a.report,a.csv,a.backup_dir),indent=2))
