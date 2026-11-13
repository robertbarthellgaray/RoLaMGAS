"""Build a Jupiter opportunity batch locally from verified cruise prefixes and a
direct-transfer survey. Every retained prefix is freshly solved with JPL vectors;
source pass flags are not trusted. No AI service is called.

Default: audit/write local results only. --publish explicitly shares candidates
through the public API and updates the bundled website archive.
"""
from pathlib import Path
from collections import Counter,defaultdict
import argparse,csv,hashlib,json,re,sys,time,urllib.parse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).resolve().parent))
import bootstrap,numpy as np
from scipy.optimize import least_squares
from dynamics import Model,lambert,kepler
from ephemeris import BODIES,DAY,Ephemerides,jd,calendar,atomic_json
from mission_search import normalize,routes_for
from community import public_record,record_variables,encounter_key,unique_encounters,exchange
from review_early2030s import save_catalog
NAMES={str(v[0]):k for k,v in BODIES.items()}

def jupiter_prefix(record):
    """Cut exactly at the first Jupiter event; discard later DSMs and branches."""
    if '599' not in record['body_ids'][1:]:return None
    end=record['body_ids'].index('599',1);tokens=re.findall(r'Me|dv|dV|[EVMJSUNX]',record['sequence'])
    taken=[];count=0
    for token in tokens:
        taken.append(token)
        if token not in ('dv','dV'):
            count+=1
            if count==end+1:break
    if count!=end+1:return None
    return dict(schema_version=1,sequence=''.join(taken),body_ids=record['body_ids'][:end+1],
                dates_jd_tdb=record['dates_jd_tdb'][:end+1],branches=record['branches'][:end],
                dsm_controls=[d for d in record['dsm_controls'] if d['leg_index']<end])

def limits(prefix,cache):
    seq=prefix['sequence'];dates=prefix['dates_jd_tdb'];durations=np.diff(dates)
    bodies=[NAMES[b] for b in prefix['body_ids']]
    maximum=100. if len(bodies)==2 else (30. if 'Venus' in bodies else 45.)
    return normalize(dict(target='Jupiter',sequences=[seq],launch_start=calendar(dates[0])[:10],launch_end=calendar(dates[0])[:10],
        event_windows_jd=[[t,t] for t in dates],min_c3=5.,max_c3=maximum,max_years=10.,max_arrival_vinf_kms=15.,
        max_dsm_kms=1.,max_single_dsm_kms=.7,max_powered_flyby_kms=.2,vinf_tolerance_mps=1.,powered_flybys=False,
        minimum_altitude_km=dict(Earth=200.,Venus=300.,Mars=200.,Mercury=200.),cache=str(cache),
        route_overrides={seq:dict(leg_days=[[max(.001,float(d)*.5),float(d)*1.5+1] for d in durations],branch_options=[[b] for b in prefix['branches']])}))

def check(prefix,ep,cache,source):
    c=limits(prefix,cache);route=routes_for(c)[0];model=Model(route,c,ep)
    x,bb=record_variables(prefix,model);q=model.evaluate(x,bb)
    if not model.accepted(q):return None
    q.update(status='passes_configured_patched_conic_screen',discovered_unix=time.time())
    record=public_record(q,c,route)
    if record is None:return None
    # Record-based provenance lives in local audit, not anonymous API payloads.
    q['study_config']=c;q['source_description']=source;q['id']=record['id'][:12]
    independent=float(np.linalg.norm(np.array(q['segments'][0]['v'])-ep.state('Earth',q['dates_jd_tdb'][0])[3:])**2)
    if abs(independent-q['launch_c3_km2_s2'])>1e-6:raise ValueError('Independent C3 check failed')
    return q,record

