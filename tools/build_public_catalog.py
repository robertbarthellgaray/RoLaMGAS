"""Curate saved search results into a static, path-free public catalog.

Run against a private trajectory_optimization tree, never against the public
repository: python tools/build_public_catalog.py --project PATH --app-data PATH --validation-cache PATH
Only selected numeric results and explicit public fields are published.
"""
import argparse
import collections
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import sys

P = argparse.ArgumentParser()
P.add_argument('--project', type=Path, required=True)
P.add_argument('--app-data', type=Path)
P.add_argument('--extra-runs', type=Path, action='append', default=[], help='Additional private runs with prepared card JSON')
P.add_argument('--validation-cache', type=Path, required=True, help='Independent JPL baseline and custom-target cache for event-state cross-checks')
P.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'docs')
A = P.parse_args()
EXPLORER = A.project / 'mission_designer/explorer'
sys.path.insert(0, str(EXPLORER))
os.environ.setdefault('NUMBA_CACHE_DIR', str(Path(os.environ.get('TEMP', '/tmp')) / 'rolamgas_catalog_numba'))
import bootstrap  # noqa: E402
import numpy as np  # noqa: E402
from dynamics import Model, kepler  # noqa: E402
from ephemeris import AU, DAY, Ephemerides, BODIES  # noqa: E402
from mission_search import normalize, routes_for, get_ephemerides  # noqa: E402
from catalog_validation import audit_candidate, POLICY  # noqa: E402
from horizons_targets import register_target  # noqa: E402

OUT = A.output
for name in ('data/cases', 'images', 'downloads'):
    (OUT / name).mkdir(parents=True, exist_ok=True)

