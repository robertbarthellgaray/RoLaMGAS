"""Portable, strictly numeric website candidates; never execute imported paths/code."""
import bootstrap
from copy import deepcopy
import json,math,hashlib,time
import numpy as np
from ephemeris import BODIES

def checked_record(record):
    if not isinstance(record,dict):raise ValueError('Missing selected trajectory record')
    r=deepcopy(record);ids=r.get('body_ids');dates=r.get('dates_jd_tdb');branches=r.get('branches');controls=r.get('dsm_controls');segments=r.get('segments')
    if r.get('schema_version')!=1 or not isinstance(ids,list) or not 2<=len(ids)<=30 or not all(isinstance(v,str) and v.lstrip('-').isdigit() and len(v)<15 for v in ids):raise ValueError('Invalid trajectory body IDs')
    if not isinstance(r.get('sequence'),str) or not 1<=len(r['sequence'])<=100:raise ValueError('Invalid trajectory sequence')
    if not isinstance(dates,list) or len(dates)!=len(ids) or not all(type(t) in (int,float) and math.isfinite(t) and 2000000<t<3000000 for t in dates) or any(b<=a for a,b in zip(dates,dates[1:])):raise ValueError('Invalid trajectory dates')
    if not isinstance(branches,list) or len(branches)!=len(ids)-1 or any(not isinstance(b,list) or len(b) not in (2,3) or type(b[0]) is not int or not 0<=b[0]<=20 or not all(type(v) is bool for v in b[1:]) for b in branches):raise ValueError('Invalid Lambert branches')
    def vector(v):return isinstance(v,list) and len(v)==3 and all(type(x) in (int,float) and math.isfinite(x) and abs(x)<1e13 for x in v)
    if not isinstance(controls,list) or len(controls)>len(ids)-1:raise ValueError('Invalid maneuver controls')
    for c in controls:
        if not isinstance(c,dict) or type(c.get('leg_index')) is not int or not 0<=c['leg_index']<len(ids)-1 or not isinstance(c.get('fraction'),(int,float)) or not .1-1e-12<=c['fraction']<=.9+1e-12 or not vector(c.get('departure_offset_kms')):raise ValueError('Invalid maneuver control')
    if len({c['leg_index'] for c in controls})!=len(controls):raise ValueError('Duplicate maneuver controls')
    if not isinstance(segments,list) or not 1<=len(segments)<=60:raise ValueError('Invalid coast count')
    for s in segments:
        if not isinstance(s,dict) or not vector(s.get('r')) or not vector(s.get('v')) or not all(type(s.get(k)) in (int,float) and math.isfinite(s[k]) for k in ('start_jd','end_jd')) or not dates[0]-1e-7<=s['start_jd']<s['end_jd']<=dates[-1]+1e-7:raise ValueError('Invalid coast state')
    m=r.get('metrics')
    if not isinstance(m,dict) or not all(type(m.get(k)) in (int,float) and math.isfinite(m[k]) and m[k]>=0 for k in ('launch_c3_km2_s2','total_dsm_kms','arrival_vinf_kms')):raise ValueError('Invalid trajectory metrics')
    # Only fixed science fields survive an import. Unknown fields are not executable settings.
    return {k:r[k] for k in ('schema_version','sequence','body_ids','dates_jd_tdb','branches','dsm_controls','segments','metrics')}

def materialize(record,config,route,ep):
    from dynamics import Model
    from community import record_variables
    r=checked_record(record);model=Model(route,config,ep);x,branches=record_variables(r,model)
    if r['sequence']!=route['id']:raise ValueError('Imported sequence differs from search settings')
    if list(r['body_ids'])!=[str(BODIES[b][0]) if b in BODIES else str(config['target_object']['id']) for b in route['bodies']]:raise ValueError('Imported body IDs differ from search settings')
    q=model.evaluate(x,branches,enforce_c3=False)
    if len(q['segments'])!=len(r['segments']):raise ValueError('Imported coast count differs from recomputed trajectory')
    max_r=0.;max_v=0.
    for a,b in zip(q['segments'],r['segments']):
        if max(abs(a[k]-b[k]) for k in ('start_jd','end_jd'))>1e-7:raise ValueError('Imported coast epochs differ')
        max_r=max(max_r,float(np.linalg.norm(np.array(a['r'])-b['r'])));max_v=max(max_v,float(np.linalg.norm(np.array(a['v'])-b['v'])))
    if max_r>2. or max_v>.002:raise ValueError(f'Cached JPL states do not reproduce this candidate: {max_r:.3f} km / {max_v:.6f} km/s. No replacement trajectory was substituted.')
    m=r['metrics']
    if abs(q['launch_c3_km2_s2']-m['launch_c3_km2_s2'])>.02 or abs(q['arrival_vinf_kms']-m['arrival_vinf_kms'])>.01:raise ValueError('Recomputed costs differ from selected website candidate')
    if abs(q['total_dsm_kms']-m['total_dsm_kms'])>.001:
        raise ValueError('Recomputed maneuver total differs from the selected candidate; check powered-flyby settings and altitude floors.')
    q.update(status='passes_configured_patched_conic_screen' if model.accepted(q) else 'near_miss_not_accepted',screening_residual_norm=float(np.linalg.norm(model.residual(x,branches))) if model.c3_in_bounds(q['launch_c3_km2_s2']) else 1e6,discovered_unix=time.time(),import_verification=dict(source='Website trajectory transfer',maximum_coast_position_difference_km=max_r,maximum_coast_velocity_difference_kms=max_v,optimization_performed=False,source_cruise_delta_v_kms=m['total_dsm_kms'],recomputed_cruise_delta_v_kms=q['total_dsm_kms']))
    q['id']=hashlib.sha256(json.dumps([r['sequence'],r['dates_jd_tdb'],r['branches'],r['dsm_controls']],separators=(',',':')).encode()).hexdigest()[:12]
    return q
