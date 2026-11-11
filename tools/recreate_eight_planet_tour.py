"""Reconstruct a supplied 1970--1988 all-eight-planet gravity-assist itinerary.

Runs locally. Horizons downloads occur only with --fetch; no uploads are made.
Example: python tools/recreate_eight_planet_tour.py --fetch --shooting --polish --window-days 35
"""
from pathlib import Path
import argparse, csv, json, math, sys, time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bootstrap
import numpy as np
from scipy.optimize import least_squares
from dynamics import lambert, flyby, kepler
from ephemeris import BODIES, Ephemerides, DAY, AU, MU_SUN, jd, calendar, fetch, atomic_json

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_DATE_LIST = [
    ('Earth', '1970-08-14'), ('Venus', '1970-12-13'),
    ('Mars', '1971-08-29'), ('Earth', '1972-03-26'),
    ('Venus', '1972-11-02'), ('Venus', '1973-06-15'),
    ('Mercury', '1974-07-25'), ('Venus', '1974-09-04'),
    ('Venus', '1975-04-18'), ('Venus', '1976-04-26'),
    ('Earth', '1978-08-07'), ('Jupiter', '1980-02-17'),
    ('Saturn', '1981-08-12'), ('Uranus', '1985-03-20'),
    ('Neptune', '1988-03-25'),
]
# Transcribed from the user's RSS/Principia maneuver/encounter table. The first
# Venus date corrects December 13 in the initial message to December 23.
# Launch time is inferred from TCM-1's clock and elapsed time, not directly shown.
EVENTS = [
    ('Earth','1970-08-14T08:04:00'), ('Venus','1970-12-23T07:15:00'),
    ('Mars','1971-08-29T23:34:00'), ('Earth','1972-03-26T11:24:00'),
    ('Venus','1972-11-02T01:32:00'), ('Venus','1973-06-15T13:17:00'),
    ('Mercury','1974-07-25T22:45:00'), ('Venus','1974-09-04T08:26:00'),
    ('Venus','1975-04-18T00:41:00'), ('Venus','1976-04-26T17:32:00'),
    ('Earth','1978-08-07T21:57:00'), ('Jupiter','1980-02-17T07:52:00'),
    ('Saturn','1981-08-12T22:38:00'), ('Uranus','1985-03-20T11:40:00'),
    ('Neptune','1988-03-25T18:34:00'),
]
SOURCE_ALTITUDES_KM = [None,10591.,2112.7,5902.,18042.,325.,2101.,1942.,261.7,623.,136.2,820164.,37145.,37447.,269264.]
SOURCE_TCM_KMS = [.0001,.000242,.00014,.0003,.000362,.00042,.00048,.00038,.000225,.0004,.0005,.00048,.000292,.000219]
CREDIT = 'Original RSS/Principia trajectory design by ReachStar on Bilibili; JPL recreation in RoLaMGAS.'
BASE = np.array([jd(d) for b, d in EVENTS])
FLOORS = {b: BODIES[b][3] for b, d in EVENTS}
# Research-only exceptions matching the particularly low passes in the source.
# These do not change the application defaults. No atmosphere/drag is modeled.
EVENT_FLOORS = {8:250.,10:130.}


def floor_at(index):
    return EVENT_FLOORS.get(index,FLOORS[EVENTS[index][0]])


def ephemerides(cache, padding=40., download=False):
    # Each body's coverage need only span its encounters, not all eighteen years.
    ep = Ephemerides(cache, [], BASE[0], BASE[-1])
    for body in dict(EVENTS):
        dates = [t for (b, _), t in zip(EVENTS, BASE) if b == body]
        lo, hi = min(dates)-padding, max(dates)+padding
        step = .25 if body == 'Mercury' else 1.
        try:
            sub = Ephemerides(cache, [body], lo, hi, step)
        except ValueError:
            if not download: raise
            fetch(cache, body, lo, hi, step)
            sub = Ephemerides(cache, [body], lo, hi, step)
        ep.splines.update(sub.splines); ep.manifest.update(sub.manifest)
        print('Ephemeris ready:', body, flush=True)
    return ep


