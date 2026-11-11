"""Fast two-body propagation and arbitrary Lambert/DSM chains."""
import bootstrap  # noqa: F401
import math
from copy import deepcopy
import numpy as np
from numba import njit
from lamberthub import izzo2015
from ephemeris import AU, DAY, MU_SUN, BODIES, calendar


@njit(cache=True)
def stumpff(z):
    if z > 1e-7:
        s = math.sqrt(z)
        return (1 - math.cos(s)) / z, (s - math.sin(s)) / (s * s * s)
    if z < -1e-7:
        s = math.sqrt(-z)
        if s > 600:
            raise ValueError('Unbound propagation overflow')
        return (math.cosh(s) - 1) / (-z), (math.sinh(s) - s) / (s * s * s)
    return 0.5 - z / 24 + z*z / 720, 1/6 - z / 120 + z*z / 5040


@njit(cache=True)
def kepler(r0, v0, dt, mu=MU_SUN):
    """Universal-variable Kepler propagation with bracketed Newton iterations."""
    if dt == 0:
        return r0.copy(), v0.copy()
    direction = 1. if dt >= 0 else -1.
    v0 = v0 * direction
    dt = abs(dt)
    radius = np.linalg.norm(r0)
    root = math.sqrt(mu)
    rv = np.dot(r0, v0) / root
    alpha = 2 / radius - np.dot(v0, v0) / mu
    lo = 0.
    hi = max(root * dt / radius, 1.)
    if alpha < -1e-14:
        # Escaping trajectories need a logarithmic anomaly guess. The linear
        # guess can require hundreds of Newton steps on decades-long legs.
        length = 1 / math.sqrt(-alpha)
        hi = max(length * math.asinh(root*dt/(radius*length)),1.)
    for _ in range(80):
        c, s = stumpff(alpha * hi * hi)
        value = rv*hi*hi*c + (1-alpha*radius)*hi**3*s + radius*hi - root*dt
        if value >= 0:
            break
        hi *= 2
    else:
        raise ValueError('Cannot bracket Kepler solution')
    x = (lo + hi) / 2
    for _ in range(120):
        z = alpha*x*x
        c, s = stumpff(z)
        value = rv*x*x*c + (1-alpha*radius)*x**3*s + radius*x - root*dt
        if abs(value) < max(root * 1e-6,abs(root*dt)*4e-14):
            break
        if value > 0:
            hi = x
        else:
            lo = x
        derivative = rv*x*(1-z*s) + (1-alpha*radius)*x*x*c + radius
        trial = x - value / derivative
        x = trial if lo < trial < hi else (lo + hi) / 2
    else:
        raise ValueError('Kepler iteration failed')
    f = 1 - x*x*c / radius
    g = dt - x**3*s / root
    r = f*r0 + g*v0
    rr = np.linalg.norm(r)
    fdot = root / (rr*radius) * (alpha*x**3*s-x)
    gdot = 1 - x*x*c / rr
    return r, (fdot*r0 + gdot*v0)*direction


def lambert(r0, r1, days, branch):
    # Legacy two-value branches keep their historical prograde meaning.
    m, low = branch[:2]
    prograde = bool(branch[2]) if len(branch)>2 else True
    return izzo2015(MU_SUN, r0, r1, days*DAY, M=int(m), prograde=prograde,
                    low_path=bool(low), maxiter=60, atol=1e-10, rtol=1e-11)


