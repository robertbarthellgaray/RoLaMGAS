import bootstrap  # noqa: F401
import unittest
import numpy as np
from moon_screen import rotation,refined_minimum


class ScreenTests(unittest.TestCase):
    def test_clock_rotation_preserves_incoming_asymptote_and_energy(self):
        axis=np.array([3.,-4.,2.]);matrix=rotation(axis,.731)
        np.testing.assert_allclose(matrix@axis,axis,atol=1e-13)
        np.testing.assert_allclose(matrix@matrix.T,np.eye(3),atol=1e-13)
        r=np.array([100.,-30.,60.]);v=np.array([4.,7.,-3.])
        self.assertAlmostEqual(np.linalg.norm(matrix@r),np.linalg.norm(r))
        self.assertAlmostEqual(float((matrix@v)@(matrix@v)),float(v@v))

    def test_off_grid_closest_approach_is_refined(self):
        grid=np.array([-3600.,0.,3600.,7200.])
        fn=lambda t:(t-123.4567)**2+42.
        value,time=refined_minimum(fn,grid,np.array([fn(t) for t in grid]))
        self.assertAlmostEqual(time,123.4567,places=3)
        self.assertAlmostEqual(value,42.,places=5)


if __name__=='__main__':unittest.main()
