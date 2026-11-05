"""Presentation severity shared by background plots and saved galleries.

The scalar unresolved-mismatch sum is a conservative screening quantity, not
an estimate or lower bound for a powered periapsis burn (Oberth applies).
"""
import math


def unresolved_mismatch_sum(q):
    if isinstance(q.get('flybys'),list):
        return sum(max(0.,float(f.get('speed_mismatch_mps',0.) or 0.)) for f in q['flybys'] if f.get('passes_powered_geometry') is not True)
    for name in ('total_unresolved_vinf_mismatch_mps','unresolved_speed_mismatch_total_mps'):
        if isinstance(q.get(name),(int,float)) and math.isfinite(q[name]):return max(0.,q[name])
    if q.get('maneuver_budget_complete') or q.get('budget_complete') or q.get('powered_geometry_valid') or q.get('unresolved_flyby_count')==0:return 0.
    return max(0.,float(q.get('max_unresolved_vinf_mismatch_mps',q.get('max_vinf_mismatch_mps',0.)) or 0.))


def unresolved_mismatch_peak(q):
    if isinstance(q.get('flybys'),list):
        return max((max(0.,float(f.get('speed_mismatch_mps',0.) or 0.)) for f in q['flybys'] if f.get('passes_powered_geometry') is not True),default=0.)
    peak=q.get('max_unresolved_vinf_mismatch_mps')
    if isinstance(peak,(int,float)) and math.isfinite(peak):return max(0.,peak)
    if q.get('maneuver_budget_complete') or q.get('budget_complete') or q.get('powered_geometry_valid') or q.get('unresolved_flyby_count')==0:return 0.
    return max(0.,float(q.get('max_vinf_mismatch_mps',0.) or 0.))


def modeled_plus_unresolved_mismatch(q):
    return float(q.get('total_dsm_kms',0.) or 0.)+unresolved_mismatch_sum(q)/1000.


def red_reason(q,config=None):
    c=config or {}
    cap=c.get('max_single_dsm_kms')
    peak=q.get('max_single_dsm_kms')
    if peak is None:peak=max((float(b.get('magnitude_kms',0.) or 0.) for b in q.get('dsms',[])),default=0.)
    powered=q.get('max_powered_flyby_kms')
    if powered is None:powered=max((float((f.get('powered_flyby') or {}).get('magnitude_kms',0.) or 0.) for f in q.get('flybys',[])),default=0.)
    if cap is not None and (unresolved_mismatch_peak(q)>1000*cap+1e-6 or peak>cap+1e-9):
        return 'Leg mismatch or individual DSM exceeds the DSM cap.'
    if c.get('max_powered_flyby_kms') is not None and powered>c['max_powered_flyby_kms']+1e-9:
        return 'Powered flyby exceeds its burn cap.'
    total=modeled_plus_unresolved_mismatch(q)
    if unresolved_mismatch_sum(q)>1e-6 and c.get('max_dsm_kms') is not None and total>c['max_dsm_kms']+1e-9:
        return 'Combined unresolved flyby mismatch and modeled burns exceed the DSM screening budget.'
    if q.get('periapsis_violation') is True or (q.get('periapsis_violation') is not False and float(q.get('min_turn_margin_deg',0.) or 0.) < -1e-8 and q.get('powered_geometry_valid') is not True):
        return 'Flyby periapsis is below its allowed floor.'
    return None
