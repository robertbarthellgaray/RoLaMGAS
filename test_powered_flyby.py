import bootstrap  # noqa: F401
import unittest
import numpy as np
from scipy.integrate import solve_ivp
from ephemeris import BODIES
from powered_flyby import geometry
from integrate_export import hyperbolic_state


class PoweredTests(unittest.TestCase):
    def test_excess_turn_is_repaired_above_floor_with_explicit_impulse(self):
        mu=BODIES['Earth'][1];floor=BODIES['Earth'][2]+200
        vin=np.array([10.,0,0]);vout=10*np.array([np.cos(np.radians(50)),np.sin(np.radians(50)),0])
        g=geometry(mu,floor,vin,vout,700000)
        r=np.array(g['peri_position_km']);vi=np.array(g['peri_in_velocity_kms']);vo=np.array(g['peri_out_velocity_kms'])
        self.assertGreaterEqual(np.linalg.norm(r),floor-1e-7)
        self.assertAlmostEqual(float(r@vi),0.,places=6);self.assertAlmostEqual(float(r@vo),0.,places=6)
        np.testing.assert_allclose(vo-vi,g['delta_v_vector_kms'],atol=1e-12)
        for sign,v,expected in [(-1,vi,vin),(1,vo,vout)]:
            far=hyperbolic_state(mu,r,v,sign*1e10)
            np.testing.assert_allclose(far[3:],expected,atol=1e-6)
            def rhs(t,y):return np.r_[y[3:],-mu*y[:3]/np.linalg.norm(y[:3])**3]
            fit=solve_ivp(rhs,(0,sign*100000),np.r_[r,v],method='DOP853',rtol=1e-12,atol=1e-10)
            expected_state=hyperbolic_state(mu,r,v,sign*100000)
            np.testing.assert_allclose(fit.y[:,-1],expected_state,rtol=1e-10,atol=1e-4)

    def test_feasible_equal_speed_flyby_needs_no_material_burn(self):
        angle=np.radians(20);mu=BODIES['Earth'][1];radius=BODIES['Earth'][2]+200
        g=geometry(mu,radius,[10,0,0],10*np.array([np.cos(angle),np.sin(angle),0]),700000)
        self.assertGreater(g['periapsis_radius_km'],radius)
        self.assertLess(g['magnitude_kms'],1e-5)


if __name__=='__main__':unittest.main()
