"""Audit, create gallery cases and desktop packages for study reconstructions.
Does not upload binaries. Run recreation searches first, then this publisher.
"""
from pathlib import Path
import json,sys,hashlib,shutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
import numpy as np
from ephemeris import Ephemerides,atomic_json,BODIES
from mission_search import normalize,routes_for
from live_gallery import card_data,thumbnail
from trajectory_transfer import materialize
from study_resonant_transfers import physical_record,audit_coasts
from catalog_validation import audit_candidate
from search_options import export_options
from add_verified_seed_cases import add
from recreate_mission_studies import study_config
ROOT=Path(__file__).resolve().parents[1]

def prepare(folder,q,c,cache,title,note):
    q=dict(q);q.pop('study_config',None)
    q.setdefault('id',hashlib.sha256(json.dumps([q['sequence'],q['dates_jd_tdb'],q['branches'],q['x']]).encode()).hexdigest()[:12])
    q['status']='passes_configured_patched_conic_screen'
    audit=audit_candidate(q,c,BODIES);coasts=audit_coasts(q)
    if not audit['passed'] or not coasts['passed']:raise ValueError([audit,coasts])
    ep=Ephemerides(cache,q['bodies'],q['dates_jd_tdb'][0]-1,q['dates_jd_tdb'][-1]+1,1.)
    # The same materializer used by GUI /api/trajectory/import: no optimizer.
    record=physical_record(q,c);verified=materialize(record,c,routes_for(c)[0],ep)
    if verified['status']!=q['status']:raise ValueError('Desktop import did not pass its original limits')
    candidate_dir=folder/'candidates';candidate_dir.mkdir(parents=True,exist_ok=True)
    card=card_data(q,ep);atomic_json(candidate_dir/(q['id']+'.json'),q);atomic_json(candidate_dir/(q['id']+'.card.json'),card)
    thumbnail(card,folder/'trajectory.png')
    atomic_json(folder/'results.json',dict(candidates=[q]))
    public_config=dict(c,cache='cache');atomic_json(folder/'run_manifest.json',dict(config=public_config))
    document=export_options(c)['document'];document['trajectory']=record
    document['display_name']=title;document['source_candidate_id']=q['id'];atomic_json(folder/'selected-trajectory.json',document)
    atomic_json(folder/'validation.json',dict(vector_audit=audit,independent_coasts=coasts,desktop_import=verified['import_verification']))
    add(folder,cache,ROOT/'docs',title=title,note=note)
    return q,c

def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',type=Path,required=True);a=p.parse_args()
    records=[];links=[]
    old=ROOT/'releases/testing/trident_reconstruction/post_fit_True_0.json';q=json.loads(old.read_text());c=q['study_config']
    folder=ROOT/'studies/trident_reconstruction';folder.mkdir(parents=True,exist_ok=True)
    note='Modified Trident date-match, not the proposed ballistic mission: every supplied encounter day matches, but three DSMs and powered Venus/Earth/Jupiter flybys are added. The final body is Neptune, not a resolved Triton flyby. Saved trajectories use ideal planet-center Lambert joins; finite-radius flyby export remains a separate desktop step. Cruise budget excludes launch injection and capture.'
    q,c=prepare(folder,q,c,a.cache,'Trident date-match — added maneuvers',note);records.append((q,c));links.append((q,'Trident date-match — added maneuvers'))
    reports=json.loads((ROOT/'studies/mission_report_recreations/summary.json').read_text())
    for report in reports:
        if not report.get('accepted'):continue
        slug=report['name'].split(' — ')[0].replace('/','-').replace(' ','_');folder=ROOT/'studies/mission_report_recreations'/slug
        q=json.loads((folder/'candidate.json').read_text());c=json.loads((folder/'run_manifest.json').read_text())['config']
        c['cache']=str(a.cache)
        note='Proposed-study schedule recreation, not an official mission ephemeris. '+report['reference'].get('note','')+' Solar-only Lambert/Kepler cruise; full powered-periapsis vector burns are charged where needed. Launch injection, resolved moon flybys, and capture are excluded.'
        q,c=prepare(folder,q,c,a.cache,report['name'],note);records.append((q,c));links.append((q,report['name']))
    from community import public_record
    from import_passing_history import canonical_records
    raw=[public_record(q,c,routes_for(c)[0]) for q,c in records]
    canonical=canonical_records(raw)
    if canonical['invalid']:raise ValueError(canonical['invalid'])
    atomic_json(ROOT/'studies/mission_report_recreations/public_candidates.json',canonical['valid'])
    mapping={r['id']:q['id'] for r,(q,c) in zip(canonical['valid'],records)}
    for file in (ROOT/'community_seed_catalog.json',ROOT/'docs/data/community_seed_catalog.json'):
        archive=json.loads(file.read_text());existing={r['id']:r for r in archive['candidates']}
        existing.update({r['id']:r for r in canonical['valid']});archive['candidates']=list(existing.values())
        archive.setdefault('curated_aliases',{}).update(mapping);atomic_json(file,archive)
    path=ROOT/'docs/data/mission_annotations.json';annotations=json.loads(path.read_text())
    for (q,title),record in zip(links,canonical['valid']):
        label='CALYPSO — Uranus cruise' if title.startswith('CALYPSO') else ('T-OWS 2030 — operations-table recreation' if title.startswith('T-OWS 2030') else title)
        entry=dict(label=label,featured_priority=8 if title.startswith('Trident') else 3,note='Proposed mission concept reconstruction; see validation and study report for differences.')
        annotations['missions'][q['id']]=entry;annotations['missions'][record['id']]=entry
    atomic_json(path,annotations)
    summary=[dict(id=q['id'],title=title,c3=q['launch_c3_km2_s2'],burns_mps=1000*q['total_dsm_kms'],url='https://robertbarthellgaray.github.io/RoLaMGAS/#mission='+q['id']) for q,title in links]
    atomic_json(ROOT/'studies/mission_report_recreations/website_links.json',summary)
    # Also make all eligible schedules selectable in the desktop presets menu.
    missions=json.loads((ROOT/'departure_seeds/mission_studies.json').read_text())['missions']
    for mission in missions:
        if not mission.get('seed_eligible') or mission['name'].startswith('Trident'):continue
        settings=export_options(study_config(mission,a.cache))['document']['settings']
        name=mission['name'].split(' — ')[0].replace('/','-').replace(' ','_')
        atomic_json(ROOT/'examples'/('study_'+name+'.json'),settings)
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
