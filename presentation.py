"""Offline candidate gallery and independent numerical arc verification."""
import bootstrap  # noqa: F401
from pathlib import Path
import csv
import json
import numpy as np
from scipy.integrate import solve_ivp
from dynamics import kepler
from ephemeris import AU, DAY, MU_SUN, atomic_json


def write_tsv(path, rows):
    if not rows:
        path.write_text('',encoding='utf-8')
        return
    with path.open('w',newline='',encoding='utf-8') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0]),delimiter='\t',extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def publish(output, summary, ep, deferred=False, config=None):
    from candidate_status import red_reason
    candidates = output/'candidates'
    candidates.mkdir(exist_ok=True)
    cards, table = [], []
    for q in summary['candidates']+summary['near_misses']:
        atomic_json(candidates/(q['id']+'.json'),q)
        events = [dict(kind='launch' if i == 0 else 'arrival' if i == len(q['events'])-1 else 'flyby',
                       body=e['body'],date=e['date'],julian_date_tdb=e['julian_date_tdb'],
                       delta_v_kms='',speed_mismatch_mps='') for i,e in enumerate(q['events'])]
        for f,e in zip(q['flybys'],events[1:-1]):
            e['speed_mismatch_mps'] = f['speed_mismatch_mps']
        events.extend(dict(kind='DSM',body='',date=b['date'],julian_date_tdb=b['julian_date_tdb'],
                           delta_v_kms=b['magnitude_kms'],speed_mismatch_mps='') for b in q['dsms'])
        write_tsv(candidates/(q['id']+'_events.tsv'),sorted(events,key=lambda e:e['julian_date_tdb']))
        paths = []
        skipped=red_reason(q,config)
        for segment in ([] if deferred or skipped else q['segments']):
            try:
                r,v = np.array(segment['r']),np.array(segment['v'])
                duration = (segment['end_jd']-segment['start_jd'])*DAY
                paths.append([(kepler(r,v,float(t))[0]/AU).tolist() for t in np.linspace(0,duration,220)])
            except (ValueError,OverflowError):
                paths.append([])
        orbits = []
        for body in ([] if deferred or skipped else dict.fromkeys(q['bodies'])):
            # Show the portion of each planet's actual ephemeris covered by this mission.
            dates = np.linspace(q['dates_jd_tdb'][0],q['dates_jd_tdb'][-1],500)
            orbits.append(dict(body=body,points=[(ep.state(body,d)[:3]/AU).tolist() for d in dates]))
        card = dict(q)
        card.pop('segments',None)
        card.update(paths=paths,planet_paths=orbits,render_skipped=skipped,render_pending=deferred and not skipped)
        cards.append(card)
        table.append({key:q[key] for key in ('id','status','sequence','launch_date','arrival_date','duration_years',
                     'launch_c3_km2_s2','arrival_vinf_kms','total_dsm_kms','max_vinf_mismatch_mps','min_turn_margin_deg')})
    write_tsv(output/'comparison.tsv',table)
    payload = dict(candidates=cards,meta={k:v for k,v in summary.items() if k not in ('candidates','near_misses')})
    template = (Path(__file__).parent/'gallery.html').read_text(encoding='utf-8')
    data = json.dumps(payload,allow_nan=False).replace('<','\\u003c')
    (output/'index.html').write_text(template.replace('/*__DATA__*/',data),encoding='utf-8')


def validate_candidate(path, output):
    q = json.loads(path.read_text(encoding='utf-8'))
    segments = q['segments']
    reports = []
    for i,s in enumerate(segments):
        state = np.r_[s['r'],s['v']]
        duration = (s['end_jd']-s['start_jd'])*DAY
        def rhs(t,y):
            return np.r_[y[3:],-MU_SUN*y[:3]/np.linalg.norm(y[:3])**3]
        fit = solve_ivp(rhs,(0,duration),state,method='DOP853',rtol=2e-12,
                        atol=np.r_[np.full(3,1e-5),np.full(3,1e-12)])
        if not fit.success:
            raise ValueError(f'Independent integration failed: {fit.message}')
        rr,vv = kepler(state[:3],state[3:],duration)
        expected = (segments[i+1]['r'] if i+1 < len(segments)
                    else q['events'][-1]['planet_state_km_kms'][:3])
        reports.append(dict(segment=i,endpoint_error_km=float(np.linalg.norm(fit.y[:3,-1]-expected)),
                            universal_vs_dop853_position_km=float(np.linalg.norm(rr-fit.y[:3,-1])),
                            universal_vs_dop853_velocity_kms=float(np.linalg.norm(vv-fit.y[3:,-1]))))
    maximum = max(r['endpoint_error_km'] for r in reports)
    report = dict(candidate_id=q['id'],segments=reports,maximum_endpoint_error_km=maximum,
                  sun_only_arcs_pass_1_km_endpoint_check=maximum < 1,
                  nbody_validated=False,
                  note='Checks the declared Sun-only arcs. Instantaneous planet-center flyby patches remain approximate; no hidden TCMs or finite-radius flyby model are added.')
    atomic_json(output,report)
    print(json.dumps(report,indent=2))
    if maximum >= 1:
        raise ValueError('Independent propagation exceeded the 1 km endpoint threshold')
