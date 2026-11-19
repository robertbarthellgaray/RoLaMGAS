"""Geocentric launch-energy reconstruction and reusable first-EE seeding."""
import bootstrap
import json,math,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from ephemeris import AU,MU_SUN,DAY,JD0,BODIES
from dynamics import Model
from earth_return_seeds import hyperbolic_departure,rtn_basis,target_departure,reference,seed_departures,expansive_departure,expansive_point,expansive_energies

class EarthCircle:
    def __init__(self):self.bodies=[]
    def state(self,body,date):
        self.bodies.append(body)
        if body!='Earth':raise AssertionError('Seed projection must not solve downstream legs')
        n=math.sqrt(MU_SUN/AU**3);angle=(date-JD0)*DAY*n
        return np.array([AU*math.cos(angle),AU*math.sin(angle),0.,-AU*n*math.sin(angle),AU*n*math.cos(angle),0.])

def model():
    c=dict(launch_jd=[2464000.,2464500.],min_c3=6.25,max_c3=11.,c3_seed_boundary='maximum',search_objective='c3',dsm_velocity_box_kms=5.)
    route=dict(id='EEJ',bodies=['Earth','Earth','Jupiter'],dsm_legs=[],leg_days=[[300,1200],[300,1800]])
    return Model(route,c,EarthCircle())

