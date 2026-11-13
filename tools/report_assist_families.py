"""Audit the assist-family study and optionally share its new screened schedules.

python tools/report_assist_families.py --input runs/assist_families_20261113
Add --publish to update the public API and both bundled archives after auditing.
"""
from pathlib import Path
from collections import Counter
import argparse,csv,json,sys,urllib.request,urllib.parse
from datetime import datetime,timedelta,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).resolve().parent))
import bootstrap,numpy as np
from ephemeris import Ephemerides,atomic_json,AU,DAY
from dynamics import Model,kepler
from mission_search import routes_for
from community import record_variables,public_record,encounter_key,unique_encounters,exchange
from trajectory_prefixes import public_records
from study_resonant_transfers import physical_record,audit_coasts
from import_passing_history import canonical_records
from review_early2030s import save_catalog

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,default=ROOT/'studies/assist_families_20261113');p.add_argument('--cache',type=Path,default=ROOT/'cache');p.add_argument('--publish',action='store_true');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    existing=json.loads((ROOT/'community_seed_catalog.json').read_text())['candidates'];known={encounter_key(r) for r in existing}
    # Re-running an already published study must retain and re-audit its own
    # output, rather than emptying the report because its routes are now shared.
    previous=a.output/'public_candidates.json'
    if previous.exists():known-={encounter_key(r) for r in json.loads(previous.read_text())}
    rows=json.loads((a.input/'all_candidates.json').read_text())
    polished=a.input/'polished_candidates.json'
    if polished.exists():rows+=json.loads(polished.read_text())
    accepted=[];records=[];audits={};ignored=[]
    for old in rows:
        # A zero-DSM rewrite of an existing ballistic route adds no new option.
        if 'dv' in old['sequence'] and old['total_dsm_kms']<.001:
            ignored.append(dict(id=old['id'],reason='Numerically zero added DSM; existing ballistic architecture retained'));continue
        c=old['study_config'];route=routes_for(c)[0];ep=Ephemerides(a.cache,old['bodies'],old['dates_jd_tdb'][0]-1,old['dates_jd_tdb'][-1]+1,1.)
        model=Model(route,c,ep);x,bb=record_variables(physical_record(old,c),model);q=model.evaluate(x,bb)
        if not model.accepted(q):raise ValueError('Fresh screen failed: '+old['id'])
        audit=audit_coasts(q)
        if not audit['passed']:raise ValueError(audit)
        independent=float(np.linalg.norm(np.array(q['segments'][0]['v'])-ep.state('Earth',q['dates_jd_tdb'][0])[3:])**2)
        if abs(independent-q['launch_c3_km2_s2'])>1e-6:raise ValueError('Independent C3 mismatch')
        q['status']='passes_configured_patched_conic_screen'
        if 'discovered_unix' in old:q['discovered_unix']=old['discovered_unix']
        raw=public_record(q,c,route);canon=canonical_records([raw])
        if canon['invalid']:raise ValueError(canon['invalid'])
        record=canon['valid'][0];key=encounter_key(record)
        if key in known:ignored.append(dict(id=record['id'],reason='Same ordered encounter days already archived'));continue
        known.add(key);q.update(id=record['id'][:12],study_config=c);accepted.append(q);records.append(record);audits[record['id']]=dict(independent_launch_c3_km2_s2=independent,**audit)
    report=json.loads((a.input/'report.json').read_text());atomic_json(a.output/'search_report.json',report)
    if (a.input/'polish_report.json').exists():atomic_json(a.output/'refinement_report.json',json.loads((a.input/'polish_report.json').read_text()))
    atomic_json(a.output/'public_candidates.json',records);atomic_json(a.output/'coast_audits.json',audits)
    fields=['id','sequence','launch_date','arrival_date','launch_c3_km2_s2','duration_years','arrival_vinf_kms','total_dsm_kms','max_vinf_mismatch_mps']
    with (a.output/'comparison.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(accepted)
    links=[dict(id=r['id'],sequence=r['sequence'],url='https://robertbarthellgaray.github.io/RoLaMGAS/#mission='+r['id']) for r in records];atomic_json(a.output/'website_links.json',links)
    summary=dict(new_schedules=len(records),by_sequence=dict(Counter(r['sequence'] for r in records)),excluded=ignored,
        maximum_coast_error_km=max((v['maximum_dop853_endpoint_error_km'] for v in audits.values()),default=0.),
        maximum_flyby_speed_gap_mps=max((q['max_vinf_mismatch_mps'] for q in accepted),default=0.))
    atomic_json(a.output/'summary.json',summary)
    plot(accepted,a.output)
    if a.publish:
        combined=records[:]
        for q in accepted:combined+=public_records(q,q['study_config'],routes_for(q['study_config'])[0])[1:]
        combined,_=unique_encounters(combined);validated=canonical_records(combined)
        if validated['invalid']:raise ValueError(validated['invalid'])
        combined=validated['valid'];receipts=[]
        for i in range(0,len(combined),10):receipts.append(exchange('https://rolamgas-community.corigarayv.workers.dev/v1/candidates',dict(candidates=combined[i:i+10])))
        atomic_json(a.input/'upload_receipts.json',receipts)
        published=publication_records({r['id'] for r in records})
        for path in [ROOT/'community_seed_catalog.json',ROOT/'docs/data/community_seed_catalog.json']:
            doc=json.loads(path.read_text());values={r['id']:r for r in doc['candidates']};values.update({r['id']:published.get(r['id'],r) for r in combined});doc['candidates'],_=unique_encounters(list(values.values()));save_catalog(path,doc)
        path=ROOT/'docs/data/mission_annotations.json';doc=json.loads(path.read_text(encoding='utf-8'))
        for q,r in zip(accepted,records):
            label=q['sequence']+' · '+q['launch_date'][:10]
            if q['launch_c3_km2_s2']<20:label='Low-C3 '+label
            doc['missions'][r['id']]=dict(label=label,mission_kind='original',note='Original continuation-search result, not a mission reconstruction. Independently propagated solar coasts and asymptotic flyby screens. Cruise DSM is explicit; finite-radius targeting corrections, launch injection and capture are separate.')
        atomic_json(path,doc);summary['shared_with_planet_prefixes']=len(combined);atomic_json(a.output/'summary.json',summary)
    print(json.dumps(summary,indent=2))

def publication_records(wanted):
    """Keep actual server publication times, separately from solver timestamps."""
    since=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat(timespec='milliseconds').replace('+00:00','Z')
    found={};cursor=None
    while True:
        params=dict(target='all',limit=100,since=since)
        if cursor:params['cursor']=cursor
        request=urllib.request.Request('https://rolamgas-community.corigarayv.workers.dev/v1/candidates?'+urllib.parse.urlencode(params),headers={'User-Agent':'RoLaMGAS study publication audit'})
        with urllib.request.urlopen(request,timeout=45) as response:page=json.load(response)
        found.update({r['id']:r for r in page['candidates']});cursor=page.get('next_cursor')
        if wanted<=found.keys() or not cursor:break
    return found

def plot(rows,folder):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(10,6));palette={'EVVEJ':'#229288','EVdvEEJ':'#6b53bb','EVdvVEJS':'#d38c27','EVdvEES':'#bb4b64'}
    for sequence,color in palette.items():
        group=[q for q in rows if q['sequence']==sequence]
        if group:ax.scatter([q['duration_years'] for q in group],[q['launch_c3_km2_s2'] for q in group],color=color,label=sequence,s=48)
    ax.scatter([8],[15.896792565582022],marker='*',s=180,color='black',label='Saved Cassini recreation (1997, 8 yr)')
    ax.set(xlabel='Flight time (years)',ylabel='Launch C3 (km²/s²)',title='New Jupiter and Saturn options — local JPL continuation searches')
    ax.grid(alpha=.18);ax.legend(fontsize=8);fig.text(.5,.01,'Screened ideal patched conics; designed DSM ≤700 m/s. Capture and finite-radius patch burns excluded.',ha='center',fontsize=8);fig.tight_layout(rect=[0,.03,1,1]);fig.savefig(folder/'tradeoffs.png',dpi=150);plt.close(fig)
    examples=[]
    for sequence in palette:
        group=[q for q in rows if q['sequence']==sequence]
        if group:examples.append(min(group,key=lambda q:q['launch_c3_km2_s2']))
    fig,axes=plt.subplots(2,2,figsize=(13,11))
    for ax,q in zip(axes.flat,examples):
        for i,s in enumerate(q['segments']):
            rr=np.array([kepler(np.array(s['r']),np.array(s['v']),dt)[0]/AU for dt in np.linspace(0,(s['end_jd']-s['start_jd'])*DAY,350)])
            ax.plot(rr[:,0],rr[:,1],lw=1.2)
        for e in q['events']:
            pos=np.array(e['planet_state_km_kms'][:3])/AU;ax.scatter(*pos[:2],s=20)
            if e['body']==q['bodies'][-1]:ax.annotate(e['body']+' '+e['date'][:10],pos[:2],xytext=(4,4),textcoords='offset points',fontsize=7)
        ax.scatter(0,0,color='gold',edgecolor='orange',s=45);ax.set_aspect('equal',adjustable='datalim');ax.grid(alpha=.15)
        ax.set(xlabel='Ecliptic x (AU)',ylabel='Ecliptic y (AU)',title=f"{q['sequence']} · {q['launch_date'][:10]} · {q['id']}\nC3 {q['launch_c3_km2_s2']:.2f} · {q['duration_years']:.2f} yr · DSM {q['total_dsm_kms']*1000:.0f} m/s · arrival {q['arrival_vinf_kms']:.2f} km/s")
    for ax in list(axes.flat)[len(examples):]:ax.set_visible(False)
    fig.tight_layout();fig.savefig(folder/'examples.png',dpi=145);plt.close(fig)
if __name__=='__main__':main()
