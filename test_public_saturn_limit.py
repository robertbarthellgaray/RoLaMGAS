import unittest
from trajectory_policy import public_small_body_reason
class SaturnPublicLimitTests(unittest.TestCase):
    def test_twenty_year_boundary(self):
        def record(years):return dict(body_ids=['399','699'],dates_jd_tdb=[2460000.,2460000.+years*365.25],metrics={'launch_c3_km2_s2':20.})
        self.assertIsNone(public_small_body_reason(record(19.999)))
        self.assertIn('20 years',public_small_body_reason(record(20)))
        self.assertIn('20 years',public_small_body_reason(record(30)))
if __name__=='__main__':unittest.main()