def arcs(ep, dates, index, max_revs=6):
    a = ep.state(EVENTS[index][0], dates[index])
    b = ep.state(EVENTS[index+1][0], dates[index+1])
    result = []
    for m in range(max_revs+1):
        for low in ((True,) if m == 0 else (True, False)):
            try:
                v0, v1 = lambert(a[:3], b[:3], dates[index+1]-dates[index], (m, low))
            except (ValueError, RuntimeError, AssertionError, ZeroDivisionError): continue
            result.append(dict(branch=[m, low], depart=v0, arrive=v1,
                               outgoing=v0-a[3:], incoming=v1-b[3:]))
    if not result: raise ValueError(f'No Lambert solution on leg {index}')
    return result


def chain(ep, dates, branches):
    states = [ep.state(b, t) for (b, d), t in zip(EVENTS, dates)]
    legs = []
    for i, branch in enumerate(branches):
        va, vb = lambert(states[i][:3], states[i+1][:3], dates[i+1]-dates[i], branch)
        legs.append(dict(branch=list(branch), depart=va, arrive=vb,
                         outgoing=va-states[i][3:], incoming=vb-states[i+1][3:]))
    checks = [flyby(EVENTS[i][0], legs[i-1]['incoming'], legs[i]['outgoing'],
                    floor_at(i), .1) for i in range(1, len(EVENTS)-1)]
    return states, legs, checks


def branch_paths(ep, dates, keep=12, max_revs=6):
    """Dynamic programming retains the best prefixes ending in each leg branch."""
    layers = [arcs(ep, dates, i, max_revs) for i in range(len(EVENTS)-1)]
    paths = {j: [(0., [a['branch']])] for j, a in enumerate(layers[0])}
    for i in range(1, len(layers)):
        nxt = {}
        for j, after in enumerate(layers[i]):
            options = []
            for k, before in enumerate(layers[i-1]):
                f = flyby(EVENTS[i][0], before['incoming'], after['outgoing'], floor_at(i), .1)
                cost = ((f['vinf_in_kms']-f['vinf_out_kms'])/.2)**2 + (min(0., f['turn_margin_deg'])/2)**2
                for score, bb in paths[k]: options.append((score+cost, bb+[after['branch']]))
            nxt[j] = sorted(options, key=lambda p:p[0])[:keep]
        paths = nxt
    return sorted([p for ps in paths.values() for p in ps], key=lambda p:p[0])[:keep], layers


def report(ep, dates, branches, label, chain_data=None):
    states, legs, checks = chain(ep, dates, branches) if chain_data is None else chain_data
    c3 = float(legs[0]['outgoing'] @ legs[0]['outgoing'])
    mu, radius = BODIES['Earth'][1:3]; park = radius+200.
    injection = math.sqrt(2*mu/park+c3)-math.sqrt(mu/park)
    rows = []
    for i, ((body, supplied), date, state) in enumerate(zip(EVENTS, dates, states)):
        row = dict(body=body, supplied_date=supplied, date_tdb=calendar(date), julian_date_tdb=float(date),
                   shift_days=float(date-BASE[i]), source_altitude_km=SOURCE_ALTITUDES_KM[i],planet_state_km_kms=state.tolist())
        if 0<i<len(EVENTS)-1: row.update(checks[i-1])
        rows.append(row)
    return dict(label=label, sequence=''.join(dict(Earth='E', Venus='V', Mercury='Me', Mars='M', Jupiter='J', Saturn='S', Uranus='U', Neptune='N')[b] for b, d in EVENTS),
                launch_c3_km2_s2=c3, injection_200km_leo_kms=injection,
                duration_years=float((dates[-1]-dates[0])/365.25), arrival_vinf_kms=float(np.linalg.norm(legs[-1]['incoming'])),
                max_speed_mismatch_mps=max(f['speed_mismatch_mps'] for f in checks),
                total_speed_mismatch_mps=sum(f['speed_mismatch_mps'] for f in checks),
                minimum_turn_margin_deg=min(f['turn_margin_deg'] for f in checks),
                all_turns_above_floors=all(f['passes_turn_screen'] for f in checks),
                passes_unpowered_screen=all(f['passes_turn_screen'] and f['passes_speed_tolerance'] for f in checks),
                modeled_dsm_mps=0., nbody_validated=False,
                reference_source=CREDIT+' User-supplied encounter-table screenshot, not a flown mission.',
                reference_timescale='Unspecified game clock; treated as TDB for this reconstruction',
                inferred_launch_time=True, source_tcm_total_mps=1000*sum(SOURCE_TCM_KMS),
                research_altitude_exceptions_km={str(i):v for i,v in EVENT_FLOORS.items()},
                events=rows, branches=branches, dates_jd_tdb=np.asarray(dates).tolist(),
                segments=[dict(start_jd=float(dates[i]), end_jd=float(dates[i+1]), r=states[i][:3].tolist(), v=a['depart'].tolist()) for i,a in enumerate(legs)])


