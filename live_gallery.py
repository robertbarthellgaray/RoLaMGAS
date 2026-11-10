"""Incremental, atomic candidate snapshots and saved scientific trajectory images."""
import bootstrap  # noqa: F401
from pathlib import Path
import time
import json
from candidate_status import red_reason
import numpy as np
from dynamics import kepler,supported_launch_energy
from ephemeris import AU,DAY,atomic_json


class RenderPreempted(Exception):
    """A newer user selection superseded optional background sampling."""


def card_data(q,ep,cancel=None):
    card = dict(q)
    paths = []
    for s in q['segments']:
        if cancel and cancel():raise RenderPreempted()
        r,v = np.array(s['r']),np.array(s['v'])
        paths.append([(kepler(r,v,float(t))[0]/AU).tolist()
                      for t in np.linspace(0,(s['end_jd']-s['start_jd'])*DAY,160)])
    dates = np.linspace(q['dates_jd_tdb'][0],q['dates_jd_tdb'][-1],250)
    orbits=[]
    for body in dict.fromkeys(q['bodies']):
        if cancel and cancel():raise RenderPreempted()
        orbits.append(dict(body=body,points=[(ep.state(body,d)[:3]/AU).tolist() for d in dates]))
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


def summary_fields(q,keys):
    fields={k:q.get(k) for k in keys}
    flybys=q.get('flybys')
    if isinstance(flybys,list):
        fields['max_unresolved_vinf_mismatch_mps']=max((f.get('speed_mismatch_mps',0.) for f in flybys if not f.get('passes_powered_geometry',False)),default=0.)
    return fields


def read_json(path,default=None):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return default


def plot_status(folder,q,config=None):
    folder=Path(folder);identifier=q['id'];manual=(folder/(identifier+'.preview_requested.json')).is_file();skip=None if manual else red_reason(q,config)
    error=read_json(folder/(identifier+'.plot_error.json'),{}).get('message')
    ready=not skip and not error and not (folder/(identifier+'.render_pending.json')).exists() and (folder/(identifier+'.png')).is_file() and (folder/(identifier+'.card.json')).is_file()
    if manual and red_reason(q,config) and not read_json(folder/(identifier+'.card.json'),{}).get('manual_preview'):ready=False
    return dict(image_ready=bool(ready),render_error=error,render_skipped=skip,manual_preview=manual,render_pending=not (skip or error or ready))


class LiveGallery:
    def __init__(self,output,ep,deferred=False,config=None):
        self.output,self.ep = Path(output),ep
        self.deferred,self.config=deferred,config or {}
        self.folder = self.output/'candidates'
        self.folder.mkdir(parents=True,exist_ok=True)

    def placeholder(self,q,force=False):
        identifier=q['id'];manual=self.folder/(identifier+'.preview_requested.json')
        reason=red_reason(q,self.config)
        if force and reason:atomic_json(manual,dict(candidate_id=identifier,requested=True))
        skip=reason if not manual.exists() else None;path=self.folder/(identifier+'.card.json')
        pending=self.folder/(identifier+'.render_pending.json')
        error=self.folder/(identifier+'.plot_error.json')
        if skip:
            atomic_json(path,dict(q,paths=[],planet_paths=[],render_pending=False,render_skipped=skip,render_error=None))
            pending.unlink(missing_ok=True)
        elif not error.exists() and (not path.exists() or not (self.folder/(identifier+'.png')).exists() or (manual.exists() and not read_json(path,{}).get('manual_preview'))):
            if not pending.exists() or not path.exists():
                atomic_json(pending,dict(candidate_id=identifier))
                atomic_json(path,dict(q,paths=[],planet_paths=[],render_pending=True,render_skipped=None,render_error=None))

    def render(self,q,cancel=None,force=False):
        identifier=q['id'];self.placeholder(q,force=force)
        manual=(self.folder/(identifier+'.preview_requested.json')).is_file()
        if red_reason(q,self.config) and not manual:return 'skipped'
        if plot_status(self.folder,q,self.config)['image_ready']:return 'ready'
        try:
            if cancel and cancel():raise RenderPreempted()
            card=card_data(q,self.ep,cancel=cancel) if cancel else card_data(q,self.ep)
            if cancel and cancel():raise RenderPreempted()
            thumbnail(card,self.folder/(identifier+'.png'))
            card.update(render_pending=False,render_skipped=None,render_error=None,manual_preview=manual,preview_warning=red_reason(q,self.config) if manual else None)
            atomic_json(self.folder/(identifier+'.card.json'),card)
            (self.folder/(identifier+'.render_pending.json')).unlink(missing_ok=True)
            return 'ready'
        except RenderPreempted:
            return 'preempted'
        except Exception as exc:
            print(f'PLOT ERROR {identifier}: {exc}',flush=True)
            atomic_json(self.folder/(identifier+'.plot_error.json'),dict(message=str(exc),candidate_id=identifier))
            atomic_json(self.folder/(identifier+'.card.json'),dict(q,paths=[],planet_paths=[],render_pending=False,render_skipped=None,render_error=str(exc)))
            (self.folder/(identifier+'.render_pending.json')).unlink(missing_ok=True)
            return 'failed'

    def update(self,summary,progress,final=False):
        ordered = sorted((q for q in summary['candidates']+summary['near_misses']
                          if supported_launch_energy(q.get('launch_c3_km2_s2'))),
                         key=lambda q:q.get('discovered_unix',0),reverse=True)
        keys = ('id','sequence','status','launch_date','arrival_date','duration_years','dates_jd_tdb','bodies',
                'launch_c3_km2_s2','arrival_vinf_kms','total_dsm_kms','max_vinf_mismatch_mps',
                'min_turn_margin_deg','screening_residual_norm','pareto_front','discovered_unix',
                'periapsis_violation','powered_geometry_valid','powered_flyby_delta_v_kms','cruise_dsm_kms',
                'max_single_dsm_kms','max_powered_flyby_kms','requested_min_c3','effective_min_c3',
                'unresolved_flyby_count','maneuver_budget_complete','budget_complete','modeled_maneuver_total_kms','turnaround_delta_v_kms',
                'total_unresolved_vinf_mismatch_mps','unresolved_speed_mismatch_total_mps','modeled_plus_unresolved_mismatch_kms')
        # Publish full scientific data for every candidate before spending time
        # drawing any picture, so a click can immediately prioritize any row.
        for q in ordered:
            atomic_json(self.folder/(q['id']+'.json'),q)
            self.placeholder(q)
        def snapshot():
            rows=[summary_fields(q,keys)|plot_status(self.folder,q,self.config) for q in ordered]
            excluded_passes=sum(not supported_launch_energy(q.get('launch_c3_km2_s2')) for q in summary['candidates'])
            atomic_json(self.output/'live.json',dict(revision=time.time(),progress=progress,candidates=rows,
                        distinct_accepted=max(0,summary['distinct_accepted']-excluded_passes),raw_accepted=summary['raw_accepted'],
                        model=summary['model'],nbody_validated=False))
        snapshot()
        if self.deferred:return
        new_images=0
        for q in ordered:
            status=plot_status(self.folder,q,self.config)
            if not status['render_pending']:continue
            if not final and new_images>=8:break
            self.render(q);new_images+=1
        snapshot()
