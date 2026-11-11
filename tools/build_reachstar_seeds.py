"""Build credited timing, prefix and resonance starters from the saved recreation.

Local CPU only. Does not fetch data, publish records or change search limits.
"""
from pathlib import Path
import json,sys,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap,numpy as np
from ephemeris import Ephemerides,BODIES,atomic_json
from dynamics import Model
from mission_search import normalize,routes_for
from community import record_variables
from earth_return_seeds import rtn_basis
from search_options import export_options
from study_resonant_transfers import physical_record,audit_coasts
from catalog_validation import audit_candidate

ROOT=Path(__file__).resolve().parents[1]
CREDIT='Original RSS/Principia trajectory by ReachStar on Bilibili; date-adjusted JPL recreation in RoLaMGAS.'
TOKENS=dict(Earth='E',Venus='V',Mars='M',Mercury='Me',Jupiter='J',Saturn='S',Uranus='U',Neptune='N')

def main():
    folder=ROOT/'studies/eight_planet_tour/verified_source_recreation'
    full=json.loads((folder/'candidate.json').read_text());c=json.loads((folder/'run_manifest.json').read_text())['config']
    original=physical_record(full,c);records=[];links=[]
    ep=Ephemerides(ROOT/'cache',full['bodies'],full['dates_jd_tdb'][0]-1,full['dates_jd_tdb'][-1]+1,1.)
    for last in (1,2,4,5,6,7,8,9,11,12,13,14):
        n=last+1;controls=[d for d in original['dsm_controls'] if d['leg_index']<last]
        seq=''.join(TOKENS[b]+('dv' if any(d['leg_index']==i for d in controls) else '') for i,b in enumerate(full['bodies'][:n]))
        dates=full['dates_jd_tdb'][:n];branches=full['branches'][:last]
        record=dict(schema_version=1,sequence=seq,body_ids=original['body_ids'][:n],dates_jd_tdb=dates,branches=branches,dsm_controls=controls)
        windows=[[e['date'].removesuffix(' TDB')]*2 for e in full['events'][:n]]
        # Preserve exact full-precision JDs rather than rounded printed seconds.
        cfg=normalize(dict(target=full['bodies'][last],sequences=[seq],launch_start=windows[0][0],launch_end=windows[0][1],
                           min_c3=5,max_c3=20,max_years=19,max_dsm_kms=.005,max_single_dsm_kms=.005,
                           max_arrival_vinf_kms=30,vinf_tolerance_mps=.1,dsm_velocity_box_kms=6.,
                           minimum_altitude_km={'Earth':130.,'Venus':250.},cache=str(ROOT/'cache'),
                           route_overrides={seq:dict(leg_days=[[max(1,d*.8),d*1.2+1] for d in np.diff(dates)],branch_options=[[b] for b in branches])}))
        # Tiny nonzero portable windows include the unrounded computed epochs.
        from ephemeris import calendar
        cfg=normalize(dict(cfg,event_windows=[[calendar(d-.001).removesuffix(' TDB'),calendar(d+.001).removesuffix(' TDB')] for d in dates]))
        route=routes_for(cfg)[0];model=Model(route,cfg,ep);x,bb=record_variables(record,model);q=model.evaluate(x,bb)
        if not model.accepted(q):raise ValueError('Prefix did not reproduce '+seq)
        coasts=audit_coasts(q)
        if not coasts['passed']:raise ValueError(coasts)
        q=json.loads(json.dumps(q));record=physical_record(q,cfg)
        record.update(id=hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:12],
                      credit=CREDIT,reference_kind='rss_principia_recreation',reference_events=q['events'],
                      standard_altitude_screen_passed=audit_candidate(q,cfg,BODIES)['passed'])
        records.append(record)
        portable_cfg=normalize(dict(cfg,minimum_altitude_km={})) if record['standard_altitude_screen_passed'] else cfg
        label='ReachStar recreation · '+seq+(' · low-altitude research' if not record['standard_altitude_screen_passed'] else '')
        document=export_options(portable_cfg)['document'];document.update(trajectory=physical_record(q,cfg),display_name=label,attribution=CREDIT)
        name=f'reachstar_{last:02d}_{seq}.json'
        file=ROOT/'departure_seeds/reachstar_imports'/name;atomic_json(file,document)
        atomic_json(ROOT/'examples'/name,document['settings'])
        links.append(dict(sequence=seq,target=q['bodies'][-1],file=str(file.relative_to(ROOT)),preset='examples/'+name,standard_altitude_screen_passed=record['standard_altitude_screen_passed'],max_endpoint_error_km=coasts['maximum_dop853_endpoint_error_km']))
        print(seq,'verified; standard altitude floors:',record['standard_altitude_screen_passed'],flush=True)
    templates=[]
    for i in (4,7):
        state=np.array(full['events'][i]['planet_state_km_kms']);u=np.array(full['departure_velocities_kms'][i])-state[3:]
        direction=rtn_basis(state).T@u/np.linalg.norm(u)
        templates.append(dict(body='Venus',leg_index=i,return_days=full['dates_jd_tdb'][i+1]-full['dates_jd_tdb'][i],
                              departure_vinf_direction_rtn=direction.tolist(),departure_vinf_kms=float(np.linalg.norm(u)),midpoint_fraction=.5))
    departure=rtn_basis(np.array(full['events'][0]['planet_state_km_kms'])).T@np.array(full['launch_vinf_vector_kms'])/full['launch_vinf_kms']
    mission=dict(name='ReachStar eight-planet JPL recreation',reference_kind='rss_principia_recreation',seed_eligible=True,
                 bodies=full['bodies'],dates=[e['date'].removesuffix(' TDB') for e in full['events']],
                 planet_leg_days=np.diff(full['dates_jd_tdb']).tolist(),
                 dsm_events=[dict(leg_index=i,fraction=.5) for i in (4,7)],
                 departure=dict(selected=dict(c3_km2_s2=full['launch_c3_km2_s2']),direction_rtn=departure.tolist()),
                 sources=[dict(title='ReachStar on Bilibili: user-supplied RSS/Principia encounter table')],credit=CREDIT,
                 note='Timings and RTN vectors are starting guesses at other epochs, not validated future opportunities. No atmosphere or n-body budget validation.')
    data=dict(schema_version=1,credit=CREDIT,missions=[mission],records=records,resonant_templates=templates)
    atomic_json(ROOT/'departure_seeds/reachstar_tour.json',data)
    if '--future' in sys.argv:
        future,missions=build_future_returns()
        data['future_records']=future;data['missions'].extend(missions)
        atomic_json(ROOT/'departure_seeds/reachstar_tour.json',data)
    atomic_json(ROOT/'studies/eight_planet_tour/seed_summary.json',dict(credit=CREDIT,starters=links))


