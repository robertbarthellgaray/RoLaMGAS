"""Geocentric launch-energy reconstruction and reusable first-EE seeding."""
import bootstrap
import json,math,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from ephemeris import AU,MU_SUN,DAY,JD0,BODIES
from dynamics import Model
from earth_return_seeds import hyperbolic_departure,rtn_basis,target_departure,reference,seed_departures

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