class EarthReturnSeedTests(unittest.TestCase):
    def test_bundled_earth_only_uranus_routes_reproduce_under_current_limits(self):
        from app_paths import RESOURCE_ROOT
        from mission_search import normalize,routes_for
        from earth_return_seeds import verified_chain_seeds,preferred_chain_branch
        data=json.loads((RESOURCE_ROOT/'departure_seeds/double_earth_uranus.json').read_text(encoding='utf-8'))
        class StoredStates:
            def state(self,body,date):
                event=next(e for e in data['reference_events'] if e['body']==body and abs(e['julian_date_tdb']-date)<1e-6)
                return np.array(event['planet_state_km_kms'])
        config=normalize(dict(target='Uranus',sequences=['EdvEdvEU'],launch_start='2028-01-01',launch_end='2045-12-31',
            min_c3=25,max_c3=90,max_years=30,dsm_velocity_box_kms=40.,max_arrival_vinf_kms=15,max_dsm_kms=1.5,max_single_dsm_kms=.7,vinf_tolerance_mps=1.,minimum_altitude_km={'Earth':200.}))
        routes=routes_for(config);result=verified_chain_seeds(config,routes,StoredStates())
        self.assertEqual(result['stats']['accepted'],len(data['candidates']))
        self.assertIsNotNone(preferred_chain_branch(config,routes[0]))
        self.assertTrue(all(c['reused_from']['library']=='bundled_double_earth_uranus' for c in result['accepted']))
        config.update(min_c3=90.,effective_min_c3=90.);self.assertEqual(verified_chain_seeds(config,routes,StoredStates())['accepted'],[])
    def test_expansion_energy_grid_preserves_user_bounds_and_boundary_order(self):
        m=model();m.config.update(min_c3=20.,max_c3=100.)
        self.assertEqual(expansive_energies(m),list(map(float,range(90,24,-5))))
        m.config.update(c3_seed_boundary='minimum',min_c3=33.,max_c3=42.)
        self.assertEqual(expansive_energies(m),[33.,35.,40.,42.])
        m.config.update(min_c3=5.,max_c3=20.);self.assertEqual(expansive_energies(m),[])
    def test_high_energy_expansion_seed_preserves_c3_and_avoids_normal_launch_velocity(self):
        earth=np.array([AU,0,0,0,math.sqrt(MU_SUN/AU),0.])
        for angle in (-25.,0.,25.):
            vector=expansive_departure(earth,30.,angle)
            self.assertAlmostEqual(vector@vector,30.,places=12)
            self.assertAlmostEqual((rtn_basis(earth).T@vector)[2],0.,places=12)
            self.assertGreater(vector@earth[3:],0.)
        pro=earth[3:]+expansive_departure(earth,30.)
        normal=earth[3:]+np.array([0,0,math.sqrt(30.)])
        self.assertGreater(pro@pro,normal@normal)

    def test_expansive_dsm_controls_reproduce_requested_launch_vector_and_aphelion(self):
        m=model();m.route['dsm_legs']=[0];m.dsm_legs=[0];m.dimension=m.n+4;m.free_indices=np.arange(m.dimension)
        m.config.update(min_c3=30.,max_c3=31.,c3_seed_boundary='minimum',dsm_velocity_box_kms=100.)
        x=np.full(m.dimension,.5);x[1]=(800.-300)/900
        result=expansive_point(m,x,[(1,True),(0,True)])
        self.assertIsNotNone(result);self.assertAlmostEqual(m.launch_c3(result,[(1,True),(0,True)]),30.,places=8)
        self.assertTrue(.1<.1+.8*result[m.n]<.9)

    def test_asymptote_recovers_analytic_hyperbola_and_not_finite_speed(self):
        mu=BODIES['Earth'][1];rp=7000.;c3=8.;e=1+rp*c3/mu;p=rp*(1+e);nu=math.radians(60.)
        radius=p/(1+e*math.cos(nu));r=radius*np.array([math.cos(nu),math.sin(nu),0.]);v=math.sqrt(mu/p)*np.array([-math.sin(nu),e+math.cos(nu),0.])
        q=hyperbolic_departure(r,v,mu)
        self.assertAlmostEqual(q['c3_km2_s2'],c3,places=12)
        np.testing.assert_allclose(q['vinf_vector_kms'],math.sqrt(c3)*np.array([-1/e,math.sqrt(e*e-1)/e,0.]),atol=1e-13)
        self.assertGreater(q['finite_speed_squared_km2_s2'],c3)
        with self.assertRaises(ValueError):hyperbolic_departure(r,-v,mu)

    def test_reference_matches_preserved_horizons_states(self):
        d=reference();q=d['selected'];computed=hyperbolic_departure(q['position_km'],q['velocity_kms'],BODIES['Earth'][1])
        self.assertAlmostEqual(computed['c3_km2_s2'],6.242944169774687,places=11)
        self.assertAlmostEqual(q['finite_speed_squared_km2_s2'],7.6966964954362185,places=11)
        np.testing.assert_allclose(computed['vinf_vector_kms'],q['vinf_vector_kms'],atol=1e-13)
        self.assertGreater(d['samples'][-1]['c3_km2_s2'],q['c3_km2_s2'])

    def test_rtn_rotation_adapts_direction_and_respects_c3_bounds(self):
        a=np.array([AU,0,0,0,30,0.]);b=np.array([0,AU,0,-30,0,0.]);turn=np.array([[0,-1,0],[1,0,0],[0,0,1.]])
        va=target_departure(a,10.,11.);vb=target_departure(b,10.,11.)
        np.testing.assert_allclose(vb,turn@va,atol=1e-14)
        np.testing.assert_allclose(rtn_basis(a).T@rtn_basis(a),np.eye(3),atol=1e-14)
        self.assertTrue(10<=float(va@va)<=11)
        self.assertAlmostEqual(float(target_departure(a,6.25,6.25)@target_departure(a,6.25,6.25)),6.25)

    def test_projection_is_bounded_deterministic_first_leg_only(self):
        m=model();samples=np.random.default_rng(502).random((32,m.dimension));saved=samples.copy();branches=[(1,False),(0,True)]
        points,stats=seed_departures(samples,m,branches)
        self.assertGreater(stats['retained'],0)
        self.assertLess(stats['minimum_seed_c3_km2_s2'],6.3)
        self.assertEqual(set(m.ep.bodies),{'Earth'})
        np.testing.assert_array_equal(samples,saved)
        for point in points:
            self.assertTrue(np.all((point>=0)&(point<=1)))
            self.assertTrue(m.c3_in_bounds(m.launch_c3(point,branches)))
        again,_=seed_departures(saved,model(),branches)
        np.testing.assert_allclose(points,again,atol=1e-13)
        self.assertLessEqual(m.launch_c3(points[0],branches),m.launch_c3(points[-1],branches))

    def test_skip_non_earth_returns_fixed_windows_extensions_and_opt_out(self):
        samples=np.random.default_rng(1).random((16,3));branches=[(1,False),(0,True)]
        for change in ('different','fixed','extension','off','local'):
            m=model()
            if change=='different':m.bodies=['Earth','Venus','Jupiter']
            if change=='fixed':m.config['event_windows_jd']=[[2464000,2464000],[2464500,2464500],[2465000,2465000]]
            if change=='extension':m.extension={'prefix_count':2}
            if change=='off':m.config['earth_return_seeds']=False
            if change=='local':m.config['local_refinement']={'seed_x':[.5]*3}
            points,stats=seed_departures(samples,m,branches);self.assertEqual(points,[],change)

    def test_normalized_option_is_portable_and_validated(self):
        from mission_search import normalize
        from search_options import export_options,import_options
        self.assertTrue(normalize({})['earth_return_seeds'])
        with self.assertRaisesRegex(ValueError,'earth_return_seeds'):normalize(dict(earth_return_seeds='yes'))
        c=normalize(dict(earth_return_seeds=False));document=export_options(c)['document']
        self.assertFalse(import_options(document)['config']['earth_return_seeds'])

if __name__=='__main__':unittest.main()
