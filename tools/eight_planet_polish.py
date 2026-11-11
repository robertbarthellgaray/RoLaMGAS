"""Constrained polish for the supplied eight-planet solar patched-conic tour.

This preserves the reconstruction's event-specific altitude floors. It optimizes
its two explicitly charged resonance corrections; it does not validate n-body
navigation, finite-radius flybys, or atmospheric survival.
"""
from functools import lru_cache
import math
from pathlib import Path
import time

import numpy as np
from scipy.optimize import minimize


def _tour_module():
    # Support both `python tools/recreate_eight_planet_tour.py` and package imports.
    try:
        from . import recreate_eight_planet_tour
    except ImportError:
        import recreate_eight_planet_tour
    return recreate_eight_planet_tour


def polish(ep, seed_report, window=35., maxiter=600, checkpoint=None):
    """Return the best feasible source-date/TCM polish, retaining a valid seed.

    `window` bounds every date's deviation from the source table, in days.
    `checkpoint` can be a JSON path or a callable accepting a report; it receives
    each improved feasible result. No files are written when it is omitted.
    Optimizer termination and physical constraint acceptance are reported
    separately: reaching an iteration limit does not invalidate a saved feasible
    input, and a feasible result is not a claim of global optimality.
    """
    tour = _tour_module()
    if not math.isfinite(window) or window <= 0:
        raise ValueError('Polish date window must be finite and positive')
    if isinstance(maxiter, bool) or not isinstance(maxiter, int) or maxiter < 1:
        raise ValueError('Polish maxiter must be a positive integer')
    if checkpoint is not None and not callable(checkpoint):
        checkpoint = Path(checkpoint)
    try:
        dates = np.asarray(seed_report['dates_jd_tdb'], dtype=float)
        velocities = np.asarray(seed_report['resonant_departure_velocities_kms'], dtype=float)
        branches = [list(b) for b in seed_report['branches']]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Polish requires dates, Lambert branches, and resonant departure velocities') from exc
    n = len(tour.BASE)
    if (dates.shape != (n,) or velocities.shape != (len(tour.RESONANT_LEGS), 3)
            or len(branches) != n-1 or not np.all(np.isfinite(dates))
            or not np.all(np.isfinite(velocities)) or np.min(np.diff(dates)) <= 0):
        raise ValueError('Polish seed has invalid dimensions, dates, or velocities')
    shifts = dates-tour.BASE
    if np.max(np.abs(shifts)) > window+1e-8:
        raise ValueError('The seed lies outside the requested source-date window; increase window')
    if np.max(np.abs(velocities)) > 65.:
        raise ValueError('Resonant velocity components must lie within the polish bounds of ±65 km/s')

    seed = np.r_[shifts, velocities.ravel()]
    scale = np.r_[np.full(n, 5.), np.ones(velocities.size)]
    neq = n-2
    started = time.monotonic()
    calls = 0
    iteration = 0
    best = None
    numerical_errors = (ValueError, RuntimeError, AssertionError, ZeroDivisionError,
                        OverflowError, FloatingPointError)

    def unpack(x):
        z = seed+np.asarray(x)*scale
        return z, tour.BASE+z[:n], z[n:].reshape(velocities.shape)

    @lru_cache(maxsize=800)
    def evaluate(key):
        nonlocal calls
        calls += 1
        z, trial_dates, trial_velocities = unpack(key)
        _, _, checks, burns, _ = tour.shooting_chain(ep, trial_dates, branches, trial_velocities)
        dv = np.asarray([b['delta_v_ecliptic_j2000_kms'] for b in burns]).ravel()
        speed = np.asarray([f['vinf_in_kms']-f['vinf_out_kms'] for f in checks])
        margin = np.asarray([f['turn_margin_deg'] for f in checks])
        objective = float(dv@dv*1e6 + .001*(z[:n]@z[:n]))
        if (speed.shape != (neq,) or margin.shape != (neq,)
                or not np.all(np.isfinite(np.r_[objective, speed, margin, dv]))):
            raise ValueError('Polish encountered non-finite dynamics or unexpected flyby counts')
        return objective, speed*10., (margin-.005)/5.

    def values(x):
        return evaluate(tuple(float(v) for v in x))

    def safe_values(x):
        try:
            return values(x)
        except numerical_errors:
            return 1e20, np.full(neq, 1e6), np.full(neq, -1e6)

    @lru_cache(maxsize=4)
    def jacobian(key):
        x = np.asarray(key)
        columns = []
        for i in range(len(x)):
            # Absolute physical steps avoid JD-rounding noise at zero offsets.
            h = (1e-4 if i < n else 2e-6)/scale[i]
            plus = x.copy(); minus = x.copy()
            plus[i] += h; minus[i] -= h
            a, b = safe_values(plus), safe_values(minus)
            columns.append(np.r_[a[0]-b[0], a[1]-b[1], a[2]-b[2]]/(2*h))
        return np.asarray(columns).T

    def make_report(x, fit_status):
        _, trial_dates, trial_velocities = unpack(x)
        states, legs, checks, burns, segments = tour.shooting_chain(ep, trial_dates, branches, trial_velocities)
        q = tour.report(ep, trial_dates, branches, 'Constrained source-date/TCM polish', (states, legs, checks))
        q.update(segments=segments, dsms=burns,
                 modeled_dsm_mps=float(sum(b['magnitude_kms']*1000 for b in burns)),
                 resonant_departure_velocities_kms=trial_velocities.tolist(), fit=fit_status)
        return q

    def consider(x, origin):
        nonlocal best
        try:
            objective, eq, ineq = values(x)
        except numerical_errors:
            return
        # The optimizer asks for an extra .005-degree turn margin. Physical
        # acceptance uses the actual zero-margin floor and 0.1 m/s speed limit.
        mismatch_mps = float(np.max(np.abs(eq))*100.)
        minimum_margin = float(np.min(ineq)*5.+.005)
        within_bounds = bool(np.max(np.abs(unpack(x)[0][:n])) <= window+1e-8)
        feasible = within_bounds and mismatch_mps <= .1 and minimum_margin >= 0.
        violation = mismatch_mps/.1 + max(0., -minimum_margin)*100.
        rank = (0, objective, mismatch_mps) if feasible else (1, violation, objective)
        if best is None or rank < best['rank']:
            best = dict(x=np.asarray(x).copy(), rank=rank, feasible=feasible,
                        origin=origin, iteration=iteration, objective=objective)
            if feasible and checkpoint is not None:
                q = make_report(x, dict(method='SLSQP', success=None, constraints_passed=True,
                    message='Feasible checkpoint; optimization is still running.',
                    selected_from=origin, selected_iteration=iteration, optimality_claimed=False))
                if callable(checkpoint):
                    checkpoint(q)
                else:
                    tour.atomic_json(checkpoint, q)

    initial = np.zeros(len(seed))
    # Validate the seed directly: a numerical error here should not be hidden by
    # the trial-point penalties used during optimization.
    values(initial)
    consider(initial, 'seed')
    lower = (np.r_[np.full(n, -window), np.full(velocities.size, -65.)]-seed)/scale
    upper = (np.r_[np.full(n, window), np.full(velocities.size, 65.)]-seed)/scale

    def callback(x):
        nonlocal iteration
        iteration += 1
        consider(x, 'optimizer iterate')

    try:
        fit = minimize(lambda x: safe_values(x)[0], initial,
            jac=lambda x: jacobian(tuple(x))[0], method='SLSQP',
            bounds=list(zip(lower, upper)), callback=callback,
            constraints=[dict(type='eq', fun=lambda x: safe_values(x)[1],
                              jac=lambda x: jacobian(tuple(x))[1:1+neq]),
                         dict(type='ineq', fun=lambda x: safe_values(x)[2],
                              jac=lambda x: jacobian(tuple(x))[1+neq:])],
            options=dict(maxiter=maxiter, ftol=1e-12, disp=False))
        consider(fit.x, 'optimizer final')
        success, message, nit = bool(fit.success), str(fit.message), int(fit.nit)
    except numerical_errors as exc:
        success, message, nit = False, f'Optimization stopped after numerical error: {exc}', iteration
    status = dict(method='SLSQP', success=success, message=message, iterations=nit,
                  constraints_passed=best['feasible'], selected_from=best['origin'],
                  selected_iteration=best['iteration'], objective_value=best['objective'],
                  objective='sum(correction components in m/s squared) + 0.001*sum(source-date shifts in days squared)',
                  elapsed_seconds=time.monotonic()-started, dynamics_evaluations=calls,
                  source_date_window_days=float(window), optimality_claimed=False)
    result = make_report(best['x'], status)
    if checkpoint is not None and best['feasible']:
        if callable(checkpoint):
            checkpoint(result)
        else:
            tour.atomic_json(checkpoint, result)
    return result