def flyby(body, incoming, outgoing, floor, tolerance):
    _, mu, radius, _ = BODIES[body]
    a, b = float(np.linalg.norm(incoming)), float(np.linalg.norm(outgoing))
    if min(a, b) < 1e-8:
        raise ValueError('Degenerate zero-speed hyperbolic flyby')
    angle = float(np.arctan2(np.linalg.norm(np.cross(incoming, outgoing)), np.dot(incoming, outgoing)))
    # Use the larger speed for a conservative unpowered-turn screen.
    u = max(a, b)
    dmax = float(2*np.arcsin(1/(1+(radius+floor)*u*u/mu)))
    rp = float(mu/u**2 * (1/np.sin(angle/2)-1)) if angle > 1e-12 else None
    mismatch = abs(a-b)
    return dict(body=body, vinf_in_kms=a, vinf_out_kms=b, speed_mismatch_mps=1000*mismatch,
                incoming_vinf_vector_kms=incoming.tolist(), outgoing_vinf_vector_kms=outgoing.tolist(),
                turn_angle_deg=float(np.degrees(angle)), max_turn_deg=float(np.degrees(dmax)),
                turn_margin_deg=float(np.degrees(dmax-angle)), minimum_altitude_km=floor,
                conservative_equal_speed_periapsis_km=rp,
                conservative_equal_speed_altitude_km=None if rp is None else rp-radius,
                speed_matched_to_1_mm_s=mismatch <= 1e-6,
                passes_speed_tolerance=mismatch <= tolerance/1000,
                passes_turn_screen=dmax >= angle - 1e-10)


HARD_MIN_C3=5.0  # Application search policy, including legacy import/export paths.
DEFAULT_MIN_C3=6.25  # Retain the existing departure-energy default for EEV seeds.


def supported_launch_energy(energy):
    return isinstance(energy,(int,float)) and math.isfinite(energy) and energy>=HARD_MIN_C3


class C3BoundsError(ValueError):
    """Rejected after the first-leg energy calculation, before a chain is solved."""
    def __init__(self,c3,minimum,maximum):
        self.c3,self.minimum,self.maximum=float(c3),float(minimum),float(maximum)
        super().__init__(f'Launch C3 {c3:.12g} is outside [{minimum:.12g}, {maximum:.12g}] km²/s²')


