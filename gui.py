"""Local browser GUI for the standalone trajectory explorer. Bound to loopback only."""
import bootstrap  # noqa: F401
from pathlib import Path
from datetime import datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import argparse
import hashlib
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from ephemeris import BODIES,atomic_json
from horizons_targets import resolve,register_target
from community import settings as community_settings,save_settings as save_community_settings
from mission_search import DEFAULT_MIN_C3,HERE,load_database,normalize,routes_for,get_ephemerides
from dynamics import HARD_MIN_C3,supported_launch_energy
from app_paths import APP_VERSION,RESOURCE_ROOT,ensure_data,worker_command,worker_environment


def read_json(path,default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (FileNotFoundError,json.JSONDecodeError):
        return default


class App:
    def __init__(self):
        ensure_data()
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.lookup_lock = threading.Lock()
        self.render_lock = threading.Lock()
        self.render_event = threading.Event()
        self.render_stop = threading.Event()
        self.render_thread = None
        self.render_runs = {}
        self.render_priority = None
        self.render_ephemerides = {}
        self.render_revision = {}
        self.render_metadata = {}
        self.active = None
        self.process = None
        self.building = set()
        self.archive_errors = {}
        self.integrations = {}
        self.targets_path = HERE/'resolved_targets.json'
        self.targets = read_json(self.targets_path,{})
        self.cache = HERE/'cache'
        (HERE/'runs').mkdir(exist_ok=True)

    def folder(self,name):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',name):
            raise ValueError('Invalid run identifier')
        return HERE/'runs'/name

    def name_candidate(self,name,identifier,label):
        """Persist a local display alias without modifying science or public uploads."""
        if not re.fullmatch(r'[a-f0-9]{12}',identifier):raise ValueError('Invalid candidate ID')
        if not isinstance(label,str) or len(label)>100 or any(ord(c)<32 or ord(c)==127 for c in label):
            raise ValueError('Use a mission name of at most 100 characters, without control characters')
        root=self.folder(name)
        if not (root/'candidates'/(identifier+'.json')).is_file():raise ValueError('Candidate not found')
        with self.lock:
            path=root/'candidate_names.json';names=read_json(path,{})
            label=label.strip()
            if label:names[identifier]=label
            else:names.pop(identifier,None)
            atomic_json(path,names)
        return dict(candidate=identifier,name=label,names=names)

    def catalog(self):
        rows = []
        for p in sorted((HERE/'runs').iterdir(),key=lambda p:p.stat().st_mtime,reverse=True):
            if not p.is_dir() or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p.name):
                continue
            request = read_json(p/'request.json') or read_json(p/'run_manifest.json',{}).get('config',{})
            if not request:
                continue
            status = read_json(p/'gui_status.json',{})
            rows.append(dict(id=p.name,target=request.get('target_object',{}).get('name') if request.get('target_object') else request.get('target','Unknown'),
                             state=status.get('state','finished' if (p/'results.json').exists() else 'unknown')))
        return rows

    def launch_performance(self,c3):
        from launch_performance import capacity_query
        return capacity_query(c3,self.cache/'launch_performance')

    def cache_status(self):
        baseline = read_json(self.cache/'baseline_manifest.json',{})
        rows = []
        for body in BODIES:
            entries = [read_json(p,{}) for p in self.cache.glob(body+'_*.json')]
            rows.append(dict(body=body,tables=len(entries),
                             start_jd=min((m['start_jd'] for m in entries),default=None),
                             end_jd=max((m['end_jd'] for m in entries),default=None),
                             minimum_step_days=min((m['max_step_days'] for m in entries),default=None)))
        return dict(planets=rows,baseline=baseline,folder=str(self.cache),
                    bytes=sum(p.stat().st_size for p in self.cache.iterdir() if p.is_file()) if self.cache.exists() else 0)

    def bootstrap(self):
        db = load_database()
        presets = []
        for p in (RESOURCE_ROOT/'examples').glob('*.json'):
            c = read_json(p,{})
            presets.append(dict(id=p.stem,target=c.get('target'),name=p.stem.replace('_',' ').title()))
        return dict(version=APP_VERSION,community=community_settings(),minimum_c3_floor=HARD_MIN_C3,token=self.token,planets=[p for p in BODIES if p!='Earth'],
                    routes=[dict(id=r['id'],target=r['target'],bodies=r['bodies'],dsm_legs=r['dsm_legs']) for r in db['sequences']],
                    custom_routes=['EX','EdvEX','EVX','EVEX','EVEEX','EJX','EdvEJX','EVEEJX','ESX','EJSX'],
                    presets=presets,runs=self.catalog(),cpu_count=os.cpu_count() or 2,active=self.active)

    def lookup(self,query,epoch,refresh=False):
        key = query.strip().casefold()
        with self.lookup_lock:
            if not refresh and key in self.targets:
                return dict(self.targets[key],cached_lookup=True)
            if self.active and read_json(self.folder(self.active)/'gui_status.json',{}).get('state')=='preparing':
                raise ValueError('Ephemerides are downloading. Resolve another target after preparation completes.')
            result = resolve(query,epoch)
            if not result.get('ambiguous'):
                self.targets[key] = result
                atomic_json(self.targets_path,self.targets)
            return result

    def export_search_options(self,config=None,run=None):
        from search_options import export_options
        if (config is None)==(run is None):
            raise ValueError('Export either the current config or one saved run')
        if run is not None:
            root=self.folder(run)
            config=read_json(root/'request.json') or read_json(root/'run_manifest.json',{}).get('config')
            if not config:raise ValueError('Saved search settings not found')
        return export_options(config)

    def import_search_options(self,document):
        from search_options import import_options
        result=import_options(document)
        obj=result['config'].get('target_object')
        if obj:
            confirmed=next((d for d in self.targets.values() if str(d['id'])==str(obj['id']) and d['name']==obj['name']),None)
            result['requires_target_resolution']=confirmed is None
            # Never treat a descriptor in an imported file as a trusted local one.
            if confirmed:
                result['config']['target_object']=dict(confirmed)
                result['notes']=[n for n in result['notes'] if not n.startswith('Confirm this Horizons target')]
                result['notes'].append('This target matches a resolved identity already cached by this client; no network lookup was made.')
        result['has_trajectory']=bool(document.get('trajectory'))
        return result

    def import_website_candidate(self,document):
        """Load one selected solution; this path never starts random optimization."""
        from search_options import import_options
        from trajectory_transfer import checked_record,pin_record_epochs
        parsed=import_options(document);record=checked_record(document.get('trajectory'))
        label=document.get('display_name','')
        if not isinstance(label,str) or len(label)>100 or any(ord(v)<32 for v in label):raise ValueError('Invalid imported display name')
        name='import_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+secrets.token_hex(3)
        output=self.folder(name);output.mkdir()
        source=str(document.get('source_candidate_id',''))[:100]
        def status(state,message,**extra):atomic_json(output/'gui_status.json',dict(state=state,message=message,**extra))
        status('preparing','Loading selected website trajectory. Using local JPL data or downloading missing coverage; no search is running.')
        atomic_json(output/'imported_record.json',record)
        config=pin_record_epochs(parsed['config'],record);config['cache']=str(self.cache);atomic_json(output/'request.json',config)
        def load():
            try:
                from mission_search import prepare
                from live_gallery import LiveGallery
                from trajectory_transfer import materialize
                obj=config.get('target_object')
                if obj:
                    confirmed=self.lookup('SPK='+str(obj['id']),config['launch_start'])
                    if confirmed.get('ambiguous') or str(confirmed.get('id'))!=str(record['body_ids'][-1]):raise ValueError('JPL target identity does not match the imported candidate')
                    from horizons_targets import target_for_epoch,moon_model_notice
                    notice=moon_model_notice(confirmed)
                    if notice:raise ValueError(notice)
                    confirmed=target_for_epoch(confirmed,record['dates_jd_tdb'][0])
                    config['target_object']=confirmed;config['target']=confirmed['name']
                c=normalize(config,HERE);routes=routes_for(c)
                if len(routes)!=1:raise ValueError('Selected-candidate import requires exactly one sequence')
                atomic_json(output/'request.json',c)
                atomic_json(output/'run_manifest.json',dict(config=c,routes=routes,source='Website selected-candidate import'))
                prepare(c,routes);ep=get_ephemerides(c,routes)
                q=materialize(record,c,routes[0],ep);q['source_candidate_id']=source
                accepted=q['status'].startswith('passes')
                summary=dict(candidates=[q] if accepted else [],near_misses=[] if accepted else [q],distinct_accepted=int(accepted),raw_accepted=int(accepted),completed_jobs=0,model='Saved website trajectory, recomputed with local JPL ephemerides',nbody_validated=False)
                atomic_json(output/'results.json',summary)
                LiveGallery(output,None,deferred=True,config=c).update(summary,dict(state='finished',completed_jobs=0,total_jobs=0),final=True)
                if label:self.name_candidate(name,q['id'],label)
                status('finished','Selected trajectory loaded and rechecked. No optimization was performed. Use Integrate & export for finite-radius planetary flybys.',candidate_id=q['id'])
                self._register_render_run(name)
            except Exception as exc:status('failed','Could not reproduce the selected candidate: '+str(exc))
        threading.Thread(target=load,daemon=True,name='website-candidate-import').start()
        return dict(run=name,optimization_performed=False)

    def confirmed_source_config(self,config,bodies):
        from copy import deepcopy
        from append_flyby import original_target_descriptors
        from horizons_targets import moon_model_notice
        descriptors=original_target_descriptors(config)
        minor={b for b in bodies if b not in BODIES}
        if not minor.issubset({d['name'] for d in descriptors}):
            raise ValueError('This candidate needs its original resolved Horizons target identities before adding a follow-on leg')
        confirmed={}
        for descriptor in descriptors:
            cached=next((d for d in self.targets.values() if str(d['id'])==str(descriptor['id']) and d['name']==descriptor['name']),None)
            if cached is None:
                raise ValueError('Resolve and confirm the original Horizons target before starting this follow-on search')
            notice=moon_model_notice(cached)
            if notice:raise ValueError(notice)
            confirmed[cached['name']]=dict(cached)
            register_target(cached)
        clean=deepcopy(config)
        if clean.get('target_object'):
            clean['target_object']=confirmed[clean['target_object']['name']]
        if clean.get('append_flyby'):
            extension=clean['append_flyby']
            extension['original_target_objects']=[confirmed[name] for name in sorted(minor)]
            old=extension.get('original_target_object')
            if old:extension['original_target_object']=confirmed[old['name']]
        return clean

    def start(self,request,recover_from=None):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                status=read_json(self.folder(self.active)/'gui_status.json',{})
                if status.get('state') in ('finished','failed','stopped'):
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        raise ValueError('The previous search is finishing cleanup. Try again shortly.')
                else:
                    raise ValueError('A search is already running. Stop it before starting another.')
            request = dict(request)
            request['cache'] = str(self.cache)
            obj = request.get('target_object')
            if obj:
                confirmed = next((d for d in self.targets.values() if str(d['id'])==str(obj.get('id')) and d['name']==obj.get('name')),None)
                if not confirmed:
                    raise ValueError('Resolve and confirm this Horizons target first')
                request['target_object'] = confirmed
            extension=request.get('append_flyby')
            if extension:
                request=self.confirmed_source_config(request,extension.get('prefix',{}).get('bodies',[]))
            c = normalize(request,HERE)
            routes_for(c)
            name = datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+secrets.token_hex(3)
            output = self.folder(name)
            output.mkdir()
            atomic_json(output/'request.json',request)
            atomic_json(output/'gui_status.json',dict(state='starting',message='Starting local search process.'))
            log = (output/'console.log').open('w',encoding='utf-8')
            try:
                flags = subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
                arguments=worker_command('gui_worker','--output',output)
                if recover_from:
                    arguments+=['--recover-from',str(self.folder(recover_from))]
                self.process = subprocess.Popen(arguments,
                                                cwd=HERE,stdout=log,stderr=subprocess.STDOUT,creationflags=flags,env=worker_environment(output/'console.log'))
            finally:
                log.close()
            self.active = name
            return dict(run=name)

    def recover(self,name):
        root=self.folder(name)
        request=read_json(root/'request.json')
        if not request or not (root/'run_manifest.json').exists():
            raise ValueError('No recoverable request/checkpoints for this run')
        return self.start(request,recover_from=name)

    def share_candidate(self,name,identifier,confirmed=False):
        """Explicit user action, including for imports which bypass search uploads."""
        if confirmed is not True:raise ValueError('Confirm public sharing of this trajectory first')
        if not re.fullmatch(r'[a-f0-9]{12}',identifier):raise ValueError('Invalid candidate ID')
        from community import settings,public_record,exchange
        from trajectory_transfer import materialize
        pref=settings()
        if not pref['share_candidates'] or not pref['endpoint']:raise ValueError('Enable community sharing in Settings first')
        root=self.folder(name);q=read_json(root/'candidates'/(identifier+'.json'))
        if not q:raise ValueError('Candidate not found')
        manifest=read_json(root/'run_manifest.json',{})
        c=normalize(manifest.get('config') or read_json(root/'request.json'),HERE)
        route=next(r for r in routes_for(c) if r['id']==q['sequence'])
        record=public_record(q,c,route)
        if record is None:raise ValueError('Only eligible pass/yellow candidates can be shared')
        # Recompute the stored solution before publishing any science vectors.
        verified=materialize(record,c,route,get_ephemerides(c,[route]))
        record=public_record(verified,c,route)
        if record is None:raise ValueError('Rechecked trajectory does not meet public screening rules')
        receipt=exchange(pref['endpoint']+'/v1/candidates',dict(candidates=[record]))
        if record['id'] not in receipt.get('ids',[]):raise ValueError('No matching server receipt; please retry')
        result=dict(record_id=record['id'],message='Submitted to the community library. Same-day duplicates keep the preferred representative.')
        atomic_json(root/'community_upload.json',result)
        return result

    def refine_candidate(self,name,identifier,days=30.,objective=None,prefer_outbound_encounters=None):
        from candidate_refinement import neighborhood_request
        if not re.fullmatch(r'[a-f0-9]{12}',identifier):raise ValueError('Invalid candidate ID')
        root=self.folder(name)
        candidate=read_json(root/'candidates'/(identifier+'.json'))
        if not candidate:raise ValueError('Candidate not found')
        manifest=read_json(root/'run_manifest.json',{})
        config=manifest.get('config') or normalize(read_json(root/'request.json'),HERE)
        route=next((r for r in manifest.get('routes',[]) if r['id']==candidate['sequence']),None)
        if route is None:route=next(r for r in routes_for(normalize(config,HERE)) if r['id']==candidate['sequence'])
        config=dict(config)
        if objective is not None:config['search_objective']=objective
        if prefer_outbound_encounters is not None:config['prefer_outbound_encounters']=prefer_outbound_encounters
        config=normalize(config,HERE)
        request=neighborhood_request(config,route,candidate,name,days)
        return self.start(request)

    def append_candidate(self,name,identifier,body=None,count=1,minimum_days=80.,maximum_days=750.,dsm=False,target_object=None):
        from append_flyby import extension_request
        if not re.fullmatch(r'[a-f0-9]{12}',identifier):raise ValueError('Invalid candidate ID')
        root=self.folder(name);candidate=read_json(root/'candidates'/(identifier+'.json'))
        if not candidate:raise ValueError('Candidate not found')
        manifest=read_json(root/'run_manifest.json',{})
        config=manifest.get('config') or normalize(read_json(root/'request.json'),HERE)
        route=next((r for r in manifest.get('routes',[]) if r['id']==candidate['sequence']),None)
        if route is None:route=next(r for r in routes_for(normalize(config,HERE)) if r['id']==candidate['sequence'])
        config=self.confirmed_source_config(config,candidate['bodies'])
        if target_object is not None:
            if not isinstance(target_object,dict):raise ValueError('Resolve and confirm the follow-on Horizons target first')
            confirmed=next((d for d in self.targets.values() if str(d['id'])==str(target_object.get('id')) and d['name']==target_object.get('name')),None)
            if confirmed is None:raise ValueError('Resolve and confirm the follow-on Horizons target first')
            return self.start(extension_request(config,route,candidate,name,body,count,minimum_days,maximum_days,dsm,target_object=dict(confirmed)))
        return self.start(extension_request(config,route,candidate,name,body,count,minimum_days,maximum_days,dsm))

    def return_to_earth(self,name,identifier,minimum_days=80.,maximum_days=750.,dsm=False):
        return self.append_candidate(name,identifier,body='Earth',count=1,
            minimum_days=minimum_days,maximum_days=maximum_days,dsm=dsm)

    def stop(self,name):
        with self.lock:
            if name!=self.active or self.process is None or self.process.poll() is not None:
                raise ValueError('This run is not active')
            (self.folder(name)/'stop.request').write_text('Stop requested by GUI\n',encoding='utf-8')
            return dict(stopping=True)

    def database_decision(self,name,run_local):
        if not isinstance(run_local,bool):raise ValueError('Choose whether to run the local search')
        with self.lock:
            if name!=self.active or self.process is None or self.process.poll() is not None:raise ValueError('This run is not awaiting a decision')
            root=self.folder(name)
            if read_json(root/'gui_status.json',{}).get('state')!='awaiting_database_decision':raise ValueError('This run is not awaiting a database decision')
            atomic_json(root/'database_decision.json',dict(run_local=run_local))
        return dict(run=name,run_local=run_local)

    def snapshot(self,name):
        output = self.folder(name)
        if not output.exists():
            raise ValueError('Run not found')
        status = read_json(output/'gui_status.json',{})
        error=read_json(output/'run_error.json')
        if error:
            status=dict(status,state='failed',message=error['type']+': '+error['message'])
        if name==self.active and self.process is not None and self.process.poll() is not None and status.get('state') in ('starting','preparing','checking_database','awaiting_database_decision','running'):
            status = dict(state='failed',message=f'Search process exited ({self.process.returncode}). See console log.')
            atomic_json(output/'gui_status.json',status)
        live = read_json(output/'live.json')
        if live is None and (output/'results.json').exists():
            with self.lock:
                if name not in self.building and name not in self.archive_errors:
                    self.building.add(name)
                    threading.Thread(target=self.build_archive,args=(name,),daemon=True).start()
            status = status or dict(state='loading',message='Preparing saved trajectory images…')
        if name in self.archive_errors:
            status = dict(state='failed',message=self.archive_errors[name])
        logs = ''
        if (output/'console.log').exists():
            with (output/'console.log').open('rb') as stream:
                stream.seek(max(0,(output/'console.log').stat().st_size-12000))
                logs = stream.read().decode('utf-8',errors='replace')
        request=read_json(output/'request.json') or read_json(output/'run_manifest.json',{}).get('config',{})
        if live and live.get('candidates'):
            from live_gallery import plot_status
            # Older live.json files predate the hard launch-energy gate. Do not
            # hydrate or queue plots for those obsolete low-energy diagnostics.
            eligible=[q for q in live['candidates'] if supported_launch_energy(q.get('launch_c3_km2_s2'))]
            hydrated=[self._hydrate_render_row(name,q,request) for q in eligible]
            self._register_render_run(name)
            live=dict(live,revision=max(float(live.get('revision',0)),self.render_revision.get(name,0)),
                      distinct_accepted=max(0,live.get('distinct_accepted',0)-sum(q.get('status','').startswith('passes') for q in live['candidates'])+sum(q.get('status','').startswith('passes') for q in eligible)),
                      excluded_below_hard_c3_floor=len(live['candidates'])-len(eligible),
                      candidates=[dict(q,**plot_status(output/'candidates',q,request)) for q in hydrated])
        limits={k:request.get(k) for k in ('target','target_object','min_c3','max_c3','arrival_date','arrival_tolerance_days','max_dsm_kms','max_single_dsm_kms','max_powered_flyby_kms','max_arrival_vinf_kms','vinf_tolerance_mps','max_years','search_objective','prefer_outbound_encounters')}
        limits['effective_min_c3']=max(float(request.get('min_c3') if request.get('min_c3') is not None else DEFAULT_MIN_C3),HARD_MIN_C3)
        return dict(run=name,status=status or dict(state='finished'),live=live,log=logs,candidate_names=read_json(output/'candidate_names.json',{}),
                    heartbeat=read_json(output/'heartbeat.json'),database=read_json(output/'database_first.json',{}),
                    limits=limits,
                    active=name==self.active and self.process is not None and self.process.poll() is None)

    def _hydrate_render_row(self,name,row,config):
        from candidate_status import unresolved_mismatch_sum,unresolved_mismatch_peak,modeled_plus_unresolved_mismatch
        q=row
        if not isinstance(row.get('total_unresolved_vinf_mismatch_mps'),(int,float)):
            path=self.folder(name)/'candidates'/(row['id']+'.json')
            try:stamp=path.stat().st_mtime_ns
            except OSError:stamp=None
            cache=getattr(self,'render_metadata',None)
            if cache is None:self.render_metadata=cache={}
            key=(name,row['id']);saved=cache.get(key)
            if saved is None or saved[0]!=stamp:
                full=read_json(path) or row
                fields=dict(total_unresolved_vinf_mismatch_mps=unresolved_mismatch_sum(full),
                            max_unresolved_vinf_mismatch_mps=unresolved_mismatch_peak(full),
                            modeled_plus_unresolved_mismatch_kms=modeled_plus_unresolved_mismatch(full))
                cache[key]=(stamp,fields)
                if len(cache)>10000:cache.pop(next(iter(cache)))
            else:fields=saved[1]
            q=dict(row,**fields)
        total=modeled_plus_unresolved_mismatch(q)
        return dict(q,modeled_plus_unresolved_mismatch_kms=total,
                    mismatch_screening_budget_exceeded=unresolved_mismatch_sum(q)>1e-6 and config.get('max_dsm_kms') is not None and total>config['max_dsm_kms']+1e-9)

    def _register_render_run(self,name):
        with self.lock:
            self.render_runs[name]=time.monotonic()
            if self.render_thread is None or not self.render_thread.is_alive():
                self.render_stop.clear()
                self.render_thread=threading.Thread(target=self._render_loop,daemon=True,name='trajectory-previews')
                self.render_thread.start()
            self.render_event.set()

    def render_candidate(self,name,identifier):
        if not re.fullmatch(r'[a-f0-9]{12}',identifier):raise ValueError('Invalid candidate ID')
        root=self.folder(name);q=read_json(root/'candidates'/(identifier+'.json'))
        if not q:raise ValueError('Candidate has not been published yet')
        from live_gallery import LiveGallery,plot_status
        config=read_json(root/'request.json') or read_json(root/'run_manifest.json',{}).get('config',{})
        gallery=LiveGallery(root,None,deferred=True,config=config)
        gallery.placeholder(q,force=True)
        status=plot_status(gallery.folder,q,config)
        if status['render_skipped']:
            state,message='skipped','Plot skipped for red diagnostic. Its science data and export options remain available.'
        elif status['image_ready']:
            state,message='ready','Trajectory preview is ready.'
        elif status['render_error']:
            state,message='failed',status['render_error']
        else:
            with self.lock:self.render_priority=(name,identifier,time.monotonic_ns())
            self._register_render_run(name)
            state,message='queued','Selected trajectory has priority over background previews. Numerical optimization continues.'
        return dict(state=state,message=message,card_url='/files/'+urllib.parse.quote(name)+'/candidates/'+identifier+'.card.json')

    def _next_render_task(self):
        from live_gallery import plot_status
        with self.lock:
            priority=self.render_priority
            names=sorted(self.render_runs,key=self.render_runs.get,reverse=True)
        if priority:
            name,identifier,_=priority;root=self.folder(name)
            q=read_json(root/'candidates'/(identifier+'.json'))
            config=read_json(root/'request.json') or read_json(root/'run_manifest.json',{}).get('config',{})
            if q and supported_launch_energy(q.get('launch_c3_km2_s2')) and plot_status(root/'candidates',q,config)['render_pending']:
                return name,q,config,priority
            with self.lock:
                if self.render_priority==priority:self.render_priority=None
        for name in names:
            root=self.folder(name);live=read_json(root/'live.json',{})
            config=read_json(root/'request.json') or read_json(root/'run_manifest.json',{}).get('config',{})
            for row in live.get('candidates',[]):
                if not supported_launch_energy(row.get('launch_c3_km2_s2')):continue
                row=self._hydrate_render_row(name,row,config)
                if not plot_status(root/'candidates',row,config)['render_pending']:continue
                q=read_json(root/'candidates'/(row['id']+'.json'))
                if q and plot_status(root/'candidates',q,config)['render_pending']:return name,q,config,None
        return None

    def _render_ephemeris(self,name,config):
        if name not in self.render_ephemerides:
            c=normalize(config,HERE)
            if not Path(c['cache']).exists():c['cache']=str(self.cache)
            ep=get_ephemerides(c,routes_for(c))
            if len(self.render_ephemerides)>=3:self.render_ephemerides.pop(next(iter(self.render_ephemerides)))
            self.render_ephemerides[name]=ep
        return self.render_ephemerides[name]

    def _render_loop(self):
        from live_gallery import LiveGallery
        while not self.render_stop.is_set():
            task=self._next_render_task()
            if task is None:
                self.render_event.wait(.25);self.render_event.clear();continue
            name,q,config,priority=task
            def preempted():
                with self.lock:current=self.render_priority
                return self.render_stop.is_set() or (current is not None and current[:2]!=(name,q['id']))
            try:
                if preempted():continue
                ep=self._render_ephemeris(name,config)
                with self.render_lock:
                    result=LiveGallery(self.folder(name),ep,deferred=True,config=config).render(q,cancel=preempted,force=priority is not None)
                if result!='preempted':
                    with self.lock:
                        self.render_revision[name]=time.time()
                        if self.render_priority==priority:self.render_priority=None
            except Exception as exc:
                from ephemeris import atomic_json
                folder=self.folder(name)/'candidates'
                atomic_json(folder/(q['id']+'.plot_error.json'),dict(message=str(exc),candidate_id=q['id']))
                atomic_json(folder/(q['id']+'.card.json'),dict(q,paths=[],planet_paths=[],render_pending=False,render_skipped=None,render_error=str(exc)))
                (folder/(q['id']+'.render_pending.json')).unlink(missing_ok=True)
                with self.lock:
                    self.render_revision[name]=time.time()
                    if self.render_priority==priority:self.render_priority=None

    def close_renderer(self):
        self.render_stop.set();self.render_event.set()
        if self.render_thread is not None:self.render_thread.join(timeout=3)

    def build_archive(self,name):
        try:
            from live_gallery import LiveGallery
            p = self.folder(name)
            c = normalize(read_json(p/'run_manifest.json')['config'],HERE)
            if not Path(c['cache']).exists():
                c['cache'] = str(self.cache)
            results = read_json(p/'results.json')
            LiveGallery(p,None,deferred=True,config=c).update(results,dict(state='finished',completed_jobs=results['completed_jobs'],
                                         total_jobs=results['completed_jobs']),final=True)
            self._register_render_run(name)
        except Exception as exc:
            self.archive_errors[name] = str(exc)
        finally:
            self.building.discard(name)




    def integrate(self,name,identifier,arrival_altitude_km=None,powered_flybys=None,post_flyby_months=0.,arrival_inclination_deg=None,refine_patches=True,patch_epoch_shift_days=2.):
        from integrate_export import validate_post_flyby_months,validate_patch_epoch_shift
        from arrival_geometry import validate_inclination
        arrival_inclination_deg=validate_inclination(arrival_inclination_deg)
        post_flyby_months=validate_post_flyby_months(post_flyby_months)
        patch_epoch_shift_days=validate_patch_epoch_shift(patch_epoch_shift_days)
        if not isinstance(refine_patches,bool):raise ValueError('Patch refinement option must be boolean')
        if powered_flybys is not None and not isinstance(powered_flybys,bool):raise ValueError('Powered flyby option must be boolean')
        if arrival_altitude_km is not None:
            import math
            arrival_altitude_km=float(arrival_altitude_km)
            if not math.isfinite(arrival_altitude_km) or arrival_altitude_km<=0:raise ValueError('Arrival altitude must be positive and finite')
        if not re.fullmatch(r'[a-f0-9]{12}',identifier):
            raise ValueError('Invalid candidate ID')
        root=self.folder(name)
        candidate=root/'candidates'/(identifier+'.json')
        if not candidate.is_file():
            raise ValueError('Candidate not found')
        with self.lock:
            if any(p.poll() is None for p in self.integrations.values()):
                raise ValueError('An integration is already running. Wait for it to finish.')
            output=root/'exports'/identifier
            if (output/'integration_report.json').is_file():
                shutil.copytree(output,root/'export_history'/(identifier+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')))
            output.mkdir(parents=True,exist_ok=True)
            request=read_json(root/'request.json') or read_json(root/'run_manifest.json',{})['config']
            request['cache']=str(self.cache)
            if powered_flybys is not None:request['powered_flybys']=powered_flybys
            config=output/'request.json'
            atomic_json(config,request)
            atomic_json(output/'integration_status.json',dict(state='running',message='Starting finite-radius integration…'))
            flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
            with (output/'integration.log').open('w',encoding='utf-8') as log:
                self.integrations[(name,identifier)]=subprocess.Popen(worker_command('integrate_export',
                       '--candidate',str(candidate),'--config',str(config),'--output',str(output),'--post-flyby-months',str(post_flyby_months),'--refine-patches' if refine_patches else '--no-refine-patches','--patch-epoch-shift-days',str(patch_epoch_shift_days))+(['--arrival-altitude-km',str(arrival_altitude_km)] if arrival_altitude_km is not None else [])+(['--powered-flybys' if powered_flybys else '--no-powered-flybys'] if powered_flybys is not None else [])+(['--arrival-inclination-deg',str(arrival_inclination_deg)] if arrival_inclination_deg is not None else []),
                       cwd=HERE,stdout=log,stderr=subprocess.STDOUT,creationflags=flags,env=worker_environment(output/'integration.log'))
            return dict(started=True)

    def export_status(self,name,identifier):
        if not re.fullmatch(r'[a-f0-9]{12}',identifier):
            raise ValueError('Invalid candidate ID')
        output=self.folder(name)/'exports'/identifier
        status=read_json(output/'integration_status.json',dict(state='none'))
        process=self.integrations.get((name,identifier))
        if status['state']=='running' and process is not None and process.poll() is not None:
            status=dict(state='failed',message='Integration exited unexpectedly. See its integration.log.')
            atomic_json(output/'integration_status.json',status)
        if status['state']=='finished':
            status['report']=read_json(output/'integration_report.json',{})
        return status

    def package(self,name,identifier,model='auto',arrival_altitude_km=None,powered_flybys=None,post_flyby_months=0.,arrival_inclination_deg=None,patch_dwarf_planet=False,dwarf_catalog_path=None,refine_patches=True,patch_epoch_shift_days=2.):
        from integrate_export import validate_post_flyby_months,validate_patch_epoch_shift
        from arrival_geometry import validate_inclination
        arrival_inclination_deg=validate_inclination(arrival_inclination_deg)
        post_flyby_months=validate_post_flyby_months(post_flyby_months)
        patch_epoch_shift_days=validate_patch_epoch_shift(patch_epoch_shift_days)
        if not isinstance(refine_patches,bool):raise ValueError('Patch refinement option must be boolean')
        if model not in ('auto','Panels','RTG'):
            raise ValueError('Invalid model choice')
        status=self.export_status(name,identifier)
        requested_altitude=float(arrival_altitude_km) if arrival_altitude_km is not None else None
        if status['state']=='finished' and (status.get('report',{}).get('arrival_altitude_option_km')!=requested_altitude or
            (powered_flybys is not None and status.get('report',{}).get('powered_flybys_active',False)!=powered_flybys) or
            status.get('report',{}).get('post_flyby_months',0.)!=post_flyby_months or
            status.get('report',{}).get('arrival_inclination_option_deg')!=arrival_inclination_deg or
            status.get('report',{}).get('refine_patches_option',False)!=refine_patches or
            status.get('report',{}).get('patch_epoch_shift_days_option',2.)!=patch_epoch_shift_days):
            self.integrate(name,identifier,arrival_altitude_km,powered_flybys,post_flyby_months,arrival_inclination_deg,refine_patches,patch_epoch_shift_days)
            return dict(state='integrating',message='Updating trajectory export options; the previous export is preserved.')
        if status['state']!='finished':
            if status['state']!='running':
                self.integrate(name,identifier,arrival_altitude_km,powered_flybys,post_flyby_months,arrival_inclination_deg,refine_patches,patch_epoch_shift_days)
            return dict(state='integrating',message='Integrating the trajectory before packaging.')
        from celestia_package import build_package
        root=self.folder(name)
        candidate=read_json(root/'candidates'/(identifier+'.json'))
        config=read_json(root/'request.json') or read_json(root/'run_manifest.json',{})['config']
        return build_package(root/'exports'/identifier,candidate,config,model,patch_dwarf_planet,dwarf_catalog_path)

    def open_package_folder(self,name,identifier):
        if not re.fullmatch(r'[a-f0-9]{12}',identifier):
            raise ValueError('Invalid candidate ID')
        folder=self.folder(name)/'exports'/identifier/'celestia_package'
        if not folder.is_dir():
            raise ValueError('Export a Celestia package first')
        if os.name=='nt':
            os.startfile(str(folder))
        else:
            subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(folder)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return dict(opened=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    @property
    def app(self):
        return self.server.app

    def json(self,value,status=200):
        raw = json.dumps(value,allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        try:
            url = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(url.query)
            if url.path=='/api/ping':
                return self.json(dict(app='trajectory-explorer-gui',version=APP_VERSION,instance_id=self.server.instance_id))
            if url.path=='/api/bootstrap':
                return self.json(self.app.bootstrap())
            if url.path=='/api/cache':
                return self.json(self.app.cache_status())
            if url.path=='/api/runs':
                return self.json(self.app.catalog())
            if url.path=='/api/preset':
                name = params.get('name',[''])[0]
                if not re.fullmatch(r'[A-Za-z0-9_-]+',name):
                    raise ValueError('Invalid preset')
                return self.json(read_json(RESOURCE_ROOT/'examples'/(name+'.json')))
            if url.path=='/api/request':
                root=self.app.folder(params.get('run',[''])[0])
                return self.json(read_json(root/'request.json') or read_json(root/'run_manifest.json',{}).get('config'))
            if url.path=='/api/live':
                return self.json(self.app.snapshot(params.get('run',[''])[0]))
            if url.path=='/api/export-status':
                return self.json(self.app.export_status(params.get('run',[''])[0],params.get('candidate',[''])[0]))
            if url.path.startswith('/files/'):
                parts = urllib.parse.unquote(url.path).split('/',3)
                if len(parts)!=4:
                    raise ValueError('Invalid file path')
                root = self.app.folder(parts[2]).resolve()
                path = (root/parts[3]).resolve()
                if not path.is_relative_to(root) or path.suffix.lower() not in ('.json','.png','.tsv','.html','.md','.log','.csv','.xyzv','.ssc','.txt','.zip'):
                    raise ValueError('File is outside this run')
            elif url.path in ('/gui_assets/launch_mass_c3.png','/gui_assets/rolamgas-icon.png','/gui_assets/launch_performance_curves.json'):
                path=RESOURCE_ROOT/'gui_assets'/url.path.rsplit('/',1)[-1]
            elif url.path in ('/','/gui.html','/gui.js','/mission_metrics.js','/gui.css'):
                path = RESOURCE_ROOT/('gui.html' if url.path=='/' else url.path[1:])
            else:
                self.send_error(404)
                return
            if not path.is_file():
                self.send_error(404)
                return
            raw = path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            self.send_header('Cache-Control','no-cache')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except (ValueError,OSError,KeyError) as exc:
            self.json(dict(error=str(exc)),400)
        except (BrokenPipeError,ConnectionResetError):
            pass

    def do_POST(self):
        try:
            origin = self.headers.get('Origin','')
            allowed = (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}')
            if self.headers.get('X-Explorer-Token')!=self.app.token or (origin and origin not in allowed):
                return self.json(dict(error='Invalid local application session'),403)
            size = int(self.headers.get('Content-Length','0'))
            maximum=1024*1024 if self.path in ('/api/options/export','/api/options/import','/api/trajectory/import') else 200000
            if not 0<size<=maximum:
                raise ValueError('Invalid request size')
            value = json.loads(self.rfile.read(size))
            if self.path=='/api/community-settings':
                return self.json(save_community_settings(value))
            if self.path=='/api/options/export':
                return self.json(self.app.export_search_options(value.get('config'),value.get('run')))
            if self.path=='/api/options/import':
                return self.json(self.app.import_search_options(value.get('document')))
            if self.path=='/api/trajectory/import':
                return self.json(self.app.import_website_candidate(value.get('document')))
            if self.path=='/api/launch-performance':
                return self.json(self.app.launch_performance(value.get('c3')))
            if self.path=='/api/resolve':
                return self.json(self.app.lookup(value['query'],value.get('epoch','2030-01-01'),value.get('refresh',False)))
            if self.path=='/api/start':
                return self.json(self.app.start(value))
            if self.path=='/api/recover':
                return self.json(self.app.recover(value['run']))
            if self.path=='/api/refine':
                return self.json(self.app.refine_candidate(value['run'],value['candidate'],value.get('days',30.),value.get('objective'),value.get('prefer_outbound_encounters')))
            if self.path=='/api/share-candidate':
                return self.json(self.app.share_candidate(value['run'],value['candidate'],value.get('confirmed',False)))
            if self.path=='/api/return-earth':
                return self.json(self.app.return_to_earth(value['run'],value['candidate'],value.get('minimum_days',80.),value.get('maximum_days',750.),value.get('dsm',False)))
            if self.path=='/api/append-flyby':
                return self.json(self.app.append_candidate(value['run'],value['candidate'],value.get('body'),value.get('count',1),
                    value.get('minimum_days',80.),value.get('maximum_days',750.),value.get('dsm',False),value.get('target_object')))
            if self.path=='/api/database-decision':
                return self.json(self.app.database_decision(value['run'],value.get('run_local')))
            if self.path=='/api/stop':
                return self.json(self.app.stop(value['run']))
            if self.path=='/api/name-candidate':
                return self.json(self.app.name_candidate(value['run'],value['candidate'],value.get('name','')))
            if self.path=='/api/render-candidate':
                return self.json(self.app.render_candidate(value['run'],value['candidate']))
            if self.path=='/api/integrate':
                return self.json(self.app.integrate(value['run'],value['candidate'],value.get('arrival_altitude_km'),value.get('powered_flybys'),value.get('post_flyby_months',0.),value.get('arrival_inclination_deg'),value.get('refine_patches',True),value.get('patch_epoch_shift_days',2.)))
            if self.path=='/api/package':
                return self.json(self.app.package(value['run'],value['candidate'],value.get('model','auto'),value.get('arrival_altitude_km'),value.get('powered_flybys'),value.get('post_flyby_months',0.),value.get('arrival_inclination_deg'),value.get('patch_dwarf_planet',False),value.get('dwarf_catalog_path'),value.get('refine_patches',True),value.get('patch_epoch_shift_days',2.)))
            if self.path=='/api/dwarf-patch-info':
                from dwarf_planet_patch import patch_info
                root=self.app.folder(value['run'])
                config=read_json(root/'request.json') or read_json(root/'run_manifest.json',{})['config']
                return self.json(patch_info(config,value.get('dwarf_catalog_path')))
            if self.path=='/api/open-package-folder':
                return self.json(self.app.open_package_folder(value['run'],value['candidate']))
            if self.path=='/api/shutdown':
                if self.app.process is not None and self.app.process.poll() is None:
                    self.app.stop(self.app.active)
                self.json(dict(closing=True))
                threading.Thread(target=self.server.shutdown,daemon=True).start()
                return
            self.send_error(404)
        except Exception as exc:
            self.json(dict(error=str(exc)),400)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--no-browser',action='store_true')
    p.add_argument('--port',type=int,default=0)
    p.add_argument('--instance-file',default=str(HERE/'gui_instance.json'))
    args = p.parse_args()
    instance_file = Path(args.instance_file)
    previous = read_json(instance_file,{})
    if previous and not args.no_browser:
        try:
            with urllib.request.urlopen(previous['url']+'api/ping',timeout=2) as response:
                ping = json.load(response)
            if ping.get('app')=='trajectory-explorer-gui' and ping.get('version')==APP_VERSION and ping.get('instance_id')==previous.get('instance_id'):
                webbrowser.open(previous['url'])
                return
        except (OSError,ValueError,KeyError):
            pass
    app = App()
    server = ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.app = app
    server.instance_id = secrets.token_hex(12)
    url = f'http://127.0.0.1:{server.server_port}/'
    atomic_json(instance_file,dict(url=url,version=APP_VERSION,instance_id=server.instance_id,pid=os.getpid()))
    print('RoLaMGAS: '+url,flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=.25)
    finally:
        app.close_renderer()
        server.server_close()
        if read_json(instance_file,{}).get('instance_id')==server.instance_id:
            instance_file.unlink(missing_ok=True)


if __name__=='__main__':
    main()
