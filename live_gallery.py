"""Incremental, atomic candidate snapshots and saved scientific trajectory images."""
import bootstrap  # noqa: F401
from pathlib import Path
import time
import numpy as np
from dynamics import kepler
from ephemeris import AU,DAY,atomic_json


def card_data(q,ep):
    card = dict(q)
    paths = []
    for s in q['segments']:
        r,v = np.array(s['r']),np.array(s['v'])
        paths.append([(kepler(r,v,float(t))[0]/AU).tolist()
                      for t in np.linspace(0,(s['end_jd']-s['start_jd'])*DAY,160)])
    dates = np.linspace(q['dates_jd_tdb'][0],q['dates_jd_tdb'][-1],250)
    orbits = [dict(body=b,points=[(ep.state(b,d)[:3]/AU).tolist() for d in dates])
              for b in dict.fromkeys(q['bodies'])]
    card.update(paths=paths,planet_paths=orbits)
    return card


def thumbnail(card,path):
    # Agg is a file renderer; no Tk window or network font/plot dependency.
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    fig = Figure(figsize=(5.4,3.4),dpi=110,facecolor='#0c1728')
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111,facecolor='#0c1728')
    for orbit in card['planet_paths']:
        p = np.asarray(orbit['points'])
        ax.plot(p[:,0],p[:,1],color='#334860',lw=.6,alpha=.65)
    colors = ('#66d4ff','#7ee2b8','#ffcf7b','#d7a2ff','#fda2ba')
    points = []
    for i,curve in enumerate(card['paths']):
        p = np.asarray(curve)
        points.append(p)
        ax.plot(p[:,0],p[:,1],color=colors[i%len(colors)],lw=1.25)
    ax.scatter([0],[0],color='#ffdc83',s=20,zorder=5)
    for event in card['events']:
        p = np.asarray(event['planet_state_km_kms'][:3])/AU
        ax.scatter([p[0]],[p[1]],color='#dfeeff',s=8,zorder=6)
    p = np.vstack(points+[[[0.,0.,0.]]])
    ax.set_xlim(p[:,0].min()-.12*max(np.ptp(p[:,0]),1),p[:,0].max()+.12*max(np.ptp(p[:,0]),1))
    ax.set_ylim(p[:,1].min()-.12*max(np.ptp(p[:,1]),1),p[:,1].max()+.12*max(np.ptp(p[:,1]),1))
    ax.set_aspect('equal',adjustable='datalim')
    ax.tick_params(colors='#91a8c2',labelsize=7)
    ax.set_xlabel('Ecliptic X · AU',color='#91a8c2',fontsize=8)
    ax.set_ylabel('Y · AU',color='#91a8c2',fontsize=8)
    for spine in ax.spines.values():
        spine.set_color('#263c55')
    ax.set_title(card['sequence'],loc='left',color='#e5efff',fontsize=11,pad=8)
    fig.tight_layout(pad=1.3)
    temporary = path.with_suffix('.tmp')
    fig.savefig(temporary,format='png',facecolor=fig.get_facecolor())
    temporary.replace(path)


class LiveGallery:
    def __init__(self,output,ep):
        self.output,self.ep = Path(output),ep
        self.folder = self.output/'candidates'
        self.folder.mkdir(parents=True,exist_ok=True)

    def update(self,summary,progress,final=False):
        rows = []
        new_images = 0
        ordered = sorted(summary['candidates']+summary['near_misses'],key=lambda q:q.get('discovered_unix',0),reverse=True)
        keys = ('id','sequence','status','launch_date','arrival_date','duration_years',
                'launch_c3_km2_s2','arrival_vinf_kms','total_dsm_kms','max_vinf_mismatch_mps',
                'min_turn_margin_deg','screening_residual_norm','pareto_front','discovered_unix',
                'periapsis_violation','powered_geometry_valid','powered_flyby_delta_v_kms','cruise_dsm_kms',
                'max_single_dsm_kms','max_powered_flyby_kms')
        if final:
            # Publish every retained candidate before potentially lengthy image
            # rendering, so archive recovery does not hide the expanded list.
            initial=[{k:q.get(k) for k in keys}|dict(image_ready=(self.folder/(q['id']+'.png')).is_file(),render_error=None) for q in ordered]
            atomic_json(self.output/'live.json',dict(revision=time.time(),progress=progress,candidates=initial,
                        distinct_accepted=summary['distinct_accepted'],raw_accepted=summary['raw_accepted'],
                        model=summary['model'],nbody_validated=False))
        for q in ordered:
            identifier = q['id']
            card_path = self.folder/(identifier+'.card.json')
            image_path = self.folder/(identifier+'.png')
            error_path = self.folder/(identifier+'.plot_error.json')
            atomic_json(self.folder/(identifier+'.json'),q)
            if not image_path.exists() and not error_path.exists() and (final or new_images < 8):
                try:
                    card = card_data(q,self.ep)
                    atomic_json(card_path,card)
                    thumbnail(card,image_path)
                except Exception as exc:
                    print(f'PLOT ERROR {identifier}: {exc}',flush=True)
                    atomic_json(error_path,dict(message=str(exc),candidate_id=identifier))
                    atomic_json(card_path,dict(q,paths=[],planet_paths=[],render_error=str(exc)))
                new_images += 1
            import json
            error=json.loads(error_path.read_text()).get('message') if error_path.exists() else None
            rows.append({k:q.get(k) for k in keys}|dict(image_ready=image_path.exists(),render_error=error))
        atomic_json(self.output/'live.json',dict(revision=time.time(),progress=progress,candidates=rows,
                    distinct_accepted=summary['distinct_accepted'],raw_accepted=summary['raw_accepted'],
                    model=summary['model'],nbody_validated=False))