def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def save(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')

def finite_round(points):
    array = np.asarray(points, dtype=float)
    assert np.isfinite(array).all()
    return np.round(array, 8).tolist()

def public_event(e):
    return dict(body=e['body'], jd=e['julian_date_tdb'], date=e['date'],
                position_au=finite_round(np.asarray(e['planet_state_km_kms'][:3]) / AU), kind=e.get('kind', 'Encounter'))

def from_candidate(q, card):
    events = [public_event(e) for e in q['events']]
    events[0]['kind'] = 'Departure'; events[-1]['kind'] = 'Arrival'
    burns = [dict(body='DSM', kind='DSM', jd=b['julian_date_tdb'], date=b['date'],
                  magnitude_mps=b['magnitude_kms'] * 1000,
                  vector_kms=b.get('delta_v_ecliptic_j2000_kms'),
                  position_au=finite_round(np.asarray(b['position_km']) / AU)) for b in q['dsms']]
    flybys = []
    for f in q['flybys']:
        item = dict(body=f['body'], jd=f['julian_date_tdb'], date=f['date'],
                    vinf_in_kms=f['vinf_in_kms'], vinf_out_kms=f['vinf_out_kms'],
                    mismatch_mps=f['speed_mismatch_mps'], turn_deg=f['turn_angle_deg'],
                    altitude_km=f.get('conservative_equal_speed_altitude_km'),
                    altitude_floor_km=f.get('minimum_altitude_km'),
                    powered_mps=q.get('powered_flyby_delta_v_kms', 0) * 1000 if len(q['flybys']) == 1 else 0)
        powered = f.get('powered_flyby') or {}
        if powered:
            item['powered_mps'] = powered.get('magnitude_kms', 0) * 1000
            item['altitude_km'] = powered.get('periapsis_altitude_km', item['altitude_km'])
        flybys.append(item)
    paths = [dict(start=s['start_jd'], end=s['end_jd'], points=finite_round(points))
             for s, points in zip(q['segments'], card['paths'])]
    return dict(id=q['id'], title=q['sequence'] + ' · ' + q['bodies'][-1], target=q['bodies'][-1],
                sequence=q['sequence'], bodies=q['bodies'], model='Lambert candidate', spotlight=False,
                start=q['dates_jd_tdb'][0], end=q['dates_jd_tdb'][-1],
                launch_date=q['launch_date'][:10], arrival_date=q['arrival_date'][:10],
                years=q['duration_years'], c3=q['launch_c3_km2_s2'], vinf=q['arrival_vinf_kms'],
                burns_mps=q['total_dsm_kms'] * 1000, events=events, burns=burns, flybys=flybys,
                paths=paths, coasts=q['segments'], planet_paths=[dict(body=p['body'], points=finite_round(p['points'])) for p in card['planet_paths']],
                note='Solar Lambert/Kepler arcs joined at planet centers. Flyby altitude is inferred from asymptotic turn geometry, not a resolved closest approach. Saved speed and turn screens passed; capture and finite-radius patch corrections are excluded.',
                provenance=dict(candidate_id=q['id'], coordinates='Heliocentric Ecliptic J2000', time_scale='TDB', plot_units='AU',
                                ephemerides='JPL Horizons geometric vectors', source='Saved RoLaMGAS result'))

def display_target(name):
    if 'ED138' in name.replace(' ',''):return '2026 ED138'
    if 'Eris' in name:return 'Eris'
    if 'Pluto' in name:return 'Pluto'
    return name

def check_arcs(q):
    worst_r=0.;worst_v=0.;min_radius=float('inf')
    for i,s in enumerate(q['segments']):
        r0=np.array(s['r']);v0=np.array(s['v']);dt=(s['end_jd']-s['start_jd'])*DAY
        if not dt>0:raise ValueError('Nonpositive coast duration')
        r,v=kepler(r0,v0,dt)
        event=next((e for e in q['events'] if abs(e['julian_date_tdb']-s['end_jd'])<1e-7),None)
        expected=np.array(event['planet_state_km_kms'][:3]) if event else np.array(q['segments'][i+1]['r'])
        worst_r=max(worst_r,float(np.linalg.norm(r-expected)))
        if event:
            j=q['events'].index(event)-1
            worst_v=max(worst_v,float(np.linalg.norm(v-np.array(q['arrival_velocities_kms'][j]))*1000))
        # Evaluate an analytic perihelion only if it lies inside this coast;
        # outbound legs must not be rejected for a fictitious pre-launch perihelion.
        h=np.cross(r0,v0);energy=np.dot(v0,v0)/2-132712440041.27942/np.linalg.norm(r0)
        eccentricity=np.linalg.norm(np.cross(v0,h)/132712440041.27942-r0/np.linalg.norm(r0))
        rp=np.dot(h,h)/132712440041.27942/(1+eccentricity)
        full_period=(2*np.pi*np.sqrt((-132712440041.27942/(2*energy))**3/132712440041.27942)) if energy<0 else float('inf')
        if dt>=full_period or (np.dot(r0,v0)<=0 and np.dot(r,v)>=0):min_radius=min(min_radius,float(rp))
        else:min_radius=min(min_radius,float(np.linalg.norm(r0)),float(np.linalg.norm(r)))
    if worst_r>1. or worst_v>.01:raise ValueError(f'Coast endpoint discrepancy: {worst_r:g} km, {worst_v:g} m/s')
    if min_radius<=695700.:raise ValueError('Solar impact on a propagated coast')
    return dict(max_coast_endpoint_error_km=worst_r,max_coast_velocity_error_mps=worst_v,minimum_solar_radius_km=min_radius)

reference_ephemerides={}
def check_ephemerides(q,cfg):
    if not A.validation_cache:return {}
    if cfg.get('target_object'):register_target(cfg['target_object'])
    key=tuple(sorted(set(q['bodies'])))
    if key not in reference_ephemerides:
        reference_ephemerides[key]=Ephemerides(A.validation_cache,key,2461406.5,2488069.5,1.)
    ep=reference_ephemerides[key];worst_r=0.;worst_v=0.
    for e in q['events']:
        actual=ep.state(e['body'],e['julian_date_tdb']);saved=np.array(e['planet_state_km_kms'])
        worst_r=max(worst_r,float(np.linalg.norm(actual[:3]-saved[:3])))
        worst_v=max(worst_v,float(np.linalg.norm(actual[3:]-saved[3:])*1000))
    if worst_r>.1 or worst_v>.001:raise ValueError(f'JPL event-state cross-check failed: {worst_r:g} km, {worst_v:g} m/s')
    return dict(max_reference_ephemeris_position_error_km=worst_r,max_reference_ephemeris_velocity_error_mps=worst_v)

def thumbnail(c):
    points = np.concatenate([np.asarray(s['points']) for s in c['paths']])
    extent = max(float(np.max(np.abs(points[:, :2]))), .5) * 1.13
    def xy(p): return (160 + p[0] / extent * 135, 110 - p[1] / extent * 88)
    chunks = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 220">',
              '<rect width="320" height="220" fill="#0b1520"/>',
              '<path d="M25 110H295M160 20V200" stroke="#20303e" stroke-width=".6"/>']
    for orbit in c['planet_paths']:
        coords = ' '.join('%.2f,%.2f' % xy(p) for p in orbit['points'])
        chunks.append(f'<polyline points="{coords}" fill="none" stroke="#304757" stroke-width=".7"/>')
    for i, s in enumerate(c['paths']):
        coords = ' '.join('%.2f,%.2f' % xy(p) for p in s['points'])
        color = ['#79d8f1', '#ffd08a', '#8ae3bd', '#a7a8ff'][i % 4]
        chunks.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="1.8"/>')
    chunks.append('<circle cx="160" cy="110" r="3" fill="#ffd08a"/>')
    for e in c['events']:
        x, y = xy(e['position_au'])
        chunks.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.7" fill="#eef7fb"/>')
    chunks.append(f'<text x="15" y="205" fill="#96a9bb" font-family="monospace" font-size="10">{html.escape(c["sequence"])} · XY / AU</text></svg>')
    (OUT / 'images' / (c['id'] + '.svg')).write_text(''.join(chunks), encoding='utf-8')

