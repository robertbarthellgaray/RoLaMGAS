"""Independently check saved low-C3 Jupiter/Saturn searches; optionally add gallery cases.

Uses local JPL data and local CPU. No network or AI service is required.
"""
from pathlib import Path
import argparse,csv,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bootstrap,numpy as np
from ephemeris import Ephemerides,atomic_json,AU,DAY
from dynamics import Model,kepler
from mission_search import normalize,routes_for
from community import record_variables,public_record,unique_encounters
from study_resonant_transfers import physical_record,audit_coasts
ROOT=Path(__file__).resolve().parents[1]

def save_catalog(path,document):
    """Keep one science record per line, matching the existing archive format."""
    expanded=json.dumps(document['candidates'],indent=2,ensure_ascii=False,allow_nan=False).splitlines()
    expanded='\n'.join([expanded[0]]+['  '+line for line in expanded[1:]])
    compact='[\n'+',\n'.join('    '+json.dumps(row,separators=(',',':'),ensure_ascii=False,allow_nan=False) for row in document['candidates'])+'\n  ]'
    text=json.dumps(document,indent=2,ensure_ascii=False,allow_nan=False)
    if expanded not in text:raise ValueError('Unexpected catalog layout')
    path.write_text(text.replace(expanded,compact,1)+'\n',encoding='utf-8',newline='\n')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jupiter',type=Path,required=True);p.add_argument('--refined',type=Path,required=True)
    p.add_argument('--saturn',type=Path,required=True);p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--publish',action='store_true')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for path in (a.jupiter,a.refined,a.saturn):rows+=json.loads(path.read_text(encoding='utf-8'))
    verified=[];public=[];links=[]
    for old in rows:
        c=normalize(old['study_config']);ep=Ephemerides(a.cache,old['bodies'],old['dates_jd_tdb'][0]-1,old['dates_jd_tdb'][-1]+1,1.)
        route=routes_for(c)[0];m=Model(route,c,ep);x,bb=record_variables(physical_record(old,c),m);q=m.evaluate(x,bb)
        if not m.accepted(q):raise ValueError('Recheck failed '+old['id'])
        coast=audit_coasts(q)
        if not coast['passed']:raise ValueError(coast)
        q.update(id=old['id'],status='passes_configured_patched_conic_screen',study_config=c)
        q=json.loads(json.dumps(q,allow_nan=False))  # Portable records require native JSON scalar types.
        independent=float(np.linalg.norm(np.array(q['segments'][0]['v'])-ep.state('Earth',q['dates_jd_tdb'][0])[3:])**2)
        if abs(independent-q['launch_c3_km2_s2'])>1e-5:raise ValueError('Launch-energy discrepancy')
        folder=a.output/q['id'];folder.mkdir(exist_ok=True)
        atomic_json(folder/'full.json',q);atomic_json(folder/'audit.json',dict(independent_launch_c3=independent,coasts=coast))
        title=('Low-C3 Jupiter '+q['launch_date'][:10] if q['bodies'][-1]=='Jupiter' else 'Fast Saturn '+q['launch_date'][:10])
        note='Original solver-built trajectory, not a historical mission reconstruction. Solar two-body Lambert coasts with unpowered flyby-speed and turn screening, independently checked against numerical solar propagation. Zero designed DSM excludes launch injection, finite-radius targeting corrections and arrival capture.'
        if a.publish:
            from publish_report_recreations import prepare
            prepare(folder,q,c,a.cache,title,note)
        record=public_record(q,c,route)
        if record is None:raise ValueError('Public admission failed')
        public.append(record);verified.append(q);links.append(dict(id=q['id'],public_id=record['id'],title=title,url='https://robertbarthellgaray.github.io/RoLaMGAS/#mission='+q['id']))
        print(q['id'],q['sequence'],'verified',round(independent,4),flush=True)
    fields=['id','sequence','launch_date','arrival_date','launch_c3_km2_s2','duration_years','arrival_vinf_kms','total_dsm_kms','max_vinf_mismatch_mps']
    with (a.output/'comparison.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(verified)
    atomic_json(a.output/'public_candidates.json',public);atomic_json(a.output/'website_links.json',links)
    if a.publish:
        for path in (ROOT/'community_seed_catalog.json',ROOT/'docs/data/community_seed_catalog.json'):
            archive=json.loads(path.read_text(encoding='utf-8'));values={r['id']:r for r in archive['candidates']};values.update({r['id']:r for r in public})
            archive['candidates'],_=unique_encounters(list(values.values()))
            archive.setdefault('curated_aliases',{}).update({record['id']:q['id'] for record,q in zip(public,verified)})
            save_catalog(path,archive)
        path=ROOT/'docs/data/mission_annotations.json';annotations=json.loads(path.read_text(encoding='utf-8'))
        for row in links:
            entry=dict(label=row['title'],featured_priority=5 if row['id']=='abd068a90487' else 1,note='Original low-energy search result; independently checked solar coasts, not a flown mission.')
            for ident in (row['id'],row['public_id']):annotations['missions'][ident]=entry
        atomic_json(path,annotations)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for target in ['Jupiter','Saturn']:
        subset=[q for q in verified if q['bodies'][-1]==target]
        fig,axes=plt.subplots(1,2,figsize=(13,5))
        for q in subset:
            if target=='Jupiter' and q['id'] not in ['abd068a90487','64c95c89d0a5','fd54bf2484be']:continue
            for i,s in enumerate(q['segments']):
                r=np.array([kepler(np.array(s['r']),np.array(s['v']),t)[0]/AU for t in np.linspace(0,(s['end_jd']-s['start_jd'])*DAY,600)])
                axes[0].plot(r[:,0],r[:,1],lw=.7,label=q['id'] if i==0 else None)
        axes[0].scatter(0,0,s=30,color='gold');axes[0].set_aspect('equal',adjustable='datalim');axes[0].set(xlabel='Ecliptic x (AU)',ylabel='Ecliptic y (AU)',title=target+' coast geometry');axes[0].legend(fontsize=7)
        sc=axes[1].scatter([q['duration_years'] for q in subset],[q['launch_c3_km2_s2'] for q in subset],c=[q['arrival_vinf_kms'] for q in subset],cmap='plasma',s=55)
        if target=='Saturn':
            ref=json.loads((ROOT/'docs/data/cases/4fed974cbffb.json').read_text())
            axes[1].scatter(ref['years'],ref['c3'],marker='*',s=180,color='green',label='Saved Cassini reproduction (412 m/s DSM)');axes[1].legend(fontsize=7)
        axes[1].set(xlabel='Flight time (years)',ylabel='Launch C3 (km²/s²)',title='Color = arrival V∞; 0 designed DSM for new paths');fig.colorbar(sc,ax=axes[1],label='Arrival V∞ (km/s)')
        for ax in axes:ax.grid(alpha=.2)
        fig.tight_layout();fig.savefig(a.output/(target.lower()+'_comparison.png'),dpi=170);plt.close(fig)
    print('VERIFIED',len(verified),'candidates',flush=True)
if __name__=='__main__':main()
