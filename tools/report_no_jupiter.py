"""Audit, plot and export the local no-Jupiter launch-window survey.

python tools/report_no_jupiter.py --input releases/testing/no_jupiter_2030s
The selected JSON files import exact candidates; .options.json also imports settings.
"""
from pathlib import Path
import argparse,csv,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
import numpy as np
from dynamics import Model,kepler
from ephemeris import AU,DAY,atomic_json,Ephemerides,jd
from mission_search import routes_for
from community import record_variables
from search_options import export_options
from study_resonant_transfers import physical_record,audit_coasts
ROOT=Path(__file__).resolve().parents[1]


def figures(selected,all_rows,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors={'Earth':'#2585c6','Venus':'#bf790c','Saturn':'#a2722b','Neptune':'#3f51d5'}
    for q in selected:
        fig,axes=plt.subplots(1,3,figsize=(16,5))
        for i,s in enumerate(q['segments']):
            dates=np.linspace(s['start_jd'],s['end_jd'],900)
            rr=np.array([kepler(np.array(s['r']),np.array(s['v']),(t-s['start_jd'])*DAY)[0]/AU for t in dates])
            label=f"{q['bodies'][i]} → {q['bodies'][i+1]}"
            for ax in axes[:2]:ax.plot(rr[:,0],rr[:,1],lw=1.1,label=label)
            axes[2].plot((dates-q['dates_jd_tdb'][0])/365.25,np.linalg.norm(rr,axis=1),lw=1.2)
        for e in q['events']:
            pos=np.array(e['planet_state_km_kms'][:3])/AU
            for ax in axes[:2]:
                ax.scatter(*pos[:2],s=22,color=colors[e['body']],zorder=5)
            axes[2].scatter((e['julian_date_tdb']-q['dates_jd_tdb'][0])/365.25,np.linalg.norm(pos),color=colors[e['body']],s=22,zorder=5)
            axes[2].annotate(e['body'],((e['julian_date_tdb']-q['dates_jd_tdb'][0])/365.25,np.linalg.norm(pos)),xytext=(3,5),textcoords='offset points',fontsize=7)
        for ax in axes[:2]:
            ax.scatter(0,0,c='gold',edgecolors='orange',s=35,zorder=6);ax.set_aspect('equal',adjustable='box');ax.set(xlabel='Ecliptic x (AU)',ylabel='Ecliptic y (AU)')
        axes[0].set_title('Heliocentric path (XY projection)');axes[0].legend(fontsize=7)
        axes[1].set(xlim=(-2.2,2.2),ylim=(-2.2,2.2),title='Inner-planet assists')
        axes[2].set(xlabel='Years after launch',ylabel='Distance from Sun (AU)',title='Flight timeline')
        for ax in axes:ax.grid(alpha=.2)
        fig.suptitle(f"{q['sequence']} · launch {q['launch_date'][:10]} · C3 {q['launch_c3_km2_s2']:.2f} km²/s² · {q['duration_years']:.2f} years\n0 modeled DSM · arrival V∞ {q['arrival_vinf_kms']:.2f} km/s · {q['id']}",fontsize=12)
        fig.tight_layout();fig.savefig(out/(q['id']+'.png'),dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for ax,target in zip(axes,['Saturn','Neptune']):
        rows=[q for q in all_rows if q['bodies'][-1]==target]
        if rows:
            sc=ax.scatter([q['duration_years'] for q in rows],[q['launch_c3_km2_s2'] for q in rows],c=[int(q['launch_date'][:4]) for q in rows],cmap='viridis',vmin=2030,vmax=2039,s=30,alpha=.65)
            fig.colorbar(sc,ax=ax,label='Launch year',ticks=[2030,2033,2036,2039])
        ax.set(title=target+' — no Jupiter',xlabel='Total flight time (years)',ylabel='Launch C3 (km²/s²)');ax.grid(alpha=.25)
    fig.suptitle('Passing Lambert / unpowered patched-conic candidates · no modeled DSMs')
    fig.tight_layout();fig.savefig(out/'comparison.png',dpi=180);plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);a=p.parse_args()
    reports=[json.loads(f.read_text(encoding='utf-8')) for f in sorted(a.input.glob('*_c3_*.json'))]
    rows=[q for r in reports for q in r['candidates']]
    if not rows:raise ValueError('No passing candidates to report')
    out=a.input/'review';out.mkdir(exist_ok=True)
    # Show minimum energy in each sampled launch year, plus fastest and lowest-Vinf alternatives.
    selected={}
    for target in ['Saturn','Neptune']:
        target_rows=[q for q in rows if q['bodies'][-1]==target]
        for year in range(2030,2040):
            group=[q for q in target_rows if q['launch_date'].startswith(str(year))]
            if group:
                q=min(group,key=lambda q:(q['launch_c3_km2_s2']//.01,q['duration_years']));selected[q['id']]=q
        if target_rows:
            for metric in ['duration_years','arrival_vinf_kms']:
                q=min(target_rows,key=lambda q:q[metric]);selected[q['id']]=q
    ep=Ephemerides(ROOT/'cache',['Earth','Venus','Saturn','Neptune'],jd('2029-01-01'),jd('2075-01-01'),1.)
    audited=[]
    for ident,original in selected.items():
        cfg=original['study_config'];model=Model(routes_for(cfg)[0],cfg,ep)
        record=physical_record(original,cfg);x,bb=record_variables(record,model);q=model.evaluate(x,bb)
        if not model.accepted(q) or 'Jupiter' in q['bodies']:raise ValueError('Candidate failed repeat evaluation: '+ident)
        audit=audit_coasts(q)
        if not audit['passed']:raise ValueError(f'Independent DOP853 audit failed: {ident} {audit}')
        q.update(id=ident,coast_audit=audit,status='passes_configured_patched_conic_screen')
        atomic_json(out/(ident+'.full.json'),q);atomic_json(out/(ident+'.json'),physical_record(q,cfg))
        document=export_options(cfg)['document'];document['trajectory']=physical_record(q,cfg)
        atomic_json(out/(ident+'.options.json'),document);audited.append(q)
        print(ident,q['sequence'],q['launch_date'][:10],round(q['launch_c3_km2_s2'],4),round(q['duration_years'],3),'DOP853 endpoint km',round(audit['maximum_dop853_endpoint_error_km'],5),flush=True)
    keys=['id','sequence','launch_date','arrival_date','duration_years','launch_c3_km2_s2','total_dsm_kms','arrival_vinf_kms','max_vinf_mismatch_mps','min_turn_margin_deg']
    for name,data in [('all_candidates.csv',rows),('selected_candidates.csv',audited)]:
        with (out/name).open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(data)
    with (out/'flyby_dates.tsv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f,delimiter='\t');w.writerow(['candidate','body','date_tdb','jd_tdb','inferred_altitude_km','vinf_mismatch_mps'])
        for q in audited:
            for fly in q['flybys']:w.writerow([q['id'],fly['body'],fly['date'],fly['julian_date_tdb'],fly['conservative_equal_speed_altitude_km'],fly['speed_mismatch_mps']])
    figures(audited,rows,out)
    summary=dict(completed_launch_c3_jobs=len(reports),launch_dates=len({r['date'] for r in reports}),c3_grid=sorted({r['c3_requested'] for r in reports}),passing_candidates=len(rows),by_target={t:sum(q['bodies'][-1]==t for q in rows) for t in ['Saturn','Neptune']},audited_candidates=len(audited),maximum_dop853_endpoint_error_km=max(q['coast_audit']['maximum_dop853_endpoint_error_km'] for q in audited),minimum_launch_c3=min(q['launch_c3_km2_s2'] for q in rows))
    atomic_json(out/'summary.json',summary)
    lines=['# No-Jupiter low-C3 launch-window survey','',f"{len(reports)} launch/C3 jobs across {summary['launch_dates']} launch dates. C3 grid: {summary['c3_grid']} km²/s². Passing candidates: {summary['by_target']}.",'','All shown candidates have zero modeled DSM/powered-flyby delta-v. Excess-speed matching and minimum turn radii are checked at every assist (Earth 200 km, Venus 300 km, Saturn 10,000 km). Saturn flight time is limited to 20 years, Neptune to 30 years, and arrival V-infinity to 12 km/s. Arrival capture and launch injection burns are excluded.','',f"The {len(audited)} selected candidates were recomputed and independently propagated with DOP853; maximum solar-coast endpoint error {summary['maximum_dop853_endpoint_error_km']:.6f} km.",'','These are Sun-only Lambert arcs joined at planet centers with asymptotic patched-conic flyby screens. Flyby altitudes are inferred from turns, not integrated finite-radius closest approaches. This is not n-body or a collision audit of resolved planet encounters. Zero DSM does not include finite-SOI targeting/TCMs. No Jupiter encounter is used; Jupiter perturbations are also absent.','', 'The launch-date/C3 grid and finite branch/duration search are not exhaustive; absence of a candidate is not proof of impossibility. Sorting ties by sampled energy does not establish a continuous optimum.','','## Selected candidates','','| ID | Target | Sequence | Launch (TDB) | Arrival (TDB) | Years | C3 km²/s² | Arrival V∞ km/s |','|---|---|---|---|---|---:|---:|---:|']
    for q in sorted(audited,key=lambda q:(q['bodies'][-1],q['launch_date'])):
        lines.append(f"| [{q['id']}]({q['id']}.png) | {q['bodies'][-1]} | {q['sequence']} | {q['launch_date'][:10]} | {q['arrival_date'][:10]} | {q['duration_years']:.3f} | {q['launch_c3_km2_s2']:.3f} | {q['arrival_vinf_kms']:.3f} |")
    lines+=['','## Files and rerun','','- `comparison.png`: C3 versus flight time, colored by launch year.','- `<id>.png`: full path, inner-assist zoom, and heliocentric distance timeline.','- `<id>.json`: exact portable candidate for RoLaMGAS import.','- `<id>.options.json`: settings plus exact candidate.','- `<id>.full.json`: solver states and independent coast audit.','- `all_candidates.csv`, `selected_candidates.csv`, `flyby_dates.tsv`.','','From the repository root, using its scientific Python environment:','','```powershell','python tools/search_no_jupiter.py --monthly --workers 4 --output releases/testing/no_jupiter_2030s','python tools/report_no_jupiter.py --input releases/testing/no_jupiter_2030s','```','','Searches run on the local CPU using the existing daily JPL cache. Completed date/C3 jobs are checkpointed and skipped on rerun. Changing algorithm or constraints requires a fresh output directory.']
    (out/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