def fit_dates(ep, branches, window, start=None, max_nfev=1500):
    def residual(offsets):
        try:
            states, legs, checks = chain(ep, BASE+offsets, branches)
            speed = [(f['vinf_in_kms']-f['vinf_out_kms'])/.1 for f in checks]
            turn = [min(f['turn_margin_deg']-.02, 0.)/2 for f in checks]
            return np.r_[speed, turn]
        except (ValueError, RuntimeError, AssertionError, ZeroDivisionError):
            return np.full(2*(len(EVENTS)-2), 1.e5)
    initial = np.zeros(len(EVENTS)) if start is None else np.asarray(start)
    fit = least_squares(residual, np.clip(initial, -window+1e-8, window-1e-8), bounds=(-window, window),
                        diff_step=1e-4, x_scale='jac', max_nfev=max_nfev, ftol=1e-12, xtol=1e-12, gtol=1e-11)
    return BASE+fit.x, dict(cost=float(fit.cost), nfev=int(fit.nfev), message=fit.message)


RESONANT_LEGS = (4, 7)


def shooting_chain(ep, dates, branches, velocities):
    """Split resonant legs at halfway, explicitly charge the targeting impulse."""
    states = [ep.state(b, t) for (b, d), t in zip(EVENTS, dates)]
    legs, burns, segments = [], [], []
    for i, branch in enumerate(branches):
        duration = dates[i+1]-dates[i]
        if i in RESONANT_LEGS:
            va = np.asarray(velocities[RESONANT_LEGS.index(i)])
            rmid, before = kepler(states[i][:3], va, duration*.5*DAY)
            after, vb = lambert(rmid, states[i+1][:3], duration*.5, (0, True))
            burns.append(dict(leg_index=i, julian_date_tdb=float(dates[i]+duration*.5),
                              magnitude_kms=float(np.linalg.norm(after-before)),
                              delta_v_ecliptic_j2000_kms=(after-before).tolist(), position_km=rmid.tolist()))
            segments.extend([dict(start_jd=float(dates[i]),end_jd=float(dates[i]+duration*.5),r=states[i][:3].tolist(),v=va.tolist()),
                             dict(start_jd=float(dates[i]+duration*.5),end_jd=float(dates[i+1]),r=rmid.tolist(),v=after.tolist())])
        else:
            va, vb = lambert(states[i][:3], states[i+1][:3], duration, branch)
            segments.append(dict(start_jd=float(dates[i]),end_jd=float(dates[i+1]),r=states[i][:3].tolist(),v=va.tolist()))
        legs.append(dict(branch=list(branch),depart=va,arrive=vb,outgoing=va-states[i][3:],incoming=vb-states[i+1][3:]))
    checks = [flyby(EVENTS[i][0], legs[i-1]['incoming'], legs[i]['outgoing'], floor_at(i), .1)
              for i in range(1,len(EVENTS)-1)]
    return states, legs, checks, burns, segments


