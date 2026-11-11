"""Local cost minimization with hard launch-energy bounds and physical flyby constraints."""
import bootstrap  # noqa: F401
from functools import lru_cache
import numpy as np
from scipy.optimize import minimize,brentq
from ephemeris import BODIES


def launch_injection(c3):
    _,mu,radius,_=BODIES['Earth'];r=radius+200.
    return float(np.sqrt(c3+2*mu/r)-np.sqrt(mu/r))


def energy_constraints(model,x,branches,interior=False):
    """Cheap preflight only: never construct later legs for an invalid energy."""
    try:
        energy=model.launch_c3(x,branches)
        lo,hi=model.c3_minimum,model.c3_maximum
        margin=min(.001*max(hi,1.),max(0.,hi-lo)*.01) if interior else 0.
        return np.array([(energy-lo-margin)/10,(hi-margin-energy)/10])
    except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):
        return np.array([-1e5,-1e5])


def boundary_seed(model,x,branches):
    """Find a first-leg solution on the user's selected C3 boundary.

    Only a first-leg Lambert solve is used while locating the launch energy.
    Fixed historical epochs remain fixed: if the exact boundary cannot be
    attained, an existing in-range point is used instead of moving its bounds.
    """
    x=np.asarray(x,dtype=float).copy();lo=model.c3_minimum;hi=model.c3_maximum
    if hi<lo:return None
    if model.extension:
        if not model.c3_in_bounds(model.launch_c3(x,branches)):
            raise ValueError('Frozen earlier cruise has launch C3 outside the requested energy range; its launch cannot be changed by adding a flyby')
        return x
    interior=min(1e-6,max(hi-lo,0)*1e-6)
    target=lo+interior if model.config.get('c3_seed_boundary','minimum')=='minimum' else hi-interior
    best=None
    def try_point(point):
        nonlocal best
        try:energy=model.launch_c3(point,branches)
        except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):return None
        if model.c3_in_bounds(energy):
            rank=abs(energy-target)
            if best is None or rank<best[0]:best=(rank,np.array(point,copy=True))
        return energy
    energy=try_point(x)
    if 0 in model.dsm_legs and energy and energy>0:
        initial=model.launch_solution(x,branches);k=model.n+4*model.dsm_legs.index(0)
        offset=(x[k+1:k+4]*2-1)*model.config['dsm_velocity_box_kms']
        vinf=initial['va']+offset-initial['states'][0][3:]
        requested=offset+vinf*(np.sqrt(target/energy)-1)
        trial=x.copy();trial[k+1:k+4]=.5+requested/(2*model.config['dsm_velocity_box_kms'])
        if np.all((trial>=0)&(trial<=1)):
            e=try_point(trial)
            if e is not None and abs(e-target)<1e-6:return trial
    # Vary encounter epoch first, then launch epoch; other dates/burn controls
    # stay at the sampled values, and their configured windows never move.
    for index in (1,0):
        if index not in model.free_indices:continue
        previous=None
        grid=np.unique(np.r_[0.,x[index],np.linspace(0.,1.,33),1.])
        for value in grid:
            trial=x.copy();trial[index]=value;e=try_point(trial)
            if e is None:previous=None;continue
            error=e-target
            if abs(error)<1e-8 and model.c3_in_bounds(e):return trial
            if previous is not None and error*previous[1]<0:
                def scalar(z):
                    point=x.copy();point[index]=z
                    return model.launch_c3(point,branches)-target
                try:
                    z=brentq(scalar,previous[0],float(value),xtol=2e-14,rtol=1e-14,maxiter=70)
                    point=x.copy();point[index]=z;e=try_point(point)
                    if e is not None and model.c3_in_bounds(e):return point
                except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):pass
            previous=(float(value),error)
    return None if best is None else best[1]


def feasible_gradient(model,z,branches,objective,step=2e-6):
    """One-sided derivatives stay inside the physical C3 range at a boundary."""
    z=np.asarray(z,dtype=float);base=objective(z);gradient=np.zeros(len(z))
    for i in range(len(z)):
        for direction in (1.,-1.):
            trial=z.copy();trial[i]+=direction*step
            if not 0<=trial[i]<=1:continue
            if np.min(energy_constraints(model,model.expand_variables(trial),branches)) < -1e-9:continue
            gradient[i]=(objective(trial)-base)/(direction*step)
            break
    return gradient


