"""Relative mission cost comparisons; never a flightworthiness certification.

Compare only the same destination within two Julian launch years. All four
costs must be no worse (within numerical tolerances), and one materially lower.
"""
from datetime import datetime, timezone
import math

PLANET_IDS = {'Mercury':'199','Venus':'299','Earth':'399','Mars':'499',
              'Jupiter':'599','Saturn':'699','Uranus':'799','Neptune':'899',
              'Pluto':'999','Ceres':'20000001','Eris':'20136199','Sedna':'20090377'}
METRICS = ('launch_c3_km2_s2','duration_years','arrival_vinf_kms','total_dsm_kms')
TOLERANCES = (.05,.002,.005,.001)
LAUNCH_WINDOW_DAYS = 2*365.25


def _epoch(q):
    dates=q.get('dates_jd_tdb')
    if isinstance(dates,list) and dates:
        return float(dates[0])
    value=q.get('launch_date')
    if not value:return None
    try:return datetime.fromisoformat(value.removesuffix(' TDB').rstrip('Z')).replace(tzinfo=timezone.utc).timestamp()/86400+2440587.5
    except (ValueError,TypeError):return None


def _target(q, fallback):
    bodies=q.get('body_ids') or q.get('bodies')
    name=str(bodies[-1]) if bodies else str(fallback or '')
    return PLANET_IDS.get(name,name)


def _comparison(q, target=None):
    try:
        metrics=q.get('metrics',q)
        vals=list(float(metrics[k]) for k in METRICS)
        dates=q.get('dates_jd_tdb')
        if isinstance(dates,list) and len(dates)>1:vals[1]=(float(dates[-1])-float(dates[0]))/365.25
        vals=tuple(vals)
        if not all(math.isfinite(v) and v>=0 for v in vals):return None
        start=_epoch(q)
        if start is None or not math.isfinite(start):return None
        if q.get('classification')=='red' or q.get('periapsis_violation') is True:return None
        margin=q.get('min_turn_margin_deg')
        if margin is not None and (not math.isfinite(float(margin)) or (margin<-1e-8 and not q.get('powered_geometry_valid'))):return None
        if isinstance(q.get('flybys'),list):
            residuals=[float(f.get('speed_mismatch_mps',0)) for f in q['flybys'] if f.get('passes_powered_geometry') is not True]
            if not all(math.isfinite(v) and v>=0 for v in residuals):return None
            mismatch=max(residuals,default=0)
        else:
            mismatch=q.get('max_unresolved_vinf_mismatch_mps')
            if mismatch is None:
                if q.get('maneuver_budget_complete') or q.get('powered_geometry_valid'):mismatch=0
                else:mismatch=q.get('max_vinf_mismatch_mps',0)
            mismatch=float(mismatch or 0)
        if not math.isfinite(mismatch) or mismatch<0 or mismatch>100:return None
        return {'id':q.get('id'),'target':_target(q,target),'epoch':start,'values':vals}
    except (ValueError,TypeError,KeyError):return None


def assess_candidates(rows, alternatives=(), target=None):
    """Return ratings for displayed rows; records themselves remain untouched."""
    peers={}
    for q in [*alternatives,*rows]:
        p=_comparison(q,target)
        if p and p['id']:peers[p['id']]=p
    groups={}
    for p in peers.values():groups.setdefault(p['target'],[]).append(p)
    ratings={}
    for q in rows:
        p=_comparison(q,target)
        base=dict(comparison_window_years=2,comparison_only=True)
        if not p or not p['target']:
            ratings[q.get('id')]=dict(base,tier=0,label='Not compared',dominator_count=0,compared_count=0)
            continue
        comparable=[v for v in groups.get(p['target'],[]) if v['id']!=p['id'] and abs(v['epoch']-p['epoch'])<=LAUNCH_WINDOW_DAYS]
        better=[v for v in comparable if all(a<=b+t for a,b,t in zip(v['values'],p['values'],TOLERANCES))
                and any(a<b-t for a,b,t in zip(v['values'],p['values'],TOLERANCES))]
        better.sort(key=lambda v:(sum(a/max(b,t) for a,b,t in zip(v['values'],p['values'],TOLERANCES)),v['id']))
        ratings[q.get('id')]=dict(base,tier=1 if better else 2,
            label='Better alternatives' if better else ('Efficient tradeoff' if comparable else 'Only comparable option'),
            dominator_count=len(better),compared_count=len(comparable),
            better_candidate_id=better[0]['id'] if better else None,
            costs=dict(zip(METRICS,p['values'])))
    return ratings
