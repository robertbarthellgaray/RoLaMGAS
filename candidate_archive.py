"""Revalidate compatible previous solutions before starting a new local search."""
import json,time
from pathlib import Path
import numpy as np
from dynamics import Model


def compatible(source,old_route,current,route):
    # Date/DSM controls must have exactly the same meaning. Never reinterpret
    # a frozen cruise or a different Horizons identity as a fresh route.
    if source.get('append_flyby') or current.get('append_flyby'):return False
    for key in ('bodies','dsm_legs','leg_days'):
        if old_route.get(key,[] if key=='dsm_legs' else None)!=route.get(key,[] if key=='dsm_legs' else None):return False
    for key in ('launch_jd','event_windows_jd','arrival_window_jd'):
        if source.get(key)!=current.get(key):return False
    if source.get('dsm_velocity_box_kms',6.)!=current.get('dsm_velocity_box_kms',6.):return False
    old_target=source.get('target_object') or {};new_target=current.get('target_object') or {}
    return str(old_target.get('id',''))==str(new_target.get('id',''))


def collect_candidates(config,routes,ephemerides,history,exclude=None):
    """Use current ephemerides and every current constraint, never old pass flags."""
    models={r['id']:Model(r,config,ephemerides) for r in routes}
    accepted=[];seen=set();stats=dict(compatible=0,rejected=0,accepted=0)
    history=Path(history);exclude=Path(exclude).resolve() if exclude else None
    canonical=lambda b:tuple(b[:2])+(bool(b[2]) if len(b)>2 else True,)
    for folder in sorted(history.iterdir()) if history.is_dir() else []:
        if not folder.is_dir() or folder.resolve()==exclude:continue
        try:
            manifest=json.loads((folder/'run_manifest.json').read_text(encoding='utf-8'))
            results=json.loads((folder/'results.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):continue
        source=manifest.get('config',{})
        old_routes={r['id']:r for r in manifest.get('routes',[])}
        for old in results.get('candidates',[]):
            try:
                model=models.get(old['sequence']);old_route=old_routes.get(old['sequence'])
                if model is None or old_route is None or not compatible(source,old_route,config,model.route):continue
                branches=old['branches'];x=np.asarray(old['x'],dtype=float)
                if old.get('bodies')!=model.bodies or x.shape!=(model.dimension,) or not np.isfinite(x).all() or np.any((x<0)|(x>1)):continue
                if len(branches)!=model.n-1 or any(canonical(b) not in [canonical(v) for v in opts] for b,opts in zip(branches,model.route['branch_options'])):continue
                key=json.dumps([old['sequence'],branches,x.tolist()],sort_keys=True)
                if key in seen:continue
                seen.add(key);stats['compatible']+=1
                # Model.evaluate performs the first-leg C3 gate before any
                # later leg, then recomputes all burns, flybys and constraints.
                q=model.evaluate(x,branches)
                if not model.accepted(q):stats['rejected']+=1;continue
                q.update(status='passes_configured_patched_conic_screen',
                         screening_residual_norm=float(np.linalg.norm(model.residual(x,branches))),
                         discovered_unix=time.time(),
                         reused_from=dict(run=folder.name,candidate=old.get('id'),revalidated=True))
                accepted.append(q);stats['accepted']+=1
            except (ValueError,KeyError,TypeError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):
                stats['rejected']+=1
    return dict(accepted=accepted,stats=stats)
