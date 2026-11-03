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
        self.active = None
        self.process = None
        self.building = set()
        self.archive_errors = {}
        self.integrations = {}
        self.moon_process = None
        self.moon_run = None
        self.targets_path = HERE/'resolved_targets.json'
        self.targets = read_json(self.targets_path,{})
        self.cache = HERE/'cache'
        (HERE/'runs').mkdir(exist_ok=True)

    def folder(self,name):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',name):
            raise ValueError('Invalid run identifier')
        return HERE/'runs'/name

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
        return dict(version=APP_VERSION,community=community_settings(),minimum_c3_floor=DEFAULT_MIN_C3,token=self.token,planets=[p for p in BODIES if p!='Earth'],
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
        return result

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

    def refine_candidate(self,name,identifier,days=30.):
        from candidate_refinement import neighborhood_request
        if not re.fullmatch(r'[a-f0-9]{12}',identifier):raise ValueError('Invalid candidate ID')
        root=self.folder(name)
        candidate=read_json(root/'candidates'/(identifier+'.json'))
        if not candidate:raise ValueError('Candidate not found')
        manifest=read_json(root/'run_manifest.json',{})
        config=manifest.get('config') or normalize(read_json(root/'request.json'),HERE)
        route=next((r for r in manifest.get('routes',[]) if r['id']==candidate['sequence']),None)
        if route is None:route=next(r for r in routes_for(normalize(config,HERE)) if r['id']==candidate['sequence'])
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

    def snapshot(self,name):
        output = self.folder(name)
        if not output.exists():
            raise ValueError('Run not found')
        status = read_json(output/'gui_status.json',{})
        error=read_json(output/'run_error.json')
        if error:
            status=dict(status,state='failed',message=error['type']+': '+error['message'])
        if name==self.active and self.process is not None and self.process.poll() is not None and status.get('state') in ('starting','preparing','running'):
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
        limits={k:request.get(k) for k in ('target','target_object','min_c3','max_c3','arrival_date','arrival_tolerance_days','max_dsm_kms','max_single_dsm_kms','max_powered_flyby_kms','max_arrival_vinf_kms','vinf_tolerance_mps','max_years')}
        limits['effective_min_c3']=max(float(request.get('min_c3') if request.get('min_c3') is not None else DEFAULT_MIN_C3),DEFAULT_MIN_C3)
        return dict(run=name,status=status or dict(state='finished'),live=live,log=logs,
                    heartbeat=read_json(output/'heartbeat.json'),
                    limits=limits,
                    active=name==self.active and self.process is not None and self.process.poll() is None)

    def build_archive(self,name):
        try:
            from live_gallery import LiveGallery
            p = self.folder(name)
            c = normalize(read_json(p/'run_manifest.json')['config'],HERE)
            if not Path(c['cache']).exists():
                c['cache'] = str(self.cache)
            ep = get_ephemerides(c,routes_for(c))
            results = read_json(p/'results.json')
            with self.render_lock:
                LiveGallery(p,ep).update(results,dict(state='finished',completed_jobs=results['completed_jobs'],
                                         total_jobs=results['completed_jobs']),final=True)
        except Exception as exc:
            self.archive_errors[name] = str(exc)
        finally:
            self.building.discard(name)

    def moon_status(self,name):
        output=self.folder(name)/'moon_screen'
        result=read_json(output/'status.json',dict(state='none',rows=[]))
        if result['state']=='running' and name==self.moon_run and self.moon_process and self.moon_process.poll() is not None:
            result.update(state='failed',message='Screening exited unexpectedly; see moon_screen/console.log')
            atomic_json(output/'status.json',result)
        return result

    def start_moon_screen(self,name,count=10,altitude=10000.,clocks=12):
        import math
        count=int(count);clocks=int(clocks);altitude=float(altitude)
        if not 1<=count<=1000 or not 1<=clocks<=72 or not math.isfinite(altitude) or altitude<=0:raise ValueError('Invalid Titan screening settings')
        with self.lock:
            if self.moon_process and self.moon_process.poll() is None:raise ValueError('A Titan screen is already running')
            root=self.folder(name)
            if not root.is_dir():raise ValueError('Saved search not found')
            request=read_json(root/'request.json') or read_json(root/'run_manifest.json',{}).get('config',{})
            if str(request.get('target','')).lower()!='saturn':raise ValueError('Open a search whose final destination is Saturn')
            output=root/'moon_screen';output.mkdir(exist_ok=True)
            if read_json(output/'status.json',{}).get('rows'):
                shutil.copytree(output,root/'moon_screen_history'/datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
            atomic_json(output/'status.json',dict(state='running',message='Starting Saturn/Titan screening…',rows=[]))
            with (output/'console.log').open('w',encoding='utf-8') as log:
                self.moon_process=subprocess.Popen(worker_command('moon_screen','--run',str(root),'--cache',str(self.cache),
                    '--count',str(count),'--altitude',str(altitude),'--clocks',str(clocks)),cwd=HERE,stdout=log,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,env=worker_environment(output/'console.log'))
            self.moon_run=name
            return dict(started=True)

    def stop_moon_screen(self,name):
        if name!=self.moon_run or not self.moon_process or self.moon_process.poll() is not None:raise ValueError('No owned Titan screening process is running for this search')
        self.moon_process.terminate()
        self.moon_process.wait(timeout=5)
        output=self.folder(name)/'moon_screen/status.json';result=read_json(output,{})
        result.update(state='stopped',message='Screening stopped; completed rows are preserved.');atomic_json(output,result)
        return dict(stopped=True)

    def integrate(self,name,identifier,arrival_altitude_km=None,powered_flybys=None,post_flyby_months=0.):
        from integrate_export import validate_post_flyby_months
        post_flyby_months=validate_post_flyby_months(post_flyby_months)
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
                       '--candidate',str(candidate),'--config',str(config),'--output',str(output),'--post-flyby-months',str(post_flyby_months))+(['--arrival-altitude-km',str(arrival_altitude_km)] if arrival_altitude_km is not None else [])+(['--powered-flybys' if powered_flybys else '--no-powered-flybys'] if powered_flybys is not None else []),
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

    def package(self,name,identifier,model='auto',arrival_altitude_km=None,powered_flybys=None,post_flyby_months=0.):
        from integrate_export import validate_post_flyby_months
        post_flyby_months=validate_post_flyby_months(post_flyby_months)
        if model not in ('auto','Panels','RTG'):
            raise ValueError('Invalid model choice')
        status=self.export_status(name,identifier)
        requested_altitude=float(arrival_altitude_km) if arrival_altitude_km is not None else None
        if status['state']=='finished' and (status.get('report',{}).get('arrival_altitude_option_km')!=requested_altitude or
            (powered_flybys is not None and status.get('report',{}).get('powered_flybys_active',False)!=powered_flybys) or
            status.get('report',{}).get('post_flyby_months',0.)!=post_flyby_months):
            self.integrate(name,identifier,arrival_altitude_km,powered_flybys,post_flyby_months)
            return dict(state='integrating',message='Updating trajectory export options; the previous export is preserved.')
        if status['state']!='finished':
            if status['state']!='running':
                self.integrate(name,identifier,arrival_altitude_km,powered_flybys,post_flyby_months)
            return dict(state='integrating',message='Integrating the trajectory before packaging.')
        from celestia_package import build_package
        root=self.folder(name)
        candidate=read_json(root/'candidates'/(identifier+'.json'))
        config=read_json(root/'request.json') or read_json(root/'run_manifest.json',{})['config']
        return build_package(root/'exports'/identifier,candidate,config,model)

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
            if url.path=='/api/moon-screen':
                return self.json(self.app.moon_status(params.get('run',[''])[0]))
            if url.path.startswith('/files/'):
                parts = urllib.parse.unquote(url.path).split('/',3)
                if len(parts)!=4:
                    raise ValueError('Invalid file path')
                root = self.app.folder(parts[2]).resolve()
                path = (root/parts[3]).resolve()
                if not path.is_relative_to(root) or path.suffix.lower() not in ('.json','.png','.tsv','.html','.md','.log','.csv','.xyzv','.ssc','.txt','.zip'):
                    raise ValueError('File is outside this run')
            elif url.path=='/gui_assets/launch_mass_c3.png':
                path=RESOURCE_ROOT/'gui_assets'/'launch_mass_c3.png'
            elif url.path in ('/','/gui.html','/gui.js','/gui.css'):
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
            maximum=1024*1024 if self.path in ('/api/options/export','/api/options/import') else 200000
            if not 0<size<=maximum:
                raise ValueError('Invalid request size')
            value = json.loads(self.rfile.read(size))
            if self.path=='/api/community-settings':
                return self.json(save_community_settings(value))
            if self.path=='/api/options/export':
                return self.json(self.app.export_search_options(value.get('config'),value.get('run')))
            if self.path=='/api/options/import':
                return self.json(self.app.import_search_options(value.get('document')))
            if self.path=='/api/resolve':
                return self.json(self.app.lookup(value['query'],value.get('epoch','2030-01-01'),value.get('refresh',False)))
            if self.path=='/api/start':
                return self.json(self.app.start(value))
            if self.path=='/api/recover':
                return self.json(self.app.recover(value['run']))
            if self.path=='/api/refine':
                return self.json(self.app.refine_candidate(value['run'],value['candidate'],value.get('days',30.)))
            if self.path=='/api/return-earth':
                return self.json(self.app.return_to_earth(value['run'],value['candidate'],value.get('minimum_days',80.),value.get('maximum_days',750.),value.get('dsm',False)))
            if self.path=='/api/append-flyby':
                return self.json(self.app.append_candidate(value['run'],value['candidate'],value.get('body'),value.get('count',1),
                    value.get('minimum_days',80.),value.get('maximum_days',750.),value.get('dsm',False),value.get('target_object')))
            if self.path=='/api/stop':
                return self.json(self.app.stop(value['run']))
            if self.path=='/api/integrate':
                return self.json(self.app.integrate(value['run'],value['candidate'],value.get('arrival_altitude_km'),value.get('powered_flybys'),value.get('post_flyby_months',0.)))
            if self.path=='/api/moon-screen':
                return self.json(self.app.start_moon_screen(value['run'],value.get('count',10),value.get('altitude',10000),value.get('clocks',12)))
            if self.path=='/api/stop-moon-screen':
                return self.json(self.app.stop_moon_screen(value['run']))
            if self.path=='/api/package':
                return self.json(self.app.package(value['run'],value['candidate'],value.get('model','auto'),value.get('arrival_altitude_km'),value.get('powered_flybys'),value.get('post_flyby_months',0.)))
            if self.path=='/api/open-package-folder':
                return self.json(self.app.open_package_folder(value['run'],value['candidate']))
            if self.path=='/api/shutdown':
                if self.app.moon_process and self.app.moon_process.poll() is None:self.app.stop_moon_screen(self.app.moon_run)
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
        server.server_close()
        if read_json(instance_file,{}).get('instance_id')==server.instance_id:
            instance_file.unlink(missing_ok=True)


if __name__=='__main__':
    main()
