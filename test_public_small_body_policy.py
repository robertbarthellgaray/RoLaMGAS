import unittest
from trajectory_policy import public_small_body_reason

class PublicSmallBodyPolicyTests(unittest.TestCase):
    def record(self,target='999',years=30,c3=100):
        return dict(body_ids=['399',target],dates_jd_tdb=[2460000,2460000+years*365.25],metrics=dict(duration_years=1,launch_c3_km2_s2=c3))
    def test_epoch_duration_and_exact_boundaries_for_all_minor_body_id_types(self):
        for target in ('9','999','20090377','54667839','1000036'):
            self.assertIsNotNone(public_small_body_reason(self.record(target,40)))
            self.assertIsNone(public_small_body_reason(self.record(target,39.999)))
            self.assertIsNotNone(public_small_body_reason(self.record(target,25,170.001)))
            self.assertIsNone(public_small_body_reason(self.record(target,25,170)))
            self.assertIsNone(public_small_body_reason(self.record(target,24.999,200)))
    def test_major_planet_tours_remain_available(self):
        self.assertIsNone(public_small_body_reason(self.record('899',50,200)))

if __name__=='__main__':unittest.main()
