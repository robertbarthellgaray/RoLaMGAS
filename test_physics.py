"""Physics and input-contract tests; run with python -m unittest -v test_physics."""
import bootstrap  # noqa: F401
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from scipy.integrate import solve_ivp
from dynamics import Model, flyby, kepler, lambert
from ephemeris import AU, DAY, JD0, MU_SUN, Ephemerides, jd, save_table
from mission_search import normalize, resolve_route, routes_for, load_database


class PhysicsTests(unittest.TestCase):
    def test_decades_long_heliocentric_escape(self):
        r=np.array([AU,0.,0.]);v=np.array([0.,55.,1.]);duration=60*365.25*DAY
        rr,vv=kepler(r,v,duration)
        fit=solve_ivp(lambda t,y:np.r_[y[3:],-MU_SUN*y[:3]/np.linalg.norm(y[:3])**3],
                      (0,duration),np.r_[r,v],method='DOP853',rtol=2e-13,atol=1e-9)
        self.assertLess(np.linalg.norm(rr-fit.y[:3,-1]),.1)
        self.assertLess(np.linalg.norm(vv-fit.y[3:,-1]),1e-8)

    def test_julian_epoch(self):
        self.assertEqual(jd('2032-01-01'),2463232.5)

    def test_kepler_against_independent_integrator(self):
        r = np.array([AU,0.,0.])
        for speed_factor in (.7,1.,1.65):
            v = np.array([2.,speed_factor*np.sqrt(MU_SUN/AU),.4])
            duration = 200*DAY
            fit = solve_ivp(lambda t,y:np.r_[y[3:],-MU_SUN*y[:3]/np.linalg.norm(y[:3])**3],
                            (0,duration),np.r_[r,v],method='DOP853',rtol=2.3e-14,atol=1e-10)
            rr,vv = kepler(r,v,duration)
            self.assertLess(np.linalg.norm(rr-fit.y[:3,-1]),.02)
            self.assertLess(np.linalg.norm(vv-fit.y[3:,-1]),1e-8)
            back,backv = kepler(rr,vv,-duration)
            self.assertLess(np.linalg.norm(back-r),.001)

    def test_multi_revolution_lambert(self):
        r = np.array([AU,0.,0.])
        endpoint = np.array([0.,AU,0.])
        period = 2*np.pi*np.sqrt(AU**3/MU_SUN)
        for m in (0,1,2):
            duration = (.25+m)*period
            va,vb = lambert(r,endpoint,duration/DAY,(m,True))
            rr,vv = kepler(r,va,duration)
            self.assertLess(np.linalg.norm(rr-endpoint),.01)
            self.assertLess(np.linalg.norm(vv-vb),1e-8)

    def test_speed_match_does_not_allow_planet_impact(self):
        incoming = np.array([10.,0.,0.])
        angle = np.radians(120)
        outgoing = 10*np.array([np.cos(angle),np.sin(angle),0.])
        f = flyby('Earth',incoming,outgoing,200,20)
        self.assertTrue(f['passes_speed_tolerance'])
        self.assertFalse(f['passes_turn_screen'])
        self.assertLess(f['conservative_equal_speed_altitude_km'],0)

    def test_speed_mismatch_fails_even_if_turn_possible(self):
        f = flyby('Jupiter',np.array([5.,0.,0.]),np.array([5.1,1.,0.]),10000,1)
        self.assertTrue(f['passes_turn_screen'])
        self.assertFalse(f['passes_speed_tolerance'])

    def test_dsm_split_has_no_hidden_velocity_join(self):
        # Circular Earth-like and Mars-like synthetic ephemerides, solely to
        # verify DSM propagation and vector bookkeeping independently of JPL.
        class Synthetic:
            def state(self,body,date):
                radius = AU if body == 'Earth' else 1.524*AU
                t = (date-JD0)*DAY
                omega = np.sqrt(MU_SUN/radius**3)
                a = .5 + omega*t
                return np.array([radius*np.cos(a),radius*np.sin(a),0.,
                                 -radius*omega*np.sin(a),radius*omega*np.cos(a),0.])
        c = normalize(dict(target='Mars',launch_start='2030-01-01',launch_end='2030-02-01',sequences=['EdvM']))
        route = resolve_route('EdvM',load_database())
        model = Model(route,c,Synthetic())
        q = model.evaluate(np.array([.5,.4,.5,.51,.49,.5]),[(0,True)])
        a,b = q['segments']
        rd,before = kepler(np.array(a['r']),np.array(a['v']),(a['end_jd']-a['start_jd'])*DAY)
        self.assertLess(np.linalg.norm(rd-np.array(b['r'])),.01)
        vector = np.array(b['v'])-before
        self.assertLess(np.linalg.norm(vector-q['dsms'][0]['delta_v_ecliptic_j2000_kms']),1e-8)

    def test_bad_configuration_and_ambiguous_mercury_notation(self):
        with self.assertRaises(ValueError):
            normalize(dict(vinf_tolerance_mps=-1))
        with self.assertRaises(ValueError):
            resolve_route('EVbadJ',load_database())
        r = resolve_route('EVdvVEJ',load_database())
        self.assertEqual(r['dsm_legs'],[1])
        self.assertEqual(resolve_route('EMe',load_database())['target'],'Mercury')
        self.assertEqual(resolve_route('EM',load_database())['target'],'Mars')

    def test_chunked_ephemeris_and_no_extrapolation(self):
        from datetime import datetime,timedelta
        def table(first,last):
            header = 'Target body name: Earth (399)\nCenter body name: Sun (10)\nOutput units : KM-S\nGEOMETRIC cartesian states\nEcliptic of J2000.0\nJDTDB,\n$$SOE\n'
            lines = []
            for day in range(first,last+1):
                date = (datetime(2000,1,1)+timedelta(days=day)).strftime('%Y-%b-%d %H:%M:%S.%f')
                lines.append(f'{JD0+day}, A.D. {date}, {AU+day*DAY},0,0,1,0,0,')
            return header+'\n'.join(lines)+'\n$$EOE'
        with tempfile.TemporaryDirectory() as folder:
            save_table(folder,'Earth',table(0,3),'synthetic unit-test fixture')
            save_table(folder,'Earth',table(3,6),'synthetic unit-test fixture')
            ep = Ephemerides(folder,['Earth'],JD0,JD0+6,1)
            self.assertAlmostEqual(ep.state('Earth',JD0+4.5)[0],AU+4.5*DAY)
            with self.assertRaises(ValueError):
                ep.state('Earth',JD0+7)
            with self.assertRaises(ValueError):
                Ephemerides(folder,['Earth'],JD0,JD0+7,1)


if __name__ == '__main__':
    unittest.main()