roots = [EXPLORER / 'runs']
if A.app_data:
    roots.append(A.app_data / 'runs')
roots.extend(A.extra_runs)
groups = collections.defaultdict(list)
seen = set()
targets = ['Mercury', 'Venus', 'Mars', 'Jupiter', 'Saturn', 'Uranus', 'Neptune']
rejected=collections.Counter()
for root in roots:
    if not root.is_dir(): continue
    for run in sorted(root.iterdir()):
        result = run / 'results.json'
        if not result.exists(): continue
        cfg=load(run/'run_manifest.json')['config']
        for q in load(result).get('candidates', []):
            target = display_target(q['bodies'][-1])
            if target not in targets+['Pluto','Eris','2026 ED138']: continue
            if not '2027' <= q['launch_date'][:4] <= '2056': continue
            if q['id'] in seen: continue
            audit=audit_candidate(q,cfg,BODIES)
            if not audit['passed']:
                rejected.update(audit['reasons']);continue
            card = run / 'candidates' / (q['id'] + '.card.json')
            if not card.exists(): continue
            try:audit.update(check_ephemerides(q,cfg))
            except (ValueError,RuntimeError,AssertionError) as e:rejected.update([str(e)]);continue
            seen.add(q['id']); groups[target].append((q, card, run, audit))

