"""Standalone, resumable multi-gravity-assist opportunity search. No AI service."""
import bootstrap  # noqa: F401
from pathlib import Path
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
import hashlib
import itertools
import json
import math
import multiprocessing
import queue
import os
import re
import signal
import sys
import time
import webbrowser
import numpy as np
from scipy.optimize import least_squares
from dynamics import Model, lambert, DEFAULT_MIN_C3, HARD_MIN_C3, C3BoundsError
from ephemeris import BODIES, DAY, JD0, Ephemerides, atomic_json, calendar, fetch, jd, save_table
from horizons_targets import register_target, moon_model_notice
from sequence_timing import pair_bounds,OTHER_DEFAULT_DAYS

from app_paths import DATA_ROOT,RESOURCE_ROOT
HERE = DATA_ROOT
DATABASE = RESOURCE_ROOT / 'sequence_database.json'
_WORKER_EP = None
_PROGRESS_QUEUE = None


def load_database():
    return json.loads(DATABASE.read_text(encoding='utf-8'))


def default_branch_options(a,b,maximum_days):
    if a==b=='Mercury':
        from mercury_returns import branch_options
        return branch_options(maximum_days)
    maximum=2 if a==b else (1 if a in ('Earth','Venus','Mercury') and b in ('Earth','Venus','Mercury') else 0)
    return [[0,True]]+[[m,low] for m in range(1,maximum+1) for low in (True,False)]


def resolve_route(sequence, db, target_object=None, custom_leg_days=None):
    if sequence.endswith('X'):
        if not target_object:
            raise ValueError('Resolve a Horizons target before using X routes')
        tokens = re.findall(r'Me|dv|dV|[EVMJSUNX]',sequence)
        if ''.join(tokens)!=sequence or tokens[0]!='E' or 'X' in tokens[:-1]:
            raise ValueError('A custom route starts at E and has exactly one terminal X')
        bodies,dsms = [],[]
        for token in tokens:
            if token in ('dv','dV'):
                if len(bodies)-1 in dsms:
                    raise ValueError('Only one DSM per leg is supported')
                dsms.append(len(bodies)-1)
            else:
                bodies.append(target_object['name'] if token=='X' else db['notation'][token])
        ranges,options = [],[]
        for index,(a,b) in enumerate(zip(bodies,bodies[1:])):
            if index==len(bodies)-2:
                ranges.append(list(custom_leg_days or OTHER_DEFAULT_DAYS))
            else:
                pair=a+'-'+b
                ranges.append(pair_bounds(a,b,db))
            options.append(default_branch_options(a,b,ranges[-1][1]))
        return dict(id=sequence,bodies=bodies,dsm_legs=dsms,leg_days=ranges,branch_options=options,
                    target=target_object['name'],provenance='Planet assists to a resolved Horizons terminal target')
    for route in db['sequences']:
        if route['id'] == sequence:
            return route.copy()
    tokens = re.findall(r'Me|dv|dV|[EVMJSUN]', sequence)
    if not tokens or ''.join(tokens) != sequence or tokens[0] != 'E' or tokens[-1] in ('dv','dV'):
        raise ValueError(f'Invalid route {sequence!r}. Use E,V,M,Me,J,S,U,N and dv inside a leg.')
    bodies, dsms = [], []
    for token in tokens:
        if token in ('dv','dV'):
            if len(bodies)-1 in dsms:
                raise ValueError('Only one DSM per leg is supported')
            dsms.append(len(bodies)-1)
        else:
            bodies.append(db['notation'][token])
    if len(bodies) < 2:
        raise ValueError('A sequence needs at least two planetary events')
    ranges = []
    for a,b in zip(bodies,bodies[1:]):
        pair = a+'-'+b
        ranges.append(pair_bounds(a,b,db))
    options=[default_branch_options(a,b,bounds[1]) for a,b,bounds in zip(bodies,bodies[1:],ranges)]
    return dict(id=sequence, bodies=bodies, target=bodies[-1], dsm_legs=dsms, leg_days=ranges,
                branch_options=options, provenance='Custom user route')


