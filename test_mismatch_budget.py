import bootstrap
import unittest
from dynamics import Model

class CombinedMismatchTests(unittest.TestCase):
    def model(self,powered=False):
        m=Model.__new__(Model);m.config=dict(min_c3=6.25,max_c3=100,max_arrival_vinf_kms=10,max_dsm_kms=.5,max_years=10,powered_flybys=powered);m.extension=None
        return m

    def candidate(self,powered=False):
        return dict(launch_c3_km2_s2=20,arrival_vinf_kms=6,total_dsm_kms=.2,duration_years=5,dsms=[],
            flybys=[dict(speed_mismatch_mps=200,passes_powered_geometry=powered,passes_speed_tolerance=True,passes_turn_screen=True),dict(speed_mismatch_mps=200,passes_powered_geometry=powered,passes_speed_tolerance=True,passes_turn_screen=True)])

    def test_individually_small_mismatches_add_up_over_remaining_budget(self):
        self.assertFalse(self.model().accepted(self.candidate()))

    def test_sum_within_budget_is_still_accepted(self):
        q=self.candidate();q['total_dsm_kms']=.1
        self.assertTrue(self.model().accepted(q))

    def test_explicit_powered_mismatches_are_not_charged_twice(self):
        self.assertTrue(self.model(True).accepted(self.candidate(True)))

if __name__=='__main__':unittest.main()