cases = []
for target, rows in groups.items():
    # Independent searches can rediscover the same cruise with a new ID.
    # Keep distinct physical solutions, rather than filling slots with copies.
    unique=[]
    for row in sorted(rows,key=lambda r:r[0]['launch_c3_km2_s2']):
        q=row[0]
        def same(previous):
            p=previous[0]
            return (q['sequence']==p['sequence'] and q['branches']==p['branches']
                    and len(q['dates_jd_tdb'])==len(p['dates_jd_tdb'])
                    and max(abs(a-b) for a,b in zip(q['dates_jd_tdb'],p['dates_jd_tdb']))<3
                    and len(q['dsms'])==len(p['dsms'])
                    and all(abs(a['julian_date_tdb']-b['julian_date_tdb'])<3
                            and np.linalg.norm(np.array(a['delta_v_ecliptic_j2000_kms'])-np.array(b['delta_v_ecliptic_j2000_kms']))<.01
                            for a,b in zip(q['dsms'],p['dsms'])))
        if not any(same(p) for p in unique):unique.append(row)
    rows=unique
    chosen = []
    def choose(row):
        if row not in chosen: chosen.append(row)
    sequences=sorted({r[0]['sequence'] for r in rows})
    limit=12 if target in ['Saturn','Neptune','Pluto','Eris','2026 ED138'] else 7
    # Reserve room for each assist sequence before filling metric tradeoffs.
    for key in ('launch_c3_km2_s2','arrival_vinf_kms','duration_years','total_dsm_kms'):
        for seq in sequences:
            if len(chosen)>=limit:break
            choose(min((r for r in rows if r[0]['sequence']==seq),key=lambda r:r[0][key]))
    for row in sorted(rows, key=lambda r: r[0]['launch_c3_km2_s2']):
        if all(abs(row[0]['dates_jd_tdb'][0] - r[0]['dates_jd_tdb'][0]) > 60 for r in chosen): choose(row)
        if len(chosen) >= limit: break
    for row in sorted(rows, key=lambda r: r[0]['launch_c3_km2_s2']):
        if len(chosen) >= limit: break
        choose(row)
    for q, card, run, audit in chosen[:limit]:
        cfg = load(run / 'run_manifest.json')['config']
        try:
            audit.update(check_arcs(q))
        except (ValueError,RuntimeError,AssertionError) as e:rejected.update([str(e)]);continue
        c = from_candidate(q, load(card))
        c['provenance']['speed_tolerance_mps'] = cfg.get('vinf_tolerance_mps', 20)
        c['provenance']['saved_limits'] = {k: cfg.get(k) for k in ('max_c3', 'max_dsm_kms', 'max_arrival_vinf_kms', 'minimum_altitude_km')}
        c['validation']=audit
        if target in ['Pluto','Eris','2026 ED138']:
            original=c['target'];suffix={'Pluto':'P','Eris':'Er','2026 ED138':'X'}[target]
            c['target']=target;c['sequence']=c['sequence'][:-1]+suffix if c['sequence'].endswith('X') else c['sequence']
            c['title']=c['sequence']+' · '+target
            c['bodies']=[target if b==original else b for b in c['bodies']]
            for event in c['events']:
                if event['body']==original:event['body']=target
            for orbit in c['planet_paths']:
                if orbit['body']==original:orbit['body']=target
            descriptor=cfg.get('target_object') or {}
            c['provenance'].update(target_horizons_id=descriptor.get('id'),target_ephemeris=descriptor.get('representation','JPL geometric object vectors'))
            if target=='Eris':c['note']+=' Eris is represented by the Eris–Dysnomia system barycenter; JPL’s primary-body table does not cover these future arrivals.'
        c['note']+=' Independent gallery admission: all unpowered joins ≤1 m/s mismatch, individual DSMs ≤700 m/s, and inferred flyby periapses above their stated floors.'
        cases.append(c)

# Fill the one missing planetary destination entirely offline from the baseline.
c = normalize(dict(target='Mars', sequences=['EM'], launch_start='2028-01-01', launch_end='2035-01-01',
                   max_c3=70, max_arrival_vinf_kms=8, max_years=2, cache=str(EXPLORER / 'cache')))
route = routes_for(c)[0]; ep = get_ephemerides(c, [route]); model = Model(route, c, ep)
mars = []
for jd in np.arange(c['launch_jd'][0], c['launch_jd'][1], 35):
    for tof in (150, 190, 230, 270, 310):
        x = [(jd - c['launch_jd'][0]) / (c['launch_jd'][1] - c['launch_jd'][0]),
             (tof - route['leg_days'][0][0]) / (route['leg_days'][0][1] - route['leg_days'][0][0])]
        if not all(0 <= v <= 1 for v in x): continue
        try:
            q = model.evaluate(x, [[0, True]])
            if model.accepted(q): mars.append(q)
        except (ValueError, RuntimeError): pass
selected = []
for q in sorted(mars, key=lambda q: q['launch_c3_km2_s2']):
    if any(abs(q['dates_jd_tdb'][0] - r['dates_jd_tdb'][0]) < 100 for r in selected): continue
    selected.append(q)
    if len(selected) == 6: break
from live_gallery import card_data
for q in selected:
    q['id'] = 'mars-' + hashlib.sha256(json.dumps(q['dates_jd_tdb']).encode()).hexdigest()[:10]
    case = from_candidate(q, card_data(q, ep))
    case['provenance'].update(source='Offline baseline scan for the static catalog', speed_tolerance_mps=20)
    case['validation']=audit_candidate(q,c,BODIES);case['validation'].update(check_arcs(q))
    case['validation'].update(check_ephemerides(q,c))
    cases.append(case)