def normalize(config, config_dir=HERE):
    c = dict(target='Jupiter', launch_start='2027-01-01', launch_end='2036-12-31',
             max_years=20., vinf_tolerance_mps=20., min_c3=DEFAULT_MIN_C3, max_c3=100., max_arrival_vinf_kms=30.,
             max_dsm_kms=1.5,max_single_dsm_kms=.7,max_powered_flyby_kms=.2,dsm_velocity_box_kms=6., minimum_altitude_km={},
             samples_per_sequence=3000, refinements_per_sequence=36, max_nfev=250,
             branch_families=16, workers=max(1,min(4,(os.cpu_count() or 2)-1)), batches=1,
             seed=502, keep=100, cache='cache', max_ephemeris_step_days=1., sequences=[],
             route_overrides={},target_object=None,custom_leg_days=list(OTHER_DEFAULT_DAYS),search_objective='feasibility',cost_refinements=3,powered_flybys=False,
             local_refinement=None,mercury_resonant_seeds=True,earth_return_seeds=True,historical_mission_seeds=True,append_flyby=None,
             arrival_date=None,arrival_tolerance_days=0.,transfer_direction='prograde',mission_profile='custom',c3_seed_boundary='minimum')
    unknown = set(config)-set(c)-{'event_windows','launch_jd','event_windows_jd','arrival_window_jd','effective_min_c3'}
    if unknown:
        raise ValueError(f'Unknown configuration keys: {sorted(unknown)}')
    c.update(config)
    if 'c3_seed_boundary' not in config:c['c3_seed_boundary']='maximum' if c['mission_profile']=='flyby' else 'minimum'
    if not isinstance(c['powered_flybys'],bool):raise ValueError('powered_flybys must be boolean')
    if not isinstance(c['mercury_resonant_seeds'],bool):raise ValueError('mercury_resonant_seeds must be boolean')
    if not isinstance(c['earth_return_seeds'],bool):raise ValueError('earth_return_seeds must be boolean')
    if not isinstance(c['historical_mission_seeds'],bool):raise ValueError('historical_mission_seeds must be boolean')
    local=c.get('local_refinement')
    if local:
        if not isinstance(local,dict) or len(c['sequences'])!=1 or not c.get('event_windows'):
            raise ValueError('Local refinement needs one sequence and explicit date windows')
        if not all(math.isfinite(float(v)) and 0<=v<=1 for v in local.get('seed_x',[])):
            raise ValueError('Local refinement seed must be finite and within bounds')
    if c['search_objective'] not in ('feasibility','balanced','c3','dsm','arrival','time'):
        raise ValueError('Search objective must be feasibility, balanced, c3, dsm, arrival or time')
    if c['mission_profile'] not in ('custom','orbiter','flyby'):
        raise ValueError('Mission profile must be custom, orbiter or flyby')
    if c['transfer_direction'] not in ('prograde','retrograde','both'):
        raise ValueError('Transfer direction must be prograde, retrograde or both')
    if c['target_object']:
        register_target(c['target_object'])
        notice = moon_model_notice(c['target_object'])
        if notice:
            raise ValueError(notice)
        c['target'] = c['target_object']['name']
    else:
        c['target'] = str(c['target']).title()
    if not c['target_object'] and (c['target'] not in BODIES or (c['target'] == 'Earth' and not c.get('append_flyby'))):
        raise ValueError('Choose Mercury, Venus, Mars, Jupiter, Saturn, Uranus, or Neptune')
    if not isinstance(c['sequences'],list) or not isinstance(c['minimum_altitude_km'],dict):
        raise ValueError('sequences must be a list and minimum_altitude_km a dictionary')
    for name in ('max_years','vinf_tolerance_mps','min_c3','arrival_tolerance_days','max_c3','max_arrival_vinf_kms','max_dsm_kms','max_single_dsm_kms','max_powered_flyby_kms',
                 'dsm_velocity_box_kms','max_ephemeris_step_days'):
        c[name] = float(c[name])
        if not math.isfinite(c[name]) or c[name] < 0 or (c[name] == 0 and name not in ('min_c3','arrival_tolerance_days','max_dsm_kms','max_single_dsm_kms','max_powered_flyby_kms')):
            raise ValueError(f'{name} must be positive and finite')
    c['effective_min_c3']=max(HARD_MIN_C3,c['min_c3'])
    if c['c3_seed_boundary'] not in ('minimum','maximum'):raise ValueError('C3 seed boundary must be minimum or maximum')
    if c['effective_min_c3']>c['max_c3']:raise ValueError(f'Maximum C3 must be at least the effective search floor {c["effective_min_c3"]:g} km²/s²')
    if c['min_c3'] > c['max_c3']:
        raise ValueError('Minimum launch C3 cannot exceed maximum launch C3')
    for name in ('samples_per_sequence','refinements_per_sequence','max_nfev','branch_families',
                 'workers','batches','keep','cost_refinements'):
        if isinstance(c[name],bool) or int(c[name]) != c[name] or c[name] < 1:
            raise ValueError(f'{name} must be a positive integer')
        c[name] = int(c[name])
    c['seed'] = int(c['seed'])
    if c.get('append_flyby'):
        from append_flyby import validate_extension
        validate_extension(c['append_flyby'],c)
        frozen_energy=float(c['append_flyby']['prefix']['launch_c3_km2_s2'])
        if not c['effective_min_c3']-1e-8<=frozen_energy<=c['max_c3']+1e-8:
            raise ValueError('Frozen earlier cruise has launch C3 outside the requested range; change the launch search instead of appending a flyby')
    if (len(c['custom_leg_days']) != 2 or not all(math.isfinite(float(v)) for v in c['custom_leg_days'])
            or not 0 < float(c['custom_leg_days'][0]) < float(c['custom_leg_days'][1])):
        raise ValueError('Custom target leg duration requires 0 < minimum < maximum days')
    if c['max_ephemeris_step_days'] < 1/1440:
        raise ValueError('Horizons download cadence must be at least one minute')
    for body, altitude in c['minimum_altitude_km'].items():
        if body not in BODIES or not math.isfinite(float(altitude)) or float(altitude) < 0:
            raise ValueError('Altitude floors must be nonnegative finite values for known planets')
        c['minimum_altitude_km'][body] = float(altitude)
    c['launch_jd'] = [jd(c['launch_start']),jd(c['launch_end'])]
    if c['launch_jd'][0] > c['launch_jd'][1]:
        raise ValueError('launch_end cannot precede launch_start')
    if c.get('event_windows'):
        if len(c['sequences']) != 1:
            raise ValueError('Explicit event_windows require exactly one sequence')
        c['event_windows_jd'] = [[jd(a),jd(b)] for a,b in c['event_windows']]
        if any(not all(math.isfinite(t) for t in (a,b)) or a > b for a,b in c['event_windows_jd']):
            raise ValueError('Each event window must have ordered, finite dates')
        c['launch_jd'] = c['event_windows_jd'][0]
    c.pop('arrival_window_jd',None)
    if c['arrival_date']:
        center=jd(str(c['arrival_date']));width=c['arrival_tolerance_days']
        c['arrival_window_jd']=[center-width,center+width]
        if c['arrival_window_jd'][1] <= c['launch_jd'][0]:
            raise ValueError('Requested arrival must follow the launch window start')
        if c.get('event_windows_jd'):
            a,b=c['event_windows_jd'][-1];lo,hi=c['arrival_window_jd']
            if max(a,lo)>min(b,hi):
                raise ValueError('Arrival date does not overlap the final encounter date window')
            c['event_windows_jd'][-1]=[max(a,lo),min(b,hi)]
    if c['target_object']:
        from horizons_targets import target_for_epoch
        c['target_object']=target_for_epoch(c['target_object'],c['launch_jd'][0])
    cache = Path(c['cache'])
    c['cache'] = str((config_dir/cache).resolve() if not cache.is_absolute() else cache.resolve())
    return c


