"""Opt-out trajectory sharing: fixed science fields only, no user identifiers."""
import bootstrap
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,math,os,queue,threading,time,urllib.parse,urllib.request
import numpy as np
from app_paths import DATA_ROOT,RESOURCE_ROOT,APP_VERSION
from ephemeris import BODIES,atomic_json
from network import tls_context

MAX_BYTES=512000
SETTINGS=DATA_ROOT/'community_settings.json'


def encounter_key(record):
    """Same ordered bodies on the same TDB calendar days share one public slot.

    Sub-day optimization controls remain in the winning record, not its identity.
    Julian days start at noon, hence +0.5 before taking the calendar-day floor.
    """
    ids=record['body_ids'];dates=record['dates_jd_tdb']
    if len(ids)!=len(dates) or not all(math.isfinite(v) for v in dates):
        raise ValueError('Invalid encounter dates')
    return '/'.join(map(str,ids))+'@'+'/'.join(str(math.floor(v+.5)) for v in dates)


def record_rank(record):
    """Deterministic representative selection, independent of solver parameters.

    Submitted pass precedes yellow. Within a class use the documented balanced
    cost C3/100 + cruise delta-v + arrival V-infinity/20 + flight-years/100.
    This picks a representative; relative quality ratings are computed separately.
    """
    m=record['metrics'];dates=record['dates_jd_tdb']
    score=(m['launch_c3_km2_s2']/100+m['total_dsm_kms']+
           m['arrival_vinf_kms']/20+(dates[-1]-dates[0])/365.25/100)
    return (0 if record['classification']=='pass' else 1,score,record.get('id',''))


def unique_encounters(records):
    """Choose one record per date string, retaining aliases for old deep links."""
    winners={};aliases={}
    for record in records:
        key=encounter_key(record);prior=winners.get(key)
        if prior is None or record_rank(record)<record_rank(prior):winners[key]=record
    for record in records:
        winner=winners[encounter_key(record)]
        if record.get('id') and record['id']!=winner.get('id'):aliases[record['id']]=winner['id']
    return list(winners.values()),aliases



def endpoint_url(value):
    value=str(value or '').strip().rstrip('/')
    if not value:return ''
    p=urllib.parse.urlparse(value)
    local=p.hostname in ('localhost','127.0.0.1','::1')
    if (p.scheme!='https' and not(p.scheme=='http' and local)) or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError('Use an HTTPS community API URL (HTTP is allowed only for local testing)')
    return value


def settings():
    try:base=json.loads((RESOURCE_ROOT/'community_config.json').read_text())
    except (OSError,ValueError):base={}
    try:saved=json.loads(SETTINGS.read_text(encoding='utf-8'))
    except (OSError,ValueError):saved={}
    endpoint=endpoint_url(os.environ.get('ROLAMGAS_COMMUNITY_URL',(saved.get('endpoint') or base.get('endpoint',''))))
    return dict(share_candidates=saved.get('share_candidates',True) is True,
                use_candidates=saved.get('use_candidates',True) is True,endpoint=endpoint,
                configured=bool(endpoint))


def save_settings(value):
    if set(value)-{'share_candidates','use_candidates','endpoint'}:raise ValueError('Unknown community setting')
    current=settings()
    for key in ('share_candidates','use_candidates'):
        if key in value:
            if not isinstance(value[key],bool):raise ValueError('Community choices must be boolean')
            current[key]=value[key]
    if 'endpoint' in value:current['endpoint']=endpoint_url(value['endpoint'])
    current.pop('configured',None);atomic_json(SETTINGS,current)
    return settings()


def body_ids(config,route):
    from append_flyby import original_target_descriptors
    objects={d['name']:str(d['id']) for d in original_target_descriptors(config)}
    return [str(BODIES[b][0]) if b in BODIES else objects.get(b,'') for b in route['bodies']]


def quality(q,c):
    from candidate_status import red_reason
    if red_reason(q,c):return 'red'
    return 'pass' if q.get('status','').startswith('passes') else 'yellow'