def integrated(id, title, sequence, source, events, burns, c3, vinf, cost, note):
    a = np.loadtxt(source, comments='#'); assert a.shape[1] == 7
    # Keep each impulsive boundary on its own side. Sample the already-integrated
    # trajectory for display; its full, unchanged XYZV is offered separately.
    splits = [0] + (np.where(np.diff(a[:, 0]) <= 0)[0] + 1).tolist() + [len(a)]
    paths = []
    for lo, hi in zip(splits[:-1], splits[1:]):
        block = a[lo:hi]
        if len(block) < 2:
            continue  # The single pre-injection state is retained in the XYZV.
        ix = np.unique(np.linspace(0, len(block) - 1, min(len(block), 1100)).astype(int))
        # Integration output is adaptive. Store each timestamp, never imply a
        # uniformly sampled clock across a flyby.
        paths.append(dict(start=float(block[0, 0]), end=float(block[-1, 0]),
                          times=block[ix, 0].tolist(), points=finite_round(block[ix, 1:4] / AU)))
    export = OUT / 'downloads' / (id + '.xyzv'); shutil.copyfile(source, export)
    sha = hashlib.sha256(export.read_bytes()).hexdigest()
    bodylist = [e['body'] for e in events]
    baseline = Ephemerides(str(EXPLORER / 'cache'), list(dict.fromkeys(bodylist)), float(a[0, 0]), float(a[-1, 0]), 1.)
    dates = np.linspace(a[0, 0], a[-1, 0], 300)
    planet_paths = [dict(body=body, points=finite_round([baseline.state(body, jd)[:3] / AU for jd in dates]))
                    for body in dict.fromkeys(bodylist)]
    case = dict(id=id, title=title, target='Uranus', sequence=sequence, bodies=bodylist,
                model='Integrated concept', spotlight=True, start=float(a[0, 0]), end=float(a[-1, 0]),
                launch_date=events[0]['date'][:10], arrival_date=events[-1]['date'][:10],
                years=(events[-1]['jd'] - events[0]['jd']) / 365.25, c3=c3, vinf=vinf, burns_mps=cost,
                events=events, burns=burns, flybys=[], paths=paths, planet_paths=planet_paths, note=note,
                download='downloads/' + export.name,
                provenance=dict(source='Original project integration', sha256=sha,
                                coordinates='Heliocentric Ecliptic J2000', time_scale='TDB', plot_units='AU',
                                export_units='JD(TDB), km, km/s; XYZV', planet_arcs='One-day JPL baseline, for visual context'))
    cases.append(case)

base = A.project / 'results/december2045_leo'
u = load(base / 'december2045_LEO_solution.json')
park = u['parking_orbit']; dsm = u['DSM']
ue = [dict(body='Earth', kind='Departure', jd=park['julian_date'], date=park['date'],
           position_au=finite_round(np.asarray(park['heliocentric_post_state'][:3]) / AU))]
for e in u['events']:
    ue.append(dict(body=e['name'], kind='Arrival' if e['name'] == 'Uranus' else 'Flyby',
                   jd=e['julian_date'], date=e['date'], altitude_km=e['altitude_km'],
                   position_au=finite_round(np.asarray(e['state'][:3]) / AU)))
ub = [dict(body='DSM', kind='DSM', jd=dsm['julian_date'], date=dsm['date'], magnitude_mps=dsm['magnitude_kms'] * 1000,
           vector_kms=dsm['delta_v_kms'], position_au=finite_round(np.asarray(dsm['pre_state'][:3]) / AU))]
integrated('claudius-uop-2045', 'CLAUDIUS / UOP · 2045 arrival', 'EdvEJU',
           base / 'december2045_from_200km_LEO_compact.xyzv', ue, ub, park['C3_km2_s2'], u['events'][-1]['vinf_kms'],
           dsm['magnitude_kms'] * 1000,
           'Original December 2045 concept, propagated from a 200 km Earth parking orbit. Sun and prescribed Earth/Venus/Mars/Jupiter/Uranus point masses; this original model omits heliocentric indirect terms. C3 is osculating Earth-relative energy at injection. The 4.445 km/s LEO injection is excluded from the displayed cruise-burn total. Display points are thinned; the downloadable XYZV preserves the compact source file.')