def routes_for(c):
    db = load_database()
    names = c['sequences'] or (['EX','EdvEX','EJX','EdvEJX'] if c['target_object'] else
            [r['id'] for r in db['sequences'] if r['target'] == c['target'] and (c['max_dsm_kms']>0 or not r['dsm_legs'])])
    routes = [json.loads(json.dumps(c['append_flyby']['route']))] if c.get('append_flyby') else [resolve_route(s, db,c['target_object'],c['custom_leg_days']) for s in names]
    if not routes:
        raise ValueError('No routes selected')
    for r in routes:
        if r['target'] != c['target']:
            raise ValueError(f"{r['id']} does not end at {c['target']}")
        override = c['route_overrides'].get(r['id'],{})
        if set(override)-{'leg_days','branch_options'}:
            raise ValueError('Route overrides support leg_days and branch_options')
        r.update(override)
        n = len(r['bodies'])-1
        if len(r['leg_days']) != n or len(r['branch_options']) != n:
            raise ValueError('One timing range and branch-options list per leg required')
        if any(not (math.isfinite(a) and math.isfinite(b) and 0 < a < b) for a,b in r['leg_days']):
            raise ValueError('Leg durations require 0 < minimum < maximum')
        for i,options in enumerate(r['branch_options']):
            if not options or any(len(v) not in (2,3) or int(v[0]) != v[0] or v[0] < 0 or not isinstance(v[1],bool)
                                  or (len(v)==3 and not isinstance(v[2],bool)) for v in options):
                raise ValueError('Branches need nonnegative integer M, boolean low-path and optional boolean prograde')
            if c.get('append_flyby') and i<c['append_flyby']['prefix_count']-1:continue
            if c['transfer_direction']=='retrograde':
                r['branch_options'][i]=[list(v) for v in dict.fromkeys(tuple(v[:2])+ (False,) for v in options)]
            elif c['transfer_direction']=='both':
                r['branch_options'][i]=[list(v[:2])+[direction] for v in options for direction in (True,False)]
                r['branch_options'][i]=[list(v) for v in dict.fromkeys(tuple(v) for v in r['branch_options'][i])]
        if c.get('event_windows_jd') and len(c['event_windows_jd']) != n+1:
            raise ValueError('One explicit event window per body required')
    return routes


def coverage(c, routes):
    if c.get('event_windows_jd'):
        return min(a for a,b in c['event_windows_jd']), max(b for a,b in c['event_windows_jd'])
    if c.get('append_flyby'):
        e=c['append_flyby'];dates=e['prefix']['dates_jd_tdb']
        return dates[0]-2,dates[-1]+sum(b for a,b in routes[0]['leg_days'][e['prefix_count']-1:])+2
    # Cover every sampled epoch, including samples rejected for excessive duration.
    end = c['launch_jd'][1]+max(sum(b for a,b in r['leg_days']) for r in routes)
    if c.get('arrival_window_jd'):end=c['arrival_window_jd'][1]
    return c['launch_jd'][0]-2, end+2


def get_ephemerides(c, routes):
    register_target(c.get('target_object'))
    from append_flyby import original_target_descriptors
    for descriptor in original_target_descriptors(c):register_target(descriptor)
    start,end = coverage(c,routes)
    return Ephemerides(c['cache'],[b for r in routes for b in r['bodies']],start,end,
                       c['max_ephemeris_step_days'])


def prepare(c, routes, local_folder=None, stop_file=None):
    start,end = coverage(c,routes)
    for body in sorted({b for r in routes for b in r['bodies']}):
        if stop_file and Path(stop_file).exists():
            raise InterruptedError('Stopped during ephemeris preparation')
        try:
            Ephemerides(c['cache'],[body],start,end,c['max_ephemeris_step_days'])
            print(f'{body}: cached coverage OK',flush=True)
            continue
        except ValueError:
            pass
        if local_folder:
            for p in sorted(Path(local_folder).glob(body+'.Sun.*.txt')):
                try:
                    save_table(c['cache'],body,p.read_text(encoding='utf-8-sig'),str(p.resolve()))
                except ValueError:
                    continue
            try:
                Ephemerides(c['cache'],[body],start,end,c['max_ephemeris_step_days'])
                print(f'{body}: imported local Horizons vectors',flush=True)
                continue
            except ValueError:
                pass
        step = min(.25,c['max_ephemeris_step_days']) if body == 'Mercury' else c['max_ephemeris_step_days']
        cursor = start
        # Keep public Horizons requests reasonably sized even for hourly caches
        # spanning decades. Save each chunk independently for restartability.
        while cursor < end:
            if stop_file and Path(stop_file).exists():
                raise InterruptedError('Stopped during ephemeris preparation')
            stop = min(end,cursor+20000*step)
            try:
                Ephemerides(c['cache'],[body],cursor,stop,step)
            except ValueError:
                fetch(c['cache'],body,cursor,stop,step)
            cursor = stop
        Ephemerides(c['cache'],[body],start,end,c['max_ephemeris_step_days'])
    print('Ephemerides ready. Searches now work offline.',flush=True)


def branch_families(route, limit, seed, preferred=None):
    options = route['branch_options']
    total = math.prod(len(o) for o in options)
    if preferred is not None and (len(preferred)!=len(options) or any(list(b) not in [list(v) for v in opts] for b,opts in zip(preferred,options))):
        raise ValueError('Parent Lambert branches are not in the route options')
    if total <= limit:
        families=[[list(v) for v in b] for b in itertools.product(*options)]
        if preferred is not None:families.sort(key=lambda b:b!=preferred)
        return families
    rng = np.random.default_rng(seed)
    # Keep complete Mercury resonance ladders together instead of selecting
    # unrelated revolution counts independently on every return.
    from mercury_returns import coherent_families
    selected = [tuple(tuple(b) for b in family) for family in coherent_families(route)]
    selected.append(tuple(tuple(o[0]) for o in options))
    if preferred is not None:selected.insert(0,tuple(tuple(b) for b in preferred))
    selected=list(dict.fromkeys(selected))
    resonant = tuple(tuple(next((v for v in o if v[0] == 1 and v[1]),o[0])) for o in options)
    if resonant not in selected:
        selected.append(resonant)
    while len(selected) < limit:
        b = tuple(tuple(o[int(rng.integers(len(o)))]) for o in options)
        if b not in selected:
            selected.append(b)
    return [[list(v) for v in b] for b in selected[:limit]]


def candidate_key(q):
    return q['launch_c3_km2_s2']/100 + q['total_dsm_kms'] + q['arrival_vinf_kms']/20 + q['duration_years']/100


def objective_key(c):
    if c.get('search_objective')=='c3':return lambda q:q['launch_c3_km2_s2']
    if c.get('search_objective')=='arrival':return lambda q:q['arrival_vinf_kms']
    if c.get('search_objective')=='time':return lambda q:q['duration_years']
    if c.get('search_objective')=='dsm':return lambda q:q['total_dsm_kms']
    return candidate_key


