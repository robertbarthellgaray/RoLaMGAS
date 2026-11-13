"""Derive planet-ending missions from an already evaluated multi-assist cruise.

No optimization, downloads or extra state integration: rerun the same Lambert
legs against the exact JPL event states used by the parent, with the original
screening limits. Arrival velocity and maneuver accounting are recomputed.
"""
from copy import deepcopy
import re
import numpy as np
from ephemeris import BODIES

def prefix_route(route,event):
    count=0;tokens=[]
    for token in re.findall(r'Me|dv|dV|[EVMJSUNX]',route['id']):
        tokens.append(token)
        if token not in ('dv','dV'):
            count+=1
            if count==event+1:break
    if count!=event+1:raise ValueError('Sequence and encounter count differ')
    r=deepcopy(route);r.update(id=''.join(tokens),target=route['bodies'][event],bodies=route['bodies'][:event+1],
        dsm_legs=[leg for leg in route.get('dsm_legs',[]) if leg<event],leg_days=route['leg_days'][:event],branch_options=route['branch_options'][:event])
    return r

def public_records(q,config,route):
    """Parent first, then accepted non-Earth planetary encounter prefixes."""
    from community import public_record,record_variables,unique_encounters
    from dynamics import Model
    parent=public_record(q,config,route)
    if parent is None:return []
    records=[parent]
    class EventStates:
        def state(self,body,date):
            for event in q.get('events',[]):
                if event['body']==body and abs(event['julian_date_tdb']-date)<1e-8:
                    return np.array(event['planet_state_km_kms'],float)
            raise ValueError('Prefix event has no matching saved JPL state')
    for event,body in enumerate(route['bodies'][1:-1],1):
        if body=='Earth' or body not in BODIES:continue
        try:
            r=prefix_route(route,event);c=dict(config,target=body,target_object=None,append_flyby=None,
                sequences=[r['id']],event_windows_jd=[[t,t] for t in q['dates_jd_tdb'][:event+1]])
            prefix=dict(parent,sequence=r['id'],body_ids=parent['body_ids'][:event+1],dates_jd_tdb=parent['dates_jd_tdb'][:event+1],
                branches=parent['branches'][:event],dsm_controls=[d for d in parent['dsm_controls'] if d['leg_index']<event])
            model=Model(r,c,EventStates());x,branches=record_variables(prefix,model);verified=model.evaluate(x,branches)
            if not model.accepted(verified):continue
            verified.update(status='passes_configured_patched_conic_screen',discovered_unix=q.get('discovered_unix'))
            if verified['discovered_unix'] is None:verified.pop('discovered_unix')
            record=public_record(verified,c,r)
            if record is not None:records.append(record)
        except (ValueError,KeyError,RuntimeError,AssertionError,ZeroDivisionError,OverflowError,FloatingPointError):continue
    return unique_encounters(records)[0]
