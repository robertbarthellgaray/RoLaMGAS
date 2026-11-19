"""Bundle validated Earth-only Uranus starters and draw their tradeoffs.

Run explore_double_earth_uranus.py and finalize_double_earth_uranus.py first.
No uploads, hidden burns, atmospheric passes or Jupiter assists.
"""
from pathlib import Path
import sys,json,math
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bootstrap
import numpy as np
from ephemeris import atomic_json,AU,DAY,MU_SUN
from dynamics import kepler

def main():
    rows=[]
    for folder in ['double_earth_uranus','planar_earth_uranus_grid','time_priority_earth_uranus']:
        path=ROOT/'studies'/folder/'validated.json'
        if path.is_file():rows+=json.loads(path.read_text())['candidates']
    unique={}
    for row in sorted(rows,key=lambda r:r['candidate']['total_dsm_kms']):
        c=row['candidate'];key=(tuple(int(t+.5) for t in c['dates_jd_tdb']),round(c['launch_c3_km2_s2']))
        unique.setdefault(key,row)
    rows=list(unique.values());events={}
    for row in rows:
        for e in row['physical_initialization']['events']:events[(e['body'],e['julian_date_tdb'])]=e
    seed=dict(schema_version=1,sequence='EdvEdvEU',description='Solver-built Earth-only Uranus routes, two DSMs at osculating solar aphelia; no Venus or Jupiter.',
              initialization_c3_grid_km2_s2=list(range(25,91,5)),minimum_earth_altitude_km=200.,
              method='Sun-only Kepler coasts, Lambert transfers, unpowered Earth turns; every stored chain rechecked in the desktop Model.',
              candidates=[r['record'] for r in rows],reference_events=list(events.values()))
    atomic_json(ROOT/'departure_seeds/double_earth_uranus.json',seed)
    out=ROOT/'studies/planar_earth_uranus_grid';fast=min(rows,key=lambda r:r['candidate']['duration_years']);efficient=min((r for r in rows if r['candidate']['duration_years']<23),key=lambda r:r['candidate']['total_dsm_kms'])
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.style.use('dark_background');fig,axes=plt.subplots(1,2,figsize=(14,6),facecolor='#09131f')
    for ax,row in zip(axes,[fast,efficient]):
        q=row['physical_initialization'];c=row['candidate']
        for i,s in enumerate(q['segments']):
            t=np.linspace(0,(s['end_jd']-s['start_jd'])*DAY,350);points=np.array([kepler(np.array(s['r']),np.array(s['v']),dt)[0]/AU for dt in t]);ax.plot(points[:,0],points[:,1],color=['#79d8f1','#ffd08a','#a5a0e2','#8ae3bd','#ff9f9a'][i],lw=1.8)
            if i in [1,3]:ax.scatter(*points[0,:2],marker='^',s=55,c='#fff1b8',zorder=4)
        for e in q['events']:
            p=np.array(e['planet_state_km_kms'][:3])/AU;ax.scatter(*p[:2],s=30,c='#ccf4ed');ax.annotate(e['body']+' '+e['date'][:10],p[:2],xytext=(5,6),textcoords='offset points',fontsize=8)
        ax.scatter(0,0,c='#ffce72',s=40);ax.set_aspect('equal',adjustable='datalim');ax.grid(alpha=.12);ax.set_xlabel('Ecliptic X (AU)');ax.set_ylabel('Ecliptic Y (AU)')
        ax.set_title(f"C3 {c['launch_c3_km2_s2']:.0f} · {c['duration_years']:.2f} years\nTwo DSMs: {1000*c['total_dsm_kms']:.0f} m/s total · {c['arrival_vinf_kms']:.2f} km/s arrival V∞",fontsize=12)
    fig.suptitle('Uranus without Jupiter or Venus: EdvEdvEU',fontsize=17);fig.text(.5,.025,'Triangles = aphelion DSMs. Sun-only Lambert/Kepler arcs and instantaneous unpowered Earth turns; finite-radius export remains to be validated.',ha='center',fontsize=8);fig.tight_layout(rect=(0,.05,1,.94));fig.savefig(out/'earth_only_uranus.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,6),facecolor='#09131f')
    for row in rows:
        c=row['candidate'];ax.scatter(c['duration_years'],c['launch_c3_km2_s2'],s=40+100*c['total_dsm_kms'],c=[c['total_dsm_kms']*1000],vmin=300,vmax=800,cmap='viridis')
        ax.annotate(f"{c['total_dsm_kms']*1000:.0f} m/s",(c['duration_years'],c['launch_c3_km2_s2']),xytext=(4,5),textcoords='offset points',fontsize=8)
    ax.set(xlabel='Flight time (Julian years)',ylabel='Launch C3 (km²/s²)',title='Earth-only Uranus candidates · labels show total DSM');ax.grid(alpha=.15);fig.tight_layout();fig.savefig(out/'c3_time_dsm.png',dpi=170);plt.close(fig)
    lines=['# Planar Earth-return routes to Uranus','','Local study, 2026-11-19. Departure guesses span C3 25–90 in increments of 5; all are initially prograde and close to Earth’s orbital plane. A finite sweep is not proof that other energies or dates are infeasible.','',
           'Sequence: **EdvEdvEU**. Both DSMs start at an osculating solar aphelion. Both Earth assists use a minimum altitude of 200 km. These routes do not visit Venus or Jupiter. C3 is launch excess speed squared, not a burn magnitude.','',
           '| Candidate | Launch (TDB) | Arrival (TDB) | C3 | Years | DSM total (m/s) | Arrival V∞ (km/s) | Largest speed gap (m/s) |',
           '|---|---|---|---:|---:|---:|---:|---:|']
    for row in sorted(rows,key=lambda r:r['candidate']['duration_years']):
        c=row['candidate'];lines.append(f"| {c['id']} | {c['launch_date'][:10]} | {c['arrival_date'][:10]} | {c['launch_c3_km2_s2']:.0f} | {c['duration_years']:.3f} | {1000*c['total_dsm_kms']:.2f} | {c['arrival_vinf_kms']:.3f} | {c['max_vinf_mismatch_mps']:.6g} |")
    lines+=['','Each `*_handoff.json` imports search settings and the exact saved candidate. The desktop Model re-evaluated every stored chain, recovered its physical DSM controls, and verified the import round trip. Flyby speed gaps are reported separately, not silently called zero.',
            '', '**Validation scope:** Kepler/Lambert heliocentric arcs and instantaneous, unpowered patched-conic turns. No n-body propagation, finite-SOI matching, atmosphere, radiation, launch vehicle performance, or Uranus capture is included. Extra finite-patch burns must be assessed by Integrate & export before describing these as integrated trajectories.','',
            'Regenerate locally:','```powershell','python tools/explore_double_earth_uranus.py --starts 280 --energies 25 30 35 40 45 50 55 60 65 70 75 80 85 90 --output studies/planar_earth_uranus_grid','python tools/finalize_double_earth_uranus.py --hold-duration --input studies/planar_earth_uranus_grid','python tools/build_double_earth_seeds.py','```','', 'Use cached JPL Earth/Uranus vectors covering 2028–2080. Optimization and plotting run locally without AI.']
    (out/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');print('Bundled',len(rows),'validated seeds; graphs:',out,flush=True)

if __name__=='__main__':main()
