"""Local cost minimization with physical flyby and mission constraints intact."""
import bootstrap  # noqa: F401
from functools import lru_cache
import numpy as np
from scipy.optimize import minimize,least_squares
from ephemeris import BODIES


def launch_injection(c3):
    _,mu,radius,_=BODIES['Earth'];r=radius+200.
    return float(np.sqrt(c3+2*mu/r)-np.sqrt(mu/r))


def refine(model,x,branches,objective='balanced',maxiter=160):
    if objective not in ('balanced','c3','dsm','arrival'):
        raise ValueError('Choose balanced, c3, dsm or arrival refinement')
    c=model.config
    @lru_cache(maxsize=256)
    def evaluate(values):
        try:return model.evaluate(np.array(values),branches)
        except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError):return None
    def q_at(values):return evaluate(tuple(float(v) for v in values))
    def cost(values):
        q=q_at(values)
        if q is None:return 1e6
        injection=launch_injection(q['launch_c3_km2_s2'])
        if objective=='c3':return q['launch_c3_km2_s2']/10+1e-5*q['total_dsm_kms']
        if objective=='dsm':return q['total_dsm_kms']+1e-5*injection
        if objective=='arrival':return q['arrival_vinf_kms']+1e-5*injection
        return injection+q['total_dsm_kms']
    def equality(values):
        q=q_at(values)
        count=model.n-2 if not model.extension else model.n-model.prefix_count
        return np.array([f['vinf_in_kms']-f['vinf_out_kms'] for f in q['flybys'] if not model.extension or f['event_index']>=model.prefix_count-1]) if q else np.full(count,1000.)
    def inequality(values):
        q=q_at(values)
        if q is None:return np.full(model.n+4,-1000.)
        return np.array([((1. if f.get('passes_powered_geometry') else -1.) if c.get('powered_flybys') else (f['turn_margin_deg']-.02)/10) for f in q['flybys']]+
                        [(c['max_c3']-q['launch_c3_km2_s2'])/10,
                         c['max_dsm_kms']-q['total_dsm_kms'],
                         (max(c['max_arrival_vinf_kms'],model.extension['reference_arrival_vinf_kms']+.001) if model.extension else c['max_arrival_vinf_kms'])-q['arrival_vinf_kms'],
                         c['max_years']-q['duration_years'],
                         c['max_single_dsm_kms']-q['max_single_dsm_kms'],
                         c['max_powered_flyby_kms']-q['max_powered_flyby_kms']])
    constraints=[dict(type='ineq',fun=inequality)]
    if model.n>2 and not c.get('powered_flybys'):constraints.append(dict(type='eq',fun=equality))
    constraints=[dict(type=constraint['type'],fun=lambda z,f=constraint['fun']:f(model.expand_variables(z))) for constraint in constraints]
    fit=minimize(lambda z:cost(model.expand_variables(z)),model.active_variables(x),method='SLSQP',bounds=[(0.,1.)]*len(model.free_indices),
                 constraints=constraints,options=dict(maxiter=maxiter,ftol=1e-10,eps=1e-6))
    result=q_at(model.expand_variables(fit.x))
    if result is None:return None
    restored=False
    if not model.accepted(result,allow_arrival_overrun=bool(model.extension)):
        recovery=least_squares(lambda z:model.residual(model.expand_variables(z),branches),np.clip(fit.x,1e-10,1-1e-10),
                  bounds=(np.zeros(len(model.free_indices)),np.ones(len(model.free_indices))),max_nfev=80,
                  ftol=1e-10,xtol=1e-10,gtol=1e-10,diff_step=2e-6)
        result=q_at(model.expand_variables(recovery.x))
        if result is None:return None
        restored=True
    result=dict(result)
    result['cost_refinement']=dict(objective=objective,optimizer_success=bool(fit.success),
             optimizer_message=str(fit.message),iterations=int(fit.nit),
             objective_before=float(cost(x)),objective_after=float(cost(result['x'])),feasibility_restored=restored,
             valid_under_requested_limits=bool(model.accepted(result)),
             note='Local optimum search only. Balanced objective is ideal 200 km launch injection delta-v plus designed DSM; no vehicle mass model or global optimum.')
    return result