base = A.project / 'mission_designer/tianwen4/results_guided_nbody'
t = load(base / 'guided_solution.json')
source = base / 'celestia_addon/data/tianwen4_eveeju_guided_nbody.xyzv'
data = np.loadtxt(source, comments='#')
te = []
for e in t['actual_encounters']:
    jd = e['julian_date_tdb']
    r = [np.interp(jd, data[:, 0], data[:, j]) / AU for j in (1, 2, 3)]
    te.append(dict(body=e['event'].split()[0], jd=jd, date=e['calendar_tdb'],
                   kind='Departure' if not te else 'Arrival' if e['event'] == 'Uranus' else 'Flyby',
                   position_au=finite_round(r), altitude_km=e['altitude_km']))
tb = []
for b in t['impulses']:
    jd = float(b['julian_date_tdb'])
    tb.append(dict(body='TCM', kind=b['event'], jd=jd, date=b['calendar_tdb'], magnitude_mps=b['magnitude_mps'],
                   vector_kms=[b['dv_x_kms'], b['dv_y_kms'], b['dv_z_kms']],
                   position_au=finite_round([np.interp(jd, data[:, 0], data[:, j]) / AU for j in (1, 2, 3)])))
integrated('tianwen4-concept', 'Tianwen-4 · Uranus flyby branch', 'EVEEJU', source, te, tb,
           t['launch_c3_km2_s2'], float(np.sqrt(t['actual_encounters'][-1]['local_osculating_c3_km2_s2'])),
           t['total_post_launch_delta_v_mps'],
           'Reconstructed mission concept, not an official Tianwen-4 trajectory. Forward n-body flight with ideal targeting corrections, prescribed JPL ephemerides and heliocentric indirect terms. This file follows the Uranus flyby branch after Jupiter; it does not include the Jovian orbiter. Navigation uncertainty is not modeled. The curve continues to April 2045 after the March Uranus flyby.')

# Keep the portfolio's explicit deep links stable when refreshing route samples.
for pinned_id in ('45a45fc7816a','3ee87f3d91eb','4fed974cbffb'):
    previous=OUT/'data/cases'/(pinned_id+'.json')
    if previous.exists() and not any(c['id']==pinned_id for c in cases):
        pinned=load(previous)
        if not pinned.get('validation',{}).get('passed'):
            raise ValueError('Pinned portfolio candidate lacks admission: '+pinned_id)
        cases.append(pinned)

index = []
for c in cases:
    assert c['paths'] and c['c3'] >= 0
    save(OUT / 'data/cases' / (c['id'] + '.json'), c)
    thumbnail(c)
    index.append({k: c[k] for k in ('id', 'title', 'target', 'sequence', 'bodies', 'model', 'spotlight', 'start', 'end', 'launch_date', 'arrival_date', 'years', 'c3', 'vinf', 'burns_mps')})
save(OUT / 'data/index.json', dict(version=1, updated='2026-11-01', cases=index,
                                 coordinates='Heliocentric Ecliptic J2000', time_scale='TDB',
                                 generation='Curated and independently screened Lambert candidates, with original integrated mission concepts; no browser-side solver.',admission_policy=POLICY))
lambert_cases=[c for c in cases if not c['spotlight']]
save(OUT/'data/catalog_audit.json',dict(policy=POLICY,lambert_candidates=len(lambert_cases),integrated_concepts=2,
    all_published_lambert_candidates_pass=all(c['validation']['passed'] for c in lambert_cases),
    largest_unpowered_mismatch_mps=max(c['validation']['max_vinf_mismatch_mps'] for c in lambert_cases),
    largest_individual_dsm_mps=max(c['validation']['max_single_dsm_mps'] for c in lambert_cases),
    largest_coast_endpoint_error_km=max(c['validation']['max_coast_endpoint_error_km'] for c in lambert_cases),
    excluded_reason_counts=dict(rejected),routes_by_target={t:sorted({c['sequence'] for c in cases if c['target']==t}) for t in sorted({c['target'] for c in cases})}))
# Remove retired catalog artifacts, retaining the original project artwork.
ids = {c['id'] for c in cases}
for file in (OUT / 'data/cases').glob('*.json'):
    if file.stem not in ids:
        file.unlink()
        (OUT / 'images' / (file.stem + '.svg')).unlink(missing_ok=True)
print(json.dumps(dict(cases=len(cases), targets=dict(collections.Counter(c['target'] for c in cases)),
                      mars_grid_evaluations=len(mars), static_bytes=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())), indent=2))