def diversity_select(pairs,existing,desired):
    # One representative per ordered encounter day first, then spread selections
    # by sequence, launch year and energy band; don't fill 300 slots in one window.
    ranked=sorted(pairs,key=lambda pair:(pair[1]['metrics']['launch_c3_km2_s2']/100+pair[1]['metrics']['total_dsm_kms']+pair[1]['metrics']['arrival_vinf_kms']/20+pair[1]['metrics']['duration_years']/100,pair[1]['id']))
    slots={}
    for q,r in ranked:
        key=encounter_key(r)
        if key not in existing:slots.setdefault(key,(q,r))
    groups=defaultdict(list)
    for q,r in slots.values():groups[(r['sequence'],q['launch_date'][:4],int(q['launch_c3_km2_s2']//10))].append((q,r))
    assisted=sum(len(rows) for key,rows in groups.items() if key[0]!='EJ')
    direct_cap=max(desired//3,desired-assisted)
    selected=[];direct=0
    while groups and len(selected)<desired:
        for key in sorted(groups):
            if len(selected)>=desired:break
            if key[0]=='EJ' and direct>=direct_cap:continue
            selected.append(groups[key].pop(0))
            if key[0]=='EJ':direct+=1
        groups={key:rows for key,rows in groups.items() if rows}
    return selected,len(slots)

def assist_variations(pairs,ep,cache):
    """Retarget nearby launch weeks while keeping the parent Lambert branches."""
    seeds,_=diversity_select([p for p in pairs if len(p[1]['body_ids'])>2],set(),90)
    found=[];attempts=0
    for old,record in seeds:
        for shift in (-14.,-7.,7.,14.):
            attempts+=1;dates=np.asarray(old['dates_jd_tdb'])+shift
            c=dict(old['study_config']);c['event_windows_jd']=[[float(t-45),float(t+45)] for t in dates]
            c['event_windows_jd'][0]=[float(dates[0]),float(dates[0])]
            route=routes_for(c)[0];model=Model(route,c,ep);x=np.array(old['x'],float)
            x[:model.n]=.5
            try:
                fit=least_squares(lambda z:model.residual(np.r_[.5,z],old['branches']),x[1:],bounds=(0,1),max_nfev=90,ftol=1e-9,xtol=1e-9,gtol=1e-9)
                candidate=model.evaluate(np.r_[.5,fit.x],old['branches'])
                if not model.accepted(candidate):continue
                pref=dict(schema_version=1,sequence=old['sequence'],body_ids=record['body_ids'],dates_jd_tdb=candidate['dates_jd_tdb'],branches=candidate['branches'],dsm_controls=[])
                n=model.n
                for j,leg in enumerate(model.dsm_legs):
                    k=n+4*j;xx=candidate['x']
                    pref['dsm_controls'].append(dict(leg_index=leg,fraction=.1+.8*xx[k],departure_offset_kms=((np.asarray(xx[k+1:k+4])*2-1)*c['dsm_velocity_box_kms']).tolist()))
                result=check(pref,ep,cache,'New retargeted launch-week variation of '+record['id'])
                if result:found.append(result)
            except (ValueError,RuntimeError,AssertionError,ZeroDivisionError,OverflowError):continue
        if attempts%40==0:print('Assist variations:',attempts,'passing:',len(found),flush=True)
    return found

def publish_saved(output):
    from import_passing_history import canonical_records
    output=Path(output);raw=json.loads((output/'public_candidates.json').read_text(encoding='utf-8'))
    valid=canonical_records(raw)
    if valid['invalid']:raise ValueError(valid['invalid'])
    records=valid['valid'];atomic_json(output/'public_candidates.json',records);receipts=[]
    from trajectory_prefixes import public_records
    extra=[]
    for q in json.loads((output/'selected_candidates.json').read_text(encoding='utf-8')):
        extra.extend(public_records(q,q['study_config'],routes_for(q['study_config'])[0])[1:])
    combined,_=unique_encounters(records+extra);all_valid=canonical_records(combined)
    if all_valid['invalid']:raise ValueError(all_valid['invalid'])
    records=all_valid['valid'];atomic_json(output/'shared_with_prefixes.json',records)
    for i in range(0,len(records),10):
        receipts.append(exchange('https://rolamgas-community.corigarayv.workers.dev/v1/candidates',dict(candidates=records[i:i+10])))
        print('Shared:',min(i+10,len(records)),'/',len(records),flush=True)
    atomic_json(output/'upload_receipts.json',receipts)
    for path in (ROOT/'community_seed_catalog.json',ROOT/'docs/data/community_seed_catalog.json'):
        doc=json.loads(path.read_text(encoding='utf-8'));values={r['id']:r for r in doc['candidates']};values.update({r['id']:r for r in records});doc['candidates'],_=unique_encounters(list(values.values()));save_catalog(path,doc)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'studies/jupiter_library_expansion')
    p.add_argument('--cache',type=Path,default=ROOT/'cache');p.add_argument('--count',type=int,default=300)
    p.add_argument('--first-year',type=int,default=2027);p.add_argument('--last-year',type=int,default=2055);p.add_argument('--publish',action='store_true');p.add_argument('--publish-saved',action='store_true',help='Share the already audited output without rerunning the solver')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    if a.publish_saved:return publish_saved(a.output)
    archive=json.loads((ROOT/'community_seed_catalog.json').read_text(encoding='utf-8'));source=archive['candidates']
    existing={encounter_key(r) for r in source if r['body_ids'][-1]=='599'}
    try:
        cursor=None
        for _ in range(40):
            args=dict(target='599',limit=100)
            if cursor:args['cursor']=cursor
            page=exchange('https://rolamgas-community.corigarayv.workers.dev/v1/candidates?'+urllib.parse.urlencode(args))
            existing.update(encounter_key(r) for r in page['candidates']);cursor=page.get('next_cursor')
            if not cursor:break
    except Exception as error:print('Online duplicate check unavailable:',type(error).__name__,flush=True)
    start=jd(f'{a.first_year}-01-01');stop=jd(f'{a.last_year+1}-01-01')
    ep=Ephemerides(a.cache,['Earth','Venus','Mars','Mercury','Jupiter'],start,stop+10*365.25,1.)
    answers=[];failures=Counter();seen=set();evaluated=0
    for old in source:
        pref=jupiter_prefix(old)
        if not pref or old['body_ids'][-1]=='599' or not start<=pref['dates_jd_tdb'][0]<stop or (pref['dates_jd_tdb'][-1]-pref['dates_jd_tdb'][0])/365.25>10:continue
        key=json.dumps(pref,sort_keys=True)
        if key in seen:continue
        seen.add(key);evaluated+=1
        try:
            result=check(pref,ep,a.cache,'Recomputed Jupiter-ending prefix of '+old['id'])
            if result:answers.append(result)
            else:failures['failed_screen']+=1
        except (ValueError,RuntimeError,AssertionError,ZeroDivisionError,OverflowError) as error:failures[type(error).__name__]+=1
        if evaluated%200==0:print('Prefixes checked:',evaluated,'passing:',len(answers),flush=True)
    prefix_passing=len(answers)
    print('Verified prefixes:',prefix_passing,'of',evaluated,dict(failures),flush=True)
    variations=assist_variations(answers,ep,a.cache);answers.extend(variations)
    # Direct launch windows are cheap enough for a systematic two-week grid.
    # Keep varied flight times and arrival speeds, not hundreds of sub-day clones.
    for launch in np.arange(start,stop,15.):
        earth=ep.state('Earth',launch)
        for days in (500.,650.,800.,1000.,1200.,1500.,1800.):
            try:
                jov=ep.state('Jupiter',launch+days);v,_=lambert(earth[:3],jov[:3],days,[0,True])
                energy=float(np.dot(v-earth[3:],v-earth[3:]))
                if not 5<=energy<=100:continue
                pref=dict(schema_version=1,sequence='EJ',body_ids=['399','599'],dates_jd_tdb=[float(launch),float(launch+days)],branches=[[0,True]],dsm_controls=[])
                result=check(pref,ep,a.cache,'New direct-transfer launch/flight-time grid')
                if result:answers.append(result)
            except (ValueError,RuntimeError,AssertionError,ZeroDivisionError,OverflowError):continue
    selected,novel=diversity_select(answers,existing,a.count)
    atomic_json(a.output/'all_candidates.json',[q for q,r in answers]);atomic_json(a.output/'selected_candidates.json',[q for q,r in selected]);atomic_json(a.output/'public_candidates.json',[r for q,r in selected])
    fields=['id','sequence','launch_date','arrival_date','launch_c3_km2_s2','duration_years','arrival_vinf_kms','total_dsm_kms','max_vinf_mismatch_mps','source_description']
    with (a.output/'comparison.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(q for q,r in selected)
    report=dict(prefixes_evaluated=evaluated,prefixes_passing=prefix_passing,retargeted_assist_variations_passing=len(variations),new_direct_passing=len(answers)-prefix_passing-len(variations),novel_encounter_day_schedules=novel,selected=len(selected),by_sequence=dict(Counter(r['sequence'] for q,r in selected)),by_launch_year=dict(sorted(Counter(q['launch_date'][:4] for q,r in selected).items())),limits=dict(max_flight_years=10,max_arrival_vinf_kms=15,max_unpowered_mismatch_mps=1,earth_altitude_km=200,venus_altitude_km=300,max_single_dsm_kms=.7,max_total_dsm_kms=1),note='Solar Lambert coasts with asymptotic unpowered flyby screens. Not finite-radius/n-body validation. Source cruise prefixes are recomputed, not original discoveries. New direct opportunities are a finite grid, not a global optimum.')
    atomic_json(a.output/'report.json',report);print(json.dumps(report,indent=2),flush=True)
    if a.publish:
        publish_saved(a.output)

if __name__=='__main__':main()