def feasibility_refine(model,x,branches,maxiter=160):
    """Optimize flyby feasibility while the launch C3 remains a hard constraint."""
    best=None
    def objective(z):
        nonlocal best
        values=model.expand_variables(z);energy=energy_constraints(model,values,branches)
        if np.min(energy)<-1e-9:
            # Gradient points back to the permitted energy interval; later legs
            # are not computed for these optimizer preflight probes.
            return float(1e6+1e4*np.minimum(energy,0.)@np.minimum(energy,0.))
        try:
            q=model.evaluate(values,branches)
            residual=model.residual(values,branches);score=float(residual@residual)
            if best is None or score<best[0]:best=(score,values.copy())
            return score
        except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):return 1e12
    start=model.active_variables(x)
    objective(start)
    fit=minimize(objective,start,jac=lambda z:feasible_gradient(model,z,branches,objective),method='SLSQP',bounds=[(0.,1.)]*len(model.free_indices),
        constraints=[dict(type='ineq',fun=lambda z:energy_constraints(model,model.expand_variables(z),branches,interior=True))],
        options=dict(maxiter=maxiter,ftol=1e-10,eps=2e-6))
    objective(fit.x)
    return None if best is None else model.evaluate(best[1],branches)


def refine(model,x,branches,objective='balanced',maxiter=160):
    if objective not in ('balanced','c3','dsm','arrival','time'):
        raise ValueError('Choose balanced, c3, dsm, arrival or time refinement')
    c=model.config
    @lru_cache(maxsize=256)
    def evaluate(values):
        try:return model.evaluate(np.array(values),branches)
        except (ValueError,RuntimeError,AssertionError,OverflowError,ZeroDivisionError,FloatingPointError):return None
    def q_at(values):return evaluate(tuple(float(v) for v in values))
    def cost(values):
        q=q_at(values)
        if q is None:
            error=np.minimum(energy_constraints(model,values,branches),0.)
            return float(1e6+1e4*(error@error))
        injection=launch_injection(q['launch_c3_km2_s2'])
        if objective=='c3':return q['launch_c3_km2_s2']/10+1e-5*q['total_dsm_kms']
        if objective=='dsm':return q['total_dsm_kms']+1e-5*injection
        if objective=='arrival':return q['arrival_vinf_kms']+1e-5*injection
        if objective=='time':return q['duration_years']+1e-7*injection
        return injection+q['total_dsm_kms']
    def equality(values):
        q=q_at(values)
        count=sum(body in BODIES for body in model.bodies[1:-1]) if not model.extension else sum(body in BODIES for body in model.bodies[model.prefix_count-1:-1])
        return np.array([f['vinf_in_kms']-f['vinf_out_kms'] for f in q['flybys'] if not model.extension or f['event_index']>=model.prefix_count-1]) if q else np.full(count,1000.)
    def inequality(values):
        q=q_at(values)
        if q is None:return np.full(sum(body in BODIES for body in model.bodies[1:-1])+5,-1000.)
        return np.array([((1. if f.get('passes_powered_geometry') else -1.) if c.get('powered_flybys') else (f['turn_margin_deg']-.02)/10) for f in q['flybys']]+
                        [c['max_dsm_kms']-q['total_dsm_kms'],
                         (max(c['max_arrival_vinf_kms'],model.extension['reference_arrival_vinf_kms']+.001) if model.extension else c['max_arrival_vinf_kms'])-q['arrival_vinf_kms'],
                         c['max_years']-q['duration_years'],
                         c['max_single_dsm_kms']-q['max_single_dsm_kms'],
                         c['max_powered_flyby_kms']-q['max_powered_flyby_kms']])
    constraints=[dict(type='ineq',fun=inequality),dict(type='ineq',fun=lambda values:energy_constraints(model,values,branches))]
    if any(body in BODIES for body in model.bodies[(model.prefix_count-1 if model.extension else 1):-1]) and not c.get('powered_flybys'):constraints.append(dict(type='eq',fun=equality))
    constraints=[dict(type=constraint['type'],fun=lambda z,f=constraint['fun']:f(model.expand_variables(z))) for constraint in constraints]
    fit=minimize(lambda z:cost(model.expand_variables(z)),model.active_variables(x),method='SLSQP',bounds=[(0.,1.)]*len(model.free_indices),
                 constraints=constraints,options=dict(maxiter=maxiter,ftol=1e-10,eps=1e-6))
    result=q_at(model.expand_variables(fit.x));restored=False
    if result is None or not model.accepted(result,allow_arrival_overrun=bool(model.extension)):
        recovery=feasibility_refine(model,x if result is None else result['x'],branches,maxiter=min(maxiter,80))
        if recovery is None:return None
        result=recovery;restored=True
    result=dict(result)
    result['cost_refinement']=dict(objective=objective,optimizer_success=bool(fit.success),
             optimizer_message=str(fit.message),iterations=int(fit.nit),
             objective_before=float(cost(x)),objective_after=float(cost(result['x'])),feasibility_restored=restored,
             valid_under_requested_limits=bool(model.accepted(result)),
             note='Local optimum search with hard launch-energy constraints. Balanced cost is ideal 200 km launch injection plus explicit modeled DSM/target-turnaround/powered-flyby delta-v. Unresolved speed mismatches are not fabricated burns.')
    return result
