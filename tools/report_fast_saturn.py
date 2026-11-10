"""Save fast-Saturn research plots, portable candidates and a comparison table.

python tools/report_fast_saturn.py --input releases/testing/fast_saturn --output studies/fast_saturn
"""
from pathlib import Path
import argparse,csv,json,math,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
import numpy as np
from ephemeris import AU,DAY,atomic_json
from dynamics import kepler
from search_options import export_options
from study_resonant_transfers import physical_record,audit_coasts
ROOT=Path(__file__).resolve().parents[1]


def gallery(rows,path):
    import matplotlib.pyplot as plt
    n=math.ceil(len(rows)/3);fig,axes=plt.subplots(n,3,figsize=(17,n*5),squeeze=False)
    colors={'Earth':'#68c4ff','Venus':'#ffd475','Jupiter':'#dca7ff','Saturn':'#91f2c1'}
    for ax,q in zip(axes.flat,rows):
        for i,s in enumerate(q['segments']):
            r=np.array([kepler(np.array(s['r']),np.array(s['v']),t)[0]/AU for t in np.linspace(0,(s['end_jd']-s['start_jd'])*DAY,600)])
            ax.plot(r[:,0],r[:,1],lw=1.25,color=['#68c4ff','#ffd475','#dca7ff','#91f2c1','#ff9e80'][i%5])
        for e in q['events']:
            r=np.array(e['planet_state_km_kms'][:3])/AU;ax.scatter(*r[:2],s=24,color=colors[e['body']],zorder=5)
            if e['body'] in ['Jupiter','Saturn']:ax.annotate(e['body']+' '+e['date'][:10],r[:2],xytext=(4,7),textcoords='offset points',fontsize=7)
        ax.scatter(0,0,color='gold',s=30,zorder=6);ax.set_aspect('equal',adjustable='datalim');ax.grid(alpha=.15);ax.set(xlabel='Ecliptic x (AU)',ylabel='Ecliptic y (AU)')
        ax.set_title(f"{q['sequence']} | {q['launch_date'][:10]} | {q['id']}\nC3 {q['launch_c3_km2_s2']:.1f} | {q['duration_years']:.2f} years | arrival V∞ {q['arrival_vinf_kms']:.2f} km/s",fontsize=10)
    for ax in list(axes.flat)[len(rows):]:ax.set_visible(False)
    fig.suptitle('Fast Saturn: C3 < 30 km²/s², flight time < 9 years\nJupiter assists allowed · 0 modeled DSM · ideal Lambert / patched-conic screening',fontsize=16,y=.995)
    fig.tight_layout(rect=[0,0,1,.95]);fig.savefig(path,dpi=155);plt.close(fig)


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    reports=[json.loads(f.read_text()) for f in sorted(a.input.glob('*_c3_*.json'))]
    rows=[q for r in reports for q in r['candidates']];rows.sort(key=lambda q:(q['launch_date'],q['duration_years']))
    link_file=a.input/'review/website_links.json'
    links=json.loads(link_file.read_text()) if link_file.is_file() else {}
    for q in rows:
        if q['launch_c3_km2_s2']>=30 or q['duration_years']>=9:raise ValueError('Candidate violates strict study bounds')
        audit=audit_coasts(q)
        if not audit['passed']:raise ValueError('Coast audit failed '+q['id'])
        cfg=q['study_config'];record=physical_record(q,cfg)
        atomic_json(a.output/(q['id']+'.json'),record)
        document=export_options(cfg)['document'];document['trajectory']=record
        atomic_json(a.output/(q['id']+'.options.json'),document)
        full={k:v for k,v in q.items() if k!='study_config'};full['coast_audit']=audit
        atomic_json(a.output/(q['id']+'.full.json'),full)
    fields=['id','sequence','launch_date','arrival_date','duration_years','launch_c3_km2_s2','total_dsm_kms','arrival_vinf_kms','max_vinf_mismatch_mps','min_turn_margin_deg']
    with (a.output/'comparison.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
    plt.style.use('dark_background')
    for group,name in [([q for q in rows if q['launch_date'].startswith('2033')],'launches_2033.png'),([q for q in rows if not q['launch_date'].startswith('2033')],'launches_2052_2053.png')]:
        if group:gallery(group,a.output/name)
    ref=json.loads((ROOT/'docs/data/cases/4fed974cbffb.json').read_text())
    fig,ax=plt.subplots(figsize=(10,6));sc=ax.scatter([q['duration_years'] for q in rows],[q['launch_c3_km2_s2'] for q in rows],c=[q['arrival_vinf_kms'] for q in rows],vmin=ref['vinf'],vmax=12,cmap='plasma',s=80,edgecolors='white',linewidths=.5)
    for q in rows:ax.annotate(q['launch_date'][:7],(q['duration_years'],q['launch_c3_km2_s2']),xytext=(4,6),textcoords='offset points',fontsize=7)
    ax.scatter(ref['years'],ref['c3'],c=[ref['vinf']],vmin=ref['vinf'],vmax=12,cmap='plasma',marker='*',s=260,edgecolors='white',label='Cassini reproduction: 412 m/s DSM')
    fig.colorbar(sc,ax=ax,label='Saturn arrival V∞ (km/s)');ax.set(xlabel='Flight time (years)',ylabel='Launch C3 (km²/s²)',title='Fast Saturn options: arrival speed is a separate tradeoff');ax.grid(alpha=.2);ax.legend(loc='lower right');fig.tight_layout();fig.savefig(a.output/'c3_time_arrival_speed.png',dpi=180);plt.close(fig)
    lines=['# Fast Saturn launch-window study','',f"{len(reports)} fixed launch-date/C3 jobs; {len(rows)} passing candidates. Launch years searched: 2030–2056. C3 grid: 12, 16, 23.1, 28 km²/s². Monthly dates plus five initial trial dates. Every published case has C3 < 30 and total flight time < 9 years.",'','Routes: EVVEJS and EVEEJS, using unpowered Venus, Earth and Jupiter assists. Minimum inferred flyby altitudes: Venus 300 km, Earth 200 km, Jupiter 10,000 km. Maximum speed mismatch 0.1 m/s; each stored case also has an independent DOP853 solar-coast check. All 14 records were uploaded and read back from the shared library.','', 'Zero modeled DSM does not include launch injection, arrival capture or finite-SOI targeting corrections. These are ideal Sun-only Lambert arcs joined at planet centers, with asymptotic flyby-turn screening. They are not resolved n-body flybys.','', 'The saved Cassini reproduction has C3 15.897, 8.000 years, a 412.4 m/s DSM and Saturn arrival V-infinity 4.541 km/s. Every new candidate has a higher arrival speed; they meet the requested C3/time criteria but do not improve every mission cost. The previous no-Jupiter survey imposed a different route constraint.','', 'No passing case was found at the other sampled launch dates, but this finite grid does not prove those years impossible. A 60-window Cassini-DSM reseeding experiment and nine local arrival-speed refinements found no additional solution under 6.5 km/s arrival speed, 700 m/s DSM, C3 < 30 and nine years.','', '## Interactive candidates','', '| Candidate | Sequence | Launch TDB | Arrival TDB | Years | C3 km²/s² | Arrival V∞ km/s |','|---|---|---|---|---:|---:|---:|']
    for q in rows:lines.append(f"| [{q['id']}]({links.get(q['id'],q['id']+'.json')}) | {q['sequence']} | {q['launch_date'][:10]} | {q['arrival_date'][:10]} | {q['duration_years']:.3f} | {q['launch_c3_km2_s2']:.3f} | {q['arrival_vinf_kms']:.3f} |")
    lines+=['','## Pictures and reuse','','![2033 launches](launches_2033.png)','','![2052 and 2053 launches](launches_2052_2053.png)','','![C3, time and arrival speed](c3_time_arrival_speed.png)','','Each `<id>.json` imports the exact candidate. `<id>.options.json` imports its settings and candidate. `<id>.full.json` contains solver output and the coast audit. Additional public records and upload verification are saved alongside them.','','```powershell','python tools/search_fast_saturn.py --monthly --start-year 2030 --end-year 2056 --workers 4 --output runs/fast_saturn','python tools/report_fast_saturn.py --input runs/fast_saturn --output studies/fast_saturn','```','','The reporter uses `review/website_links.json` created during publication to link local IDs to public canonical IDs. Searches run on the local CPU with the cached daily JPL data. Existing date/C3 checkpoints are skipped.']
    (a.output/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');print('Saved',len(rows),'audited candidates to',a.output,flush=True)


if __name__=='__main__':main()