def shooting_fit(ep, branches, window, seed_report, attempts, output, max_nfev):
    rng=np.random.default_rng(1970)
    dates=np.array(seed_report['dates_jd_tdb'])
    if seed_report.get('resonant_departure_velocities_kms'):
        seed_states,seed_legs,seed_checks,_,_=shooting_chain(ep,dates,branches,seed_report['resonant_departure_velocities_kms'])
    else:
        seed_states,seed_legs,seed_checks=chain(ep,dates,branches)
    # Project an incoming excess velocity onto the one-Venus-year energy cone.
    guesses=[]
    for i in RESONANT_LEGS:
        s=seed_states[i];incoming=seed_legs[i-1]['incoming'];u=np.linalg.norm(incoming)
        axis=s[3:]/np.linalg.norm(s[3:]);parallel=-u*u/(2*np.linalg.norm(s[3:]))
        lateral=incoming-axis*(incoming@axis);lateral/=np.linalg.norm(lateral)
        excess=parallel*axis+math.sqrt(max(0.,u*u-parallel*parallel))*lateral
        guesses.append(s[3:]+excess)
    initial=np.r_[dates-BASE,np.array(guesses).ravel()]
    if seed_report.get('resonant_departure_velocities_kms'):
        initial[len(BASE):]=np.array(seed_report['resonant_departure_velocities_kms']).ravel()
    bounds=(np.r_[np.full(len(BASE),-window),np.full(6,-65.)],np.r_[np.full(len(BASE),window),np.full(6,65.)])
    def unpack(z):return BASE+z[:len(BASE)],z[len(BASE):].reshape(2,3)
    def residual(z, burn_scale=.01):
        try:
            d,v=unpack(z);states,legs,checks,burns,segments=shooting_chain(ep,d,branches,v)
            return np.r_[[(f['vinf_in_kms']-f['vinf_out_kms'])/.1 for f in checks],
                          [min(f['turn_margin_deg']-.05,0.)/2 for f in checks],
                          np.array([b['delta_v_ecliptic_j2000_kms'] for b in burns]).ravel()/burn_scale]
        except (ValueError,RuntimeError,AssertionError,ZeroDivisionError):return np.full(32,1e5)
    def jac(z,scale):
        # Fixed absolute date steps avoid JD-rounding noise at zero offsets.
        base=residual(z,scale);matrix=[]
        for i in range(len(z)):
            h=.0001 if i<len(BASE) else 1e-5
            trial=z.copy();trial[i]+=h
            matrix.append((residual(trial,scale)-base)/h)
        return np.array(matrix).T
    best=None
    for attempt in range(attempts):
        start=initial.copy()
        if attempt:
            start[:len(BASE)]+=rng.normal(0.,min(window/4,2.),len(BASE))
            for j,i in enumerate(RESONANT_LEGS):
                k=len(BASE)+j*3
                # Sample a different orientation of the excess-velocity cone.
                axis=seed_states[i][3:]/np.linalg.norm(seed_states[i][3:]);ex=start[k:k+3]-seed_states[i][3:]
                beta=rng.uniform(-1.2,1.2)
                ex=ex*math.cos(beta)+np.cross(axis,ex)*math.sin(beta)+axis*(axis@ex)*(1-math.cos(beta))
                start[k:k+3]=seed_states[i][3:]+ex
        z=np.clip(start,bounds[0]+1e-7,bounds[1]-1e-7)
        for scale in (.1,.01,.001):
            fit=least_squares(lambda x:residual(x,scale),z,jac=lambda x:jac(x,scale),bounds=bounds,
                              x_scale='jac',max_nfev=max_nfev,ftol=1e-11,xtol=1e-11,gtol=1e-10)
            z=fit.x
            print('  stage',attempt,scale,'cost',float(fit.cost),'evaluations',fit.nfev,flush=True)
        d,v=unpack(z);states,legs,checks,burns,segments=shooting_chain(ep,d,branches,v)
        q=report(ep,d,branches,f'Resonant shooting family {attempt}, ±{window:g} days',(states,legs,checks))
        for row,f in zip(q['events'][1:-1],checks):row.update(f)
        q.update(segments=segments,dsms=burns,modeled_dsm_mps=sum(b['magnitude_kms']*1000 for b in burns),
                 resonant_departure_velocities_kms=v.tolist(),
                 max_speed_mismatch_mps=max(f['speed_mismatch_mps'] for f in checks),
                 total_speed_mismatch_mps=sum(f['speed_mismatch_mps'] for f in checks),
                 minimum_turn_margin_deg=min(f['turn_margin_deg'] for f in checks),
                 all_turns_above_floors=all(f['passes_turn_screen'] for f in checks),
                 passes_unpowered_screen=all(f['passes_turn_screen'] and f['passes_speed_tolerance'] for f in checks),
                 fit=dict(cost=float(fit.cost),nfev=int(fit.nfev)))
        atomic_json(output/f'shooting_{attempt}.json',q)
        rank=lambda q:(not q['all_turns_above_floors'],q['max_speed_mismatch_mps']+q['modeled_dsm_mps'])
        if best is None or rank(q)<rank(best):
            best=q;atomic_json(output/'best_shooting.json',q)
            if attempt==0 or rng.random()<.7:initial=z.copy()
        print('SHOOT',attempt,'C3',q['launch_c3_km2_s2'],'max mismatch m/s',q['max_speed_mismatch_mps'],
              'TCMs m/s',q['modeled_dsm_mps'],'turn margin',q['minimum_turn_margin_deg'],flush=True)
        if q['passes_unpowered_screen'] and q['modeled_dsm_mps']<10.:break
    return best