def build_future_returns():
    """A small reproducible capability check, not a global launch-window search."""
    from ephemeris import jd,calendar
    from resonant_shooting_seeds import seed_venus_returns,reference
    reference.cache_clear()
    years=[2029,2031,2033,2035,2039];ep=Ephemerides(ROOT/'cache',['Earth','Venus'],jd('2029-01-01'),jd('2042-01-01'),1.)
    records=[];missions=[];rows=[];attempted=0
    for year in years:
        found=False
        for month in range(1,13):
            for days in (90,110,130,150):
                t=jd(f'{year}-{month:02d}-01');dates=[t,t+days,t+days+224.701]
                text=[calendar(d).removesuffix(' TDB') for d in dates];seq='EVdvV'
                c=normalize(dict(target='Venus',sequences=[seq],launch_start=text[0],launch_end=text[0],event_windows=[[d,d] for d in text],
                    min_c3=5,max_c3=20,max_dsm_kms=.01,max_single_dsm_kms=.01,max_years=3,max_arrival_vinf_kms=30,dsm_velocity_box_kms=6,vinf_tolerance_mps=.1,
                    route_overrides={seq:dict(leg_days=[[45,250],[200,250]],branch_options=[[[0,True]],[[1,True]]])}))
                route=routes_for(c)[0];model=Model(route,c,ep);x=np.full(model.dimension,.5);branches=[[0,True],[1,True]]
                try:
                    if not model.c3_in_bounds(model.launch_c3(x,branches)):continue
                    attempted+=1;points,_=seed_venus_returns(np.tile(x,(4,1)),model,branches)
                    for point in points:
                        q=model.evaluate(point,branches)
                        if not model.accepted(q):continue
                        audit=audit_candidate(q,c,BODIES);coasts=audit_coasts(q)
                        if not audit['passed'] or not coasts['passed']:raise ValueError('Independent future starter audit failed')
                        q=json.loads(json.dumps(q));record=physical_record(q,c)
                        record.update(id=hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest()[:12],credit='ReachStar-inspired resonance initializer; fresh JPL solution by RoLaMGAS',reference_events=q['events'])
                        records.append(record)
                        document=export_options(c)['document'];document.update(trajectory=physical_record(q,c),display_name=f'ReachStar-inspired Venus return {year}',attribution=record['credit'])
                        name=f'reachstar_future_{year}_EVdvV.json'
                        atomic_json(ROOT/'departure_seeds/reachstar_imports'/name,document)
                        atomic_json(ROOT/'examples'/name,document['settings'])
                        direction=rtn_basis(np.array(q['events'][0]['planet_state_km_kms'])).T@np.array(q['launch_vinf_vector_kms'])/q['launch_vinf_kms']
                        missions.append(dict(name=f'ReachStar-inspired Venus return {year}',reference_kind='solver_built_resonant_starter',seed_eligible=True,bodies=q['bodies'],dates=[e['date'].removesuffix(' TDB') for e in q['events']],planet_leg_days=np.diff(q['dates_jd_tdb']).tolist(),dsm_events=[dict(leg_index=1,fraction=.5)],sources=[dict(title=CREDIT)],departure=dict(selected=dict(c3_km2_s2=q['launch_c3_km2_s2']),direction_rtn=direction.tolist())))
                        rows.append(dict(launch=q['launch_date'],c3=q['launch_c3_km2_s2'],dsm_mps=q['total_dsm_kms']*1000,altitude_km=q['flybys'][0]['conservative_equal_speed_altitude_km'],maximum_speed_mismatch_mps=q['max_vinf_mismatch_mps'],independent_coasts=coasts,source='Fresh JPL epochs; not a shifted historical spacecraft state'))
                        found=True;break
                except (ValueError,RuntimeError,AssertionError,ZeroDivisionError):pass
                if found:break
            if found:break
    atomic_json(ROOT/'studies/eight_planet_tour/future_seed_benchmark.json',dict(requested_years=years,attempted_in_range=attempted,passing=rows,note='A limited EVdvV starter check, not complete outer-planet missions or an infeasibility proof for missing years.'))
    print('Future Venus return starters independently verified:',len(records),flush=True)
    return records,missions

if __name__=='__main__':main()
