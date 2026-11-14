import bootstrap  # noqa: F401
import unittest
import numpy as np
from moon_arrival import (SATURN_GM,relative_acceleration,point_mass_gradient,
                          illustrative_entry_normal,propagate,shoot,MoonSystem)

class MoonArrivalTests(unittest.TestCase):
    def test_stop_interrupts_a_numerical_step(self):
        with self.assertRaises(InterruptedError):
            propagate([1e6,0,0,0,5,0],1000,lambda t:np.array([1e7,0,0]),system=MoonSystem(cancelled=lambda:True))
    def test_differential_acceleration_has_the_indirect_term(self):
        r=np.array([100.,-20.,30.]);m=np.array([1e6,2e5,-3e5]);mu=9000.
        actual=relative_acceleration(r,m,primary_mu=0.,moon_mu=mu)
        linear=point_mass_gradient(-m,mu)@r
        np.testing.assert_allclose(actual,linear,rtol=5e-4,atol=1e-16)
        self.assertLess(np.linalg.norm(actual),mu/np.linalg.norm(m)**2/1000)

    def test_gravity_gradient_matches_numerical_derivative(self):
        r=np.array([700000.,-300000.,50000.]);step=.1;eye=np.eye(3)
        fn=lambda q:-SATURN_GM*q/np.linalg.norm(q)**3
        numerical=np.column_stack([(fn(r+v*step)-fn(r-v*step))/(2*step) for v in eye])
        np.testing.assert_allclose(point_mass_gradient(r,SATURN_GM),numerical,rtol=1e-7,atol=1e-18)

    def test_circular_orbit_and_velocity_sensitivities(self):
        radius=7e5;omega=np.sqrt(SATURN_GM/radius**3);seconds=.2*2*np.pi/omega
        y=np.array([radius,0.,0.,0.,radius*omega,0.]);moon=lambda t:np.array([1e12,0.,0.])
        fit=propagate(y,seconds,moon,variational=True)
        expected=radius*np.array([np.cos(omega*seconds),np.sin(omega*seconds),0.])
        np.testing.assert_allclose(fit.y[:3,-1],expected,atol=.001,rtol=0)
        eps=1e-5;columns=[]
        for i in range(3):
            offset=np.zeros(6);offset[3+i]=eps
            plus=propagate(y+offset,seconds,moon).y[:3,-1]
            minus=propagate(y-offset,seconds,moon).y[:3,-1]
            columns.append((plus-minus)/(2*eps))
        np.testing.assert_allclose(fit.y[6:,-1].reshape(6,3)[:3],np.column_stack(columns),rtol=2e-7,atol=.01)

    def test_shooting_recovers_a_known_endpoint(self):
        radius=7e5;speed=np.sqrt(SATURN_GM/radius);seconds=50000.
        y=np.array([radius,0.,0.,0.,speed,0.]);moon=lambda t:np.array([1e12,0.,0.])
        target=propagate(y,seconds,moon).y[:3,-1]
        velocity,solution,report=shoot(y,seconds,target,moon,y[3:]+[.001,-.002,.001])
        np.testing.assert_allclose(velocity,y[3:],atol=1e-7,rtol=0)
        self.assertLess(report['endpoint_error_km'],.01)

    def test_entry_normal_is_inbound_for_every_clock(self):
        velocity=np.array([2.,3.,4.]);u=velocity/np.linalg.norm(velocity)
        for clock in [0.,90.,180.,270.]:
            normal=illustrative_entry_normal(velocity,[0.,0.,1.],-65.,clock)
            self.assertAlmostEqual(np.linalg.norm(normal),1.,places=13)
            self.assertAlmostEqual(float(np.degrees(np.arcsin(normal@u))),-65.,places=10)
        with self.assertRaises(ValueError):illustrative_entry_normal(velocity,[0,0,1],5.)

if __name__=='__main__':unittest.main()