def plots(q, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(14, 6.5))
    colors = plt.get_cmap('turbo')(np.linspace(.05,.95,len(q['segments'])))
    end=np.array(q['events'][-1]['planet_state_km_kms'][:2])
    angle=-math.atan2(end[1],end[0]);rotation=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
    for i, (s, color) in enumerate(zip(q['segments'], colors)):
        ts = np.linspace(0., (s['end_jd']-s['start_jd'])*DAY, 1200)
        positions = np.array([kepler(np.array(s['r']), np.array(s['v']), t)[0]/AU for t in ts])
        if s['end_jd']<=q['dates_jd_tdb'][10]+1e-9:
            axes[0].plot(positions[:,0],positions[:,1],color=color,lw=1.1)
        rotated=positions[:,:2]@rotation.T
        axes[1].plot(rotated[:,0],rotated[:,1],color=color,lw=1.1)
    offsets={0:(18,-19),1:(-40,32),2:(8,-8),3:(-28,4),4:(-38,17),5:(0,30),6:(7,7),7:(-40,0),8:(-20,-18),9:(7,7),10:(20,2)}
    for i, event in enumerate(q['events']):
        r = np.array(event['planet_state_km_kms'][:3])/AU
        if i<=10:
            axes[0].scatter(*r[:2],s=18,color=colors[min(i,len(colors)-1)])
            axes[0].annotate(f"{i} {event['body']}",r[:2],xytext=offsets[i],textcoords='offset points',fontsize=7,
                             arrowprops=dict(arrowstyle='-',lw=.4,color='.4'))
        rotated=rotation@r[:2]
        if i>=11:
            axes[1].scatter(*rotated,s=22,color=colors[min(i,len(colors)-1)])
            axes[1].annotate(f"{event['body']}\n{event['date_tdb'][:10]}",rotated,xytext=(-5,14),textcoords='offset points',fontsize=8,ha='center')
    for ax in axes:
        ax.scatter(0,0,c='gold',s=60);ax.grid(alpha=.2)
    axes[0].set_aspect('equal',adjustable='box');axes[1].set_aspect('equal',adjustable='datalim')
    axes[0].set(xlim=(-1.8,1.8),ylim=(-1.8,1.8),xlabel='Ecliptic J2000 x (AU)',ylabel='Ecliptic J2000 y (AU)',title='Inner encounters, numbered in time order')
    axes[1].set(xlabel='Rotated ecliptic x (AU)',ylabel='Rotated ecliptic y (AU)',title='Full route, view rotated toward Neptune')
    fig.suptitle(f"All eight planets | C3 {q['launch_c3_km2_s2']:.3f} km²/s² | {q['duration_years']:.2f} years\nSolar patched-conic screen with two explicitly charged resonance corrections",fontsize=12)
    fig.text(.5,.02,'JPL-based date-adjusted recreation. Flyby altitudes are inferred asymptotic geometry; atmosphere, moons and n-body navigation are not modeled.',ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.05,1,.94));fig.savefig(output/'trajectory.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,6))
    labels=[f"{i} {e['body']}" for i,e in enumerate(q['events'])]
    shifts=[e['shift_days'] for e in q['events']]
    axes[0].barh(np.arange(len(labels)),shifts,color='#337bb6');axes[0].set_yticks(np.arange(len(labels)),labels)
    axes[0].invert_yaxis();axes[0].axvline(0,c='.3',lw=.7);axes[0].set(xlabel='Recreation minus source date (days)',title='Encounter timing comparison')
    for i,e in enumerate(q['events'][1:-1],1):
        axes[1].scatter(e['source_altitude_km'],i,c='#d58025',marker='x',s=40,label='Source table' if i==1 else None)
        axes[1].scatter(e['conservative_equal_speed_altitude_km'],i,c='#337bb6',s=20,label='Inferred JPL recreation' if i==1 else None)
    axes[1].set_xscale('log');axes[1].set_yticks(np.arange(1,len(labels)-1),labels[1:-1]);axes[1].invert_yaxis()
    axes[1].set(xlabel='Flyby altitude (km, log scale)',title='Geometric flyby altitude comparison');axes[1].legend(fontsize=8)
    for ax in axes:ax.grid(axis='x',alpha=.2)
    fig.tight_layout();fig.savefig(output/'encounter_comparison.png',dpi=170);plt.close(fig)


def write_report(q,output):
    columns=['body','supplied_date','date_tdb','julian_date_tdb','shift_days','source_altitude_km','vinf_in_kms','vinf_out_kms','speed_mismatch_mps','turn_angle_deg','conservative_equal_speed_altitude_km','minimum_altitude_km','passes_turn_screen']
    with (output/'encounters.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(q['events'])
    lines=['# Eight-planet RSS/Principia itinerary: JPL patched-conic recreation','',
           CREDIT,'',
           'This is a date-adjusted reconstruction of a user-supplied game trajectory, not a flown mission or an exact Principia replay.',
           '',f"C3: **{q['launch_c3_km2_s2']:.6f} km²/s²**. Impulsive injection from 200 km circular Earth orbit: **{q['injection_200km_leo_kms']:.6f} km/s**. Duration: **{q['duration_years']:.5f} years**.",
           '',f"The two explicitly modeled solar midpoint corrections total **{q['modeled_dsm_mps']:.6f} m/s**. This is not the n-body navigation budget. The source table's fourteen TCMs total **4.54 m/s**.",
           '',f"Largest flyby excess-speed mismatch: **{q['max_speed_mismatch_mps']:.8f} m/s**. All configured flyby turns pass: **{q['all_turns_above_floors']}**.",
           '', 'The screenshot corrects the first Venus flyby from December 13 to **December 23, 1970**. Its launch time is inferred from TCM-1 and elapsed time. The game clock time scale is unspecified; its printed times are treated as TDB here.',
           '', 'Research exceptions: the 1975 Venus floor is 250 km and the 1978 Earth floor is 130 km, following the particularly low source passes (261.7 and 136.2 km). Application and public-library defaults remain unchanged. Atmospheric drag, heating, terrain, moon encounters and navigation uncertainty are excluded.',
           '', 'The saved coast segments meet at ideal planet-center nodes. Inferred periapses screen whether unpowered asymptotes can turn sufficiently; they are not resolved finite-radius flybys. Do not use these center-node coasts as a ready-to-render collision-free Celestia addon. Desktop finite-radius export is a separate calculation and may add corrections.',
           '', '![Trajectory](trajectory.png)', '', '![Timing and altitudes](encounter_comparison.png)', '',
           '| Encounter | Source table | JPL recreation (TDB) | Shift (days) | Inferred altitude (km) |',
           '|---|---|---|---:|---:|']
    for i,e in enumerate(q['events']):
        altitude=e.get('conservative_equal_speed_altitude_km');alt='—' if altitude is None else f'{altitude:,.2f}'
        lines.append(f"| {i} {e['body']} | {e['supplied_date'].replace('T',' ')} | {e['date_tdb'].removesuffix(' TDB').replace('T',' ')} | {e['shift_days']:+.5f} | {alt} |")
    lines += ['', 'Files: `best.json` is the shooting result; `candidate.json` is the normal desktop-model recomputation; `selected-trajectory.json` imports the exact saved candidate into RoLaMGAS; `validation.json` contains independent solar integrations, scalar-vector checks and desktop re-import checks. The separate standard public-catalog audit retains its stricter default altitude floors.',
              '', 'Offline verification from the repository root:', '', '```powershell',
              '.venv\\Scripts\\python.exe tools/recreate_eight_planet_tour.py --audit-json studies/eight_planet_tour/verified_source_recreation/best.json --output runs/eight_planet_recheck',
              '```', '', 'Add `--fetch` if the historical ephemeris cache is missing. For a fresh local exploration use `--fetch --shooting --polish --window-days 35 --attempts 4`; failed trials are saved with their actual mismatches and constraints. For constrained refinement of this saved result use `--seed-json studies/eight_planet_tour/verified_source_recreation/best.json --polish --window-days 35 --output runs/eight_planet_refine`. No AI service or trajectory upload is involved.', '']
    (output/'README.md').write_text('\n'.join(lines),encoding='utf-8')


def save_app_candidate(q, ep, output):
    """Recompute the shooting solution through the normal desktop Model/import."""
    import hashlib
    from dynamics import Model
    from mission_search import normalize, routes_for
    from community import record_variables
    from search_options import export_options
    from trajectory_transfer import materialize
    from study_resonant_transfers import physical_record, audit_coasts
    from catalog_validation import audit_candidate
    dates=np.array(q['dates_jd_tdb']);velocities=np.array(q['resonant_departure_velocities_kms'])
    seq='EVMEVdvVMeVdvVVEJSUN'
    branches=list(q['branches']);controls=[]
    for j,i in enumerate(RESONANT_LEGS):
        candidates=arcs(ep,dates,i)
        chosen=min(candidates,key=lambda a:np.linalg.norm(a['depart']-velocities[j]))
        branches[i]=chosen['branch']
        controls.append(dict(leg_index=i,fraction=.5,departure_offset_kms=(velocities[j]-chosen['depart']).tolist()))
    windows=[[calendar(d-.25).split(' TDB')[0],calendar(d+.25).split(' TDB')[0]] for d in dates]
    c=normalize(dict(target='Neptune',sequences=[seq],launch_start=windows[0][0],launch_end=windows[0][1],
                     event_windows=windows,min_c3=5.,max_c3=20.,max_dsm_kms=.005,max_single_dsm_kms=.005,
                     max_arrival_vinf_kms=25.,max_years=19.,vinf_tolerance_mps=.1,dsm_velocity_box_kms=60.,
                     minimum_altitude_km={'Earth':130.,'Venus':250.},cache=str(ROOT/'cache'),
                     route_overrides={seq:dict(leg_days=[[max(1.,d*.8),d*1.2+1] for d in np.diff(dates)],
                                               branch_options=[[b] for b in branches])}))
    route=routes_for(c)[0];model=Model(route,c,ep)
    record=dict(schema_version=1,sequence=seq,body_ids=[str(BODIES[b][0]) for b,d in EVENTS],
                dates_jd_tdb=dates.tolist(),branches=branches,dsm_controls=controls)
    x,bb=record_variables(record,model);candidate=model.evaluate(x,bb)
    candidate['id']=hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:12]
    candidate['status']='passes_configured_patched_conic_screen' if model.accepted(candidate) else 'near_miss_not_accepted'
    candidate['reference_note']='RSS/Principia all-eight-planet itinerary reconstruction; solar patched-conic screen only. Research altitude floors Earth 130 km, Venus 250 km; atmosphere and moons excluded.'
    candidate=json.loads(json.dumps(candidate,allow_nan=False))
    # Keep the public catalog's usual conservative floors visible. This research
    # recreation explicitly follows the source's lower Earth/Venus passes.
    catalog_audit=audit_candidate(candidate,c,BODIES)
    research_bodies={b:(data[0],data[1],data[2],c['minimum_altitude_km'].get(b,data[3])) for b,data in BODIES.items()}
    audit=audit_candidate(candidate,c,research_bodies);coasts=audit_coasts(candidate)
    if not model.accepted(candidate) or not audit['passed'] or not coasts['passed']:
        raise ValueError(dict(model_accepted=model.accepted(candidate),vector_audit=audit,independent_coasts=coasts))
    record=physical_record(candidate,c)
    reimport=materialize(record,c,route,ep)
    if reimport['status']!='passes_configured_patched_conic_screen':raise ValueError('Desktop re-import did not pass')
    document=export_options(c)['document'];document['trajectory']=record
    document['display_name']='Eight-planet RSS/Principia recreation';document['source_candidate_id']=candidate['id']
    atomic_json(output/'selected-trajectory.json',document)
    atomic_json(output/'candidate.json',candidate)
    atomic_json(output/'run_manifest.json',dict(config=c))
    atomic_json(output/'validation.json',dict(research_vector_audit=audit,standard_catalog_audit=catalog_audit,
                                             independent_coasts=coasts,desktop_reimport=reimport['import_verification']))
    print('DESKTOP',candidate['id'],'independent coast error km',coasts['maximum_dop853_endpoint_error_km'],flush=True)
    return candidate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache', type=Path, default=ROOT/'cache')
    p.add_argument('--output', type=Path, default=ROOT/'studies/eight_planet_tour/source_table')
    p.add_argument('--fetch', action='store_true');p.add_argument('--fit',action='store_true')
    p.add_argument('--shooting',action='store_true');p.add_argument('--attempts',type=int,default=8)
    p.add_argument('--seed-json',type=Path)
    p.add_argument('--polish',action='store_true',help='Constrained speed-equality and altitude-floor refinement')
    p.add_argument('--polish-iterations',type=int,default=600)
    p.add_argument('--audit-json',type=Path,help='Audit and package an already computed shooting result without another search')
    p.add_argument('--window-days', type=float, default=1.)
    p.add_argument('--paths',type=int,default=8);p.add_argument('--max-nfev',type=int,default=1500)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    if not 0<a.window_days<=35:raise ValueError('Date window must be in (0,35] days')
    if min(a.paths,a.attempts,a.max_nfev,a.polish_iterations)<1:raise ValueError('Search and refinement counts must be positive')
    ep=ephemerides(a.cache,40.,a.fetch)
    atomic_json(a.output/'ephemeris_manifest.json',ep.manifest)
    if a.audit_json:
        seed=json.loads(a.audit_json.read_text(encoding='utf-8'))
        dates=np.array(seed['dates_jd_tdb']);v=seed['resonant_departure_velocities_kms']
        states,legs,checks,burns,segments=shooting_chain(ep,dates,seed['branches'],v)
        best=report(ep,dates,seed['branches'],'Audited source-table reconstruction',(states,legs,checks))
        best.update(segments=segments,dsms=burns,modeled_dsm_mps=sum(b['magnitude_kms']*1000 for b in burns),resonant_departure_velocities_kms=v)
        if 'fit' in seed:best['fit']=seed['fit']
        atomic_json(a.output/'best.json',best)
        save_app_candidate(best,ep,a.output)
        plots(best,a.output)
        write_report(best,a.output)
        return
    paths,layers=branch_paths(ep,BASE,a.paths)
    atomic_json(a.output/'branch_choices.json',dict(leg_counts=[len(layer) for layer in layers],paths=paths))
    initial=report(ep,BASE,paths[0][1],'Best fixed source-time Lambert branch chain')
    atomic_json(a.output/'fixed_dates.json',initial)
    print('FIXED',json.dumps({k:v for k,v in initial.items() if k not in ('events','branches','segments','dates_jd_tdb')}),flush=True)
    best=initial
    if a.shooting:
        seed=json.loads(a.seed_json.read_text(encoding='utf-8')) if a.seed_json else initial
        best=shooting_fit(ep,seed['branches'],a.window_days,seed,a.attempts,a.output,a.max_nfev)
    elif a.seed_json:
        best=json.loads(a.seed_json.read_text(encoding='utf-8'))
    if a.fit:
        for index,(score,branches) in enumerate(paths):
            dates,stats=fit_dates(ep,branches,a.window_days,max_nfev=a.max_nfev)
            q=report(ep,dates,branches,f'Date fit ±{a.window_days:g} days, branch family {index}')
            q['fit']=stats;atomic_json(a.output/f'fit_{index}.json',q)
            rank=lambda r:(not r['all_turns_above_floors'],r['total_speed_mismatch_mps'])
            if rank(q)<rank(best):best=q
            print('FIT',index,'C3',q['launch_c3_km2_s2'],'max mismatch',q['max_speed_mismatch_mps'],'sum',q['total_speed_mismatch_mps'],'turn margin',q['minimum_turn_margin_deg'],stats,flush=True)
            if q['passes_unpowered_screen']:break
    if a.polish:
        if not best.get('resonant_departure_velocities_kms'):raise ValueError('Polish requires --shooting or a shooting result supplied by --seed-json')
        from eight_planet_polish import polish
        best=polish(ep,best,a.window_days,a.polish_iterations,a.output/'polish_checkpoint.json')
    atomic_json(a.output/'best.json',best)
    if best['passes_unpowered_screen'] and best.get('resonant_departure_velocities_kms'):
        save_app_candidate(best,ep,a.output)
    plots(best,a.output)
    write_report(best,a.output)
    print('Saved:',a.output,flush=True)


if __name__=='__main__':main()