def public_record(q,c,route):
    """Never serialize a request, candidate wholesale, paths, names or run IDs."""
    from dynamics import supported_launch_energy
    if not supported_launch_energy(q.get('launch_c3_km2_s2')):return None
    classification=quality(q,c)
    if classification=='red':return None
    ids=body_ids(c,route)
    if not all(ids):return None
    n=len(route['bodies']);controls=[]
    for j,leg in enumerate(route.get('dsm_legs',[])):
        k=n+4*j;x=q['x']
        controls.append(dict(leg_index=leg,fraction=.1+.8*x[k],departure_offset_kms=((np.asarray(x[k+1:k+4])*2-1)*c['dsm_velocity_box_kms']).tolist()))
    record=dict(schema_version=1,engine_version=APP_VERSION,sequence=route['id'],body_ids=ids,
                dates_jd_tdb=list(q['dates_jd_tdb']),branches=q['branches'],dsm_controls=controls,
                classification=classification,solved_at=datetime.fromtimestamp(q.get('discovered_unix',time.time()),timezone.utc).isoformat(),
                metrics={k:float(q[k]) for k in ('launch_c3_km2_s2','total_dsm_kms','arrival_vinf_kms','duration_years','max_vinf_mismatch_mps')},
                segments=[{k:s[k] for k in ('start_jd','end_jd','r','v')} for s in q['segments']])
    # Identity is trajectory-based, never a device/install/account fingerprint.
    key={k:record[k] for k in ('sequence','body_ids','dates_jd_tdb','branches','dsm_controls')}
    record['id']=hashlib.sha256(json.dumps(key,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return record


def exchange(url,payload=None):
    parsed=urllib.parse.urlparse(url)
    endpoint_url(urllib.parse.urlunparse(parsed._replace(query='',fragment='')))
    data=json.dumps(payload,separators=(',',':'),allow_nan=False).encode() if payload is not None else None
    if data is not None and len(data)>MAX_BYTES:raise ValueError('Community batch too large')
    request=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json','User-Agent':'RoLaMGAS-community/1'})
    context=tls_context() if url.startswith('https:') else None
    with urllib.request.urlopen(request,timeout=6,context=context) as response:
        raw=response.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError('Community response too large')
    return json.loads(raw)


def record_variables(record,model):
    if record.get('schema_version')!=1 or record.get('sequence')!=model.route['id']:raise ValueError('Unsupported shared trajectory')
    if record.get('body_ids')!=body_ids(model.config,model.route) or model.extension:raise ValueError('Shared target identities differ')
    dates=np.asarray(record['dates_jd_tdb'],float);n=model.n
    if dates.shape!=(n,) or not np.isfinite(dates).all() or np.any(np.diff(dates)<=0):raise ValueError('Invalid shared dates')
    x=np.full(model.dimension,.5)
    def control(value,a,b):
        if b==a:
            if abs(value-a)>1e-7:raise ValueError('Shared epoch outside fixed window')
            return .5
        z=(value-a)/(b-a)
        if not -1e-10<=z<=1+1e-10:raise ValueError('Shared epoch outside current date bounds')
        return float(np.clip(z,0,1))
    if model.config.get('event_windows_jd'):
        for i,(a,b) in enumerate(model.config['event_windows_jd']):x[i]=control(dates[i],a,b)
    else:
        x[0]=control(dates[0],*model.config['launch_jd'])
        for i,(a,b) in enumerate(model.route['leg_days'],1):
            x[i]=control(dates[i],*model.config['arrival_window_jd']) if i==n-1 and model.config.get('arrival_window_jd') else control(dates[i]-dates[i-1],a,b)
    controls=record['dsm_controls']
    if [v['leg_index'] for v in controls]!=model.dsm_legs:raise ValueError('Shared DSM legs differ')
    for j,v in enumerate(controls):
        k=n+4*j;x[k]=(float(v['fraction'])-.1)/.8
        offset=np.asarray(v['departure_offset_kms'],float)
        if offset.shape!=(3,):raise ValueError('Invalid shared burn controls')
        x[k+1:k+4]=.5+offset/(2*model.config['dsm_velocity_box_kms'])
    if not np.isfinite(x).all() or np.any((x<0)|(x>1)):raise ValueError('Shared controls exceed current parameter bounds')
    branches=record['branches'];canonical=lambda b:tuple(b[:2])+(bool(b[2]) if len(b)>2 else True,)
    if len(branches)!=n-1 or any(canonical(b) not in [canonical(v) for v in options] for b,options in zip(branches,model.route['branch_options'])):raise ValueError('Shared Lambert branch unavailable')
    return x,branches


def download_candidates(c,routes,ep,stop_file=None):
    from dynamics import Model
    pref=settings();accepted=[];near=[]
    info=dict(online_status='disabled' if not pref['use_candidates'] else 'not_configured',downloaded_records=0)
    if not pref['use_candidates'] or c.get('append_flyby'):return dict(accepted=accepted,near_misses=near,**info)
    records=[]
    if pref['endpoint']:
        target=str((c.get('target_object') or {}).get('id') or BODIES[c['target']][0])
        params=dict(target=target,min_c3=c['effective_min_c3'],max_c3=c['max_c3'],launch_start=c['launch_jd'][0],launch_end=c['launch_jd'][1],max_arrival_vinf=c['max_arrival_vinf_kms'],max_years=c['max_years'],limit=100)
        cursors=set()
        try:
            while True:
                if stop_file and Path(stop_file).exists():raise InterruptedError('Stopped while checking shared database')
                result=exchange(pref['endpoint']+'/v1/candidates?'+urllib.parse.urlencode(params))
                page=result.get('candidates',[])
                if not isinstance(page,list):raise ValueError('Invalid database response')
                records.extend(dict(record,seed_source='online') for record in page)
                cursor=result.get('next_cursor')
                if not cursor:break
                if cursor in cursors or len(cursors)>=1000:raise ValueError('Invalid database pagination')
                cursors.add(cursor);params['cursor']=cursor
            info.update(online_status='available',downloaded_records=len(records))
        except InterruptedError:raise
        except Exception as exc:
            info.update(online_status='unavailable',downloaded_records=len(records))
            print(f'Community database unavailable; continuing from bundled/local data ({type(exc).__name__}).',flush=True)
    try:bundled=json.loads((RESOURCE_ROOT/'community_seed_catalog.json').read_text(encoding='utf-8')).get('candidates',[])
    except (OSError,ValueError):bundled=[]
    records.extend(dict(record,seed_source='bundled') for record in bundled)
    models={r['id']:Model(r,c,ep) for r in routes};seen=set();slots={}
    for record in records:
        if stop_file and Path(stop_file).exists():raise InterruptedError('Stopped while verifying database matches')
        try:
            if record.get('id') in seen:continue
            model=models.get(record.get('sequence'))
            if model is None:continue
            x,branches=record_variables(record,model)
            q=model.evaluate(x,branches)
            q.update(status='passes_configured_patched_conic_screen' if model.accepted(q) else 'near_miss_not_accepted',
                     screening_residual_norm=float(np.linalg.norm(model.residual(x,branches))),discovered_unix=time.time(),
                     community_source=dict(id=record.get('id'),library=record.get('seed_source'),revalidated=True,submitted_classification=record.get('classification')))
            if quality(q,c)=='red':continue
            key=encounter_key(record)
            rank=record_rank(dict(metrics=q,dates_jd_tdb=q['dates_jd_tdb'],classification=quality(q,c),id=record.get('id','')))
            if key not in slots or rank<slots[key][0]:slots[key]=(rank,q,model.accepted(q))
            seen.add(record.get('id'))
        except (ValueError,KeyError,TypeError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError):continue
    accepted=[q for rank,q,passes in slots.values() if passes];near=[q for rank,q,passes in slots.values() if not passes]
    if accepted or near:print(f'Bundled/community library: {len(accepted)} passing and {len(near)} yellow candidates revalidated locally.',flush=True)
    return dict(accepted=accepted,near_misses=near,**info)


class CommunitySync:
    """Bounded background uploads cannot stall numerical workers or finalization."""
    def __init__(self,c,routes):
        self.c=c;self.routes={r['id']:r for r in routes};self.queue=queue.Queue(maxsize=1000);self.seen={};self.stop=threading.Event();self.last_error=0.
        self.thread=threading.Thread(target=self._work,daemon=True);self.thread.start()
    def offer(self,q):
        if q.get('reused_from') or q.get('community_source') or q.get('launch_c3_km2_s2',0)>250:return
        pref=settings()
        if not pref['share_candidates'] or not pref['endpoint']:return
        try:
            record=public_record(q,self.c,self.routes[q['sequence']])
            if record is None:return
            key=encounter_key(record);rank=record_rank(record)
            if key in self.seen and self.seen[key]<=rank:return
            target=int(record['body_ids'][-1]);years=(record['dates_jd_tdb'][-1]-record['dates_jd_tdb'][0])/365.25
            if (target==999 or target>=1000) and years>=60:return
            self.queue.put_nowait(record);self.seen[key]=rank
        except (ValueError,KeyError,TypeError,queue.Full):pass
    def _work(self):
        while not self.stop.is_set() or not self.queue.empty():
            try:first=self.queue.get(timeout=.3)
            except queue.Empty:continue
            batch=[first]
            while len(batch)<10:
                try:batch.append(self.queue.get_nowait())
                except queue.Empty:break
            batch,_=unique_encounters(batch)
            pref=settings()
            if not pref['share_candidates'] or not pref['endpoint']:continue
            try:exchange(pref['endpoint']+'/v1/candidates',dict(candidates=batch))
            except Exception as exc:
                if time.monotonic()-self.last_error>60:
                    print(f'Community upload unavailable ({type(exc).__name__}); local search continues.',flush=True);self.last_error=time.monotonic()
    def close(self):
        self.stop.set();self.thread.join(timeout=1.)
