"""Historical references remain reproducible, bounded, and first-leg-only."""
import bootstrap
import unittest,math
from unittest.mock import patch
import numpy as np
from dynamics import Model
from ephemeris import AU,MU_SUN,DAY,JD0,BODIES
from historical_seeds import references,timing_guess,seed_missions,matching_references
from earth_return_seeds import hyperbolic_departure
class Circles:
    def __init__(self):self.queried=[]
    def state(self,body,date):
        self.queried.append(body)
        if body not in ('Earth','Venus'):raise AssertionError('Later legs must not be evaluated while seeding')
        r=AU*(1 if body=='Earth' else .723);n=math.sqrt(MU_SUN/r**3);t=(date-JD0)*DAY*n
        return np.array([r*math.cos(t),r*math.sin(t),0,-r*n*math.sin(t),r*n*math.cos(t),0])
def model():
    c=dict(launch_jd=[2464000,2464500],min_c3=6.25,max_c3=100,c3_seed_boundary='minimum',dsm_velocity_box_kms=5.)
    r=dict(id='EVEEJ',bodies=['Earth','Venus','Earth','Earth','Jupiter'],dsm_legs=[],leg_days=[[90,140],[200,400],[600,900],[900,1400]])
    return Model(r,c,Circles())
class HistoricalSeedTests(unittest.TestCase):
    def test_all_five_missions_have_sourced_timing_and_four_have_reproducible_vectors(self):
        refs=[r for r in references() if not r.get('reference_kind')];self.assertEqual({r['name'] for r in refs},{'Europa Clipper','Galileo','Mariner 10','Cassini','Juno'})
        for r in refs:
            self.assertEqual(len(r['planet_leg_days']),len(r['bodies'])-1);self.assertTrue(r['sources'])
            if r['name']=='Mariner 10':self.assertNotIn('departure',r);continue
            d=r['departure'];q=d['selected'];fresh=hyperbolic_departure(q['position_km'],q['velocity_kms'],BODIES['Earth'][1]);self.assertAlmostEqual(fresh['c3_km2_s2'],q['c3_km2_s2'],places=11);self.assertAlmostEqual(np.linalg.norm(d['direction_rtn']),1,places=12)
    def test_study_references_are_seeded_but_continuous_thrust_is_excluded(self):
        refs=references();names={r['name'] for r in refs}
        self.assertIn('ADVENTS primary Venus concept',names);self.assertIn('CORAL chemical Centaur concept',names)
        self.assertNotIn('CROCODILE',names)
        for r in refs:self.assertEqual(len(r['planet_leg_days']),len(r['bodies'])-1)
    def test_reference_launch_is_used_only_inside_user_window(self):
        from ephemeris import jd
        m=model();m.config['launch_jd']=[jd('2030-01-01'),jd('2030-12-31')]
        ref=dict(bodies=m.bodies,dates=['2030-04-02'],planet_leg_days=[115,301,731,1094])
        point=timing_guess(m,np.full(m.dimension,.5),ref)
        self.assertAlmostEqual(m.dates(point)[0],jd('2030-04-02'))
        m.config['launch_jd']=[jd('2031-01-01'),jd('2031-12-31')]
        point=timing_guess(m,np.full(m.dimension,.5),ref)
        self.assertGreaterEqual(m.dates(point)[0],jd('2031-01-01'))
    def test_galileo_durations_map_without_modifying_inputs_or_windows(self):
        m=model();x=np.full(m.dimension,.5);original=x.copy();ref=next(r for r in references() if r['name']=='Galileo');point=timing_guess(m,x,ref)
        np.testing.assert_allclose(np.diff(m.dates(point)),[115,301,731,1094]);np.testing.assert_array_equal(x,original)
        dates=m.dates(point);m.config['event_windows_jd']=[[d,d] for d in dates];np.testing.assert_allclose(m.dates(timing_guess(m,x,ref)),dates)
    def test_seed_projection_obeys_energy_bounds_uses_only_first_leg_and_is_deterministic(self):
        m=model();x=np.random.default_rng(14).random((16,m.dimension));original=x.copy();branches=[(0,True)]*4
        points,stats=seed_missions(x,m,branches);self.assertGreater(stats['retained'],0)
        self.assertEqual(stats['attempted'],len(matching_references(m)))
        self.assertEqual(stats['attempted'],stats['retained']+stats['c3_rejected']+stats['duplicates'])
        for p in points:self.assertTrue(m.c3_in_bounds(m.launch_c3(p,branches)));self.assertTrue(np.all((p>=0)&(p<=1)))
        self.assertEqual(set(m.ep.queried),{'Earth','Venus'});np.testing.assert_array_equal(x,original)
        again,_=seed_missions(x,model(),branches);np.testing.assert_allclose(points,again)
    def test_all_references_are_tried_even_with_one_sample_and_valid_timing_is_preserved(self):
        m=model();sample=np.full((1,m.dimension),.5)
        refs=[dict(name=f'reference {i}',bodies=m.bodies,dates=['2030-01-01'],
                   planet_leg_days=[100+i,240+i,700+i,1000+i]) for i in range(8)]
        with patch('historical_seeds.matching_references',return_value=refs),patch.object(m,'launch_c3',return_value=25.),patch('cost_refinement.boundary_seed',side_effect=AssertionError('An in-range reference must keep its dates')):
            points,stats=seed_missions(sample,m,[(0,True)]*4)
        self.assertEqual(stats['eligible'],8);self.assertEqual(stats['attempted'],8)
        self.assertEqual(stats['retained'],8)
        for point,ref in zip(points,refs):np.testing.assert_allclose(np.diff(m.dates(point)),ref['planet_leg_days'])
    def test_worker_refines_every_reference_even_when_normal_refinement_budget_is_one(self):
        from mission_search import normalize,routes_for,planned_jobs,job_search
        from test_hard_c3_generation import CircularStates
        c=normalize(dict(target='Jupiter',sequences=['EJ'],samples_per_sequence=8,
                         refinements_per_sequence=1,max_nfev=8,branch_families=1,max_c3=1e5))
        job=list(planned_jobs(c,routes_for(c)))[0]
        points=[np.array([.1+i*.1,.5]) for i in range(6)]
        names=[f'reference {i}' for i in range(6)]
        stats=dict(missions=names,retained=len(points))
        def refine(model,x,branches,maxiter):return model.evaluate(x,branches)
        with patch('mission_search._WORKER_EP',CircularStates()),patch('mission_search._PROGRESS_QUEUE',None),patch('historical_seeds.seed_missions',return_value=(points,stats)),patch('cost_refinement.feasibility_refine',side_effect=refine) as solver:
            result=job_search(job)
        self.assertEqual(result['historical_mission_seeds']['refinement_attempted'],6)
        self.assertEqual(result['historical_mission_seeds']['refinement_evaluated'],6)
        self.assertEqual({q['initialization_reference'] for q in result['accepted']+result['near_misses'] if 'initialization_reference' in q},set(names))
        for point in points:self.assertTrue(any(np.array_equal(point,call.args[1]) for call in solver.call_args_list))
    def test_opt_out_and_frozen_cruises_skip_historical_guesses(self):
        for option in ['off','local','extension']:
            m=model()
            if option=='off':m.config['historical_mission_seeds']=False
            if option=='local':m.config['local_refinement']={1:1}
            if option=='extension':m.extension={1:1}
            self.assertEqual(matching_references(m),[])
        from mission_search import normalize
        self.assertTrue(normalize({})['historical_mission_seeds'])
        with self.assertRaises(ValueError):normalize(dict(historical_mission_seeds='yes'))
if __name__=='__main__':unittest.main()
