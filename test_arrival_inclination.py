"""Terminal inclination geometry and capture estimates independent of heliocentric paths."""
import bootstrap
import json,math,tempfile,unittest
from pathlib import Path
import numpy as np
from arrival_geometry import planet_pole,target_plane_axis,inclination_bounds,validate_inclination
from ephemeris import AU,BODIES,DAY,JD0
from integrate_export import planet_pieces,export

class LinearPlanet:
    def state(self,body,date):return np.array([AU,30*(date-JD0)*DAY,0.,0.,30.,0.])

class ArrivalInclinationTests(unittest.TestCase):
    def test_reference_poles_have_correct_frame_and_epoch(self):
        epsilon=math.radians(84381.448/3600.)
        np.testing.assert_allclose(planet_pole('Earth',2451545.),[0.,math.sin(epsilon),math.cos(epsilon)],atol=1e-14)
        # IAU north, not rotation angular velocity: Uranus north has positive
        # Ecliptic J2000 z despite the planet's retrograde spin.
        self.assertGreater(planet_pole('Uranus',2451545.)[2],0)
        self.assertGreater(np.linalg.norm(planet_pole('Mars',2451545.)-planet_pole('Mars',2488070.)),1e-4)
        for body in BODIES:self.assertAlmostEqual(np.linalg.norm(planet_pole(body,2460000.)),1.)

    def test_fixed_asymptote_bounds_and_inaccessible_target(self):
        incoming=np.array([math.cos(math.pi/6),0.,math.sin(math.pi/6)])
        np.testing.assert_allclose(inclination_bounds(incoming,[0,0,1]),[30.,150.],atol=1e-12)
        with self.assertRaisesRegex(ValueError,'30.000000 to 150.000000'):
            target_plane_axis(incoming,[0,0,1],[0,1,0],20.)
        for i in (30.,90.,150.):
            h=target_plane_axis(incoming,[0,0,1],[0,1,0],i)
            self.assertAlmostEqual(float(h@incoming),0.,places=13)
            self.assertAlmostEqual(math.degrees(math.acos(np.clip(h[2],-1,1))),i,places=11)

    def test_pole_parallel_and_equatorial_asymptote_cases(self):
        h=target_plane_axis([0,0,1],[0,0,1],[0,0,1],90.)
        self.assertAlmostEqual(h[2],0.)
        np.testing.assert_allclose(inclination_bounds([0,0,1],[0,0,1]),[90.,90.])
        for i,expected in [(0,[0,0,1]),(180,[0,0,-1])]:
            np.testing.assert_allclose(target_plane_axis([1,0,0],[0,0,1],[0,1,0],i),expected,atol=1e-14)

    def test_all_planets_polar_hyperbola_preserves_asymptote_periapsis_and_energy(self):
        incoming=np.array([5.,-3.,2.]);ep=LinearPlanet()
        for body in BODIES:
            with self.subTest(body=body):
                node=planet_pieces(body,JD0,ep,uin=incoming,altitude=200.,terminal=True,arrival_inclination_deg=90.)
                r,v=node['peri_position'],node['peri_in_velocity'];mu=BODIES[body][1]
                self.assertAlmostEqual(np.linalg.norm(r),BODIES[body][2]+200.,places=6)
                self.assertAlmostEqual(float(r@v),0.,delta=1e-7)
                self.assertAlmostEqual(float(v@v)-2*mu/np.linalg.norm(r),float(incoming@incoming),places=9)
                e=1+node['rp']*float(incoming@incoming)/mu
                recovered=r/np.linalg.norm(r)/e+v/np.linalg.norm(v)*math.sqrt(e*e-1)/e
                np.testing.assert_allclose(recovered,incoming/np.linalg.norm(incoming),atol=1e-13)
                report=node['capture_assessment']
                self.assertAlmostEqual(report['achieved_inclination_deg'],90.,places=10)
                self.assertFalse(report['capture_applied'])
                self.assertFalse(report['capture_cost_included_in_onboard_budget'])
                circular=np.array(report['hypothetical_circular_state_km_kms'])
                self.assertAlmostEqual(float(circular[3:]@circular[3:]),mu/node['rp'],places=8)
                np.testing.assert_allclose(circular[3:]-v,report['hypothetical_circular_capture_burn_vector_kms'],atol=1e-13)
                b=np.array(report['b_plane_vector_km'])
                self.assertAlmostEqual(float(b@incoming),0.,delta=1e-7)

    def test_no_target_preserves_original_plane(self):
        ep=LinearPlanet();incoming=np.array([5.,2.,0.])
        a=planet_pieces('Earth',JD0,ep,uin=incoming,terminal=True)
        b=planet_pieces('Earth',JD0,ep,uin=incoming,terminal=True,arrival_inclination_deg=None)
        np.testing.assert_array_equal(a['peri_position'],b['peri_position'])
        self.assertIsNone(a['capture_assessment']['requested_inclination_deg'])

    def test_invalid_targets_rejected_without_ephemeris_or_silent_burn(self):
        for value in (-1,181,float('nan'),float('inf')):
            with self.assertRaises(ValueError):validate_inclination(value)
        with self.assertRaisesRegex(ValueError,'terminal'):
            planet_pieces('Earth',JD0,LinearPlanet(),uout=np.array([5.,0.,0.]),departure=True,arrival_inclination_deg=90.)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'candidate.json';p.write_text(json.dumps(dict(status='passes',events=[dict(body='Asteroid')])) )
            with self.assertRaisesRegex(ValueError,'known pole and GM'):
                export(p,{},Path(folder)/'export',arrival_inclination_deg=90.)

if __name__=='__main__':unittest.main()