class Model:
    def __init__(self, route, config, ephemerides):
        self.route, self.config, self.ep = route, config, ephemerides
        self.bodies = route['bodies']
        self.n = len(self.bodies)
        self.dsm_legs = route.get('dsm_legs', [])
        self.dimension = self.n + 4*len(self.dsm_legs)
        self.extension=config.get('append_flyby')
        self.prefix_count=self.extension['prefix_count'] if self.extension else 1
        self.free_indices=np.arange(self.dimension)
        self._launch_cache={}
        self.c3_preflight_evaluations=0
        self.c3_pruned_evaluations=0
        if self.extension:
            n0=self.prefix_count
            new_dsms=[i for i,leg in enumerate(self.dsm_legs) if leg>=n0-1]
            self.free_indices=np.array(list(range(n0,self.n))+[self.n+4*i+j for i in new_dsms for j in range(4)],dtype=int)

    def expand_variables(self,values):
        if not self.extension:return np.asarray(values)
        x=np.array(self.extension['seed_x'],dtype=float);x[self.free_indices]=values
        return x

    def active_variables(self,values):return np.asarray(values)[self.free_indices]

    def dates(self, x):
        if self.extension:
            dates=list(self.extension['prefix']['dates_jd_tdb'])
            for i in range(self.prefix_count,self.n):
                if self.config.get('event_windows_jd'):
                    a,b=self.config['event_windows_jd'][i];dates.append(a+x[i]*(b-a))
                else:
                    a,b=self.route['leg_days'][i-1];dates.append(dates[-1]+a+x[i]*(b-a))
            if self.config.get('arrival_window_jd') and not self.config.get('event_windows_jd'):
                a,b=self.config['arrival_window_jd'];dates[-1]=a+x[self.n-1]*(b-a)
            return dates
        launch = self.config['launch_jd']
        dates = [launch[0] + x[0]*(launch[1]-launch[0])]
        if self.config.get('event_windows_jd'):
            windows = self.config['event_windows_jd']
            dates = [a + v*(b-a) for v, (a, b) in zip(x[:self.n], windows)]
        else:
            for v, (a, b) in zip(x[1:self.n], self.route['leg_days']):
                dates.append(dates[-1] + a + v*(b-a))
            if self.config.get('arrival_window_jd'):
                a,b=self.config['arrival_window_jd'];dates[-1]=a+x[self.n-1]*(b-a)
        return dates

    @property
    def c3_minimum(self):return max(HARD_MIN_C3,float(self.config.get('effective_min_c3',self.config.get('min_c3',DEFAULT_MIN_C3))))

    @property
    def c3_maximum(self):
        from trajectory_policy import c3_ceiling
        return c3_ceiling(self.bodies,self.config)

    def c3_in_bounds(self,energy):
        return (math.isfinite(energy) and self.c3_minimum-1e-8<=energy<=self.c3_maximum+1e-8)

    def launch_solution(self,x,branches):
        """Only the launch leg; no later ephemerides, DSM shooting or flyby work."""
        if self.extension:
            p=self.extension['prefix']
            return dict(c3=float(p['launch_c3_km2_s2']))
        dates=self.dates(x)
        if dates[1]-dates[0]<=1e-6:raise ValueError('Nonpositive first-leg time of flight')
        offset=np.zeros(3)
        if 0 in self.dsm_legs:
            k=self.n+4*self.dsm_legs.index(0)
            offset=(np.asarray(x[k+1:k+4])*2-1)*self.config['dsm_velocity_box_kms']
        key=(dates[0],dates[1],*branches[0],*offset)
        if key in self._launch_cache:return self._launch_cache[key]
        a,b=(self.ep.state(body,date) for body,date in zip(self.bodies[:2],dates[:2]))
        va,vb=lambert(a[:3],b[:3],dates[1]-dates[0],branches[0])
        velocity=va+offset-a[3:];energy=float(velocity@velocity)
        if not math.isfinite(energy):raise ValueError('Nonfinite launch energy')
        result=dict(c3=energy,states=(a,b),va=va,vb=vb)
        self.c3_preflight_evaluations+=1
        if len(self._launch_cache)>=256:self._launch_cache.pop(next(iter(self._launch_cache)))
        self._launch_cache[key]=result
        return result

    def launch_c3(self,x,branches):return self.launch_solution(x,branches)['c3']

    def evaluate(self, x, branches,enforce_c3=True):
        if self.extension:
            x=self.expand_variables(self.active_variables(x))
            if [list(b) for b in branches[:self.prefix_count-1]]!=self.extension['prefix']['branches']:
                raise ValueError('Original Lambert branches cannot change')
        dates = self.dates(x)
        if min(np.diff(dates)) <= 1e-6:
            raise ValueError('Nonpositive time of flight')
        launch_preflight=self.launch_solution(x,branches)
        # Imports/exports may inspect candidates outside the user's requested
        # interval, but must never bypass the application's absolute floor.
        if (not supported_launch_energy(launch_preflight['c3'])
                or (enforce_c3 and not self.c3_in_bounds(launch_preflight['c3']))):
            self.c3_pruned_evaluations+=1
            raise C3BoundsError(launch_preflight['c3'],self.c3_minimum if enforce_c3 else HARD_MIN_C3,
                                self.c3_maximum if enforce_c3 else float('inf'))
        if self.extension:
            states=[self.ep.state(body,date) for body,date in zip(self.bodies,dates)]
        else:
            states=list(launch_preflight['states'])+[self.ep.state(body,date) for body,date in zip(self.bodies[2:],dates[2:])]
        segments, dep, arr, burns = [], [], [], []
        first_leg=0
        if self.extension:
            prefix=self.extension['prefix'];first_leg=self.prefix_count-1
            states[:self.prefix_count]=[np.asarray(e['planet_state_km_kms']) for e in prefix['events']]
            segments=deepcopy(prefix['segments']);burns=deepcopy(prefix['dsms'])
            dep=[np.asarray(v) for v in prefix['departure_velocities_kms']]
            arr=[np.asarray(v) for v in prefix['arrival_velocities_kms']]
        for i in range(first_leg,self.n-1):
            r0, r1 = states[i][:3], states[i+1][:3]
            duration = dates[i+1]-dates[i]
            va,vb=(launch_preflight['va'],launch_preflight['vb']) if i==0 else lambert(r0,r1,duration,branches[i])
            if i in self.dsm_legs:
                k = self.n + 4*self.dsm_legs.index(i)
                fraction = 0.1 + 0.8*x[k]
                offset = (np.array(x[k+1:k+4])*2-1)*self.config['dsm_velocity_box_kms']
                va = va + offset
                dt = duration*fraction
                rd, before = kepler(r0, va, dt*DAY)
                after, vb = lambert(rd, r1, duration-dt, (0, True, branches[i][2]) if len(branches[i])>2 else (0, True))
                vector = after-before
                burns.append(dict(leg_index=i, julian_date_tdb=dates[i]+dt,
                                  date=calendar(dates[i]+dt), magnitude_kms=float(np.linalg.norm(vector)),
                                  delta_v_ecliptic_j2000_kms=vector.tolist(), position_km=rd.tolist()))
                segments.extend([dict(start_jd=dates[i], end_jd=dates[i]+dt, r=r0.tolist(), v=va.tolist()),
                                 dict(start_jd=dates[i]+dt, end_jd=dates[i+1], r=rd.tolist(), v=after.tolist())])
            else:
                segments.append(dict(start_jd=dates[i], end_jd=dates[i+1], r=r0.tolist(), v=va.tolist()))
            dep.append(va)
            arr.append(vb)
        flybys = deepcopy(self.extension['prefix']['flybys']) if self.extension else []
        event_burns=deepcopy(self.extension['prefix'].get('event_burns',[])) if self.extension else []
        for i in range(max(1,first_leg), self.n-1):
            body = self.bodies[i]
            if body not in BODIES:
                vector=dep[i]-arr[i-1]
                event_burns.append(dict(kind='target_turnaround',body=body,event_index=i,
                    julian_date_tdb=dates[i],date=calendar(dates[i]),position_km=states[i][:3].tolist(),
                    magnitude_kms=float(np.linalg.norm(vector)),delta_v_ecliptic_j2000_kms=vector.tolist(),
                    incoming_heliocentric_velocity_kms=arr[i-1].tolist(),outgoing_heliocentric_velocity_kms=dep[i].tolist(),
                    model='Explicit heliocentric velocity-change impulse at a zero-GM point encounter; no target gravity or free assist is assumed.'))
                continue
            floor = self.config['minimum_altitude_km'].get(body, BODIES[body][3])
            f = flyby(body, arr[i-1]-states[i][3:], dep[i]-states[i][3:], floor,
                      self.config['vinf_tolerance_mps'])
            f.update(event_index=i, julian_date_tdb=dates[i], date=calendar(dates[i]))
            if self.config.get('powered_flybys'):
                from powered_flyby import geometry
                try:
                    mu,radius=BODIES[body][1:3]
                    soi=np.linalg.norm(states[i][:3])*(mu/MU_SUN)**.4
                    power=geometry(mu,radius+floor,arr[i-1]-states[i][3:],dep[i]-states[i][3:],.799*soi)
                    power['altitude_km']=power['periapsis_radius_km']-radius
                    f['powered_flyby']=power
                    f['passes_powered_geometry']=True
                except ValueError as exc:
                    f['passes_powered_geometry']=False;f['powered_geometry_error']=str(exc)
            f['maneuver_status']='powered' if f.get('passes_powered_geometry') else ('unpowered_exact_speed_match' if f['speed_matched_to_1_mm_s'] and f['passes_turn_screen'] else ('unpowered_within_tolerance' if f['passes_speed_tolerance'] and f['passes_turn_screen'] else 'unresolved'))
            flybys.append(f)
        launch = dep[0]-states[0][3:]
        terminal = arr[-1]-states[-1][3:]
        c3 = float(launch @ launch)
        if not math.isfinite(c3) or not np.all(np.isfinite(terminal)):
            raise ValueError('Nonfinite launch or arrival velocity')
        vinf = float(np.linalg.norm(terminal))
        total_dsm = sum(b['magnitude_kms'] for b in burns)
        cruise_dsm=total_dsm
        turnaround_dv=sum(b['magnitude_kms'] for b in event_burns)
        total_dsm+=turnaround_dv
        powered_dv=sum(f.get('powered_flyby',{}).get('magnitude_kms',0.) for f in flybys)
        total_dsm+=powered_dv
        mismatch_sum=sum(f['speed_mismatch_mps'] for f in flybys if not f.get('passes_powered_geometry'))
        screening_total=total_dsm+mismatch_sum/1000.
        unresolved=[f for f in flybys if not f.get('passes_powered_geometry') and not (f['speed_matched_to_1_mm_s'] and f['passes_turn_screen'])]
        extension_source=None
        if self.extension:
            p=self.extension['prefix']
            extension_source=dict(parent_run=self.extension['parent_run'],parent_candidate=p['id'],
                frozen_encounters=self.prefix_count,original_arrival_vinf_kms=p['arrival_vinf_kms'],
                arrival_vinf_reduction_kms=p['arrival_vinf_kms']-vinf,
                prefix_dates_unchanged=dates[:self.prefix_count]==p['dates_jd_tdb'],
                prefix_segments_unchanged=segments[:len(p['segments'])]==p['segments'],
                launch_c3_change_km2_s2=c3-p['launch_c3_km2_s2'])
        return dict(sequence=self.route['id'], bodies=self.bodies, x=np.asarray(x).tolist(), branches=branches,
                    extension_source=extension_source,
                    dates_jd_tdb=dates, launch_date=calendar(dates[0]), arrival_date=calendar(dates[-1]),
                    duration_years=(dates[-1]-dates[0])/365.25, launch_c3_km2_s2=c3,
                    launch_vinf_kms=float(np.sqrt(c3)),requested_min_c3=self.config.get('min_c3',DEFAULT_MIN_C3),effective_min_c3=self.c3_minimum,effective_max_c3=self.c3_maximum,
                    launch_c3_definition='Squared Sun-centered departure velocity relative to launch body; km^2/s^2',
                    requested_arrival_window_jd=self.config.get('arrival_window_jd'),
                    arrival_vinf_kms=vinf, total_dsm_kms=total_dsm, cruise_dsm_kms=cruise_dsm,powered_flyby_delta_v_kms=powered_dv,
                    modeled_maneuver_total_kms=total_dsm,maneuver_budget_complete=not unresolved,budget_complete=not unresolved,
                    unresolved_flyby_count=len(unresolved),
                    unresolved_speed_mismatch_total_mps=sum(f['speed_mismatch_mps'] for f in unresolved),
                    total_unresolved_vinf_mismatch_mps=mismatch_sum,modeled_plus_unresolved_mismatch_kms=screening_total,
                    mismatch_screening_budget_exceeded=(mismatch_sum>1e-6 and screening_total>self.config['max_dsm_kms']+1e-9),
                    mismatch_screening_note='Modeled burns plus unresolved excess-speed mismatch sum is a screening criterion, not an actual periapsis burn estimate. Construct powered flybys for physical burn vectors and costs.',
                    maneuver_budget_note=('Explicit designed DSM, target-turnaround impulses and full powered-periapsis vector burns only; unresolved flybys require physical retargeting or a powered-flyby construction, not a scalar mismatch sum.'),
                    max_single_dsm_kms=max((burn['magnitude_kms'] for burn in burns+event_burns),default=0.),
                    max_powered_flyby_kms=max((f.get('powered_flyby',{}).get('magnitude_kms',0.) for f in flybys),default=0.),
                    periapsis_violation=any(not f['passes_turn_screen'] and not f.get('passes_powered_geometry',False) for f in flybys),
                    powered_geometry_valid=all(f.get('passes_powered_geometry',False) for f in flybys) if self.config.get('powered_flybys') else None,
                    flybys=flybys, dsms=burns,event_burns=event_burns,turnaround_delta_v_kms=turnaround_dv,
                    mercury_returns=__import__('mercury_returns').return_diagnostics(self.bodies,dates,branches),
                    max_vinf_mismatch_mps=max([f['speed_mismatch_mps'] for f in flybys], default=0.),
                    min_turn_margin_deg=min([f['turn_margin_deg'] for f in flybys], default=180.),
                    launch_vinf_vector_kms=launch.tolist(), arrival_vinf_vector_kms=terminal.tolist(),
                    departure_velocities_kms=[v.tolist() for v in dep],
                    arrival_velocities_kms=[v.tolist() for v in arr], segments=segments,
                    events=[dict(body=b, julian_date_tdb=t, date=calendar(t), planet_state_km_kms=s.tolist())
                            for b, t, s in zip(self.bodies, dates, states)])

    def residual(self, x, branches):
        # Fixed dimension, including constraints with zero residual when satisfied.
        count = 2*sum(body in BODIES for body in self.bodies[1:-1])+7
        try:
            q = self.evaluate(x, branches)
            # Balance speed and turn errors during global-to-local discovery.
            # An extremely small user tolerance must not suppress all turn-angle
            # gradients. The acceptance check still uses the exact user limit.
            speed_scale = 0.5
            res = []
            for f in q['flybys']:
                if self.config.get('powered_flybys') and f.get('passes_powered_geometry'):
                    res.extend([0.,0.])
                else:
                    res.extend([(f['vinf_in_kms']-f['vinf_out_kms'])/speed_scale,min(f['turn_margin_deg']-.01, 0.)/5])
            # Tiny interior margins avoid converging infinitesimally outside a
            # hard bound and incorrectly publishing that near miss as accepted.
            min_c3=self.c3_minimum;max_c3=self.c3_maximum
            margin=min(.001*max(max_c3,1.),max(0.,max_c3-min_c3)*.1)
            res.extend([max(min_c3+margin-q['launch_c3_km2_s2'],0.)/10 if min_c3>0 else 0.,
                        max(q['launch_c3_km2_s2']-(max_c3-margin), 0.)/10,
                        0. if self.extension else max(q['arrival_vinf_kms']-.999*self.config['max_arrival_vinf_kms'], 0.),
                        max(q['modeled_plus_unresolved_mismatch_kms']-.999*self.config['max_dsm_kms'], 0.)/0.5,
                        max(q['duration_years']-.999*self.config['max_years'], 0.),
                        max(q['max_single_dsm_kms']-self.config.get('max_single_dsm_kms',float('inf')),0.)/.1,
                        max(q['max_powered_flyby_kms']-self.config.get('max_powered_flyby_kms',float('inf')),0.)/.1])
            return np.asarray(res)
        except C3BoundsError as exc:
            # Preserve an energy gradient without evaluating a forbidden chain.
            res=np.zeros(count)
            res[-7]=max(exc.minimum-exc.c3,0.)/10
            res[-6]=max(exc.c3-exc.maximum,0.)/10
            return res
        except (ValueError, RuntimeError, AssertionError, ZeroDivisionError, OverflowError, FloatingPointError):
            return np.full(count, 1e6)

    def accepted(self, q,allow_arrival_overrun=False):
        return (all(f.get('passes_powered_geometry',False) if self.config.get('powered_flybys') else f['passes_speed_tolerance'] and f['passes_turn_screen'] for f in q['flybys'])
                and self.c3_minimum-1e-8 <= q['launch_c3_km2_s2'] <= self.c3_maximum+1e-8
                and (not self.config.get('arrival_window_jd') or
                     self.config['arrival_window_jd'][0]-1e-8 <= q['dates_jd_tdb'][-1] <= self.config['arrival_window_jd'][1]+1e-8)
                and ((allow_arrival_overrun and self.extension) or q['arrival_vinf_kms'] <= self.config['max_arrival_vinf_kms']+1e-9)
                and q['total_dsm_kms']+sum(f.get('speed_mismatch_mps',0.) for f in q['flybys'] if not f.get('passes_powered_geometry'))/1000. <= self.config['max_dsm_kms']+1e-9
                and max((burn['magnitude_kms'] for burn in q.get('dsms',[])+q.get('event_burns',[])),default=0.)<=self.config.get('max_single_dsm_kms',float('inf'))+1e-9
                and max((f.get('powered_flyby',{}).get('magnitude_kms',0.) for f in q['flybys']),default=0.)<=self.config.get('max_powered_flyby_kms',float('inf'))+1e-9
                and q['duration_years'] <= self.config['max_years']+1e-9)