def worker_initialize(progress_queue=None):
    global _PROGRESS_QUEUE
    _PROGRESS_QUEUE = progress_queue
    signal.signal(signal.SIGINT,signal.SIG_IGN)


def job_search(job):
    """One branch family in one process, with no network calls."""
    route,c,branch,seed,nsamples,nstarts,identifier = job[:7]
    supplied=job[7] if len(job)>7 else []
    start = time.monotonic()
    global _WORKER_EP
    if _WORKER_EP is None:
        _WORKER_EP = get_ephemerides(c,routes_for(c))
    ep = _WORKER_EP
    model = Model(route,c,ep)
    rng = np.random.default_rng(seed)
    dimension = model.dimension
    # Latin hypercube spreads the initial dates over all allowed launch epochs.
    samples = np.column_stack([(rng.permutation(nsamples)+rng.random(nsamples))/nsamples for _ in range(dimension)])
    from mercury_returns import seed_returns
    resonant_rows=seed_returns(samples,model,branch,rng)
    local=c.get('local_refinement')
    if local:
        if len(local['seed_x'])!=dimension:raise ValueError('Parent candidate dimension differs from route')
        samples[0]=np.asarray(local['seed_x'])
    # Small velocity offsets make useful low-DSM starts more common.
    for k in range(len(model.dsm_legs)):
        offset = model.n+4*k+1
        samples[:nsamples//2,offset:offset+3] = np.clip(rng.normal(.5,.06,(nsamples//2,3)),.001,.999)
    if model.extension:
        samples=np.array([model.expand_variables(model.active_variables(x)) for x in samples])
    from earth_return_seeds import seed_departures
    departure_seeds,departure_seed_stats=seed_departures(samples,model,branch)
    from historical_seeds import seed_missions
    historical_points,historical_stats=seed_missions(samples,model,branch)
    departure_seeds=departure_seeds+historical_points
    for i,point in enumerate(departure_seeds[:len(samples)]):samples[i]=point
    from cost_refinement import boundary_seed,feasibility_refine
    ranked, accepted, near = [], [], []
    boundary_seeds=[]
    if model.extension and not model.c3_in_bounds(model.launch_c3(samples[0],branch)):
        raise ValueError('Frozen earlier cruise has launch C3 outside the configured range; its launch cannot change in an appended-flyby search')
    for sample in samples[:min(len(samples),max(1,min(nstarts,16)))]:
        projected=boundary_seed(model,sample,branch)
        if projected is not None and all(np.linalg.norm(projected[:model.n]-previous[:model.n])>.01 for previous in boundary_seeds):
            boundary_seeds.append(projected)

    def record(x,cost_refinement=None,known_source=None):
        try:
            q = model.evaluate(x,branch)
        except (ValueError,RuntimeError,AssertionError,ZeroDivisionError,OverflowError,FloatingPointError):
            return
        score = float(np.linalg.norm(model.residual(x,branch)))
        q['screening_residual_norm'] = score
        if cost_refinement is not None:q['cost_refinement']=cost_refinement
        if known_source:q.update(known_source)
        q['discovered_unix'] = time.time()
        if local:
            q['refinement_source']=dict(parent_run=local['parent_run'],parent_candidate=local['parent_candidate'],
                reference_c3_km2_s2=local['reference_c3_km2_s2'],
                c3_reduction_km2_s2=local['reference_c3_km2_s2']-q['launch_c3_km2_s2'])
        if model.accepted(q):
            q['status'] = 'passes_configured_patched_conic_screen'
            accepted.append(q)
        else:
            q['status'] = 'near_miss_not_accepted'
            near.append(q)
        if _PROGRESS_QUEUE is not None:
            try:
                _PROGRESS_QUEUE.put_nowait(dict(job_id=identifier,candidate=q))
            except queue.Full:
                pass  # Final checkpoint still includes every retained result.
        return q

    warm_starts=[]
    for known in supplied:
        q=record(known['x'],known_source={k:known[k] for k in ('reused_from','community_source') if k in known})
        if q is not None:warm_starts.append(np.asarray(q['x']))
    root_seeds=[]
    if model.extension:
        from append_flyby import return_root_seeds
        root_seeds=return_root_seeds(model,branch)
        for x in root_seeds:record(x)
    if local:record(local['seed_x'])
    for x in boundary_seeds:record(x)
    valid = 0
    for x in samples:
        try:energy=model.launch_c3(x,branch)
        except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):continue
        if not model.c3_in_bounds(energy):
            model.c3_pruned_evaluations+=1
            continue
        res = model.residual(x,branch)
        if np.max(np.abs(res)) < 1e5:
            valid += 1
            ranked.append((float(res@res),x))
            if np.linalg.norm(res) < 1:
                record(x)
    # Every retained historical/proposal guess gets its own short refinement.
    # Otherwise a useful reference can be crowded out by random samples or
    # by the small number of full-refinement slots assigned to this branch.
    historical_stats.update(refinement_attempted=0,refinement_evaluated=0,refinement_passing=0,
                            refinement_maxiter=min(60,c['max_nfev']))
    for name,x in zip(historical_stats['missions'],historical_points):
        historical_stats['refinement_attempted']+=1
        refined=feasibility_refine(model,x,branch,maxiter=historical_stats['refinement_maxiter'])
        if refined is None:continue
        q=record(refined['x'],known_source=dict(initialization_reference=name))
        if q is None:continue
        historical_stats['refinement_evaluated']+=1
        historical_stats['refinement_passing']+=int(model.accepted(q))
        ranked.append((q['screening_residual_norm']**2,np.asarray(q['x'])))
    ranked.sort(key=lambda row:row[0])
    # Spread refinements across the good random starts, avoid identical basins.
    starts = [np.asarray(local['seed_x'])] if local and model.c3_in_bounds(model.launch_c3(local['seed_x'],branch)) else []
    # Reserve a quarter of refinement slots for empirical low-energy Earth
    # departures, even when the user starts ordinary C3 trials at the maximum.
    priority_departures=departure_seeds[:max(1,nstarts//4)]
    for x in priority_departures+boundary_seeds+root_seeds:
        if len(starts)<nstarts and all(np.linalg.norm(x[:model.n]-p[:model.n])>.01 for p in starts):starts.append(np.asarray(x))
    for score,x in ranked:
        if len(starts)>=nstarts:break
        if all(np.linalg.norm(x[:model.n]-p[:model.n]) > .08 for p in starts):
            starts.append(x)
        if len(starts) >= nstarts:
            break
    for x in warm_starts+starts:
        refined=feasibility_refine(model,x,branch,maxiter=c['max_nfev'])
        if refined is not None:record(refined['x'])
    if c['search_objective']!='feasibility':
        from cost_refinement import refine
        pool=accepted+[q for q in near if model.extension and model.accepted(q,allow_arrival_overrun=True)]
        seeds=sorted(pool,key=objective_key(c))[:c['cost_refinements']]
        for cost_seed in seeds:
            try:
                polished=refine(model,cost_seed['x'],branch,c['search_objective'],maxiter=c['max_nfev'])
            except Exception as exc:
                print(f'COST REFINEMENT ERROR {route["id"]}: {exc}',flush=True)
                continue
            if polished is not None:
                if polished['cost_refinement']['objective_after']<=polished['cost_refinement']['objective_before']:
                    record(polished['x'],polished['cost_refinement'])
    return dict(job_id=identifier,sequence=route['id'],branch=branch,seed=seed,
                random_evaluations=nsamples,valid_random_evaluations=valid,refinements=len(starts)+len(warm_starts)+historical_stats['refinement_attempted'],known_seed_refinements=len(warm_starts),mercury_resonant_seed_rows=resonant_rows,
                appended_return_roots=len(root_seeds),earth_return_departure_seeds=departure_seed_stats,historical_mission_seeds=historical_stats,
                c3_seed_boundary=c.get('c3_seed_boundary','minimum'),c3_boundary_seed_count=len(boundary_seeds),
                effective_min_c3=model.c3_minimum,c3_preflight_evaluations=model.c3_preflight_evaluations,
                c3_pruned_evaluations=model.c3_pruned_evaluations,
                elapsed_seconds=time.monotonic()-start,accepted=accepted,near_misses=near)


def summarize(jobs, c, reused=None, reused_near=None):
    completed_jobs=len(jobs)
    if reused or reused_near:jobs=[*jobs,dict(accepted=reused or [],near_misses=reused_near or [])]
    floor=max(HARD_MIN_C3,c.get('effective_min_c3',c.get('min_c3',DEFAULT_MIN_C3)));ceiling=c.get('max_c3',float('inf'))
    in_energy_range=lambda q:'launch_c3_km2_s2' not in q or floor-1e-8<=q['launch_c3_km2_s2']<=ceiling+1e-8
    found = [q for job in jobs for q in job['accepted'] if in_energy_range(q)]
    rank=objective_key(c)
    found.sort(key=rank)
    unique = []
    for q in found:
        if any(q['sequence'] == p['sequence'] and q['branches'] == p['branches']
               and max(abs(a-b) for a,b in zip(q['dates_jd_tdb'],p['dates_jd_tdb'])) < 3
               and abs(q['total_dsm_kms']-p['total_dsm_kms']) < .05 for p in unique):
            continue
        unique.append(q)
    metrics = ('launch_c3_km2_s2','total_dsm_kms','arrival_vinf_kms','duration_years')
    for q in unique:
        q['pareto_front'] = not any(all(p[m] <= q[m] for m in metrics) and any(p[m] < q[m] for m in metrics)
                                          for p in unique if p is not q)
    # Preserve route coverage first, then fill with tradeoffs and combined-score ranking.
    chosen = []
    for sequence in dict.fromkeys(q['sequence'] for q in unique):
        chosen.append(next(q for q in unique if q['sequence'] == sequence))
    for q in sorted(unique,key=lambda v:(not v['pareto_front'],rank(v))):
        if not any(q is p for p in chosen):
            chosen.append(q)
    chosen = chosen[:c['keep']]
    near = sorted([q for job in jobs for q in job['near_misses'] if in_energy_range(q)],key=lambda q:q['screening_residual_norm'])
    seen=set();diagnostics=[]
    for q in near:
        key=json.dumps([q['sequence'],q['branches'],q['dates_jd_tdb'],q['x']],sort_keys=True)
        if key not in seen:diagnostics.append(q);seen.add(key)
    near=diagnostics
    for q in chosen+near:
        identity = json.dumps([q['sequence'],q['branches'],q['dates_jd_tdb'],q['x']],sort_keys=True)
        q['id'] = hashlib.sha256(identity.encode()).hexdigest()[:12]
    return dict(model='Sun-only Lambert/Kepler arcs, instantaneous asymptotic flyby joins',
                frame='Sun-centered Ecliptic J2000; km, km/s; JD TDB', nbody_validated=False,
                arrival_mode='Hyperbolic arrival; capture and terminal rendezvous burns excluded',
                mismatch_note='Accepted unpowered joins are below the user tolerance, not an exactly continuous trajectory. Explicit powered periapsis vector burns are charged when enabled; unresolved scalar speed residuals are never silently treated as free or as complete burn constructions.',
                requested_min_c3=c.get('min_c3',DEFAULT_MIN_C3),effective_min_c3=floor,max_c3=ceiling,
                completed_jobs=completed_jobs, reused_candidates=len(reused or []), raw_accepted=len(found), distinct_accepted=len(unique),
                candidates=chosen,near_misses=near)


def planned_jobs(c, routes):
    """Give each sequence the same trials alone, grouped or reordered.

    The user seed belongs to each sequence independently. Route-list indexes
    only name checkpoint files; they must not affect branch choices or dates.
    This also preserves successful seeds from existing standalone searches.
    """
    for batch in range(c['batches']):
        for ri,route in enumerate(routes):
            preferred=(c.get('local_refinement') or {}).get('branches')
            if preferred is None:
                from earth_return_seeds import preferred_chain_branch
                preferred=preferred_chain_branch(c,route)
            if preferred is None:
                from mercury_returns import preferred_resonant_branch
                preferred=preferred_resonant_branch(c,route)
            families = branch_families(route,c['branch_families'],c['seed'],preferred=preferred)
            nsamples = max(8,math.ceil(c['samples_per_sequence']/len(families)))
            nstarts = max(1,math.ceil(c['refinements_per_sequence']/len(families)))
            for bi,branch in enumerate(families):
                identifier = f'b{batch:03d}_r{ri:02d}_f{bi:03d}'
                yield route,c,branch,c['seed']+batch*100000+bi,nsamples,nstarts,identifier


def run(c, routes, output, resume=False, stop_file=None, managed=False, checkpoint_seed=None, database_gate=None):
    from presentation import publish
    from live_gallery import LiveGallery
    output = Path(output).resolve()
    control_files = {'gui_status.json','request.json','console.log','stop.request','heartbeat.json'} if managed else set()
    if output.exists() and any(p.name not in control_files for p in output.iterdir()) and not resume:
        raise ValueError(f'{output} is not empty. Choose another output or use --resume.')
    output.mkdir(parents=True,exist_ok=True)
    ep = get_ephemerides(c,routes)
    # Freeze the reused set per run so resume does not change when other
    # searches finish. Fresh searches revalidate historical pass candidates.
    archive_path=output/'reused_candidates.json'
    if not archive_path.exists():
        from community import download_candidates
        online=download_candidates(c,routes,ep,stop_file=stop_file)
        from candidate_archive import collect_candidates
        archive=collect_candidates(c,routes,ep,HERE/'runs',exclude=output)
        archive['accepted'].extend(online['accepted']);archive['near_misses']=online['near_misses']
        from earth_return_seeds import verified_chain_seeds
        chain_seeds=verified_chain_seeds(c,routes,ep)
        archive['accepted'].extend(chain_seeds['accepted']);archive['chain_seed_stats']=chain_seeds['stats']
        from mercury_returns import verified_resonant_seeds
        resonant_seeds=verified_resonant_seeds(c,routes,ep)
        archive['accepted'].extend(resonant_seeds['accepted']);archive['resonant_seed_stats']=resonant_seeds['stats']
        if resonant_seeds['accepted']:
            print(f"Revalidated {len(resonant_seeds['accepted'])} bundled resonant-transfer starters under the current limits.",flush=True)
        if chain_seeds['accepted']:
            print(f"Revalidated {len(chain_seeds['accepted'])} complete EdvEVEEJ C3/DSM starters under the current limits.",flush=True)
        archive['database_status']=online.get('online_status','unknown');archive['downloaded_records']=online.get('downloaded_records',0)
        atomic_json(archive_path,archive)
    else:
        archive=json.loads(archive_path.read_text(encoding='utf-8'))
    reused=archive['accepted']
    reused_near=archive.get('near_misses',[])
    archive_hash=hashlib.sha256(archive_path.read_bytes()).hexdigest()
    if reused:print(f'Revalidated {len(reused)} compatible saved candidates against all current limits.',flush=True)
    engine_hashes = {name:hashlib.sha256((RESOURCE_ROOT/name).read_bytes()).hexdigest()
                     for name in ('mission_search.py','dynamics.py','ephemeris.py','bootstrap.py','horizons_targets.py','cost_refinement.py','powered_flyby.py','mercury_returns.py','append_flyby.py','candidate_archive.py','community.py','earth_return_seeds.py','historical_seeds.py','departure_seeds/historical_missions.json','departure_seeds/mission_studies.json','departure_seeds/decadal_missions.json','departure_seeds/juice_departure.json','departure_seeds/eevee_chain.json')}
    signature = hashlib.sha256(json.dumps([c,routes,ep.manifest,engine_hashes,archive_hash],sort_keys=True).encode()).hexdigest()
    manifest_path = output/'run_manifest.json'
    if resume:
        if not manifest_path.exists() or json.loads(manifest_path.read_text())['signature'] != signature:
            raise ValueError('Resume requires the same configuration, route definitions, engine code and ephemeris source hashes')
    atomic_json(manifest_path,dict(signature=signature,config=c,routes=routes,ephemerides=ep.manifest,
                                  engine_hashes=engine_hashes,reused_candidates_sha256=archive_hash,reused_candidates=len(reused),executable=sys.executable,created_local=datetime.now().isoformat()))
    checkpoint = output/'checkpoints'
    checkpoint.mkdir(exist_ok=True)
    if checkpoint_seed:
        source=Path(checkpoint_seed).resolve()
        previous=json.loads((source/'run_manifest.json').read_text(encoding='utf-8'))
        if normalize(previous['config'],source)!=c or previous['routes']!=routes or previous['ephemerides']!=ep.manifest:
            raise ValueError('Recovery requires identical request, routes and ephemeris sources')
        recovered=0
        for path in (source/'checkpoints').glob('*.json'):
            item=json.loads(path.read_text(encoding='utf-8'))
            route=next(r for r in routes if r['id']==item['sequence'])
            model=Model(route,c,ep)
            valid=[];near=[]
            for old in item['accepted']+item['near_misses']:
                try:
                    q=model.evaluate(old['x'],item['branch'])
                except (ValueError,RuntimeError,AssertionError):
                    continue
                q.update(discovered_unix=old.get('discovered_unix',time.time()),
                         screening_residual_norm=float(np.linalg.norm(model.residual(q['x'],item['branch']))))
                if old.get('cost_refinement'):q['cost_refinement']=old['cost_refinement']
                if model.accepted(q):
                    q['status']='passes_configured_patched_conic_screen';valid.append(q)
                else:
                    q['status']='near_miss_not_accepted';near.append(q)
            item.update(accepted=valid,near_misses=sorted(near,key=lambda q:q['screening_residual_norm']))
            atomic_json(checkpoint/path.name,item);recovered+=1
        atomic_json(output/'recovery.json',dict(source=str(source),revalidated_checkpoints=recovered))
        if (source/'results.json').exists():
            atomic_json(output/'previous_results.json',json.loads((source/'results.json').read_text(encoding='utf-8')))
        print(f'Recovered and revalidated {recovered} completed branch checkpoints.',flush=True)
    jobs, done = [], []
    canonical=lambda branch:tuple(tuple(b[:2])+(bool(b[2]) if len(b)>2 else True,) for b in branch)
    for job in planned_jobs(c,routes):
        bank=[q for q in reused+reused_near if q['sequence']==job[0]['id'] and canonical(q['branches'])==canonical(job[2])]
        if bank:job=(*job,bank)
        # Slot 6 is always the job ID; slot 7 optionally holds saved seeds.
        p = checkpoint/(job[6]+'.json')
        if p.exists():
            done.append(json.loads(p.read_text(encoding='utf-8')))
        else:
            jobs.append(job)
    total = len(jobs)+len(done)
    if c['min_c3']<c['effective_min_c3']:print(f"Requested minimum C3 {c['min_c3']:g}; applying supported search floor {c['effective_min_c3']:g} km²/s².",flush=True)
    print(f'{len(routes)} routes; {total} branch jobs; {c["workers"]} CPU workers; {len(done)} completed checkpoints.',flush=True)
    initial = summarize(done,c,reused,reused_near)
    atomic_json(output/'results.json',initial)
    publish(output,initial,ep,deferred=managed,config=c)
    live = LiveGallery(output,ep,deferred=managed,config=c)
    started = time.monotonic()
    progress = dict(state='running',completed_jobs=len(done),total_jobs=total,elapsed_seconds=0)
    live.update(initial,progress)
    if database_gate is not None:
        library=[q for q in reused if q.get('community_source')]
        library_summary=summarize([],dict(c,keep=max(c['keep'],3)),library)
        matches=library_summary['candidates']
        report=dict(passing_matches=library_summary['distinct_accepted'],online_matches=sum(q['community_source'].get('library')=='online' for q in matches),bundled_matches=sum(q['community_source'].get('library')=='bundled' for q in matches),online_status=archive.get('database_status','unknown'),downloaded_records=archive.get('downloaded_records',0),all_user_limits_revalidated=True)
        atomic_json(output/'database_first.json',report)
        proceed=database_gate(report)
        report['cpu_search_started']=bool(proceed);atomic_json(output/'database_first.json',report)
        if not proceed:
            initial['database_first']=report;atomic_json(output/'results.json',initial)
            progress.update(state='finished',total_jobs=0,completed_jobs=0,elapsed_seconds=time.monotonic()-started,local_search_skipped=True)
            live.update(initial,progress,final=True);publish(output,initial,ep,deferred=managed,config=c)
            print(f"Using {report['passing_matches']} verified database matches; local optimization skipped.",flush=True)
            return output/'index.html'
    print('Preparing local optimizer workers. Ctrl+C preserves completed jobs.',flush=True)
    last_gallery = time.monotonic()
    last_live = 0.
    context = multiprocessing.get_context('spawn')
    # Manager queues have no per-worker feeder thread to block process exit.
    # Losing optional progress must never block the durable result channel.
    progress_manager = context.Manager()
    progress_queue = progress_manager.Queue(maxsize=256)
    pool = ProcessPoolExecutor(max_workers=c['workers'],mp_context=context,
                               initializer=worker_initialize,initargs=(progress_queue,))
    from community import CommunitySync
    sharing=CommunitySync(c,routes)
    pending_live = {}
    futures = {}
    stopped = False
    dirty = False
    try:
        futures = {pool.submit(job_search,job):job[6] for job in jobs}
        while futures:
            from concurrent.futures import wait, FIRST_COMPLETED
            if stop_file and Path(stop_file).exists():
                raise KeyboardInterrupt
            ready,_ = wait(futures,timeout=.5,return_when=FIRST_COMPLETED)
            for _ in range(1000):
                try:
                    packet = progress_queue.get_nowait()
                except queue.Empty:
                    break
                if packet['job_id'] not in futures.values():
                    continue
                bucket = pending_live.setdefault(packet['job_id'],dict(accepted=[],near_misses=[]))
                q = packet['candidate']
                sharing.offer(q)
                if q['status'].startswith('passes'):
                    bucket['accepted'].append(q)
                else:
                    bucket['near_misses'].append(q)
                progress['active_sequence'] = q['sequence']
                dirty = True
            for future in ready:
                identifier = futures.pop(future)
                result = future.result()
                for q in result['accepted']+result['near_misses']:sharing.offer(q)
                pending_live.pop(identifier,None)
                atomic_json(checkpoint/(identifier+'.json'),result)
                done.append(result)
                summary = summarize(done,c,reused,reused_near)
                atomic_json(output/'results.json',summary)
                dirty = True
                if time.monotonic()-last_gallery > 30:
                    publish(output,summary,ep,deferred=managed,config=c)
                    last_gallery = time.monotonic()
                print(f'[{len(done)}/{total}] {result["sequence"]}: {len(result["accepted"])} accepted, '
                      f'{result["valid_random_evaluations"]}/{result["random_evaluations"]} valid samples; '
                      f'{summary["distinct_accepted"]} distinct overall; {result["elapsed_seconds"]:.1f}s.',flush=True)
            if time.monotonic()-last_live > 2 and (dirty or time.monotonic()-last_live > 15):
                preview = summarize(done+list(pending_live.values()),c,reused,reused_near)
                preview['completed_jobs'] = len(done)
                progress.update(completed_jobs=len(done),elapsed_seconds=time.monotonic()-started)
                live.update(preview,progress)
                last_live = time.monotonic()
                dirty = False
    except KeyboardInterrupt:
        stopped = True
        for future in futures:
            future.cancel()
        # Only processes owned by this executor; workers never write checkpoints.
        # Termination cannot corrupt completed results, written atomically here.
        for process in list(pool._processes.values()):
            process.terminate()
        print('Stopped. Completed checkpoints retained; rerun with --resume.',flush=True)
    except BaseException as exc:
        atomic_json(output/'run_error.json',dict(message=str(exc),type=type(exc).__name__,updated_unix=time.time()))
        print(f'SEARCH ERROR: {type(exc).__name__}: {exc}',flush=True)
        for future in futures:
            future.cancel()
        for process in list((pool._processes or {}).values()):
            process.terminate()
        raise
    finally:
        pool.shutdown(wait=True,cancel_futures=True)
        # Preserve candidates already reported by interrupted jobs, separately
        # from completed checkpoints. Resuming reruns those unfinished jobs.
        summary = summarize(done+list(pending_live.values()),c,reused,reused_near)
        summary['completed_jobs'] = len(done)
        atomic_json(output/'results.json',summary)
        progress.update(state='failed' if (output/'run_error.json').exists() else 'stopped' if stopped else 'finished',completed_jobs=len(done),
                        elapsed_seconds=time.monotonic()-started)
        live.update(summary,progress,final=True)
        publish(output,summary,ep,deferred=managed,config=c)
        progress_manager.shutdown()
        sharing.close()
    print(f'Saved {len(summary["candidates"])} accepted candidates and {len(summary["near_misses"])} diagnostics to {output}',flush=True)
    if not summary['candidates']:
        print('No passing candidate found in this search. Inspect the diagnostics, add starts or broaden bounds.',flush=True)
    return output/'index.html'


def console_database_decision(report):
    count=report['passing_matches']
    if count<3:
        print(f'Database check found {count} verified matches; starting local optimization automatically.',flush=True)
        return True
    if not sys.stdin.isatty():
        print(f'{count} verified database matches saved. Use --local-search to additionally optimize in a noninteractive run.',flush=True)
        return False
    answer=input(f'{count} database trajectories satisfy all limits. Run a local CPU search too? [y/N]: ')
    return answer.strip().lower() in ('y','yes')


def wizard():
    def ask(label,default):
        return input(f'{label} [{default}]: ').strip() or str(default)
    print('\nLOCAL MULTI-GRAVITY-ASSIST SEARCH\nAll numerical work runs on this computer.\n')
    target = ask('Destination (Mercury/Venus/Mars/Jupiter/Saturn/Uranus/Neptune)','Jupiter').title()
    start = ask('First launch date','2027-01-01')
    end = ask('Last launch date','2036-12-31')
    names = ask('Sequences (comma-separated), or all','all')
    config = dict(target=target,launch_start=start,launch_end=end,
                  sequences=[] if names.lower() == 'all' else [s.strip() for s in names.split(',')],
                  vinf_tolerance_mps=float(ask('Maximum flyby excess-speed mismatch (m/s)',20)),
                  min_c3=float(ask('Minimum launch C3 (km^2/s^2)',DEFAULT_MIN_C3)),
                  max_c3=float(ask('Maximum launch C3 (km^2/s^2)',100)),
                  max_arrival_vinf_kms=float(ask('Maximum arrival V-infinity (km/s)',15)),
                  max_dsm_kms=float(ask('Maximum total designed DSM delta-v (km/s)',1.5)),
                  max_single_dsm_kms=float(ask('Maximum individual DSM magnitude (m/s)',700))/1000,
                  max_powered_flyby_kms=float(ask('Maximum individual powered-flyby magnitude (m/s)',200))/1000,
                  max_years=float(ask('Maximum flight duration (years)',20)),
                  workers=int(ask('CPU workers',max(1,min(4,(os.cpu_count() or 2)-1)))))
    effort = ask('Search effort: quick / standard / deep','standard').lower()
    if effort not in ('quick','standard','deep'):
        raise ValueError('Choose quick, standard or deep')
    samples,starts,nfev = {'quick':(1200,24,200),'standard':(6000,72,350),'deep':(25000,240,500)}[effort]
    config.update(samples_per_sequence=samples,refinements_per_sequence=starts,max_nfev=nfev)
    config['search_objective']=ask('Refinement objective: balanced / c3 / dsm / arrival / time / feasibility','balanced').lower()
    config['batches'] = int(ask('Independent batches (more batches explore more starts)',1))
    output = HERE/'runs'/datetime.now().strftime('%Y%m%d_%H%M%S')
    config['cache'] = str(HERE/'cache')
    c = normalize(config)
    routes = routes_for(c)
    config_path = HERE/'requests'/(output.name+'.json')
    atomic_json(config_path,config)
    print(f'Your editable request: {config_path}',flush=True)
    print('Checking local JPL cache; only missing coverage will be downloaded.',flush=True)
    prepare(c,routes)
    page = run(c,routes,output,database_gate=console_database_decision)
    webbrowser.open(page.as_uri())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('wizard',help='Interactive local setup and search')
    listing = sub.add_parser('list',help='List editable sequence presets')
    listing.add_argument('--target')
    init = sub.add_parser('init',help='Write a default editable request')
    init.add_argument('--target',default='Jupiter')
    init.add_argument('--output',required=True)
    for command in ('prepare','search'):
        p = sub.add_parser(command)
        p.add_argument('--config',required=True)
        if command == 'prepare':
            p.add_argument('--local-folder',help='Import existing Horizons CSV vector tables before downloading')
        else:
            p.add_argument('--output',required=True)
            p.add_argument('--resume',action='store_true')
            p.add_argument('--open',action='store_true')
            p.add_argument('--local-search',action='store_true',help='Also optimize locally without the database-first confirmation')
    validate = sub.add_parser('validate',help='Independently integrate a saved candidate with DOP853')
    validate.add_argument('--candidate',required=True)
    validate.add_argument('--output',required=True)
    args = parser.parse_args()
    if args.command in (None,'wizard'):
        wizard()
    elif args.command == 'list':
        for r in load_database()['sequences']:
            if args.target is None or r['target'].lower() == args.target.lower():
                print(f"{r['id']:23s} {' -> '.join(r['bodies'])}  DSM legs={r['dsm_legs']}")
    elif args.command == 'init':
        request = dict(target=args.target.title(),launch_start='2027-01-01',launch_end='2036-12-31',
                       sequences=[],vinf_tolerance_mps=20,max_c3=100,max_arrival_vinf_kms=15,
                       max_dsm_kms=1.5,max_years=20,minimum_altitude_km={'Earth':200,'Venus':300},
                       samples_per_sequence=6000,refinements_per_sequence=72,branch_families=16,
                       workers=4,batches=1,seed=502,keep=100,cache=str(HERE/'cache'))
        routes_for(normalize(request))
        atomic_json(args.output,request)
    elif args.command == 'validate':
        from presentation import validate_candidate
        validate_candidate(Path(args.candidate),Path(args.output))
    else:
        path = Path(args.config).resolve()
        c = normalize(json.loads(path.read_text(encoding='utf-8-sig')),path.parent)
        routes = routes_for(c)
        if args.command == 'prepare':
            prepare(c,routes,args.local_folder)
        else:
            page = run(c,routes,args.output,args.resume,database_gate=None if args.resume or args.local_search else console_database_decision)
            if args.open:
                webbrowser.open(page.as_uri())


if __name__ == '__main__':
    multiprocessing.freeze_support()
    try:
        main()
    except (ValueError,OSError) as exc:
        print(f'ERROR: {exc}',file=sys.stderr,flush=True)
        sys.exit(2)
