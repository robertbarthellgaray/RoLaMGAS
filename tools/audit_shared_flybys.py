"""Recover flyby speed gaps and estimate explicit periapsis burns from shared coasts.

python tools/audit_shared_flybys.py --record candidate.json --cache PATH --output audit.json
No search, downloads, or trajectory modifications. Uses the same analytic powered
flyby construction as the desktop solver, with fresh locally cached JPL states.
"""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
import numpy as np
from app_paths import DATA_ROOT
from ephemeris import Ephemerides,BODIES,MU_SUN,DAY,atomic_json
from dynamics import kepler
from powered_flyby import geometry

def audit(record,cache,altitudes=None):
    altitudes=altitudes or {};names={str(v[0]):k for k,v in BODIES.items()}
    dates=record['dates_jd_tdb'];ids=record['body_ids'];flyby_dates=dates[1:-1]
    ep=Ephemerides(cache,[names[i] for i in ids[1:-1] if i in names],min(flyby_dates)-1,max(flyby_dates)+1,1.) if flyby_dates else None
    rows=[]
    for i in range(1,len(ids)-1):
        row=dict(body=names.get(ids[i],ids[i]),event_index=i,jd=dates[i]);rows.append(row)
        try:
            body=names[ids[i]];planet=ep.state(body,dates[i]);mu,radius,floor=BODIES[body][1:];floor=float(altitudes.get(body,floor))
            if not np.isfinite(floor) or floor<0:raise ValueError('Invalid minimum altitude')
            before=next(s for s in record['segments'] if abs(s['end_jd']-dates[i])<1e-6)
            after=next(s for s in record['segments'] if abs(s['start_jd']-dates[i])<1e-6)
            incoming=kepler(np.array(before['r']),np.array(before['v']),(dates[i]-before['start_jd'])*DAY)[1]-planet[3:]
            outgoing=np.array(after['v'])-planet[3:]
            row.update(mismatch_mps=float(abs(np.linalg.norm(incoming)-np.linalg.norm(outgoing))*1000),
                incoming_vinf_kms=incoming.tolist(),outgoing_vinf_kms=outgoing.tolist(),planet_state_km_kms=planet.tolist(),minimum_altitude_km=floor)
            power=geometry(mu,radius+floor,incoming,outgoing,.799*np.linalg.norm(planet[:3])*(mu/MU_SUN)**.4)
            row.update(estimated_burn_mps=power['magnitude_kms']*1000,estimated_altitude_km=power['periapsis_radius_km']-radius,delta_v_vector_kms=power['delta_v_vector_kms'])
        except (ValueError,KeyError,StopIteration) as exc:row['error']=str(exc) or 'Encounter coasts unavailable'
    return dict(candidate_id=record['id'],stored_modeled_burns_mps=record['metrics']['total_dsm_kms']*1000,
        stored_max_vinf_mismatch_mps=record['metrics'].get('max_vinf_mismatch_mps'),rows=rows,
        sum_speed_mismatches_mps=sum(r['mismatch_mps'] for r in rows) if all('mismatch_mps' in r for r in rows) else None,
        estimated_periapsis_burn_sum_mps=sum(r['estimated_burn_mps'] for r in rows) if all('estimated_burn_mps' in r for r in rows) else None,
        model='One conservative common-periapsis impulse per planetary encounter; original saved asymptotes preserved. Not a minimum-fuel solution. Nominal encounter epochs are not finite-radius periapsis times. Launch injection, capture, targeting corrections and any already modeled coast DSMs are separate.',
        ephemeris='Locally cached JPL Horizons, heliocentric Ecliptic J2000, TDB, km and km/s')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--record',type=Path,required=True);p.add_argument('--cache',type=Path,default=DATA_ROOT/'cache');p.add_argument('--output',type=Path,default=Path('runs/flyby_audit.json'))
    a=p.parse_args();record=json.loads(a.record.read_text(encoding='utf-8'));result=audit(record,a.cache);a.output.parent.mkdir(parents=True,exist_ok=True);atomic_json(a.output,result)
    print(json.dumps({k:result[k] for k in ['candidate_id','stored_max_vinf_mismatch_mps','sum_speed_mismatches_mps','estimated_periapsis_burn_sum_mps']}),flush=True)
