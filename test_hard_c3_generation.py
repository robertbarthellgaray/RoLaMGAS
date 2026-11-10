"""Hard launch-energy preflight, boundary seeding and explicit burn accounting."""
import bootstrap
import copy
import unittest
from unittest.mock import patch
import numpy as np
from dynamics import Model,C3BoundsError,DEFAULT_MIN_C3,HARD_MIN_C3
from ephemeris import AU,DAY,JD0,MU_SUN
from mission_search import normalize,routes_for,job_search
from cost_refinement import boundary_seed,feasibility_refine,refine

class CircularStates:
    def __init__(self):self.calls=[]
    def state(self,body,date):
        self.calls.append(body)
        radius=AU*dict(Earth=1.,Venus=.723,Mars=1.524,Jupiter=5.2,Uranus=19.2)[body]
        omega=np.sqrt(MU_SUN/radius**3);angle=.4+(date-JD0)*DAY*omega
        return np.array([radius*np.cos(angle),radius*np.sin(angle),0.,-radius*omega*np.sin(angle),radius*omega*np.cos(angle),0.])

class HardLaunchC3Tests(unittest.TestCase):
    def model(self,route='EJU',**updates):
        c=normalize(dict(target='Uranus' if route=='EJU' else 'Mars',sequences=[route],launch_start='2030-01-01',launch_end='2031-01-01',max_c3=1e5,**updates))
        return Model(routes_for(c)[0],c,CircularStates())

    def test_out_of_range_is_rejected_before_any_later_ephemeris_or_lambert(self):
        model=self.model();x=[.4,.5,.5];branches=[[0,True],[0,True]]
        energy=model.launch_c3(x,branches);model.config.update(min_c3=energy+10,effective_min_c3=energy+10,max_c3=energy+20)
        model.ep.calls.clear();model._launch_cache.clear()
        with patch('dynamics.lambert',wraps=__import__('dynamics').lambert) as solver:
            with self.assertRaises(C3BoundsError):model.evaluate(x,branches)
            self.assertEqual(solver.call_count,1)
        self.assertEqual(model.ep.calls,['Earth','Jupiter'])
        self.assertNotIn('Uranus',model.ep.calls)

    def test_initial_dsm_offsets_are_included_in_preflight_energy(self):
        model=self.model('EdvM');x=np.array([.4,.5,.6,.57,.44,.53]);branches=[[0,True]]
        launch=model.launch_solution(x,branches);offset=(x[model.n+1:model.n+4]*2-1)*model.config['dsm_velocity_box_kms']
        velocity=launch['va']+offset-launch['states'][0][3:]
        self.assertAlmostEqual(launch['c3'],float(velocity@velocity),places=10)
        model.config.update(min_c3=launch['c3']+5,effective_min_c3=launch['c3']+5,max_c3=launch['c3']+10)
        with patch('dynamics.kepler',side_effect=AssertionError('Forbidden DSM coast was propagated')):
            with self.assertRaises(C3BoundsError):model.evaluate(x,branches)

    def test_absolute_floor_cannot_be_bypassed_by_legacy_import_or_export(self):
        for route in ('EJU','EdvM'):
            model=self.model(route,min_c3=0)
            x=np.full(model.dimension,.5);branches=[[0,True]]*(model.n-1)
            for energy in (0.,4.99,np.nextafter(HARD_MIN_C3,0.),float('nan')):
                for enforce in (True,False):
                    with self.subTest(route=route,energy=energy,enforce=enforce):
                        with patch.object(model,'launch_solution',return_value=dict(c3=energy)),patch.object(model.ep,'state',side_effect=AssertionError('Later planet was evaluated')),patch('dynamics.kepler',side_effect=AssertionError('DSM was propagated')):
                            with self.assertRaises(C3BoundsError):model.evaluate(x,branches,enforce_c3=enforce)

    def test_boundary_seeds_hit_user_minimum_and_maximum(self):
        model=self.model('EM');x=np.array([.4,.5]);branches=[[0,True]]
        energies=[]
        for control in np.linspace(.1,.9,19):
            trial=x.copy();trial[1]=control;energies.append(model.launch_c3(trial,branches))
        low=max(DEFAULT_MIN_C3,float(np.percentile(energies,30)));high=float(np.percentile(energies,70))
        model.config.update(min_c3=low,effective_min_c3=low,max_c3=high)
        for side,target in [('minimum',low),('maximum',high)]:
            model.config['c3_seed_boundary']=side;seed=boundary_seed(model,x,branches)
            self.assertIsNotNone(seed)
            self.assertAlmostEqual(model.launch_c3(seed,branches),target,delta=2e-6)

    def test_constrained_refinement_never_constructs_forbidden_full_chain(self):
        model=self.model('EM');x=np.array([.4,.5]);branches=[[0,True]]
        e=model.launch_c3(x,branches);model.config.update(min_c3=max(DEFAULT_MIN_C3,e*.8),effective_min_c3=max(DEFAULT_MIN_C3,e*.8),max_c3=e*1.1,max_arrival_vinf_kms=200,max_years=50)
        seed=boundary_seed(model,x,branches);energies=[];original=model.evaluate
        def checked(*args,**kwargs):
            q=original(*args,**kwargs);energies.append(q['launch_c3_km2_s2']);return q
        with patch.object(model,'evaluate',side_effect=checked):
            result=feasibility_refine(model,seed,branches,20)
            self.assertIsNotNone(result)
            polished=refine(model,result['x'],branches,'c3',20)
            self.assertIsNotNone(polished)
        self.assertTrue(energies)
        self.assertTrue(all(model.c3_in_bounds(value) for value in energies))

    def test_new_search_diagnostics_are_within_bounds_not_merely_hidden(self):
        c=normalize(dict(target='Mars',sequences=['EM'],launch_start='2030-01-01',launch_end='2031-01-01',min_c3=30,max_c3=60,samples_per_sequence=32,refinements_per_sequence=3,max_nfev=12))
        route=routes_for(c)[0];ep=CircularStates()
        with patch('mission_search._WORKER_EP',ep):
            result=job_search((route,c,[[0,True]],502,32,3,'regression'))
        self.assertGreater(result['c3_pruned_evaluations'],0)
        self.assertGreater(result['c3_boundary_seed_count'],0)
        records=result['accepted']+result['near_misses'];self.assertTrue(records)
        self.assertTrue(all(30-1e-8<=q['launch_c3_km2_s2']<=60+1e-8 for q in records))

    def test_unresolved_zero_dsm_is_incomplete_and_powered_geometry_is_fully_charged(self):
        c=normalize(dict(target='Mars',sequences=['EVM'],max_c3=1e5,max_dsm_kms=100,max_powered_flyby_kms=100))
        route=routes_for(c)[0];x=[.4,.5,.5];branches=[[0,True],[0,True]]
        unpowered=Model(route,c,CircularStates()).evaluate(x,branches)
        self.assertEqual(unpowered['total_dsm_kms'],0.)
        self.assertFalse(unpowered['budget_complete'])
        self.assertEqual(unpowered['unresolved_flyby_count'],1)
        powered=Model(route,dict(c,powered_flybys=True),CircularStates()).evaluate(x,branches)
        burn=powered['flybys'][0]['powered_flyby']
        full_vector=np.linalg.norm(np.asarray(burn['peri_out_velocity_kms'])-np.asarray(burn['peri_in_velocity_kms']))
        self.assertGreater(full_vector,0.)
        self.assertAlmostEqual(powered['total_dsm_kms'],full_vector,places=10)
        self.assertAlmostEqual(powered['modeled_maneuver_total_kms'],full_vector,places=10)
        self.assertTrue(powered['budget_complete'])
        self.assertEqual(powered['unresolved_flyby_count'],0)

    def test_legacy_zero_request_uses_positive_floor_without_mutating_requested_value(self):
        c=normalize(dict(min_c3=0));self.assertEqual(c['min_c3'],0);self.assertEqual(c['effective_min_c3'],HARD_MIN_C3)
        self.assertEqual(normalize(dict(min_c3=0,effective_min_c3=0))['effective_min_c3'],HARD_MIN_C3)
        self.assertEqual(normalize({})['effective_min_c3'],6.25)
        self.assertEqual(normalize(dict(min_c3=5,max_c3=5.5))['effective_min_c3'],5.)

if __name__=='__main__':unittest.main()
